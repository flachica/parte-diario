"""Módulo de sesión interactiva para el CLI parte-diario."""
from __future__ import annotations

import io
import os
import re
import shlex
import shutil
import sys
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from . import diary, state
from .cli import (
    _close_current,
    _today_file,
    dispatch_command,
    do_config_set_vault,
    do_interrupt,
    do_log,
    do_note,
    do_review,
    do_start,
    do_status,
    do_stop,
    get_status_info,
    get_vault_path,
)


def _get_hist_file() -> Path:
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "parte-diario" / "history"


try:
    import readline
    HAVE_READLINE = True
except ImportError:
    HAVE_READLINE = False


COMMANDS = [
    "start",
    "stop",
    "status",
    "note",
    "interrupt",
    "log",
    "show",
    "edit",
    "editar",
    "review",
    "repasar",
    "repaso",
    "config",
    "completion",
    "help",
    "ayuda",
    "menu",
    "clear",
    "cls",
    "salir",
    "exit",
    "quit",
]


def configure_readline() -> None:
    if not HAVE_READLINE:
        return
    try:
        readline.parse_and_bind("tab: complete")
    except Exception:
        pass
    for setting in (
        "set show-all-if-ambiguous on",
        "set completion-ignore-case on",
        "set completion-query-items 0",
    ):
        try:
            readline.parse_and_bind(setting)
        except Exception:
            pass


class ListCompleter:
    def __init__(self, options: List[str]):
        self.options = options

    def complete(self, text: str, state_idx: int) -> Optional[str]:
        matches = [opt for opt in self.options if opt.lower().startswith(text.lower())]
        if state_idx < len(matches):
            return matches[state_idx]
        return None


class InteractiveCompleter:
    def __init__(self, commands: List[str]):
        self.commands = commands

    def complete(self, text: str, state_idx: int) -> Optional[str]:
        if not HAVE_READLINE:
            return None
        buf = readline.get_line_buffer()
        line = buf.lstrip()
        parts = line.split()

        # Si estamos completando la primera palabra (el comando)
        if len(parts) == 0 or (len(parts) == 1 and not buf.endswith(" ")):
            matches = [cmd for cmd in self.commands if cmd.lower().startswith(text.lower())]
        else:
            first_cmd = parts[0].lower()
            if first_cmd == "config":
                matches = [c for c in ["show", "set-vault"] if c.lower().startswith(text.lower())]
            elif first_cmd in ("show", "edit", "editar"):
                matches = [opt for opt in ["--fecha", "--editor"] if opt.lower().startswith(text.lower())]
            elif first_cmd in ("review", "repasar", "repaso"):
                matches = [opt for opt in ["--fecha", "--con-nombre", "--nombres", "--todo", "--all", "--iterativo"] if opt.lower().startswith(text.lower())]
            elif first_cmd == "note":
                matches = [opt for opt in ["--loose", "--suelta"] if opt.lower().startswith(text.lower())]
            elif first_cmd in ("start", "interrupt"):
                candidates = ["--url"]
                try:
                    for name, _ in get_today_tasks():
                        if name not in candidates:
                            candidates.append(name)
                except Exception:
                    pass
                matches = [c for c in candidates if c.lower().startswith(text.lower())]
            elif first_cmd == "log":
                candidates = ["--url", "--resta"]
                try:
                    for name, _ in get_today_tasks():
                        if name not in candidates:
                            candidates.append(name)
                except Exception:
                    pass
                matches = [c for c in candidates if c.lower().startswith(text.lower())]
            elif first_cmd == "completion":
                matches = [c for c in ["bash", "zsh", "--install"] if c.lower().startswith(text.lower())]
            else:
                matches = []

        if state_idx < len(matches):
            return matches[state_idx]
        return None


def input_with_completion(prompt_text: str, candidates: List[str]) -> str:
    if not HAVE_READLINE or not sys.stdin.isatty():
        return input(prompt_text)
    old_completer = readline.get_completer()
    try:
        configure_readline()
        readline.set_completer(ListCompleter(candidates).complete)
        return input(prompt_text)
    finally:
        readline.set_completer(old_completer)



def _can_color() -> bool:
    return sys.stdout.isatty() and "NO_COLOR" not in os.environ and os.environ.get("TERM") != "dumb"


def _can_clear() -> bool:
    return (
        sys.stdout.isatty()
        and sys.stdin.isatty()
        and "NO_COLOR" not in os.environ
        and os.environ.get("TERM") != "dumb"
        and "PARTE_NO_CLEAR" not in os.environ
    )


