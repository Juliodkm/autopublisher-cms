# src/api/main.py (Versión FINAL - Rebote Corregido: Link EcoTV)

import os
import requests
import openai
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends, status, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta, timezone
import psycopg2
import psycopg2.extras
from passlib.context import CryptContext
from jose import JWTError, jwt
from bs4 import BeautifulSoup
import math
from urllib.parse import urlparse
import re 
import mimetypes
import io
import shutil
import trafilatura

# --- CONFIGURACIÓN ---
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
load_dotenv(dotenv_path=dotenv_path)

SECRET_KEY = "CLAVE_MAESTRA_DOCKER_12345" 
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 30 

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai_client = openai.OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

FACEBOOK_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID")
FACEBOOK_ACCESS_TOKEN = os.getenv("FACEBOOK_ACCESS_TOKEN")
FACEBOOK_GRAPH_API_URL_BASE = "https://graph.facebook.com/v18.0"
WP_URL = os.getenv("WP_URL")
WP_USER = os.getenv("WP_USER")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD")
PUBLIC_API_URL = os.getenv("PUBLIC_API_URL", "")

# DB CONFIG
DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "DB_Publicaciones"),
    "user": os.getenv("DB_USER", "myuser"),
    "password": os.getenv("DB_PASSWORD", "mypassword"),
    "host": "db", 
    "port": "5432"
}

WP_CATEGORY_MAP = {"General": 1, "Deporte": 45, "Economía": 99, "Educación": 175, "Entretenimiento": 44, "Ica Noticias": 40, "Investigación": 101, "Mundo": 105, "Nacional": 42, "Negocios": 97, "Política": 46, "Salud": 100, "Seguridad Ciudadana": 1804, "Tecnologia": 104, "Turismo": 1823}

# --- MODELOS ---
class Token(BaseModel):
    access_token: str
    token_type: str
class UserBase(BaseModel):
    username: str
    full_name: str | None = None
    role: str | None = None
class Post(BaseModel):
    id: int
    source_url: str | None = None
    source_title: str | None = None
    image_url: str | None = None
    status: str
    category: str | None = "General"
    fb_title: str | None = None
    fb_content: str | None = None
    wp_title: str | None = None
    wp_content: str | None = None
    scheduled_at: datetime | None = None
    publication_mode: str | None = "auto"
class PostUpdate(BaseModel):
    status: str | None = None
    image_url: str | None = None
    fb_title: str | None = None
    fb_content: str | None = None
    wp_title: str | None = None
    wp_content: str | None = None
    scheduled_at: datetime | None = None
    publication_mode: str | None = None
    category: str | None = None
class PaginatedPostsResponse(BaseModel):
    posts: List[Post]
    total_count: int
    page: int
    limit: int
    total_pages: int
class SelectedIds(BaseModel):
    ids: List[int]
class RegenerateRequest(BaseModel):
    field_to_update: str
    custom_prompt: str
    post_id: int
class Settings(BaseModel):
    scraper_interval: int
    publish_interval: int

# --- APP ---
app = FastAPI(title="Automatizador API (Docker)")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

