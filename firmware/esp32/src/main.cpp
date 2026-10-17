// ESP32: índice de confort ambiental calculado con una red neuronal (TFLite Micro)
// y envío de los resultados a la plataforma por MQTT.
//
// El ESP32 es un microcontrolador: no tiene sistema operativo como una Raspberry Pi, así que
// todo el programa es un bucle que se repite continuamente (función loop).
//
// Temas MQTT:
//   edge/esp32-env/status      online/offline (el broker publica offline si se pierde la conexión)
//   edge/esp32-env/telemetry   {"cpu":..,"ram":..,"temp":..}
//   edge/esp32-env/inference   {"model":..,"version":..,"latency_ms":..}
//   edge/esp32-env/deploy      <- órdenes de despliegue (se responde por deploy/ack)

#include <Arduino.h>
#include <ArduinoJson.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <Wire.h>
#include <Adafruit_SSD1306.h>
#include <esp_heap_caps.h>

#include "model_runner.h"

#ifndef WIFI_CHANNEL
#define WIFI_CHANNEL 0  // 0 = escanear todos los canales
#endif

// Nombre y versión con los que el modelo figura en el registro de la plataforma
static const char *MODEL_NAME = "env-regressor";
static const char *MODEL_VERSION = "1.1";
// Periodos en milisegundos: telemetría cada 5 s e inferencia cada segundo
static const uint32_t TELEMETRY_MS = 5000;
static const uint32_t INFERENCE_MS = 1000;

WiFiClient net;
PubSubClient mqtt(net);
ModelRunner runner;
Adafruit_SSD1306 oled(128, 64, &Wire, -1);  // OLED I2C 0x3C en SDA=21, SCL=22

// Últimos valores mostrados en la pantalla del dispositivo
float lastT = 0, lastH = 0, lastCo2 = 0, lastComfort = 0, lastLatency = 0;
uint32_t inferences = 0;

// Dibuja la pantalla OLED: estado de la conexión, lecturas, índice de confort con una barra
// y latencia de la última inferencia
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

// Construye el tema MQTT propio del dispositivo, por ejemplo edge/esp32-env/telemetry
String topic(const char *suffix) { return String("edge/") + DEVICE_ID + "/" + suffix; }

// Convierte el documento a texto JSON y lo publica
void publishJson(const char *suffix, JsonDocument &doc, bool retain = false) {
  char buf[256];
  size_t n = serializeJson(doc, buf, sizeof(buf));
  mqtt.publish(topic(suffix).c_str(), reinterpret_cast<uint8_t *>(buf), n, retain);
}

void onMessage(char *t, byte *payload, unsigned int len) {
  // El ESP32 no tiene memoria suficiente para descargar e instalar modelos a distancia:
  // se rechaza la orden de forma explícita para que la plataforma registre el fallo.
  JsonDocument cmd;
  if (deserializeJson(cmd, payload, len)) return;
  JsonDocument ack;
  ack["deployment_id"] = cmd["deployment_id"];
  ack["status"] = "failed";
  ack["message"] = "OTA de modelo no soportada; reflashear firmware";
  publishJson("deploy/ack", ack);
}

// Conecta a la red WiFi y espera hasta conseguirlo
void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS, WIFI_CHANNEL);
  Serial.printf("WiFi: conectando a %s", WIFI_SSID);
  drawScreen("WIFI...");
  while (WiFi.status() != WL_CONNECTED) { delay(250); Serial.print("."); }
  Serial.printf(" ok, IP %s\r\n", WiFi.localIP().toString().c_str());
}

// Conecta con el broker. Al conectar deja registrado el mensaje "offline" que el broker
// publicará si la conexión se pierde, anuncia "online" y se suscribe a sus órdenes
void connectMqtt() {
  mqtt.setServer(MQTT_HOST, 1883);
  mqtt.setCallback(onMessage);
  drawScreen("MQTT...");
  while (!mqtt.connected()) {
    Serial.printf("MQTT: conectando a %s:1883\r\n", MQTT_HOST);
    String id = String("fw-") + DEVICE_ID;
    if (mqtt.connect(id.c_str(), nullptr, nullptr, topic("status").c_str(), 1, true, "offline")) {
      mqtt.publish(topic("status").c_str(), "online", true);
      mqtt.subscribe(topic("deploy").c_str(), 1);
      Serial.println("MQTT: conectado, estado online publicado");
    } else {
      Serial.printf("MQTT: fallo (rc=%d), reintento en 2 s\r\n", mqtt.state());
      delay(2000);
    }
  }
}

// Envía el uso de memoria, el porcentaje de tiempo dedicado a inferir y la temperatura del chip
void publishTelemetry() {
  JsonDocument doc;
  size_t total = heap_caps_get_total_size(MALLOC_CAP_DEFAULT);
  size_t free_ = heap_caps_get_free_size(MALLOC_CAP_DEFAULT);
  doc["ram"] = 100.0 * (total - free_) / total;
  doc["cpu"] = runner.lastDutyCyclePct();
  // Sensor interno del SoC; Wokwi no lo simula y devuelve un valor sin sentido
  float temp = temperatureRead();
  if (temp > -10 && temp < 125) doc["temp"] = temp;
  else doc["temp"] = nullptr;
  publishJson("telemetry", doc);
}

// Lee los sensores, ejecuta el modelo, mide cuánto tarda y publica el resultado
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
  Serial.printf("Inferencia #%lu: %.1f C, %.0f %%, %.0f ppm -> confort %.1f (%.2f ms)\r\n",
                (unsigned long)inferences, lastT, lastH, lastCo2, prediction, latency_ms);
  drawScreen("ONLINE");
}

// Se ejecuta una vez al encender: pantalla, modelo, WiFi y MQTT
void setup() {
  Serial.begin(115200);
  Wire.begin(21, 22);
  if (!oled.begin(SSD1306_SWITCHCAPVCC, 0x3C)) Serial.println("OLED no encontrada");
  runner.begin();
  connectWifi();
  connectMqtt();
}

// Bucle principal: mantiene la conexión y lanza cada tarea cuando le toca según millis()
void loop() {
  static uint32_t lastTelemetry = 0, lastInference = 0;
  if (!mqtt.connected()) connectMqtt();
  mqtt.loop();
  uint32_t now = millis();
  if (now - lastInference >= INFERENCE_MS) { lastInference = now; publishInference(); }
  if (now - lastTelemetry >= TELEMETRY_MS) { lastTelemetry = now; publishTelemetry(); }
}
