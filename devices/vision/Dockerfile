# --- Etapa 1: exporta YOLOv8n (pesos oficiales de Ultralytics) a ONNX -------
# PyTorch solo se usa aquí; la imagen final lleva únicamente ONNX Runtime,
# igual que una Raspberry Pi en producción.
FROM python:3.12-slim AS export
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu \
      "torch==2.*" "torchvision==0.*" "ultralytics>=8.3,<9" "onnx>=1.16" "onnxslim"
# Ultralytics trae OpenCV con interfaz gráfica (pide libxcb); en un contenedor basta la versión headless
RUN pip uninstall -y opencv-python && pip install --no-cache-dir opencv-python-headless
WORKDIR /export
RUN yolo export model=yolov8n.pt format=onnx imgsz=640 opset=12 simplify=True \
 && test -f yolov8n.onnx

# Escenas reales de COCO val2017 (CC BY 4.0) para la "cámara"
ADD http://images.cocodataset.org/val2017/000000000139.jpg /scenes/01-salon.jpg
ADD http://images.cocodataset.org/val2017/000000000632.jpg /scenes/02-dormitorio.jpg
ADD http://images.cocodataset.org/val2017/000000039769.jpg /scenes/03-gatos.jpg
ADD http://images.cocodataset.org/val2017/000000000785.jpg /scenes/04-esqui.jpg
ADD http://images.cocodataset.org/val2017/000000397133.jpg /scenes/05-cocina.jpg
ADD http://images.cocodataset.org/val2017/000000037777.jpg /scenes/06-cocina-2.jpg
ADD http://images.cocodataset.org/val2017/000000252219.jpg /scenes/07-calle.jpg
ADD http://images.cocodataset.org/val2017/000000087038.jpg /scenes/08-calle-2.jpg

# --- Etapa 2: el dispositivo -------------------------------------------------
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY edge-agent /tmp/edge-agent
RUN pip install --no-cache-dir "onnxruntime>=1.18" "numpy>=1.26" "pillow>=10" /tmp/edge-agent \
 && rm -rf /tmp/edge-agent
COPY --from=export /export/yolov8n.onnx /models/yolov8n.onnx
COPY --from=export /scenes /scenes
COPY devices/vision/detector.py devices/vision/app.py devices/vision/calibrate.py devices/vision/screen.html ./
RUN useradd --system --uid 10002 device && mkdir -p /data/models && chown -R device /data /scenes
USER device
EXPOSE 8101
HEALTHCHECK --interval=15s --timeout=3s CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8101/healthz')"
CMD ["python", "app.py"]
