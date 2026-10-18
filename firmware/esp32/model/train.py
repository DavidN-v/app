"""Entrena el regresor ambiental del ESP32 y lo exporta a src/model_data.h."""

from pathlib import Path

import numpy as np
import tensorflow as tf

HERE = Path(__file__).resolve().parent
OUT_TFLITE = HERE / "env_regressor.tflite"
OUT_HEADER = HERE.parent / "src" / "model_data.h"


def comfort(t, h, co2):
    score = 100 - 6 * np.abs(t - 22) - 0.8 * np.abs(h - 50) - 0.04 * np.clip(co2 - 600, 0, None)
    return np.clip(score, 0, 100)


def dataset(n, rng):
    t = rng.uniform(10, 40, n)
    h = rng.uniform(15, 90, n)
    co2 = rng.uniform(400, 2000, n)
    x = np.stack([t, h, co2], axis=1).astype(np.float32)
    y = (comfort(t, h, co2) + rng.normal(0, 1.5, n)).astype(np.float32)
    return x, y


def main():
    tf.random.set_seed(7)
    rng = np.random.default_rng(7)
    x, y = dataset(20000, rng)
    x_val, y_val = dataset(2000, rng)

    mean, std = x.mean(axis=0), x.std(axis=0)
    model = tf.keras.Sequential([
        tf.keras.Input(shape=(3,), name="features"),
        tf.keras.layers.Dense(16, activation="relu"),
        tf.keras.layers.Dense(16, activation="relu"),
        tf.keras.layers.Dense(1, name="comfort"),
    ])
    model.compile(optimizer=tf.keras.optimizers.Adam(0.01), loss="mse", metrics=["mae"])
    model.fit((x - mean) / std, y, epochs=40, batch_size=256,
              validation_data=((x_val - mean) / std, y_val), verbose=0)

    # La normalización se pliega en la primera capa: el firmware pasa las lecturas en crudo
    # y el grafo solo contiene FULLY_CONNECTED, soportado por cualquier TFLite Micro.
    w, b = model.layers[0].get_weights()
    model.layers[0].set_weights([w / std[:, None], b - (mean / std) @ w])
    _, mae = model.evaluate(x_val, y_val, verbose=0)
    print(f"MAE validación: {mae:.2f} puntos")

    tflite = tf.lite.TFLiteConverter.from_keras_model(model).convert()
    OUT_TFLITE.write_bytes(tflite)

    interp = tf.lite.Interpreter(model_content=tflite)
    interp.allocate_tensors()
    sample = np.array([[24.0, 56.0, 600.0]], dtype=np.float32)
    interp.set_tensor(interp.get_input_details()[0]["index"], sample)
    interp.invoke()
    pred = interp.get_tensor(interp.get_output_details()[0]["index"])[0, 0]
    print(f"Ejemplo 24 °C / 56 % / 600 ppm -> {pred:.1f} (referencia {comfort(24, 56, 600):.1f})")

    rows = [", ".join(f"0x{b:02x}" for b in tflite[i:i + 12]) for i in range(0, len(tflite), 12)]
    OUT_HEADER.write_text(
        "// Generado por model/train.py: regresor de confort ambiental (temp, HR, CO2 -> 0-100).\n"
        f"// MAE de validación: {mae:.2f} puntos. No editar a mano.\n"
        "#pragma once\n\n"
        "alignas(16) const unsigned char env_regressor_tflite[] = {\n  "
        + ",\n  ".join(rows)
        + "\n};\n"
        f"const unsigned int env_regressor_tflite_len = {len(tflite)};\n",
        encoding="utf-8",
    )
    print(f"{OUT_HEADER.name}: {len(tflite)} bytes")


if __name__ == "__main__":
    main()
