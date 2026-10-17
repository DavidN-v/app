FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir "paho-mqtt>=2.1"
COPY simulate.py .
USER nobody
ENTRYPOINT ["python", "-u", "simulate.py"]
