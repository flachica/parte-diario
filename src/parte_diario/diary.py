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
OPEN_LINE_RE = re.compile(r"^(?P<start>\d{1,2}:\d{2})\s*-\s*$")


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

    @property
    def url(self) -> Optional[str]:
        match = HEADER_LINK_RE.match(self.header)
        if match:
            return match.group("url").strip()
        return None


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


def get_blocks_info(lines: List[str]) -> List[tuple[str, Optional[str]]]:
    """Devuelve una lista de tuplas (nombre, url) de las tareas encontradas en el fichero,
    ignorando notas sueltas y evitando duplicados."""
    res: List[tuple[str, Optional[str]]] = []
    seen = set()
    for b in find_blocks(lines):
        name = b.name.strip()
        if not name or name.startswith(("*", "-", "+")):
            continue
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        match = HEADER_LINK_RE.match(b.header)
        url = match.group("url").strip() if match else None
        res.append((name, url))
    return res



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


def close_open_line(
    lines: List[str],
    start_time: str,
    prefer_block_name: Optional[str] = None,
    end_time: Optional[str] = None,
) -> Optional[List[str]]:
    """Busca la línea abierta ``HH:MM - `` con la hora de inicio dada y la cierra.

    Si se indica ``prefer_block_name`` se busca primero dentro del bloque de
    esa tarea; si no aparece ahí, se busca en cualquier bloque como último
    recurso (por si el fichero se editó a mano).
    Devuelve las nuevas líneas, o ``None`` si no se encontró la línea abierta.
    """
    target = f"{start_time} - "
    open_re = re.compile(rf"^{re.escape(start_time)}\s*-\s*$")

    def _try_close(candidate_indices: range) -> Optional[tuple[int, str]]:
        # Primero busca coincidencia exacta o flexible con start_time
        for idx in candidate_indices:
            line_str = lines[idx].strip()
            if lines[idx] == target or open_re.match(line_str):
                return idx, start_time
        # Si no hay coincidencia exacta con start_time pero hay una línea abierta genérica
        for idx in candidate_indices:
            m = OPEN_LINE_RE.match(lines[idx].strip())
            if m:
                return idx, m.group("start")
        return None

    result: Optional[tuple[int, str]] = None
    if prefer_block_name:
        block = find_block_by_name(lines, prefer_block_name)
        if block is not None:
            result = _try_close(range(block.start, block.end))

    if result is None:
        result = _try_close(range(len(lines)))

    if result is None:
        return None

    idx, actual_start = result
    actual_end = end_time or datetime.now().strftime("%H:%M")
    new_lines = list(lines)
    new_lines[idx] = f"{actual_start} - {actual_end}"
    return new_lines


def find_open_task_in_lines(lines: List[str]) -> Optional[tuple[str, str]]:
    """Busca si hay alguna tarea con línea abierta en las líneas del fichero.
    Devuelve (nombre_tarea, start_time) de la última tarea abierta encontrada, o None."""
    blocks = find_blocks(lines)
    for b in reversed(blocks):
        for line in reversed(b.lines[1:]):  # Ignoramos la cabecera
            m = OPEN_LINE_RE.match(line.strip())
            if m:
                return b.name, m.group("start")
    return None


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


CLOSED_LINE_RE = re.compile(r"^(?P<start>\d{1,2}:\d{2})\s*-\s*(?P<end>\d{1,2}:\d{2})$")
ADJUSTMENT_RE = re.compile(r"^([+-])\s*(\d+)(?:\s.*)?$")


@dataclass
class TaskReviewItem:
    name: str
    url: Optional[str]
    minutes: int
    is_open: bool = False


def minutes_between(start_str: str, end_str: str) -> int:
    """Calcula la diferencia en minutos entre dos horas en formato HH:MM (soporta paso de medianoche)."""
    s_parts = start_str.split(":")
    e_parts = end_str.split(":")
    start_m = int(s_parts[0]) * 60 + int(s_parts[1])
    end_m = int(e_parts[0]) * 60 + int(e_parts[1])
    diff = end_m - start_m
    if diff < 0:
        diff += 24 * 60
    return diff


