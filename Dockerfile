FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=7860 \
    HOME=/home/user \
    HF_HOME=/home/user/.cache/huggingface

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
WORKDIR /home/user/app

COPY --chown=user:user requirements-full.txt .
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r requirements-full.txt

COPY --chown=user:user backend ./backend
COPY --chown=user:user frontend ./frontend
COPY --chown=user:user .streamlit ./.streamlit
COPY --chown=user:user pyproject.toml .

RUN mkdir -p /home/user/app/data/chroma /home/user/.cache/huggingface && \
    chown -R user:user /home/user/app /home/user/.cache

USER user
EXPOSE 7860

CMD ["sh", "-c", "streamlit run frontend/app.py --server.port=${PORT:-7860} --server.address=0.0.0.0 --server.headless=true --server.enableCORS=false --server.enableXsrfProtection=false"]
