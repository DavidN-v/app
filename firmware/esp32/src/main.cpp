// ESP32 - Predicción ambiental (TFLite Micro) con telemetría hacia la plataforma.
//
// Tópicos:
//   edge/esp32-env/status      online/offline (LWT, retenido)
//   edge/esp32-env/telemetry   {"cpu":..,"ram":..,"temp":..}
//   edge/esp32-env/inference   {"model":..,"version":..,"latency_ms":..}
//   edge/esp32-env/deploy      <- órdenes OTA (se responde por deploy/ack)

#include <Arduino.h>
#include <ArduinoJson.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <esp_heap_caps.h>

#include "model_runner.h"

static const char *MODEL_NAME = "env-regressor";
static const char *MODEL_VERSION = "1.1";
static const uint32_t TELEMETRY_MS = 5000;
static const uint32_t INFERENCE_MS = 1000;

WiFiClient net;
PubSubClient mqtt(net);
ModelRunner runner;

String topic(const char *suffix) { return String("edge/") + DEVICE_ID + "/" + suffix; }

void publishJson(const char *suffix, JsonDocument &doc, bool retain = false) {
  char buf[256];
  size_t n = serializeJson(doc, buf, sizeof(buf));
  mqtt.publish(topic(suffix).c_str(), reinterpret_cast<uint8_t *>(buf), n, retain);
}

void onMessage(char *t, byte *payload, unsigned int len) {
  // El ESP32 no tiene espacio para descargar modelos grandes en caliente:
  // se rechaza la orden explícitamente para que la plataforma registre el fallo.
  JsonDocument cmd;
  if (deserializeJson(cmd, payload, len)) return;
  JsonDocument ack;
  ack["deployment_id"] = cmd["deployment_id"];
  ack["status"] = "failed";
  ack["message"] = "OTA de modelo no soportada; reflashear firmware";
  publishJson("deploy/ack", ack);
}

void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) delay(250);
}

void connectMqtt() {
  mqtt.setServer(MQTT_HOST, 1883);
  mqtt.setCallback(onMessage);
  while (!mqtt.connected()) {
    String id = String("fw-") + DEVICE_ID;
    if (mqtt.connect(id.c_str(), nullptr, nullptr, topic("status").c_str(), 1, true, "offline")) {
      mqtt.publish(topic("status").c_str(), "online", true);
      mqtt.subscribe(topic("deploy").c_str(), 1);
    } else {
      delay(2000);
    }
  }
}

void publishTelemetry() {
  JsonDocument doc;
  size_t total = heap_caps_get_total_size(MALLOC_CAP_DEFAULT);
  size_t free_ = heap_caps_get_free_size(MALLOC_CAP_DEFAULT);
  doc["ram"] = 100.0 * (total - free_) / total;
  doc["cpu"] = runner.lastDutyCyclePct();
  doc["temp"] = temperatureRead();  // sensor interno del SoC
  publishJson("telemetry", doc);
}

void publishInference() {
  float features[3] = {runner.readTemperature(), runner.readHumidity(), runner.readCo2()};
  uint32_t t0 = micros();
  float prediction = runner.predict(features);
  float latency_ms = (micros() - t0) / 1000.0f;

  JsonDocument doc;
  doc["model"] = MODEL_NAME;
  doc["version"] = MODEL_VERSION;
  doc["latency_ms"] = latency_ms;
  doc["prediction"] = prediction;
  publishJson("inference", doc);
}

void setup() {
  Serial.begin(115200);
  runner.begin();
  connectWifi();
  connectMqtt();
}

void loop() {
  static uint32_t lastTelemetry = 0, lastInference = 0;
  if (!mqtt.connected()) connectMqtt();
  mqtt.loop();
  uint32_t now = millis();
  if (now - lastInference >= INFERENCE_MS) { lastInference = now; publishInference(); }
  if (now - lastTelemetry >= TELEMETRY_MS) { lastTelemetry = now; publishTelemetry(); }
}
