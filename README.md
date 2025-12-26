# AutoPublisher CMS 🚀

Sistema automatizado para la gestión, reescritura con IA y publicación de noticias en múltiples plataformas (WordPress y Facebook). Diseñado para optimizar el tráfico web mediante estrategias de rebote.

## 📋 Características

* **Scraping Automático:** Monitorea medios de noticias configurados cada X minutos.
* **IA Integrada:** Utiliza GPT-4o-mini para reescribir y resumir noticias.
* **Estrategia de Rebote:** * *Modo Foto:* Sube imagen a FB con enlace en la descripción.
    * *Modo Link:* Genera tarjeta de vista previa apuntando a la web.
* **Programación Inteligente:** Cálculo automático de colas (+45min) y agenda manual.
* **Dockerizado:** Despliegue sencillo y entorno aislado.

## 🛠️ Tecnologías

* **Backend:** Python (FastAPI)
* **Base de Datos:** PostgreSQL
* **Frontend:** HTML5, TailwindCSS, JS Vanilla
* **Infraestructura:** Docker & Docker Compose

## 🚀 Instalación y Uso

### Requisitos
* Docker Desktop instalado.
* Git.

### Pasos para desplegar

1.  **Clonar el repositorio:**
    ```bash
    git clone [https://github.com/TU_USUARIO/autopublisher-cms.git](https://github.com/TU_USUARIO/autopublisher-cms.git)
    cd autopublisher-cms
    ```

2.  **Configurar Variables de Entorno:**
    * Copia el archivo de ejemplo:
        ```bash
        cp .env.example .env
        ```
    * Edita el archivo `.env` y coloca tus claves reales (OpenAI, FB Token, Credenciales WP).

3.  **Iniciar con Docker:**
    ```bash
    docker-compose up -d --build
    ```

4.  **Inicializar Base de Datos (Solo primera vez):**
    ```bash
    docker-compose exec api python src/create_admin.py
    ```

5.  **Acceder al Dashboard:**
    * Abre tu navegador en: `http://localhost:8000`
    * Credenciales por defecto: `admin` / `admin123` (Se recomienda cambiar en producción).

## 📂 Estructura del Proyecto

* `src/api`: Lógica del Backend (FastAPI).
* `src/scraper.py`: Robot de extracción de noticias.
* `src/scheduler.py`: Orquestador de tareas cronometradas.
* `src/static`: Archivos estáticos e imágenes.