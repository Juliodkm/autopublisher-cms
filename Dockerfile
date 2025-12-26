FROM python:3.11-slim

# Configurar Zona Horaria a Lima (Vital para tus horarios de publicación)
ENV TZ=America/Lima
RUN apt-get update && \
    apt-get install -y tzdata && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && \
    echo $TZ > /etc/timezone && \
    apt-get clean

WORKDIR /app

# Instalar dependencias (usando el requirements.txt corregido)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar todo el código
COPY . .

# Exponer el puerto
EXPOSE 8000

# Comando por defecto
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]