def clear_screen() -> None:
    if _can_clear():
        print("\033[H\033[2J", end="", flush=True)


def _c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _can_color() else text


def bold(text: str) -> str:
    return _c(text, "1")


def green(text: str) -> str:
    return _c(text, "32")


def yellow(text: str) -> str:
    return _c(text, "33")


def cyan(text: str) -> str:
    return _c(text, "36")


def dim(text: str) -> str:
    return _c(text, "90")


def format_status_line() -> str:
    info = get_status_info()
    if info is None:
        return f"{dim('○')} {dim('Sin trabajo abierto')}"

    hours = info["hours"]
    mins = info["minutes"]
    dur = f"{hours}h {mins:02d}m" if hours > 0 else f"{mins}m"
    url_part = f" {dim('(' + info['url'] + ')')}" if info["url"] else ""
    return f"{green('●')} {bold(info['name'])}{url_part} {dim('·')} desde {info['start_time']} ({dur})"


def format_help() -> str:
    lines = [
        bold("Comandos y atajos disponibles:"),
        f"  {bold('1-10')}               Ejecuta la opción del menú superior",
        f"  {bold('start')} <tarea>       Inicia una tarea (opcionales: --url, --hora, --latest)",
        f"  {bold('stop')}                Cierra la tarea actualmente abierta",
        f"  {bold('status')} (o 7)        Muestra la información de la tarea abierta",
        f"  {bold('note')} <texto>        Añade una nota al trabajo actual (o --loose)",
        f"  {bold('interrupt')} <motivo> <min>  Resta minutos a la tarea abierta y anota la interrupción",
        f"  {bold('log')} <tarea> <min>   Anota minutos sueltos (+ o con --resta)",
        f"  {bold('show')}                Muestra el diario de hoy (o con --fecha YYYY-MM-DD)",
        f"  {bold('review')} (o 9)        Repasa el parte del día paso a paso (o con --todo)",
        f"  {bold('edit')} (o 8)          Edita entradas interactivamente (o -e para abrir $EDITOR)",
        f"  {bold('config')} show|set-vault  Muestra o fija la ruta del vault",
        f"  {bold('[Enter]')}             Refresca la pantalla y actualiza el tiempo transcurrido",
        f"  {bold('clear / cls')}         Limpia la sección de resultados",
        f"  {bold('0 / q / exit')}        Salir de la aplicación",
    ]
    return "\n".join(lines)


def print_dashboard(result_content: Optional[str] = None, clear: bool = True) -> None:
    if clear:
        clear_screen()

    vault = get_vault_path()
    status_line = format_status_line()
    width = 70

    # SECCIÓN 1: OPERACIONES Y ESTADO
    print("=" * width)
    print(bold("                     PARTE DIARIO - MODO INTERACTIVO").center(width))
    print("=" * width)
    print(f" Vault:  {dim(str(vault))}")
    print(f" Estado: {status_line}")
    print("-" * width)
    print(f" {bold('[1]')} Iniciar / reanudar tarea       {bold('[6]')} Ver diario de hoy / fecha")
    print(f" {bold('[2]')} Parar tarea abierta (stop)     {bold('[7]')} Ver tarea abierta")
    print(f" {bold('[3]')} Añadir nota (note)             {bold('[8]')} Editar entradas (edit)")
    print(f" {bold('[4]')} Registrar interrupción         {bold('[9]')} Repasar parte (review)")
    print(f" {bold('[5]')} Anotar minutos sueltos (log)  {bold('[10]')} Configurar vault")
    print()
    print(f" {bold('[0]')} Salir (q / exit)               {bold('[?]')} Ayuda / Atajos")
    print("=" * width)

    # SECCIÓN 2: RESULTADOS Y ACTIVIDAD
    label = " RESULTADOS / ACTIVIDAD "
    dash_len = max(0, width - len(label) - 4)
    print(cyan(f"───{label}{'─' * dash_len}"))
    if result_content:
        for line in result_content.splitlines():
            print(f" {line}")
    else:
        print(dim(" Selecciona una opción [1-10] o escribe un comando (Enter para refrescar)."))
    print(cyan("─" * width))


def print_banner() -> None:
    print_dashboard(result_content=None, clear=False)


def print_status_bar() -> None:
    print("-" * 70)
    print(f" Estado: {format_status_line()}")
    print(dim(" Opciones: [1] Iniciar  [2] Parar  [3] Nota  [4] Interrumpir  [5] Minutos  [6] Ver  [7] Tarea  [8] Editar  [9] Repasar  [10] Config  [0] Salir"))


