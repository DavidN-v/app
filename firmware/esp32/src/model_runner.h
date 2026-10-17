// Ejecución del modelo de confort ambiental con TensorFlow Lite Micro, la versión de
// TensorFlow pensada para microcontroladores. El modelo va incluido dentro del firmware.
// El modelo se incluye como array C generado con:
//   xxd -i env_regressor.tflite > src/model_data.h
#pragma once

#include <Arduino.h>
#include <TensorFlowLite_ESP32.h>
#include <tensorflow/lite/micro/all_ops_resolver.h>
#include <tensorflow/lite/micro/micro_error_reporter.h>
#include <tensorflow/lite/micro/micro_interpreter.h>
#include <tensorflow/lite/schema/schema_generated.h>

#include "model_data.h"

class ModelRunner {
 public:
  void begin() {
    model_ = tflite::GetModel(env_regressor_tflite);
    static tflite::AllOpsResolver resolver;
    static tflite::MicroErrorReporter reporter;
    static tflite::MicroInterpreter interpreter(model_, resolver, arena_, kArenaSize, &reporter);
    interpreter_ = &interpreter;
    interpreter_->AllocateTensors();
  }

  float predict(const float features[3]) {
    uint32_t t0 = micros();
    TfLiteTensor *in = interpreter_->input(0);
    for (int i = 0; i < 3; i++) in->data.f[i] = features[i];
    interpreter_->Invoke();
    busyUs_ += micros() - t0;
    return interpreter_->output(0)->data.f[0];
  }

  // Porcentaje del tiempo dedicado a inferencia desde la última consulta (aprox. de CPU)
  float lastDutyCyclePct() {
    uint32_t now = micros();
    float pct = 100.0f * busyUs_ / max<uint32_t>(1, now - windowStart_);
    busyUs_ = 0;
    windowStart_ = now;
    return pct;
  }

  // Sustituir por la lectura real de los sensores (p. ej. BME280 + SCD40)
  float readTemperature() { return 24.0f + random(-10, 10) / 10.0f; }
  float readHumidity() { return 56.0f + random(-20, 20) / 10.0f; }
  float readCo2() { return 600.0f + random(-30, 30); }

 private:
  static constexpr int kArenaSize = 16 * 1024;
  alignas(16) uint8_t arena_[kArenaSize];
  const tflite::Model *model_ = nullptr;
  tflite::MicroInterpreter *interpreter_ = nullptr;
  uint32_t busyUs_ = 0;
  uint32_t windowStart_ = 0;
};
