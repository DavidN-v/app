"""Instalación segura de modelos en el dispositivo.

Pasos: descargar el archivo a un fichero temporal, comprobar que su resumen SHA-256 coincide
con el registrado en la plataforma, moverlo a su sitio definitivo en una sola operación y
actualizar el manifiesto (el archivo que indica qué modelo está instalado). Si cualquier paso
falla, el modelo anterior sigue intacto, de modo que un fallo nunca deja el dispositivo sin modelo.
"""

import hashlib
import json
import os
import shutil
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

# Los archivos se leen por bloques de 1 MB para no cargar un modelo grande entero en memoria
CHUNK = 1024 * 1024


@dataclass
class InstallResult:
    """Resultado de una instalación o de una vuelta atrás."""

    ok: bool
    message: str
    path: Path | None = None


def sha256_of(path: Path) -> str:
    """Resumen SHA-256 de un archivo."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, dest: Path, timeout: float = 60) -> None:
    """Descarga el modelo. Las direcciones file:// se usan en las pruebas."""
    if url.startswith("file://"):
        shutil.copyfile(url.removeprefix("file://"), dest)
        return
    if not url.startswith(("https://", "http://")):
        raise ValueError(f"Esquema de URL no soportado: {url}")
    with urllib.request.urlopen(url, timeout=timeout) as resp, open(dest, "wb") as out:  # noqa: S310
        shutil.copyfileobj(resp, out, CHUNK)


class ModelStore:
    """Carpeta de modelos del dispositivo. Recuerda el modelo actual y el anterior."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.root / "manifest.json"

    def manifest(self) -> dict:
        if self.manifest_path.exists():
            return json.loads(self.manifest_path.read_text())
        return {"current": None, "previous": None}

    def _write_manifest(self, manifest: dict) -> None:
        """Se escribe en un archivo temporal y se renombra: si se corta la luz a mitad,
        el manifiesto anterior sigue siendo válido."""
        tmp = self.manifest_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(manifest, indent=2))
        os.replace(tmp, self.manifest_path)

    def install(self, command: dict, downloader=_download, progress=lambda stage: None) -> InstallResult:
        """Instala el modelo de la orden y avisa de cada etapa a través de progress."""
        name, version = command["model"], command["version"]
        expected = command["sha256"].lower()
        target = self.root / f"{name}-{version}.{command.get('framework', 'bin')}"

        fd, tmp_name = tempfile.mkstemp(dir=self.root, suffix=".part")
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            progress("downloading")
            downloader(command["url"], tmp)
            progress("verifying")
            actual = sha256_of(tmp)
            if actual != expected:
                return InstallResult(False, f"sha256 no coincide: esperado {expected[:12]}…, "
                                            f"obtenido {actual[:12]}…")
            progress("installing")
            os.replace(tmp, target)
        except Exception as exc:  # red, disco, URL inválida…
            return InstallResult(False, f"Error de instalación: {exc}")
        finally:
            tmp.unlink(missing_ok=True)

        manifest = self.manifest()
        manifest["previous"] = manifest["current"]
        manifest["current"] = {"model": name, "version": version, "path": str(target),
                               "sha256": expected}
        self._write_manifest(manifest)
        return InstallResult(True, f"{name} v{version} instalado", target)

    def rollback(self) -> InstallResult:
        """Vuelve al modelo anterior si todavía está en disco."""
        manifest = self.manifest()
        previous = manifest.get("previous")
        if not previous or not Path(previous["path"]).exists():
            return InstallResult(False, "No hay versión anterior disponible")
        manifest["current"], manifest["previous"] = previous, manifest["current"]
        self._write_manifest(manifest)
        return InstallResult(True, f"Rollback a {previous['model']} v{previous['version']}",
                             Path(previous["path"]))