def get_today_tasks() -> List[Tuple[str, Optional[str]]]:
    vault = get_vault_path()
    today_file = _today_file(vault)
    lines = diary.read_lines(today_file)
    return diary.get_blocks_info(lines)


def interactive_start() -> Optional[str]:
    vault = get_vault_path()
    today_file = _today_file(vault)
    lines = diary.read_lines(today_file) if today_file.exists() else []

    tasks_info = get_today_tasks()
    task_names = [name for name, _ in tasks_info]

    if tasks_info:
        print("\nTareas registradas hoy:")
        for idx, (name, url) in enumerate(tasks_info, 1):
            url_str = f" {dim('(' + url + ')')}" if url else ""
            print(f"  {bold(f'[{idx}]')} {name}{url_str}")
        prompt = "\nNombre de la tarea (número para reanudar, o nuevo nombre) [c para cancelar]: "
    else:
        prompt = "\nNombre de la nueva tarea [c para cancelar]: "

    try:
        choice = input_with_completion(prompt, task_names).strip()
    except (KeyboardInterrupt, EOFError):
        return "Operación cancelada."

    if not choice or choice.lower() in ("c", "cancel", "cancelar"):
        return "Operación cancelada."

    selected_name = choice
    existing_url = None

    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(tasks_info):
            selected_name, existing_url = tasks_info[idx]
        else:
            return yellow("Número de tarea no válido.")
    else:
        for name, url in tasks_info:
            if name.lower() == selected_name.lower():
                existing_url = url
                selected_name = name
                break

    try:
        if existing_url:
            print(f"URL actual: {existing_url}")
            new_url = input("Nueva URL (Enter para mantener la actual): ").strip()
            final_url = new_url if new_url else existing_url
        else:
            final_url = input("URL asociada (opcional, Enter para omitir): ").strip() or None
    except (KeyboardInterrupt, EOFError):
        return "Operación cancelada."

    # Opción de hora de inicio: hora del sistema (por defecto) o la más alta registrada
    now_str = datetime.now().strftime("%H:%M")
    highest_time = diary.find_highest_time_in_lines(lines)

    chosen_start = now_str
    if highest_time and highest_time != now_str:
        print(f"\nHora de inicio:")
        print(f"  {bold('[1]')} Hora del sistema: {now_str} {dim('(por defecto)')}")
        print(f"  {bold('[2]')} Hora más alta registrada: {highest_time}")
        try:
            time_choice = input(f"Opción [Enter=1 ({now_str}), 2={highest_time}, o escribe HH:MM]: ").strip()
        except (KeyboardInterrupt, EOFError):
            return "Operación cancelada."

        if time_choice.lower() in ("c", "cancel", "cancelar"):
            return "Operación cancelada."
        elif time_choice in ("2", "u", "ultima", "última", "alta"):
            chosen_start = highest_time
        elif time_choice in ("", "1", "s", "sistema"):
            chosen_start = now_str
        elif _is_valid_time(time_choice):
            chosen_start = time_choice
        else:
            print(yellow(f"Opción o formato no válido ('{time_choice}'). Se usará la hora del sistema ({now_str})."))
            chosen_start = now_str

    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(buf):
        do_start(selected_name, final_url, start_time=chosen_start)
    return buf.getvalue().strip() or f"Iniciado: {selected_name} a las {chosen_start}"


