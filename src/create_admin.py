# src/create_admin.py
import psycopg2
import os
from passlib.context import CryptContext

# Configuración Inteligente:
# Si estamos en Docker, usa 'db'. Si ejecutamos manual, intenta 'localhost'.
DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "DB_Publicaciones"),
    "user": os.getenv("DB_USER", "myuser"),
    "password": os.getenv("DB_PASSWORD", "mypassword"),
    "host": os.getenv("DB_HOST", "db"), 
    "port": "5432"
}

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def create_admin_user():
    conn = None
    try:
        print(f"--- 🛠️  INICIALIZANDO BASE DE DATOS ({DB_CONFIG['host']}) ---")
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        # 1. Crear Tablas
        print("1. Creando tablas...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY, 
                username VARCHAR(50) UNIQUE, 
                hashed_password VARCHAR(255), 
                full_name VARCHAR(100), 
                role VARCHAR(20)
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key VARCHAR(50) PRIMARY KEY, 
                value_int INT
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id SERIAL PRIMARY KEY, 
                source_url TEXT UNIQUE, 
                source_title TEXT, 
                image_url TEXT, 
                status VARCHAR(50) DEFAULT 'crudo', 
                category VARCHAR(100) DEFAULT 'General', 
                fb_title TEXT, 
                fb_content TEXT, 
                wp_title TEXT, 
                wp_content TEXT, 
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
                scheduled_at TIMESTAMP WITHOUT TIME ZONE, 
                publication_mode VARCHAR(50) DEFAULT 'auto'
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sources (
                id SERIAL PRIMARY KEY, 
                name VARCHAR(100) UNIQUE, 
                scrape_url TEXT, 
                is_active BOOLEAN DEFAULT TRUE
            );
        """)

        # 2. Datos Iniciales: Fuentes
        print("2. Configurando fuentes...")
        sources = [
            ('RPP Noticias', 'https://rpp.pe/ultimas-noticias', True),
            ('La República', 'https://larepublica.pe/ultimas-noticias', True),
            ('Exitosa Noticias', 'https://www.exitosanoticias.pe/ultimas-noticias/', True)
        ]
        for name, url, active in sources:
            cur.execute("""
                INSERT INTO sources (name, scrape_url, is_active) 
                VALUES (%s, %s, %s) 
                ON CONFLICT (name) DO UPDATE SET scrape_url=EXCLUDED.scrape_url;
            """, (name, url, active))

        # 3. Datos Iniciales: Admin
        print("3. Creando administrador...")
        hashed = pwd_context.hash("admin123")
        cur.execute("""
            INSERT INTO users (username, hashed_password, full_name, role) 
            VALUES ('admin', %s, 'Admin Principal', 'admin') 
            ON CONFLICT (username) DO UPDATE SET hashed_password=EXCLUDED.hashed_password;
        """, (hashed,))
        
        # 4. Datos Iniciales: Tiempos (5 y 45)
        print("4. Configurando tiempos...")
        cur.execute("""
            INSERT INTO settings (key, value_int) 
            VALUES ('scraper_interval', 5), ('publish_interval', 45) 
            ON CONFLICT (key) DO UPDATE SET value_int=EXCLUDED.value_int;
        """)
        
        conn.commit()
        print("✅ INSTALACIÓN COMPLETA EXITOSA.")

    except Exception as e:
        print(f"❌ Error Fatal: {e}")
    finally:
        if conn: conn.close()

if __name__ == "__main__":
    create_admin_user()