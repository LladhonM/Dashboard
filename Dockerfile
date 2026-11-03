# Contenedor del tablero para Hugging Face Spaces (sdk: docker, app_port: 8501 en README.md).
FROM python:3.13-slim

# Spaces corre el contenedor con el usuario 1000: la app y sus caches van en su carpeta.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    MPLCONFIGDIR=/home/user/.cache/matplotlib \
    PYTHONUNBUFFERED=1
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

COPY --chown=user . .

EXPOSE 8501
# Se corre desde la carpeta de app.py para que Streamlit lea .streamlit/config.toml (el tema).
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true", "--browser.gatherUsageStats=false"]
