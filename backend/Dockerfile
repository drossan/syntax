# ─────────────────────────────────────────────────────────────────────────────
# Dockerfile — imagen del servicio `api`.
#
# GUIÓN: multi-stage. `builder` compila deps en un venv; la imagen final es
# python:3.12-slim con el venv copiado y un usuario NON-ROOT. La entrada
# `app.main:app` la crea la TAREA 07 (app factory FastAPI); aquí solo se cablea
# el arranque. No copiar secretos: la config llega por entorno (.env / compose).
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: builder ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# venv aislado (se copia tal cual a la imagen final)
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Instalar deps primero (capa cacheable). El lockfile real lo genera pip-compile
# (ver requirements.txt): mientras sea placeholder, instalar desde requirements.in.
COPY requirements.in requirements.txt ./
RUN pip install --upgrade pip pip-tools && \
    pip-compile --quiet requirements.in -o requirements.lock && \
    pip install -r requirements.lock

# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    APP_ENV=production

# Usuario non-root
RUN groupadd --system app && useradd --system --gid app --home /app app

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app app ./app

USER app
EXPOSE 8000

# `app.main:app` → app factory de la tarea 07. Healthcheck HTTP contra /health.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import httpx,sys; sys.exit(0 if httpx.get('http://localhost:8000/health').status_code==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
