# Usa linux/amd64 per compatibilità
FROM --platform=linux/amd64 python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    OLLAMA_HOST=0.0.0.0

WORKDIR /app

# 1. Dipendenze di sistema (AGGIUNTE: pkg-config e libicu-dev per PyICU)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    dos2unix \
    curl \
    wget \
    bzip2 \
    xz-utils \
    zlib1g \
    libxml2-dev \
    libxslt1-dev \
    libpopt0 \
    libzstd1 \
    libgomp1 \
    libarchive-dev \
    pkg-config \
    libicu-dev \
    && rm -rf /var/lib/apt/lists/*

# 2. INSTALLAZIONE SCANCODE (Source Code Method)
WORKDIR /opt

# Scarichiamo il codice sorgente (v32.4.1)
RUN wget -qO scancode-source.tar.gz https://github.com/aboutcode-org/scancode-toolkit/archive/refs/tags/v32.4.1.tar.gz \
    && mkdir scancode-toolkit \
    && tar -xzf scancode-source.tar.gz -C scancode-toolkit --strip-components=1 \
    && rm scancode-source.tar.gz

# Ora 'pip install .' funzionerà perché abbiamo installato 'pkg-config' e 'libicu-dev'
WORKDIR /opt/scancode-toolkit
RUN pip install .

# Verifica immediata
RUN scancode --version

# 3. Setup Ollama
RUN curl -fsSL https://ollama.com/install.sh | sh

# 4. Configurazione App
WORKDIR /app
COPY pyproject.toml requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY start-container.sh /app/start-container.sh
# dos2unix per convertire i file di script da Windows a Unix
RUN dos2unix /app/start-container.sh && chmod +x /app/start-container.sh
RUN mkdir -p /app/data

EXPOSE 8000
CMD ["/app/start-container.sh"]