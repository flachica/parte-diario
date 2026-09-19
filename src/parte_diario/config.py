"""Configuración del CLI: ubicación del vault y de los ficheros de estado."""
from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_VAULT = Path.home() / "Diario Profesional"

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "parte-diario"
CONFIG_FILE = CONFIG_DIR / "config.json"

STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "parte-diario"
STATE_FILE = STATE_DIR / "estado.json"


def get_vault_path() -> Path:
    """Devuelve la ruta del vault del diario.

    Orden de prioridad: variable de entorno DIARIO_VAULT > fichero de
    configuración > valor por defecto.
    """
    env_value = os.environ.get("DIARIO_VAULT")
    if env_value:
        return Path(env_value).expanduser()

    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            vault = data.get("vault")
            if vault:
                return Path(vault).expanduser()
        except (json.JSONDecodeError, OSError):
            pass

    return DEFAULT_VAULT


def set_vault_path(path: Path) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps({"vault": str(path)}, ensure_ascii=False, indent=2), encoding="utf-8")
