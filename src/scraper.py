# src/scraper.py
import psycopg2
import psycopg2.extras
import requests
from bs4 import BeautifulSoup
import os
import trafilatura
from trafilatura.settings import DEFAULT_CONFIG
from configparser import ConfigParser
from urllib.parse import urljoin, urlparse
from dotenv import load_dotenv

# --- Configuración Inteligente (Carga desde .env o Entorno) ---
current_dir = os.path.dirname(os.path.abspath(__file__))
base_dir = os.path.dirname(current_dir)
dotenv_path = os.path.join(base_dir, '.env')
load_dotenv(dotenv_path=dotenv_path)

DB_NAME = os.getenv("DB_NAME", "DB_Publicaciones")
DB_USER = os.getenv("DB_USER", "myuser")
DB_PASS = os.getenv("DB_PASSWORD", "mypassword")
DB_HOST = os.getenv("DB_HOST", "db") # En el nuevo proyecto Docker, el host es 'db'
DB_PORT = os.getenv("DB_PORT", "5432")

# --- Configuración de Trafilatura ---
new_config = ConfigParser()
new_config.read_dict(DEFAULT_CONFIG)
new_config.set("DEFAULT", "EXTRACTION_TIMEOUT", "15")

# --- Mapeo de Categorías (Tu lista original) ---
MAPA_DE_CATEGORIAS = {
    "politica": "Política", "gobierno": "Política", "congreso": "Política", "elecciones": "Política",
    "ejecutivo": "Política", "legislativo": "Política", "presidencia": "Política",
    "actualidad": "Nacional", "nacional": "Nacional", "sociedad": "Nacional", "peru": "Nacional",
    "lima": "Nacional", "regiones": "Nacional", "provincia": "Nacional", "local": "Nacional",
    "policiales": "Seguridad Ciudadana", "policial": "Seguridad Ciudadana", "delincuencia": "Seguridad Ciudadana",
    "crimen": "Seguridad Ciudadana", "judicial": "Seguridad Ciudadana", "judiciales": "Seguridad Ciudadana",
    "inseguridad": "Seguridad Ciudadana", "mundo": "Mundo", "internacional": "Mundo", "america": "Mundo",
    "latinoamerica": "Mundo", "economia": "Economía", "finanzas": "Economía", "bolsa": "Economía",
    "negocios": "Negocios", "empresas": "Negocios", "dinero": "Negocios",
    "deportes": "Deporte", "futbol": "Deporte", "voley": "Deporte", "tenis": "Deporte",
    "polideportivo": "Deporte", "seleccion-peruana": "Deporte", "copa-libertadores": "Deporte", "liga-1": "Deporte",
    "espectaculos": "Entretenimiento", "entretenimiento": "Entretenimiento", "farandula": "Entretenimiento",
    "cultura": "Entretenimiento", "cine": "Entretenimiento", "musica": "Entretenimiento", "tv": "Entretenimiento",
    "famosos": "Entretenimiento", "tecnologia": "Tecnologia", "ciencia": "Tecnologia", "redes-sociales": "Tecnologia",
    "gadgets": "Tecnologia", "videojuegos": "Tecnologia", "celulares": "Tecnologia",
    "estilo-de-vida": "Salud", "bienestar": "Salud", "salud": "Salud",
    "educacion": "Educación", "colegios": "Educación", "ica-noticias": "Ica Noticias", "ica": "Ica Noticias",
    "investigacion": "Investigación", "turismo": "Turismo", "viajes": "Turismo",
    "gastronomia": "General", "opinion": "General", "virales": "General", "loterias": "General",
}

def get_db_connection():
    try:
        return psycopg2.connect(dbname=DB_NAME, user=DB_USER, password=DB_PASS, host=DB_HOST, port=DB_PORT)
    except Exception as e:
        print(f"❌ ERROR [Scraper] DB: {e}")
        return None

def get_active_sources(conn):
    if not conn: return []
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("SELECT id, name, scrape_url FROM sources WHERE is_active = TRUE ORDER BY id")
            return [dict(source) for source in cur.fetchall()]
    except Exception as e:
        print(f"❌ ERROR [Scraper] Sources: {e}")
        return []

def find_best_image_url(element, base_url):
    if not element: return None
    current = element
    for _ in range(3):
        parent = current.find_parent()
        if not parent: break
        img = parent.select_one('figure img') or parent.find('img')
        if img:
            src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
            if src:
                 p = urlparse(src.strip())
                 if p.scheme in ['http', 'https', ''] and (p.netloc or not p.scheme):
                     return urljoin(base_url, src.strip())
        current = parent
    return None

def clean_category(url):
    try:
        parts = urlparse(url).path.split('/')
        for p in parts:
            if p.lower() in MAPA_DE_CATEGORIAS: return MAPA_DE_CATEGORIAS[p.lower()]
        return "General"
    except: return "General"

def scrape_main_story(name, url):
    print(f"  Scanning: {name} ({url})...")
    try:
        html = trafilatura.fetch_url(url, config=new_config)
        if not html: return None
        soup = BeautifulSoup(html, 'html.parser')

        link = None
        selectors = []
        if name == 'RPP Noticias': selectors = ['article.news--summary-standard h2.news__title a', 'article h2 a', '.main-content article h2 a']
        elif name == 'La República': selectors = ['div.ListSection_list__section--item__zeP_z h2 a', 'div[class*="ListSection"] h2 a']
        elif name == 'Exitosa Noticias': selectors = ['section.tres article.noti-box:first-of-type h2.tit a']
        else: selectors = ['article h1 a', 'article h2 a', '.main-story a']
        
        # Añadir genéricos por si acaso
        selectors.extend(['h2 a', 'h1 a'])

        for s in selectors:
            link = soup.select_one(s)
            if link and link.get('href') and link.get_text(strip=True): break

        if not link: 
            print(f"  ⚠️ No se encontró noticia principal en {name}")
            return None

        src_url = urljoin(url, link.get('href'))
        title = link.get('title') or link.get_text(strip=True)
        if name == 'Exitosa Noticias' and link.get('title'): title = link.get('title').strip()
        
        return {
            "source_url": src_url,
            "source_title": ' '.join(title.split()),
            "image_url": find_best_image_url(link, url),
            "category": clean_category(src_url)
        }
    except Exception as e:
        print(f"  ❌ Error scraping {name}: {e}")
        return None

def save_to_db(item):
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO posts (source_url, source_title, image_url, category, status) VALUES (%s, %s, %s, %s, 'crudo') ON CONFLICT (source_url) DO NOTHING",
                (item['source_url'], item['source_title'], item['image_url'], item['category'])
            )
            if cur.rowcount > 0: print(f"  ✅ NUEVA: {item['source_title']}")
            else: print(f"  💤 Repetida: {item['source_title']}")
            conn.commit()
    except Exception as e: print(f"❌ Error guardando: {e}")
    finally: conn.close()

def main():
    print("--- 🕵️  SCRAPER INICIADO ---")
    conn = get_db_connection()
    if not conn: return
    sources = get_active_sources(conn)
    conn.close()
    for s in sources:
        item = scrape_main_story(s['name'], s['scrape_url'])
        if item: save_to_db(item)
    print("--- FIN ---")

if __name__ == "__main__": main()