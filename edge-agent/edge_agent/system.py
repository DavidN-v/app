from pathlib import Path

import psutil

THERMAL_ZONE = Path("/sys/class/thermal/thermal_zone0/temp")


def read_temperature() -> float | None:
    """Temperatura del SoC. En Raspberry Pi viene de thermal_zone0 en miligrados."""
    try:
        return round(int(THERMAL_ZONE.read_text().strip()) / 1000, 1)
    except (OSError, ValueError):
        pass
    try:
        sensors = psutil.sensors_temperatures()  # type: ignore[attr-defined]
    except AttributeError:  # Windows/macOS
        return None
    for entries in sensors.values():
        if entries:
            return round(entries[0].current, 1)
    return None


def collect() -> dict:
    return {
        "cpu": psutil.cpu_percent(interval=None),
        "ram": psutil.virtual_memory().percent,
        "temp": read_temperature(),
        "disk": psutil.disk_usage("/").percent,
    }
