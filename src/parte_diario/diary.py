"""Lectura y edición de los ficheros diarios del diario profesional.

Formato observado en el vault (ficheros ``YYYY-MM-DD.md``):

    Nombre de tarea            <- también puede ser "[Nombre](url)"
    08:15 - 08:52              <- rango de tiempo cerrado
    09:10 -                    <- rango de tiempo abierto (sin hora de fin)
    * una nota                 <- nota suelta dentro del bloque
    -15 texto                  <- ajuste manual de minutos (no lo tocamos)

    Otra tarea
    ...

Los bloques van separados por una o más líneas en blanco. Una misma tarea
puede tener varios rangos de tiempo dentro del mismo bloque (reanudaciones).
Este módulo edita los ficheros a nivel de línea para no destrozar el
formato ni las anotaciones manuales que ya contengan.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

HEADER_LINK_RE = re.compile(r"^\[(?P<name>.+?)\]\((?P<url>.+?)\)\s*$")
OPEN_LINE_RE = re.compile(r"^(?P<start>\d{2}:\d{2}) - \s*$")


@dataclass
class Block:
    start: int  # índice (inclusive) de la primera línea del bloque
    end: int  # índice (exclusivo) tras la última línea del bloque
    lines: List[str]

    @property
    def header(self) -> str:
        return self.lines[0] if self.lines else ""

    @property
    def name(self) -> str:
        match = HEADER_LINK_RE.match(self.header)
        if match:
            return match.group("name").strip()
        return self.header.strip()


def read_lines(path: Path) -> List[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    if text.strip() == "":
        return []
    return text.split("\n")


def write_lines(path: Path, lines: List[str]) -> None:
    # Aseguramos un único salto de línea final, sin líneas en blanco extra.
    while lines and lines[-1] == "":
        lines.pop()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def find_blocks(lines: List[str]) -> List[Block]:
    blocks: List[Block] = []
    i = 0
    n = len(lines)
    while i < n:
        if lines[i].strip() == "":
            i += 1
            continue
        start = i
        while i < n and lines[i].strip() != "":
            i += 1
        blocks.append(Block(start=start, end=i, lines=lines[start:i]))
    return blocks


def find_block_by_name(lines: List[str], name: str) -> Optional[Block]:
    target = name.strip().lower()
    matches = [b for b in find_blocks(lines) if b.name.strip().lower() == target]
    return matches[-1] if matches else None


def make_header(name: str, url: Optional[str]) -> str:
    if url:
        return f"[{name}]({url})"
    return name


def append_new_block(lines: List[str], header: str, first_content_line: str) -> List[str]:
    new_lines = list(lines)
    if new_lines and new_lines[-1] != "":
        new_lines.append("")
    elif new_lines:
        # Aseguramos exactamente una línea en blanco de separación.
        while len(new_lines) >= 2 and new_lines[-1] == "" and new_lines[-2] == "":
            new_lines.pop()
    new_lines.append(header)
    new_lines.append(first_content_line)
    return new_lines


def append_line_to_block(lines: List[str], block: Block, new_line: str) -> List[str]:
    new_lines = list(lines)
    new_lines.insert(block.end, new_line)
    return new_lines


def close_open_line(lines: List[str], start_time: str, prefer_block_name: Optional[str] = None) -> Optional[List[str]]:
    """Busca la línea abierta ``HH:MM - `` con la hora de inicio dada y la cierra.

    Si se indica ``prefer_block_name`` se busca primero dentro del bloque de
    esa tarea; si no aparece ahí, se busca en cualquier bloque como último
    recurso (por si el fichero se editó a mano).
    Devuelve las nuevas líneas, o ``None`` si no se encontró la línea abierta.
    """
    target = f"{start_time} - "

    def _try_close(candidate_indices: range) -> Optional[int]:
        for idx in candidate_indices:
            if lines[idx] == target:
                return idx
        return None

    idx: Optional[int] = None
    if prefer_block_name:
        block = find_block_by_name(lines, prefer_block_name)
        if block is not None:
            idx = _try_close(range(block.start, block.end))

    if idx is None:
        idx = _try_close(range(len(lines)))

    if idx is None:
        return None

    end_time = datetime.now().strftime("%H:%M")
    new_lines = list(lines)
    new_lines[idx] = f"{start_time} - {end_time}"
    return new_lines


def add_note_to_block(lines: List[str], name: str, note: str) -> Optional[List[str]]:
    block = find_block_by_name(lines, name)
    if block is None:
        return None
    bullet = note if note.startswith(("*", "-")) else f"* {note}"
    return append_line_to_block(lines, block, bullet)


def add_or_create_block_line(lines: List[str], name: str, url: Optional[str], content_line: str) -> List[str]:
    """Añade ``content_line`` al bloque de ``name`` si existe, o crea el bloque.

    Se usa tanto para ajustes de minutos (``+15`` / ``-15``) como para el
    primer rango horario de una tarea nueva.
    """
    block = find_block_by_name(lines, name)
    if block is not None:
        return append_line_to_block(lines, block, content_line)
    header = make_header(name, url)
    return append_new_block(lines, header, content_line)


def append_free_block(lines: List[str], text_lines: List[str]) -> List[str]:
    """Añade un bloque suelto (nota sin tarea asociada) al final del fichero."""
    new_lines = list(lines)
    if new_lines and new_lines[-1] != "":
        new_lines.append("")
    new_lines.extend(text_lines)
    return new_lines