static_dir = "/app/src/static"
if not os.path.exists(static_dir): os.makedirs(static_dir, exist_ok=True)
static_images_dir = os.path.join(static_dir, 'images')
if not os.path.exists(static_images_dir): os.makedirs(static_images_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
async def read_index(): return FileResponse("/app/index.html")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# --- UTILS ---
def get_db_connection():
    try: return psycopg2.connect(**DB_CONFIG)
    except: return None

def verify_password(plain, hashed): return pwd_context.verify(plain, hashed)

def get_user(db, username):
    with db.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        return cur.fetchone()

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None: raise HTTPException(401, "Token inválido")
    except JWTError: raise HTTPException(401, "Token expirado")
    conn = get_db_connection()
    if not conn: raise HTTPException(503, "Error DB")
    user = get_user(conn, username)
    conn.close()
    if user is None: raise HTTPException(401, "Usuario no existe")
    return dict(user)

def extract_article_text(url: str):
    try:
        d = trafilatura.fetch_url(url)
        return trafilatura.extract(d) if d else None
    except: return None

def get_pretty_source_name(source_url: str) -> str:
    try:
        domain = urlparse(source_url).netloc
        if domain.startswith("www."): domain = domain[4:]
        return domain.capitalize()
    except: return "Fuente Externa"

# --- PUBLISHING LOGIC CORREGIDA ---

def publish_to_facebook(post_data: dict, publish_url: Optional[str] = None, force_link_post: bool = False):
    if not FACEBOOK_PAGE_ID: return False, "No creds FB"
    
    title = post_data.get('fb_title', '')
    post_text = post_data.get('fb_content', '')
    
    # [CORRECCIÓN] Si hay un URL de publicación (EcoTV), úsalo. Si no, usa la fuente original.
    target_link = publish_url if publish_url else post_data.get('source_url', '')
    
    # [CORRECCIÓN] El mensaje ahora siempre apunta al link objetivo
    msg = f"{title}\n\n{post_text}\n\n📲 Ver nota: {target_link}"
    
    img = post_data.get('image_url')
    if img and img.startswith('/static') and not img.startswith('http'):
        if PUBLIC_API_URL: img = f"{PUBLIC_API_URL}{img}"
    
    # Modo Link (Rebote Link)
    if force_link_post and publish_url:
        url = f"{FACEBOOK_GRAPH_API_URL_BASE}/{FACEBOOK_PAGE_ID}/feed"
        # En modo link, Facebook genera la vista previa desde 'link'
        payload = {'message': f"{title}\n\n{post_text}", 'link': publish_url, 'access_token': FACEBOOK_ACCESS_TOKEN}
    
    # Modo Foto (Rebote Foto)
    elif img and not img.startswith('/static'):
        url = f"{FACEBOOK_GRAPH_API_URL_BASE}/{FACEBOOK_PAGE_ID}/photos"
        # En modo foto, el link va en el 'caption' (mensaje)
        payload = {'url': img, 'caption': msg, 'access_token': FACEBOOK_ACCESS_TOKEN}
    
    # Fallback (Solo texto)
    else:
        url = f"{FACEBOOK_GRAPH_API_URL_BASE}/{FACEBOOK_PAGE_ID}/feed"
        payload = {'message': msg, 'access_token': FACEBOOK_ACCESS_TOKEN}
    
    try:
        r = requests.post(url, data=payload, timeout=60)
        r.raise_for_status()
        return True, r.json()
    except Exception as e: return False, str(e)

def _upload_image_to_wp(image_url: str, title: str):
    if not image_url or not WP_URL: return None
    full_url = image_url
    if full_url.startswith('/static') and PUBLIC_API_URL: full_url = f"{PUBLIC_API_URL}{full_url}"
    elif full_url.startswith('/static'): return None
    try:
        ir = requests.get(full_url, timeout=20)
        ir.raise_for_status()
        filename = os.path.basename(urlparse(full_url).path) or "image.jpg"
        files = {'file': ('img.jpg', io.BytesIO(ir.content), mimetypes.guess_type(full_url)[0] or 'image/jpeg')}
        r = requests.post(f"{WP_URL.rstrip('/')}/wp-json/wp/v2/media", files=files, auth=(WP_USER, WP_APP_PASSWORD), timeout=45)
        return r.json().get('id') if r.ok else None
    except: return None

def publish_to_wordpress(post_data: dict):
    if not WP_URL: return False, "No creds WP"
    mid = _upload_image_to_wp(post_data.get('image_url'), post_data.get('wp_title'))
    cat = WP_CATEGORY_MAP.get(post_data.get('category'), 1)
    data = {
        'title': post_data.get('wp_title'),
        'content': post_data.get('wp_content') + f"<p>Fuente: {get_pretty_source_name(post_data.get('source_url'))}</p>",
        'status': 'publish', 
        'categories': [cat]
    }
    if mid: data['featured_media'] = mid
    try:
        r = requests.post(f"{WP_URL.rstrip('/')}/wp-json/wp/v2/posts", json=data, auth=(WP_USER, WP_APP_PASSWORD), timeout=45)
        r.raise_for_status()
        # Devolvemos el objeto JSON para obtener el link generado
        return True, r.json()
    except Exception as e: return False, str(e)

# --- ENDPOINTS ---
@app.post("/token", response_model=Token)
async def login_token(form: OAuth2PasswordRequestForm = Depends()):
    conn = get_db_connection()
    user = get_user(conn, form.username)
    conn.close()
    if not user or not verify_password(form.password, user['hashed_password']): raise HTTPException(401, "Credenciales incorrectas")
    return {"access_token": create_access_token({"sub": user['username']}), "token_type": "bearer"}

@app.get("/users/me", response_model=UserBase)
async def read_users_me(current_user: dict = Depends(get_current_user)): return UserBase(**current_user)

@app.get("/settings", response_model=Settings)
def get_settings_ep(user: dict = Depends(get_current_user)):
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT key, value_int FROM settings")
        d = {row[0]: row[1] for row in cur.fetchall()}
    conn.close()
    return {"scraper_interval": d.get('scraper_interval', 5), "publish_interval": d.get('publish_interval', 45)}

@app.post("/settings")
def update_settings(s: Settings, user: dict = Depends(get_current_user)):
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("INSERT INTO settings (key, value_int) VALUES ('scraper_interval', %s), ('publish_interval', %s) ON CONFLICT (key) DO UPDATE SET value_int=EXCLUDED.value_int", (s.scraper_interval, s.publish_interval))
        conn.commit()
    conn.close()
    return s

def _paginated(where, page, limit, order="id DESC"):
    conn = get_db_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(f"SELECT COUNT(*) FROM posts WHERE {where}")
        total = cur.fetchone()[0]
        cur.execute(f"SELECT * FROM posts WHERE {where} ORDER BY {order} LIMIT %s OFFSET %s", (limit, (page-1)*limit))
        items = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"posts": items, "total_count": total, "page": page, "limit": limit, "total_pages": math.ceil(total/limit)}

