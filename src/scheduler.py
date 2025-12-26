# src/scheduler.py
import requests
import schedule
import time
import sys
import os

# Importar scraper directamente para ejecución interna
try:
    import scraper
except ImportError:
    # Ajuste de ruta si se ejecuta como script suelto
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    import scraper

# --- CONFIGURACIÓN INTELIGENTE ---
# Si existe API_URL (Docker), úsala. Si no, usa localhost (Local).
API_URL = os.getenv("API_URL", "http://localhost:8000")

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"

TOKEN = None
SETTINGS = {"scraper_interval": 5, "publish_interval": 45}

def login():
    global TOKEN
    print(f"--- [Scheduler] Conectando a API: {API_URL} ---")
    try:
        resp = requests.post(f"{API_URL}/token", data={'username': ADMIN_USERNAME, 'password': ADMIN_PASSWORD})
        if resp.ok:
            TOKEN = resp.json()['access_token']
            print("✅ Login OK")
            return True
        print(f"❌ Login Falló: {resp.status_code}")
    except Exception as e:
        print(f"❌ Error Conexión: {e}")
    return False

def load_settings():
    if not TOKEN: return
    try:
        resp = requests.get(f"{API_URL}/settings", headers={'Authorization': f'Bearer {TOKEN}'})
        if resp.ok:
            data = resp.json()
            SETTINGS.update(data)
            print(f"✅ Configuración: Scraper {SETTINGS['scraper_interval']}m / Publicador {SETTINGS['publish_interval']}m")
    except: pass

def run_scraper():
    print("\n--- 🕵️  Ejecutando Scraper ---")
    try: scraper.main()
    except Exception as e: print(f"❌ Error en Scraper: {e}")

def run_publisher():
    print("\n--- 📢  Ejecutando Publicador (Cola) ---")
    if not TOKEN: login()
    try:
        resp = requests.post(f"{API_URL}/posts/publish-next", headers={'Authorization': f'Bearer {TOKEN}'})
        print(f"   Resultado: {resp.json()}")
    except Exception as e: print(f"❌ Error Publicando: {e}")

def check_scheduled():
    # Tarea de 1 minuto para posts programados
    if not TOKEN: login()
    try:
        resp = requests.post(f"{API_URL}/posts/publish-scheduled", headers={'Authorization': f'Bearer {TOKEN}'})
        if "Nada" not in resp.text: print(f"⏰ Programado: {resp.json()}")
    except: pass

if __name__ == "__main__":
    print("--- INICIANDO SCHEDULER (NUEVO PROYECTO) ---")
    time.sleep(5) # Espera de cortesía para que arranque la API
    login()
    load_settings()

    schedule.every(SETTINGS['scraper_interval']).minutes.do(run_scraper)
    schedule.every(SETTINGS['publish_interval']).minutes.do(run_publisher)
    schedule.every(1).minutes.do(check_scheduled)

    print("-> Tareas programadas y listas.")
    
    # Ejecución inicial del scraper
    run_scraper()

    while True:
        schedule.run_pending()
        time.sleep(1)