FROM python:3.12-slim
WORKDIR /app
ARG INSTALL_EXTRAS=postgres,governance,auth
COPY requirements.txt pyproject.toml ./
COPY app ./app
COPY config ./config
COPY data ./data
COPY deploy ./deploy
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -e ".[${INSTALL_EXTRAS}]" \
    && useradd --system --uid 10001 --create-home appuser \
    && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2)"
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--proxy-headers","--timeout-graceful-shutdown","25"]
