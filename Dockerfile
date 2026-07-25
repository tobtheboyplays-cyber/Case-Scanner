# Case-radar – kjørbar server (scanner + KI + godkjenning).
# Bygg:  docker build -t case-radar .
# Kjør:  docker run -p 8000:8000 -e ANTHROPIC_API_KEY=sk-ant-... case-radar
FROM python:3.11-slim

WORKDIR /app

# Systemavhengigheter for enkelte hjul (holdes minimalt)
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY . .

# Installer app + KI-agentene (Claude). pytrends utelates (skjør, valgfri).
RUN pip install --no-cache-dir ".[ai]"

# SQLite-data (godkjente saker). Merk: på gratis-hosting er disken flyktig og
# nullstilles ved ny deploy – helt greit for testing.
ENV CASE_RADAR_DB=/tmp/case_radar.sqlite3

# Hosten (Render/Fly) setter $PORT. Default 8000 lokalt.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
