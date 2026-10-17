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
#include <Wire.h>
#include <Adafruit_SSD1306.h>
#include <esp_heap_caps.h>

#include "model_runner.h"

static const char *MODEL_NAME = "env-regressor";
static const char *MODEL_VERSION = "1.1";
static const uint32_t TELEMETRY_MS = 5000;
static const uint32_t INFERENCE_MS = 1000;

WiFiClient net;
PubSubClient mqtt(net);
ModelRunner runner;
Adafruit_SSD1306 oled(128, 64, &Wire, -1);  // OLED I2C 0x3C en SDA=21, SCL=22

// Últimos valores mostrados en la pantalla del dispositivo
float lastT = 0, lastH = 0, lastCo2 = 0, lastComfort = 0, lastLatency = 0;
uint32_t inferences = 0;

void drawScreen(const char *status) {
  oled.clearDisplay();
  oled.setTextColor(SSD1306_WHITE);
  oled.setTextSize(1);
  oled.setCursor(0, 0);
  oled.print("ESP32-ENV  ");
  oled.print(status);
  oled.drawFastHLine(0, 10, 128, SSD1306_WHITE);
  oled.setCursor(0, 14);
  oled.printf("%.1fC  %.0f%%  %.0fppm", lastT, lastH, lastCo2);
  oled.setCursor(0, 26);
  oled.print("CONFORT");
  oled.setTextSize(2);
  oled.setCursor(56, 24);
  oled.printf("%.0f", lastComfort);
  oled.drawRect(0, 42, 128, 6, SSD1306_WHITE);
  oled.fillRect(1, 43, (int)(126 * constrain(lastComfort, 0.0f, 100.0f) / 100.0f), 4, SSD1306_WHITE);
  oled.setTextSize(1);
  oled.setCursor(0, 54);
  oled.printf("%.2fms  #%lu", lastLatency, (unsigned long)inferences);
  oled.display();
}

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
  Serial.printf("WiFi: conectando a %s", WIFI_SSID);
  drawScreen("WIFI...");
  while (WiFi.status() != WL_CONNECTED) { delay(250); Serial.print("."); }
  Serial.printf(" ok, IP %s\n", WiFi.localIP().toString().c_str());
}

void connectMqtt() {
  mqtt.setServer(MQTT_HOST, 1883);
  mqtt.setCallback(onMessage);
  drawScreen("MQTT...");
  while (!mqtt.connected()) {
    Serial.printf("MQTT: conectando a %s:1883\n", MQTT_HOST);
    String id = String("fw-") + DEVICE_ID;
    if (mqtt.connect(id.c_str(), nullptr, nullptr, topic("status").c_str(), 1, true, "offline")) {
      mqtt.publish(topic("status").c_str(), "online", true);
      mqtt.subscribe(topic("deploy").c_str(), 1);
      Serial.println("MQTT: conectado, estado online publicado");
    } else {
      Serial.printf("MQTT: fallo (rc=%d), reintento en 2 s\n", mqtt.state());
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

  lastT = features[0]; lastH = features[1]; lastCo2 = features[2];
  lastComfort = prediction; lastLatency = latency_ms; inferences++;
  Serial.printf("Inferencia #%lu: %.1f C, %.0f %%, %.0f ppm -> confort %.1f (%.2f ms)\n",
                (unsigned long)inferences, lastT, lastH, lastCo2, prediction, latency_ms);
  drawScreen("ONLINE");
}

void setup() {
  Serial.begin(115200);
  Wire.begin(21, 22);
  if (!oled.begin(SSD1306_SWITCHCAPVCC, 0x3C)) Serial.println("OLED no encontrada");
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
