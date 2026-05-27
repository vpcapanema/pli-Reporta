FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_HOME=/app

WORKDIR ${APP_HOME}

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Gera ícones na imagem (placeholders).
RUN python scripts/generate_icons.py

EXPOSE 8080

CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080"]