@app.get("/posts/raw")
def list_raw(page: int=1, limit: int=15, user: dict=Depends(get_current_user)): return _paginated("status='crudo'", page, limit)

@app.get("/posts/pending")
def list_pending(page: int=1, limit: int=15, category: Optional[str] = None, user: dict=Depends(get_current_user)):
    where = "status='pendiente' OR status='programado'"
    if category and category!='Todas': where += f" AND category='{category}'"
    return _paginated(where, page, limit, "scheduled_at ASC NULLS LAST, id DESC")

@app.get("/posts/published")
def list_published(page: int=1, limit: int=15, user: dict=Depends(get_current_user)): return _paginated("status IN ('publicado','publicar','publicando')", page, limit, "updated_at DESC")

@app.get("/posts/errors")
def list_errors(page: int=1, limit: int=15, user: dict=Depends(get_current_user)): return _paginated("status IN ('error','error_publishing')", page, limit)

@app.get("/posts/categories", response_model=List[str])
def list_cats(user: dict=Depends(get_current_user)): return list(WP_CATEGORY_MAP.keys())

@app.post("/posts/upload-image/{post_id}")
def upload_img(post_id: int, file: UploadFile = File(...), user: dict=Depends(get_current_user)):
    fname = f"{post_id}-{file.filename}"
    with open(os.path.join(static_images_dir, fname), "wb") as f: shutil.copyfileobj(file.file, f)
    conn = get_db_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("UPDATE posts SET image_url=%s, updated_at=NOW() WHERE id=%s RETURNING *", (f"/static/images/{fname}", post_id))
        post = cur.fetchone()
        conn.commit()
    conn.close()
    return dict(post)

@app.put("/posts/{post_id}")
def update_post(post_id: int, update: PostUpdate, user: dict=Depends(get_current_user)):
    conn = get_db_connection()
    data = update.model_dump(exclude_unset=True)
    fields = [f"{k}=%s" for k in data.keys()] + ["updated_at=NOW()"]
    vals = list(data.values()) + [post_id]
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(f"UPDATE posts SET {', '.join(fields)} WHERE id=%s RETURNING *", tuple(vals))
        res = cur.fetchone()
        conn.commit()
    conn.close()
    return dict(res)

@app.post("/posts/process-selected")
def process_sel(payload: SelectedIds, user: dict=Depends(get_current_user)):
    if not openai_client: raise HTTPException(500, "No OpenAI")
    conn = get_db_connection()
    for pid in payload.ids: _process_single_post_with_chatgpt(pid)
    conn.close()
    return {"message": "OK"}

@app.post("/posts/process-all-raw")
def process_all(user: dict=Depends(get_current_user)):
    if not openai_client: raise HTTPException(500, "No OpenAI")
    conn = get_db_connection()
    with conn.cursor() as cur: cur.execute("SELECT id FROM posts WHERE status='crudo'"); ids = [r[0] for r in cur.fetchall()]
    conn.close()
    for pid in ids: _process_single_post_with_chatgpt(pid)
    return {"message": "OK"}

