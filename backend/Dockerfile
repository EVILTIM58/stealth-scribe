FROM python:3.11-slim

WORKDIR /app

# Build tools for any wheels that need compiling
# fonts-dejavu-core  -> Latin, Cyrillic, Greek for the PDF
# fonts-noto-core    -> Arabic, Hebrew and much more, so a translated
#                       transcript's ORIGINAL text renders instead of
#                       coming out as empty boxes
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libffi-dev \
    curl \
    fonts-dejavu-core \
    fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

# Requirements first so Docker can cache the dependency layer
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Audio library and in-flight uploads (bind-mounted on the NAS)
RUN mkdir -p /data/media /data/tmp

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8001/api/health || exit 1

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001", \
     "--timeout-keep-alive", "120", "--proxy-headers", "--forwarded-allow-ips", "*"]