def get_tasks_summary(
    lines: List[str],
    file_date: Optional[str] = None,
    reference_time: Optional[datetime] = None,
) -> List[TaskReviewItem]:
    """Procesa las líneas de un diario y devuelve el resumen agrupado de tareas,
    con sus URLs (si tienen) y el total de minutos invertidos."""
    now = reference_time or datetime.now()
    today_str = f"{now:%Y-%m-%d}"
    target_date = file_date or today_str
    is_today = (target_date == today_str)
    now_hm = f"{now:%H:%M}"

    blocks = find_blocks(lines)
    items: List[TaskReviewItem] = []

    for b in blocks:
        name = b.name.strip()
        if not name or name.startswith(("*", "-", "+", "#", ">")):
            continue

        block_mins = 0
        has_time_entry = False
        block_is_open = False

        for line in b.lines[1:]:
            tr = parse_time_range(line)
            if tr:
                has_time_entry = True
                s_str, e_str = tr
                if e_str:
                    block_mins += minutes_between(s_str, e_str)
                else:
                    block_is_open = True
                    if is_today:
                        block_mins += minutes_between(s_str, now_hm)
            else:
                adj = ADJUSTMENT_RE.match(line.strip())
                if adj:
                    has_time_entry = True
                    sign = -1 if adj.group(1) == "-" else 1
                    block_mins += sign * int(adj.group(2))

        if not has_time_entry:
            continue

        match: Optional[TaskReviewItem] = None
        if b.url:
            for item in items:
                if item.url and item.url == b.url:
                    match = item
                    break

        if match is None:
            for item in items:
                if item.name.lower() == name.lower():
                    match = item
                    break

        if match is not None:
            match.minutes += block_mins
            if not match.url and b.url:
                match.url = b.url
            if block_is_open:
                match.is_open = True
        else:
            items.append(
                TaskReviewItem(
                    name=name,
                    url=b.url,
                    minutes=block_mins,
                    is_open=block_is_open,
                )
            )

    return items


def parse_time_range(line: str) -> Optional[tuple[str, Optional[str]]]:
    """Si la línea es un rango horario (abierto o cerrado), devuelve (inicio, fin_o_None)."""
    s = line.strip()
    m_closed = CLOSED_LINE_RE.match(s)
    if m_closed:
        return m_closed.group("start"), m_closed.group("end")
    m_open = OPEN_LINE_RE.match(s)
    if m_open:
        return m_open.group("start"), None
    return None


def format_time_range(start: str, end: Optional[str]) -> str:
    """Formatea un rango de tiempo 'HH:MM - HH:MM' o 'HH:MM - ' asegurando dos dígitos."""
    s_parts = start.split(":")
    start_fmt = f"{int(s_parts[0]):02d}:{int(s_parts[1]):02d}"
    if end:
        e_parts = end.split(":")
        end_fmt = f"{int(e_parts[0]):02d}:{int(e_parts[1]):02d}"
        return f"{start_fmt} - {end_fmt}"
    return f"{start_fmt} - "


def find_highest_time_in_lines(lines: List[str]) -> Optional[str]:
    """Busca y devuelve la hora más alta registrada en los rangos horarios del fichero (formato HH:MM)."""
    times: List[tuple[int, int, str]] = []
    for line in lines:
        tr = parse_time_range(line)
        if tr:
            start_str, end_str = tr
            s_parts = start_str.split(":")
            times.append((int(s_parts[0]), int(s_parts[1]), f"{int(s_parts[0]):02d}:{int(s_parts[1]):02d}"))
            if end_str:
                e_parts = end_str.split(":")
                times.append((int(e_parts[0]), int(e_parts[1]), f"{int(e_parts[0]):02d}:{int(e_parts[1]):02d}"))

    if not times:
        return None

    times.sort(key=lambda t: (t[0], t[1]))
    return times[-1][2]


def update_block_header(lines: List[str], block: Block, new_name: str, new_url: Optional[str]) -> List[str]:
    """Actualiza la cabecera del bloque con el nuevo nombre y URL."""
    new_header = make_header(new_name.strip(), new_url.strip() if new_url else None)
    new_lines = list(lines)
    new_lines[block.start] = new_header
    return new_lines


def update_block_line(lines: List[str], global_line_idx: int, new_content: str) -> List[str]:
    """Actualiza una línea específica del fichero."""
    new_lines = list(lines)
    new_lines[global_line_idx] = new_content
    return new_lines


def delete_block_line(lines: List[str], global_line_idx: int) -> List[str]:
    """Elimina una línea específica del fichero."""
    new_lines = list(lines)
    del new_lines[global_line_idx]
    return new_lines


def delete_block(lines: List[str], block: Block) -> List[str]:
    """Elimina un bloque completo y normaliza las líneas en blanco circundantes."""
    new_lines = list(lines[:block.start]) + list(lines[block.end:])
    cleaned: List[str] = []
    prev_blank = False
    for line in new_lines:
        if line.strip() == "":
            if not prev_blank and cleaned:
                cleaned.append("")
                prev_blank = True
        else:
            cleaned.append(line)
            prev_blank = False
    return cleaned

