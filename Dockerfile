# ── TalktoDB — Monolith ───────────────────────────────────────────────────
# Single image: FastAPI backend (port 8000) + Streamlit UI (port $PORT).
# start.sh boots both; Cloud Run routes public traffic to Streamlit.
#
# Build:
#   docker build -t talktodb .
#
# Run locally:
#   docker run --env-file .env -p 8501:8501 talktodb
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    API_URL=http://localhost:8000

WORKDIR /app

# ── Install all dependencies (API + UI) ──────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Copy source ───────────────────────────────────────────────────────────
COPY api/        ./api/
COPY agent/      ./agent/
COPY db/         ./db/
COPY mcp_server/ ./mcp_server/
COPY config/     ./config/
COPY ui/         ./ui/
COPY start.sh    .

# ── Streamlit config + runtime dirs ──────────────────────────────────────
RUN mkdir -p /app/.streamlit /app/data /app/logs \
    && printf '[server]\nheadless = true\nenableCORS = false\nenableXsrfProtection = false\n\n[browser]\ngatherUsageStats = false\n' \
       > /app/.streamlit/config.toml \
    && chmod +x start.sh

# ── Non-root user ─────────────────────────────────────────────────────────
RUN adduser --disabled-password --gecos "" --uid 1001 appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT:-8501}/_stcore/health')" || exit 1

CMD ["./start.sh"]
