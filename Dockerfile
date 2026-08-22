FROM python:3.12-slim
WORKDIR /app
ARG INSTALL_EXTRAS=postgres,governance,auth
COPY requirements.txt pyproject.toml ./
COPY app ./app
COPY config ./config
COPY data ./data
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -e ".[${INSTALL_EXTRAS}]"
EXPOSE 8000
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
