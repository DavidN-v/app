FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY edge-agent /tmp/edge-agent
RUN pip install --no-cache-dir /tmp/edge-agent && rm -rf /tmp/edge-agent
COPY devices/agent/anomaly.py devices/agent/app.py devices/agent/screen.html ./
RUN useradd --system --uid 10004 device && mkdir -p /data/models && chown -R device /data
USER device
EXPOSE 8103
HEALTHCHECK --interval=15s --timeout=3s CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8103/healthz')"
CMD ["python", "app.py"]