def interactive_stop() -> Optional[str]:
    open_task = state.load()
    if open_task is None:
        return yellow("No hay ningún trabajo abierto para parar.")

    try:
        confirm = input(f"¿Cerrar '{bold(open_task.name)}' iniciada a las {open_task.start_time}? [S/n]: ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        return "Operación cancelada."

    if confirm in ("", "s", "si", "y", "yes"):
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(buf):
            do_stop()
        return buf.getvalue().strip() or f"Cerrado: {open_task.name}"
    else:
        return "Operación cancelada. La tarea sigue abierta."


def interactive_note() -> Optional[str]:
    open_task = state.load()
    loose = False

    if open_task is not None:
        print(f"Tarea abierta actual: {bold(open_task.name)}")
        try:
            opc = input(f"¿Asociar nota a '{open_task.name}'? [S/n] (o 'n' para nota suelta, 'c' para cancelar): ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            return "Operación cancelada."

        if opc in ("c", "cancel", "cancelar"):
            return "Operación cancelada."
        if opc in ("n", "no"):
            loose = True

    prompt = "Texto de la nota suelta [c para cancelar]: " if loose or open_task is None else f"Nota para '{open_task.name}' [c para cancelar]: "
    try:
        texto = input(prompt).strip()
    except (KeyboardInterrupt, EOFError):
        return "Operación cancelada."

    if not texto or texto.lower() in ("c", "cancel", "cancelar"):
        return "Operación cancelada."

    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(buf):
        do_note(texto, loose=loose)
    return buf.getvalue().strip() or "✓ Nota añadida."


def interactive_interrupt() -> Optional[str]:
    open_task = state.load()
    if open_task is None:
        return yellow("No hay ninguna tarea abierta a la que restar tiempo.\nSugerencia: Usa la opción [5] (Anotar minutos sueltos) para registrar tiempo independiente.")

    print(f"Tarea abierta actual: {bold(open_task.name)} (se le restará el tiempo)")
    try:
        nombre = input("Motivo o tarea de la interrupción [c para cancelar]: ").strip()
        if not nombre or nombre.lower() in ("c", "cancel", "cancelar"):
            return "Operación cancelada."

        minutos_str = input("Minutos de duración (ej. 15): ").strip()
        try:
            minutos = int(minutos_str)
            if minutos <= 0:
                raise ValueError()
        except ValueError:
            return yellow("Los minutos deben ser un número entero positivo.")

        url = input("URL opcional para la interrupción (Enter para omitir): ").strip() or None
    except (KeyboardInterrupt, EOFError):
        return "Operación cancelada."

    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(buf):
        do_interrupt(nombre, minutos, url=url)
    return buf.getvalue().strip() or "✓ Interrupción registrada."


def interactive_log() -> Optional[str]:
    tasks_info = get_today_tasks()
    task_names = [name for name, _ in tasks_info]

    if tasks_info:
        print("\nTareas registradas hoy:")
        for idx, (name, _) in enumerate(tasks_info, 1):
            print(f"  {bold(f'[{idx}]')} {name}")
        prompt = "\nNombre de la tarea (número para seleccionar, o nuevo nombre) [c para cancelar]: "
    else:
        prompt = "\nNombre de la tarea [c para cancelar]: "

    try:
        choice = input_with_completion(prompt, task_names).strip()
        if not choice or choice.lower() in ("c", "cancel", "cancelar"):
            return "Operación cancelada."

        selected_name = choice
        existing_url = None
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(tasks_info):
                selected_name, existing_url = tasks_info[idx]
            else:
                return yellow("Número de tarea no válido.")
        else:
            for name, url in tasks_info:
                if name.lower() == selected_name.lower():
                    existing_url = url
                    selected_name = name
                    break

        minutos_str = input("Minutos invertidos (ej. 15): ").strip()
        try:
            minutos = int(minutos_str)
            if minutos <= 0:
                raise ValueError()
        except ValueError:
            return yellow("Los minutos deben ser un número entero positivo.")

        tipo = input("¿Sumar (+) o Restar (-) minutos? [+]: ").strip()
        resta = (tipo == "-")

        if existing_url:
            url = existing_url
        else:
            url = input("URL opcional (Enter para omitir): ").strip() or None
    except (KeyboardInterrupt, EOFError):
        return "Operación cancelada."

    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(buf):
        do_log(selected_name, minutos, resta=resta, url=url)
    return buf.getvalue().strip() or "✓ Minutos anotados."


def interactive_show() -> Optional[str]:
    today_str = datetime.now().strftime("%Y-%m-%d")
    try:
        fecha = input(f"Fecha a consultar [YYYY-MM-DD] (Enter para hoy: {today_str}, c para cancelar): ").strip()
    except (KeyboardInterrupt, EOFError):
        return "Operación cancelada."

    if fecha.lower() in ("c", "cancel", "cancelar"):
        return "Operación cancelada."

    fecha_consultar = fecha if fecha else today_str
    try:
        when = datetime.strptime(fecha_consultar, "%Y-%m-%d")
    except ValueError:
        return yellow("Formato de fecha no válido. Debe ser YYYY-MM-DD.")

    vault = get_vault_path()
    path = _today_file(vault, when)
    if not path.exists():
        return yellow(f"No existe el fichero para {fecha_consultar} ({path}).")

    content = path.read_text(encoding="utf-8").strip()
    header = f"--- Diario: {fecha_consultar} ({path.name}) ---"
    if not content:
        body = dim("(El fichero existe pero está vacío)")
    else:
        body = content
    return f"{bold(header)}\n{body}\n{bold('-' * len(header))}"


def interactive_review() -> Optional[str]:
    today_str = datetime.now().strftime("%Y-%m-%d")
    try:
        fecha = input(f"Fecha a repasar [YYYY-MM-DD] (Enter para hoy: {today_str}, c para cancelar): ").strip()
    except (KeyboardInterrupt, EOFError):
        return "Operación cancelada."

    if fecha.lower() in ("c", "cancel", "cancelar"):
        return "Operación cancelada."

    fecha_consultar = fecha if fecha else today_str
    try:
        when = datetime.strptime(fecha_consultar, "%Y-%m-%d")
    except ValueError:
        return yellow("Formato de fecha no válido. Debe ser YYYY-MM-DD.")

    vault = get_vault_path()
    path = _today_file(vault, when)
    if not path.exists():
        return yellow(f"No existe el fichero para {fecha_consultar} ({path}).")

    header = f"--- Repaso del parte: {fecha_consultar} ({path.name}) ---"
    print("\n" + bold(header))
    do_review(fecha=fecha_consultar, iterative=True)
    print(bold("-" * len(header)) + "\n")
    return f"✓ Repaso del parte finalizado ({fecha_consultar})."


def _is_valid_time(s: str) -> bool:
    m = re.match(r"^(\d{1,2}):(\d{2})$", s.strip())
    if not m:
        return False
    h, m_val = int(m.group(1)), int(m.group(2))
    return 0 <= h < 24 and 0 <= m_val < 60


def _open_in_editor(path: Path) -> None:
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if not editor:
        for cand in ("nano", "vim", "vi"):
            if shutil.which(cand):
                editor = cand
                break
    if not editor:
        print(yellow("No se encontró ningún editor de texto en el sistema ($EDITOR, nano, vi)."))
        return

    try:
        import subprocess
        subprocess.run(f"{editor} {shlex.quote(str(path))}", shell=True, check=True)
    except Exception as e:
        print(yellow(f"Error al abrir el editor: {e}"))


def _refresh_state_from_file(path: Path) -> None:
    lines = diary.read_lines(path)
    open_info = diary.find_open_task_in_lines(lines)
    if open_info is not None:
        task_name, start_time = open_info
        block = diary.find_block_by_name(lines, task_name)
        url = block.url if block else None
        state.save(
            state.OpenTask(
                name=task_name,
                url=url,
                file=str(path),
                date=datetime.now().strftime("%Y-%m-%d"),
                start_time=start_time,
            )
        )
    else:
        state.clear()


def _interactive_edit_block(path: Path, target_block_idx: int, is_today: bool) -> None:
    lines = diary.read_lines(path)
    blocks = diary.find_blocks(lines)
    if not (0 <= target_block_idx < len(blocks)):
        return
    curr_block = blocks[target_block_idx]

    header = f"--- Editando: {curr_block.name} ---"
    print("\n" + bold(header))
    print(dim("(Enter mantiene el valor actual, 'c' o 'fin' guarda y sale, 'cancelar' descarta)\n"))

    new_name = curr_block.name
    new_url = curr_block.url
    body_lines = curr_block.lines[1:]
    new_body_lines: List[str] = []

    def _apply_changes() -> None:
        new_header = diary.make_header(new_name, new_url)
        has_changes = (
            new_header != curr_block.header
            or new_body_lines != body_lines
        )
        if not has_changes:
            print("\nSin cambios en la entrada.")
            return

        updated_block = [new_header] + new_body_lines
        new_lines = list(lines[:curr_block.start]) + updated_block + list(lines[curr_block.end:])
        diary.write_lines(path, new_lines)
        print(green(f"\n✓ Entrada '{new_name}' actualizada."))
        if is_today:
            _refresh_state_from_file(path)

    # 1. Nombre / Texto principal de la tarea
    is_bullet = curr_block.header.strip().startswith(("*", "-", "+"))
    label = "Texto" if is_bullet else "Nombre"
    try:
        ans_name = input(f"{label} [{curr_block.name}] (Enter mantiene, 'd' borra tarea, 'fin' guarda): ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nOperación cancelada.")
        return

    if ans_name.lower() in ("cancelar", "cancel", "descartar", "abort"):
        print("Edición cancelada.")
        return

    if ans_name.lower() in ("c", "fin", "ok", "listo", "guardar", "salir", "q"):
        new_body_lines = list(body_lines)
        _apply_changes()
        return

    if ans_name.lower() == "d":
        try:
            conf = input(f"¿Seguro que deseas eliminar por completo la tarea '{curr_block.name}'? [s/N]: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\nOperación cancelada.")
            return
        if conf in ("s", "si", "y", "yes"):
            new_lines = diary.delete_block(lines, curr_block)
            diary.write_lines(path, new_lines)
            print(green(f"✓ Tarea '{curr_block.name}' eliminada."))
            if is_today:
                _refresh_state_from_file(path)
        else:
            print("Eliminación cancelada.")
        return

    if ans_name:
        new_name = ans_name

    # 2. URL
    current_url_display = curr_block.url if curr_block.url else dim("(ninguna)")
    try:
        ans_url = input(f"URL [{current_url_display}] (Enter mantiene, '-' quita URL, 'fin' guarda): ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nOperación cancelada.")
        return

    if ans_url.lower() in ("cancelar", "cancel", "descartar", "abort"):
        print("Edición cancelada.")
        return

    if ans_url.lower() in ("c", "fin", "ok", "listo", "guardar", "salir", "q"):
        new_body_lines = list(body_lines)
        _apply_changes()
        return

    if ans_url == "-":
        new_url = None
    elif ans_url:
        new_url = ans_url

    # 3. Líneas de contenido existentes
    finish_early = False

    for l_idx, line in enumerate(body_lines, 1):
        if finish_early:
            new_body_lines.append(line)
            continue

        tr = diary.parse_time_range(line)
        if tr:
            old_start, old_end = tr
            end_display = old_end if old_end else "abierta"
            print(f"\n  Línea {l_idx} (rango horario: {line}):")

            # Hora inicio
            final_start = old_start
            while True:
                try:
                    ans_start = input(f"    Hora inicio [{old_start}] (Enter mantiene, 'd' borra línea, 'fin' guarda): ").strip()
                except (KeyboardInterrupt, EOFError):
                    print("\nOperación cancelada.")
                    return

                if ans_start.lower() in ("cancelar", "cancel", "descartar", "abort"):
                    print("Edición cancelada.")
                    return
                if ans_start.lower() in ("c", "fin", "ok", "listo", "guardar", "salir", "q"):
                    new_body_lines.extend(body_lines[l_idx - 1:])
                    finish_early = True
                    break
                if ans_start.lower() == "d":
                    final_start = None
                    break
                if not ans_start:
                    final_start = old_start
                    break
                if _is_valid_time(ans_start):
                    final_start = ans_start
                    break
                print(yellow("    Formato inválido. Usa HH:MM (ej. 08:30)."))

            if finish_early:
                break

            if final_start is None:
                print(dim(f"    (Línea {l_idx} eliminada)"))
                continue

            # Hora fin
            final_end = old_end
            while True:
                try:
                    ans_end = input(f"    Hora fin [{end_display}] (Enter mantiene, '-' abierta, 'd' borra línea, 'fin' guarda): ").strip()
                except (KeyboardInterrupt, EOFError):
                    print("\nOperación cancelada.")
                    return

                if ans_end.lower() in ("cancelar", "cancel", "descartar", "abort"):
                    print("Edición cancelada.")
                    return
                if ans_end.lower() in ("c", "fin", "ok", "listo", "guardar", "salir", "q"):
                    new_body_lines.append(diary.format_time_range(final_start, old_end))
                    new_body_lines.extend(body_lines[l_idx:])
                    finish_early = True
                    break
                if ans_end.lower() == "d":
                    final_end = "DELETE"
                    break
                if ans_end == "-":
                    final_end = None
                    break
                if not ans_end:
                    final_end = old_end
                    break
                if _is_valid_time(ans_end):
                    final_end = ans_end
                    break
                print(yellow("    Formato inválido. Usa HH:MM (ej. 17:00) o '-' para abierta."))

            if finish_early:
                break

            if final_end == "DELETE":
                print(dim(f"    (Línea {l_idx} eliminada)"))
                continue

            new_body_lines.append(diary.format_time_range(final_start, final_end))
        else:
            print(f"\n  Línea {l_idx}:")
            try:
                ans_text = input(f"    Texto [{line}] (Enter mantiene, 'd' borra línea, 'fin' guarda): ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nOperación cancelada.")
                return

            if ans_text.lower() in ("cancelar", "cancel", "descartar", "abort"):
                print("Edición cancelada.")
                return
            if ans_text.lower() in ("c", "fin", "ok", "listo", "guardar", "salir", "q"):
                new_body_lines.extend(body_lines[l_idx - 1:])
                finish_early = True
                break
            if ans_text.lower() == "d":
                print(dim(f"    (Línea {l_idx} eliminada)"))
                continue
            if ans_text:
                new_body_lines.append(ans_text)
            else:
                new_body_lines.append(line)

    if finish_early:
        _apply_changes()
        return

    # 4. Añadir nueva línea (opcional)
    print()
    try:
        ans_add = input("¿Añadir nueva línea (tiempo, nota, ajuste)? (Enter omite/termina): ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nOperación cancelada.")
        return

    if ans_add.lower() in ("cancelar", "cancel", "descartar", "abort"):
        print("Edición cancelada.")
        return
    if ans_add and ans_add.lower() not in ("c", "fin", "ok", "listo", "guardar", "salir", "q"):
        new_body_lines.append(ans_add)

    # 5. Guardar cambios
    _apply_changes()


def interactive_edit(fecha_param: Optional[str] = None) -> Optional[str]:
    today_str = datetime.now().strftime("%Y-%m-%d")
    if fecha_param:
        fecha_str = fecha_param
    else:
        try:
            prompt_date = input(f"Fecha a editar [YYYY-MM-DD] (Enter para hoy: {today_str}, c para cancelar): ").strip()
        except (KeyboardInterrupt, EOFError):
            return "Operación cancelada."
        if prompt_date.lower() in ("c", "cancel", "cancelar"):
            return "Operación cancelada."
        fecha_str = prompt_date if prompt_date else today_str

    try:
        when = datetime.strptime(fecha_str, "%Y-%m-%d")
    except ValueError:
        return yellow("Formato de fecha no válido. Debe ser YYYY-MM-DD.")

    vault = get_vault_path()
    path = _today_file(vault, when)
    if not path.exists():
        return yellow(f"No existe el fichero para {fecha_str} ({path}).")

    while True:
        lines = diary.read_lines(path)
        blocks = diary.find_blocks(lines)
        if not blocks:
            return yellow(f"El fichero de {fecha_str} está vacío.")

        header = f"--- Entradas de {fecha_str} ({path.name}) ---"
        print("\n" + bold(header))
        for idx, b in enumerate(blocks, 1):
            url_str = f" {dim('(' + b.url + ')')}" if b.url else ""
            print(f"  {bold(f'[{idx}]')} {b.name}{url_str}")
            for line in b.lines[1:]:
                print(f"      {dim(line)}")
        print()
        print(f"  {bold('[e]')} Abrir fichero en editor de texto ($EDITOR)")
        print(f"  {bold('[c]')} Volver al menú principal")
        print(bold("-" * len(header)))

        try:
            choice = input("\nSelecciona el número de entrada a editar (o 'd <núm>' para borrar, 'c' volver): ").strip()
        except (KeyboardInterrupt, EOFError):
            return "Operación cancelada."

        if not choice or choice.lower() in ("c", "cancel", "cancelar", "0", "volver", "q", "exit"):
            return "✓ Edición finalizada."

        if choice.lower() == "e":
            _open_in_editor(path)
            if fecha_str == today_str:
                _refresh_state_from_file(path)
            continue

        lower_choice = choice.lower()
        if (
            lower_choice.startswith("d ")
            or lower_choice.startswith("del ")
            or lower_choice.startswith("borrar ")
            or (lower_choice.startswith("d") and lower_choice[1:].strip().isdigit())
        ):
            parts = lower_choice.split()
            del_str = parts[1] if len(parts) > 1 else lower_choice[1:].strip()
            if del_str.isdigit():
                del_idx = int(del_str) - 1
                if 0 <= del_idx < len(blocks):
                    del_block = blocks[del_idx]
                    try:
                        conf = input(f"¿Seguro que deseas eliminar por completo la tarea '{del_block.name}'? [s/N]: ").strip().lower()
                    except (KeyboardInterrupt, EOFError):
                        continue
                    if conf in ("s", "si", "y", "yes"):
                        new_lines = diary.delete_block(lines, del_block)
                        diary.write_lines(path, new_lines)
                        print(green(f"✓ Tarea '{del_block.name}' eliminada."))
                        if fecha_str == today_str:
                            _refresh_state_from_file(path)
                    else:
                        print("Eliminación cancelada.")
                    continue
                else:
                    print(yellow("Número de entrada no válido."))
                    continue

        if not choice.isdigit():
            print(yellow("Opción no válida. Introduce un número de entrada, 'd <núm>' o 'e'."))
            continue

        block_idx = int(choice) - 1
        if not (0 <= block_idx < len(blocks)):
            print(yellow("Número de entrada no válido."))
            continue

        _interactive_edit_block(path, block_idx, fecha_str == today_str)


def interactive_config() -> Optional[str]:
    vault = get_vault_path()
    print(f"Vault actual: {bold(str(vault))}")
    try:
        cambiar = input("¿Deseas cambiar la ruta del vault? [s/N]: ").strip().lower()
        if cambiar not in ("s", "si", "y", "yes"):
            return "Configuración sin cambios."

        nueva = input("Nueva ruta del vault [c para cancelar]: ").strip()
        if not nueva or nueva.lower() in ("c", "cancel", "cancelar"):
            return "Operación cancelada."

        path = Path(nueva).expanduser().resolve()
        if not path.exists():
            crear = input(f"La ruta '{path}' no existe. ¿Deseas crearla? [S/n]: ").strip().lower()
            if crear in ("", "s", "si", "y", "yes"):
                path.mkdir(parents=True, exist_ok=True)
    except (KeyboardInterrupt, EOFError):
        return "Operación cancelada."

    do_config_set_vault(path)
    return green(f"✓ Vault configurado: {path}")


def run_interactive() -> None:
    hist_file = _get_hist_file()
    if HAVE_READLINE:
        if hist_file.exists():
            try:
                readline.read_history_file(str(hist_file))
            except Exception:
                pass
        readline.set_history_length(1000)

    last_result: Optional[str] = None

    try:
        while True:
            try:
                print_dashboard(result_content=last_result, clear=True)
                if HAVE_READLINE and sys.stdin.isatty():
                    configure_readline()
                    readline.set_completer(InteractiveCompleter(COMMANDS).complete)

                line = input(cyan("parte> ")).strip()
            except KeyboardInterrupt:
                last_result = dim("(Usa 0, 'q' o Ctrl+D para salir)")
                continue
            except EOFError:
                print("\n¡Hasta luego!")
                break

            if not line:
                last_result = f"Dashboard actualizado a las {datetime.now().strftime('%H:%M:%S')}."
                continue

            if line.lower() in ("0", "q", "quit", "exit", "salir"):
                print("¡Hasta luego!")
                break

            if line.lower() in ("?", "help", "ayuda", "menu"):
                last_result = format_help()
                continue

            if line.lower() in ("clear", "cls"):
                last_result = None
                continue

            if line in ("1", "start"):
                last_result = interactive_start() or last_result
            elif line in ("2", "stop"):
                last_result = interactive_stop() or last_result
            elif line in ("3", "note"):
                last_result = interactive_note() or last_result
            elif line in ("4", "interrupt"):
                last_result = interactive_interrupt() or last_result
            elif line in ("5", "log"):
                last_result = interactive_log() or last_result
            elif line in ("6", "show"):
                last_result = interactive_show() or last_result
            elif line in ("7", "status", "tarea"):
                buf = io.StringIO()
                with redirect_stdout(buf), redirect_stderr(buf):
                    do_status()
                last_result = buf.getvalue().strip() or "Sin trabajo abierto actualmente."
            elif line in ("8", "edit", "editar"):
                last_result = interactive_edit() or "✓ Edición finalizada."
            elif line in ("9", "r", "review", "repasar", "repaso"):
                last_result = interactive_review() or "✓ Repaso finalizado."
            elif line in ("10", "config"):
                last_result = interactive_config() or "Configuración finalizada."
            else:
                try:
                    parts = shlex.split(line)
                except ValueError as e:
                    last_result = yellow(f"Error al analizar el comando: {e}")
                    continue

                if parts[0].lower() in (
                    "start", "stop", "status", "note", "interrupt", "log",
                    "show", "edit", "editar", "review", "repasar", "repaso",
                    "config", "completion"
                ):
                    is_interactive_dispatch = (
                        parts[0].lower() in ("review", "repasar", "repaso")
                        and "--todo" not in parts
                        and "--all" not in parts
                    ) or (
                        parts[0].lower() in ("edit", "editar")
                        and "-e" not in parts
                        and "--editor" not in parts
                    )
                    if is_interactive_dispatch:
                        dispatch_command(parts)
                        last_result = "✓ Operación completada."
                    else:
                        buf = io.StringIO()
                        with redirect_stdout(buf), redirect_stderr(buf):
                            dispatch_command(parts)
                        last_result = buf.getvalue().strip() or "✓ Comando ejecutado."
                else:
                    last_result = yellow(f"Opción no reconocida: '{line}'. Escribe un número [1-10], un comando, o '?' para ver el menú.")

    finally:
        if HAVE_READLINE:
            try:
                hist_file.parent.mkdir(parents=True, exist_ok=True)
                readline.write_history_file(str(hist_file))
            except Exception:
                pass