def _process_single_post_with_chatgpt(post_id):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("SELECT * FROM posts WHERE id=%s FOR UPDATE", (post_id,))
            post = cur.fetchone()
        if not post: return
        txt = extract_article_text(post['source_url'])
        if not txt: 
            with conn.cursor() as cur: cur.execute("UPDATE posts SET status='error', fb_content='No se pudo extraer texto (Trafilatura)' WHERE id=%s", (post_id,)); conn.commit()
            return
        sys_p = f"Eres editor de {post.get('category')}. Genera: <FB-TITLE>..</FB-TITLE> <FB-POST>..hashtags..</FB-POST> <WP-TITLE>..</WP-TITLE> <WP-CONTENT>..</WP-CONTENT>"
        user_p = f"Articulo:\n{txt[:4000]}"
        resp = openai_client.chat.completions.create(model="gpt-4o-mini", messages=[{"role":"system","content":sys_p},{"role":"user","content":user_p}])
        c = resp.choices[0].message.content
        fb_t = re.search(r'<FB-TITLE>(.*?)</FB-TITLE>', c, re.DOTALL).group(1).strip() if '<FB-TITLE>' in c else "Titulo"
        fb_p = re.search(r'<FB-POST>(.*?)</FB-POST>', c, re.DOTALL).group(1).strip() if '<FB-POST>' in c else c
        wp_t = re.search(r'<WP-TITLE>(.*?)</WP-TITLE>', c, re.DOTALL).group(1).strip() if '<WP-TITLE>' in c else fb_t
        wp_c = re.search(r'<WP-CONTENT>(.*?)</WP-CONTENT>', c, re.DOTALL).group(1).strip() if '<WP-CONTENT>' in c else c
        with conn.cursor() as cur:
            cur.execute("UPDATE posts SET fb_title=%s, fb_content=%s, wp_title=%s, wp_content=%s, status='pendiente', updated_at=NOW() WHERE id=%s", (fb_t, fb_p, wp_t, wp_c, post_id))
            conn.commit()
    except Exception as e:
        with conn.cursor() as cur: cur.execute("UPDATE posts SET status='error', fb_content=%s WHERE id=%s", (str(e)[:200], post_id)); conn.commit()
    finally: conn.close()

@app.post("/posts/delete-selected")
def delete_sel(payload: SelectedIds, user: dict=Depends(get_current_user)):
    conn = get_db_connection()
    with conn.cursor() as cur: cur.execute("UPDATE posts SET status='eliminado' WHERE id=ANY(%s)", (payload.ids,)); conn.commit()
    conn.close()
    return {"message": "OK"}

@app.post("/posts/{post_id}/regenerate-quick", response_model=Post)
async def regenerate_quick(post_id: int, platform: str = Query(...), user: dict = Depends(get_current_user)):
    return _process_single_post_with_chatgpt(post_id) or {}

@app.post("/posts/regenerate-custom", response_model=Post)
async def regenerate_custom(req: RegenerateRequest, user: dict = Depends(get_current_user)):
    if not openai_client: raise HTTPException(500)
    conn = get_db_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("SELECT * FROM posts WHERE id=%s", (req.post_id,))
        post = cur.fetchone()
    conn.close()
    txt = extract_article_text(post['source_url'])
    resp = openai_client.chat.completions.create(model="gpt-4o-mini", messages=[{"role":"user","content":f"Ref:{txt[:2000]} Instr:{req.custom_prompt}"}])
    val = resp.choices[0].message.content
    conn = get_db_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(f"UPDATE posts SET {req.field_to_update}=%s WHERE id=%s RETURNING *", (val, req.post_id))
        r = cur.fetchone()
        conn.commit()
    conn.close()
    return dict(r)

