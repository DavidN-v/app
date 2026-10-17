import os
import time
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


def _processes():
    for p in psutil.process_iter(["cpu_times", "memory_info"]):
        times, mem = p.info["cpu_times"], p.info["memory_info"]
        if times is not None and mem is not None:
            yield p.pid, times.user + times.system, mem.rss


class BoardMeter:
    """Uso de una placa emulada (por ejemplo, una Raspberry Pi 5 dentro de un contenedor).

    psutil a nivel de sistema ve la máquina anfitriona entera, así que se suman los procesos
    visibles (los del contenedor y los de los contenedores que comparten su espacio de PID)
    y se comparan con la capacidad de la placa: `cpus` núcleos y `ram_mb` de memoria."""

    def __init__(self, cpus: float, ram_mb: float, processes=_processes, clock=time.monotonic) -> None:
        self.cpus, self.ram_bytes = cpus, ram_mb * 1024 * 1024
        self._processes, self._clock = processes, clock
        self._last_cpu: dict[int, float] = {}
        self._last_ts: float | None = None

    def sample(self) -> tuple[float, float]:
        now = self._clock()
        busy, rss, seen = 0.0, 0, {}
        for pid, cpu_s, mem in self._processes():
            # Un proceso nuevo solo cuenta desde que se le ve: su tiempo previo es de antes
            busy += max(0.0, cpu_s - self._last_cpu.get(pid, cpu_s))
            rss += mem
            seen[pid] = cpu_s
        elapsed = now - self._last_ts if self._last_ts is not None else 0.0
        self._last_cpu, self._last_ts = seen, now
        cpu = min(100.0, 100.0 * busy / (elapsed * self.cpus)) if elapsed > 0 else 0.0
        return round(cpu, 1), round(min(100.0, 100.0 * rss / self.ram_bytes), 1)


def _board_from_env() -> BoardMeter | None:
    cpus, ram_mb = os.getenv("EDGE_BOARD_CPUS"), os.getenv("EDGE_BOARD_RAM_MB")
    return BoardMeter(float(cpus), float(ram_mb)) if cpus and ram_mb else None


_board = _board_from_env()


def collect() -> dict:
    if _board is not None:
        cpu, ram = _board.sample()
    else:
        cpu, ram = psutil.cpu_percent(interval=None), psutil.virtual_memory().percent
    return {
        "cpu": cpu,
        "ram": ram,
        "temp": read_temperature(),
        "disk": psutil.disk_usage("/").percent,
    }
