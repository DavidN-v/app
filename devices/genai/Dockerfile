# El modelo lo sirve el contenedor oficial de llama.cpp (servicio genai-llm);
# esta imagen es el asistente que corre en la placa: contexto, chat y métricas.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY edge-agent /tmp/edge-agent
RUN pip install --no-cache-dir /tmp/edge-agent && rm -rf /tmp/edge-agent
COPY devices/genai/assistant.py devices/genai/app.py devices/genai/screen.html ./
RUN useradd --system --uid 10003 device && mkdir -p /data/models && chown -R device /data
USER device
EXPOSE 8102
HEALTHCHECK --interval=15s --timeout=3s CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8102/healthz')"
CMD ["python", "app.py"]
