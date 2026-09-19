"""Persistencia del trabajo actualmente abierto (solo puede haber uno)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from .config import STATE_FILE


@dataclass
class OpenTask:
    name: str
    url: Optional[str]
    file: str
    date: str
    start_time: str


def load() -> Optional[OpenTask]:
    if not STATE_FILE.exists():
        return None
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not data:
        return None
    return OpenTask(**data)


def save(task: OpenTask) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(asdict(task), ensure_ascii=False, indent=2), encoding="utf-8")


def clear() -> None:
    if STATE_FILE.exists():
        STATE_FILE.unlink()
