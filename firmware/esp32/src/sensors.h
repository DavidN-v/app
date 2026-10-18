// Lectura de los sensores ambientales: temperatura (°C), humedad relativa (%) y CO2 (ppm).
// Con SENSOR_SCD4X se lee un SCD40/41 por I2C (SDA 21, SCL 22, 3,3 V).
// Si no responde, se usan valores simulados.
#pragma once

#include <Arduino.h>
#include <Wire.h>

#include "model_runner.h"

#ifdef SENSOR_SCD4X
#include <SensirionI2cScd4x.h>
#endif

class Sensors {
 public:
  explicit Sensors(ModelRunner &fallback) : fallback_(fallback) {}

  void begin() {
#ifdef SENSOR_SCD4X
    scd_.begin(Wire, SCD41_I2C_ADDR_62);
    scd_.stopPeriodicMeasurement();  // por si venía de un arranque anterior
    delay(500);
    real_ = scd_.startPeriodicMeasurement() == 0;
#endif
    Serial.println(real_ ? "Sensor SCD4x detectado: lecturas reales"
                         : "Sin sensor ambiental: se usan valores simulados");
  }

  bool real() const { return real_; }

  // Actualiza la última lectura. El SCD4x da un dato nuevo cada 5 s; entre medias se reutiliza
  void update() {
#ifdef SENSOR_SCD4X
    if (!real_) return;
    bool ready = false;
    if (scd_.getDataReadyStatus(ready) != 0 || !ready) return;
    uint16_t co2 = 0;
    float t = 0, h = 0;
    if (scd_.readMeasurement(co2, t, h) == 0 && co2 > 0) {
      temperature_ = t;
      humidity_ = h;
      co2_ = co2;
      valid_ = true;
    }
#endif
  }

  float temperature() { return real_ && valid_ ? temperature_ : fallback_.readTemperature(); }
  float humidity() { return real_ && valid_ ? humidity_ : fallback_.readHumidity(); }
  float co2() { return real_ && valid_ ? co2_ : fallback_.readCo2(); }

 private:
  ModelRunner &fallback_;
  bool real_ = false;
  bool valid_ = false;
  float temperature_ = 0, humidity_ = 0, co2_ = 0;
#ifdef SENSOR_SCD4X
  SensirionI2cScd4x scd_;
#endif
};