# --- LÓGICA CENTRAL DE PUBLICACIÓN Y REBOTE ---
def execute_publish(post_data, mode):
    """Lógica centralizada para publicar según el modo (auto, rebote_foto, rebote_link)"""
    
    fb_success, wp_success = False, False
    final_msg = ""
    
    # 1. Publicar siempre en WordPress primero (es la fuente del rebote)
    wp_success, wp_res = publish_to_wordpress(post_data)
    
    # Obtener el enlace generado por WP
    wp_link = wp_res.get('link') if wp_success else None
    
    # 2. Publicar en Facebook usando el link de WP
    if mode == 'rebote_link':
        # Modo LINK: La tarjeta de FB apunta a la web
        fb_success, fb_res = publish_to_facebook(post_data, publish_url=wp_link, force_link_post=True)
        final_msg = f"Rebote Link. WP:{'OK' if wp_success else 'Fail'} FB:{'OK' if fb_success else 'Fail'}"
        
    elif mode == 'rebote_foto':
        # Modo FOTO: Se sube foto, y el link de WP va en el texto
        fb_success, fb_res = publish_to_facebook(post_data, publish_url=wp_link, force_link_post=False)
        final_msg = f"Rebote Foto. WP:{'OK' if wp_success else 'Fail'} FB:{'OK' if fb_success else 'Fail'}"
        
    else: # 'auto' o default
        # Modo AUTO: El usuario no especificó rebote, pero si ya publicamos en WP, usamos ese link.
        # Si WP falló, usamos el link original.
        fb_success, fb_res = publish_to_facebook(post_data, publish_url=wp_link, force_link_post=False)
        final_msg = f"Auto. WP:{'OK' if wp_success else 'Fail'} FB:{'OK' if fb_success else 'Fail'}"

    # Estado Final (Solo 'publicado' si ambos tienen éxito, o al menos uno si no es estricto)
    # Asumimos que si falló FB pero salió en WP, es un 'error_publishing' para revisar.
    final_status = 'publicado' if (fb_success and wp_success) else 'error_publishing'
    
    return final_status, final_msg

@app.post("/posts/publish-scheduled")
def pub_scheduled(user: dict=Depends(get_current_user)):
    conn = get_db_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("SELECT * FROM posts WHERE status='programado' AND scheduled_at <= LOCALTIMESTAMP LIMIT 1 FOR UPDATE SKIP LOCKED")
        post = cur.fetchone()
        if not post: return {"message": "Nada programado"}
        cur.execute("UPDATE posts SET status='publicando' WHERE id=%s", (post['id'],)); conn.commit()
    
    d = dict(post)
    mode = d.get('publication_mode', 'auto')
    
    # Usar la función centralizada
    final, msg = execute_publish(d, mode)
    
    conn = get_db_connection()
    with conn.cursor() as cur: cur.execute("UPDATE posts SET status=%s, fb_content=%s, updated_at=NOW() WHERE id=%s", (final, msg, d['id'])); conn.commit()
    conn.close()
    return {"message": f"Programado: {final}"}

@app.post("/posts/publish-next")
def pub_next(user: dict=Depends(get_current_user)):
    conn = get_db_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("SELECT * FROM posts WHERE status='publicar' ORDER BY updated_at ASC LIMIT 1 FOR UPDATE SKIP LOCKED")
        post = cur.fetchone()
        if not post: return {"message": "Nada en cola"}
        cur.execute("UPDATE posts SET status='publicando' WHERE id=%s", (post['id'],)); conn.commit()
    
    d = dict(post)
    mode = d.get('publication_mode', 'auto') # La cola también respeta el modo
    
    final, msg = execute_publish(d, mode)
    
    conn = get_db_connection()
    with conn.cursor() as cur: cur.execute("UPDATE posts SET status=%s, fb_content=%s, updated_at=NOW() WHERE id=%s", (final, msg, d['id'])); conn.commit()
    conn.close()
    return {"message": f"Cola: {final}"}

# Endpoints manuales (para pruebas directas desde botón)
@app.post("/posts/{post_id}/publish-rebound")
def publish_rebound(post_id: int, user: dict=Depends(get_current_user)):
    conn = get_db_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("SELECT * FROM posts WHERE id=%s", (post_id,)); post = dict(cur.fetchone())
    conn.close()
    final, msg = execute_publish(post, 'rebote_foto')
    return {"message": f"{final}: {msg}"}

@app.post("/posts/{post_id}/publish-rebound-link")
def publish_rebound_link(post_id: int, user: dict=Depends(get_current_user)):
    conn = get_db_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("SELECT * FROM posts WHERE id=%s", (post_id,)); post = dict(cur.fetchone())
    conn.close()
    final, msg = execute_publish(post, 'rebote_link')
    return {"message": f"{final}: {msg}"}

@app.post("/posts/errors/clear")
def clear_err(user: dict=Depends(get_current_user)):
    conn = get_db_connection()
    with conn.cursor() as cur: cur.execute("DELETE FROM posts WHERE status IN ('error','error_publishing')"); conn.commit()
    conn.close()
    return {"message": "OK"}