"""Módulo de sesión interactiva para el CLI parte-diario."""
from __future__ import annotations

import os
import shlex
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from . import diary, state
from .cli import (
    _today_file,
    dispatch_command,
    do_config_set_vault,
    do_interrupt,
    do_log,
    do_note,
    do_start,
    do_status,
    do_stop,
    get_status_info,
    get_vault_path,
)

HIST_FILE = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "parte-diario" / "history"

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
            elif first_cmd == "show":
                matches = [opt for opt in ["--fecha"] if opt.lower().startswith(text.lower())]
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


def print_banner() -> None:
    vault = get_vault_path()
    status_line = format_status_line()
    width = 70
    print("=" * width)
    print(bold("                     PARTE DIARIO - MODO INTERACTIVO").center(width))
    print("=" * width)
    print(f" Vault:  {dim(str(vault))}")
    print(f" Estado: {status_line}")
    print("-" * width)
    print(f" {bold('[1]')} Iniciar / reanudar tarea       {bold('[5]')} Anotar minutos sueltos (log)")
    print(f" {bold('[2]')} Parar tarea abierta (stop)     {bold('[6]')} Ver diario de hoy / fecha")
    print(f" {bold('[3]')} Añadir nota (note)             {bold('[7]')} Ver estado detallado")
    print(f" {bold('[4]')} Registrar interrupción         {bold('[8]')} Configurar vault")
    print()
    print(f" {bold('[0]')} Salir (q / exit)               {bold('[?]')} Ayuda / Mostrar menú")
    print("=" * width)


def print_status_bar() -> None:
    print("-" * 70)
    print(f" Estado: {format_status_line()}")
    print(dim(" Opciones: [1] Iniciar  [2] Parar  [3] Nota  [4] Interrumpir  [5] Minutos  [6] Ver  [7] Estado  [8] Config  [0] Salir"))


def get_today_tasks() -> List[Tuple[str, Optional[str]]]:
    vault = get_vault_path()
    today_file = _today_file(vault)
    lines = diary.read_lines(today_file)
    return diary.get_blocks_info(lines)


def interactive_start() -> None:
    open_task = state.load()
    if open_task:
        print(yellow(f"Aviso: La tarea '{open_task.name}' está abierta. Se cerrará automáticamente."))

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
        print("\nOperación cancelada.")
        return

    if not choice or choice.lower() in ("c", "cancel", "cancelar"):
        print("Operación cancelada.")
        return

    selected_name = choice
    existing_url = None

    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(tasks_info):
            selected_name, existing_url = tasks_info[idx]
        else:
            print(yellow("Número de tarea no válido."))
            return
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
        print("\nOperación cancelada.")
        return

    do_start(selected_name, final_url)


def interactive_stop() -> None:
    open_task = state.load()
    if open_task is None:
        print(yellow("No hay ningún trabajo abierto para parar."))
        return

    try:
        confirm = input(f"¿Cerrar '{bold(open_task.name)}' iniciada a las {open_task.start_time}? [S/n]: ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print("\nOperación cancelada.")
        return

    if confirm in ("", "s", "si", "y", "yes"):
        do_stop()
    else:
        print("Operación cancelada. La tarea sigue abierta.")


def interactive_note() -> None:
    open_task = state.load()
    loose = False

    if open_task is not None:
        print(f"Tarea abierta actual: {bold(open_task.name)}")
        try:
            opc = input(f"¿Asociar nota a '{open_task.name}'? [S/n] (o 'n' para nota suelta, 'c' para cancelar): ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\nOperación cancelada.")
            return

        if opc in ("c", "cancel", "cancelar"):
            print("Operación cancelada.")
            return
        if opc in ("n", "no"):
            loose = True

    prompt = "Texto de la nota suelta [c para cancelar]: " if loose or open_task is None else f"Nota para '{open_task.name}' [c para cancelar]: "
    try:
        texto = input(prompt).strip()
    except (KeyboardInterrupt, EOFError):
        print("\nOperación cancelada.")
        return

    if not texto or texto.lower() in ("c", "cancel", "cancelar"):
        print("Operación cancelada.")
        return

    do_note(texto, loose=loose)


def interactive_interrupt() -> None:
    open_task = state.load()
    if open_task is None:
        print(yellow("No hay ninguna tarea abierta a la que restar tiempo."))
        print(dim("Sugerencia: Usa la opción [5] (Anotar minutos sueltos) para registrar tiempo independiente."))
        return

    print(f"Tarea abierta actual: {bold(open_task.name)} (se le restará el tiempo)")
    try:
        nombre = input("Motivo o tarea de la interrupción [c para cancelar]: ").strip()
        if not nombre or nombre.lower() in ("c", "cancel", "cancelar"):
            print("Operación cancelada.")
            return

        minutos_str = input("Minutos de duración (ej. 15): ").strip()
        try:
            minutos = int(minutos_str)
            if minutos <= 0:
                raise ValueError()
        except ValueError:
            print(yellow("Los minutos deben ser un número entero positivo."))
            return

        url = input("URL opcional para la interrupción (Enter para omitir): ").strip() or None
    except (KeyboardInterrupt, EOFError):
        print("\nOperación cancelada.")
        return

    do_interrupt(nombre, minutos, url=url)


def interactive_log() -> None:
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
            print("Operación cancelada.")
            return

        selected_name = choice
        existing_url = None
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(tasks_info):
                selected_name, existing_url = tasks_info[idx]
            else:
                print(yellow("Número de tarea no válido."))
                return
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
            print(yellow("Los minutos deben ser un número entero positivo."))
            return

        tipo = input("¿Sumar (+) o Restar (-) minutos? [+]: ").strip()
        resta = (tipo == "-")

        if existing_url:
            url = existing_url
        else:
            url = input("URL opcional (Enter para omitir): ").strip() or None
    except (KeyboardInterrupt, EOFError):
        print("\nOperación cancelada.")
        return

    do_log(selected_name, minutos, resta=resta, url=url)


def interactive_show() -> None:
    today_str = datetime.now().strftime("%Y-%m-%d")
    try:
        fecha = input(f"Fecha a consultar [YYYY-MM-DD] (Enter para hoy: {today_str}, c para cancelar): ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nOperación cancelada.")
        return

    if fecha.lower() in ("c", "cancel", "cancelar"):
        print("Operación cancelada.")
        return

    fecha_consultar = fecha if fecha else today_str
    try:
        when = datetime.strptime(fecha_consultar, "%Y-%m-%d")
    except ValueError:
        print(yellow("Formato de fecha no válido. Debe ser YYYY-MM-DD."))
        return

    vault = get_vault_path()
    path = _today_file(vault, when)
    if not path.exists():
        print(yellow(f"\nNo existe el fichero para {fecha_consultar} ({path})."))
        return

    content = path.read_text(encoding="utf-8").strip()
    header = f"--- Diario: {fecha_consultar} ({path.name}) ---"
    print("\n" + bold(header))
    if not content:
        print(dim("(El fichero existe pero está vacío)"))
    else:
        print(content)
    print(bold("-" * len(header)) + "\n")


def interactive_config() -> None:
    vault = get_vault_path()
    print(f"Vault actual: {bold(str(vault))}")
    try:
        cambiar = input("¿Deseas cambiar la ruta del vault? [s/N]: ").strip().lower()
        if cambiar not in ("s", "si", "y", "yes"):
            return

        nueva = input("Nueva ruta del vault [c para cancelar]: ").strip()
        if not nueva or nueva.lower() in ("c", "cancel", "cancelar"):
            print("Operación cancelada.")
            return

        path = Path(nueva).expanduser().resolve()
        if not path.exists():
            crear = input(f"La ruta '{path}' no existe. ¿Deseas crearla? [S/n]: ").strip().lower()
            if crear in ("", "s", "si", "y", "yes"):
                path.mkdir(parents=True, exist_ok=True)
    except (KeyboardInterrupt, EOFError):
        print("\nOperación cancelada.")
        return

    do_config_set_vault(path)
    print(green(f"✓ Vault configurado: {path}"))


def run_interactive() -> None:
    if HAVE_READLINE:
        if HIST_FILE.exists():
            try:
                readline.read_history_file(str(HIST_FILE))
            except Exception:
                pass
        readline.set_history_length(1000)

    print_banner()

    try:
        while True:
            try:
                print_status_bar()
                if HAVE_READLINE and sys.stdin.isatty():
                    configure_readline()
                    readline.set_completer(InteractiveCompleter(COMMANDS).complete)

                line = input(cyan("parte> ")).strip()
            except KeyboardInterrupt:
                print(dim("\n(Usa 0, 'q' o Ctrl+D para salir)"))
                continue
            except EOFError:
                print("\n¡Hasta luego!")
                break

            if not line:
                continue

            if line.lower() in ("0", "q", "quit", "exit", "salir"):
                print("¡Hasta luego!")
                break

            if line.lower() in ("?", "help", "ayuda", "menu"):
                print_banner()
                continue

            if line.lower() in ("clear", "cls"):
                print("\033[H\033[2J", end="")
                print_banner()
                continue

            if line in ("1", "start"):
                interactive_start()
            elif line in ("2", "stop"):
                interactive_stop()
            elif line in ("3", "note"):
                interactive_note()
            elif line in ("4", "interrupt"):
                interactive_interrupt()
            elif line in ("5", "log"):
                interactive_log()
            elif line in ("6", "show"):
                interactive_show()
            elif line in ("7", "status"):
                do_status()
            elif line in ("8", "config"):
                interactive_config()
            else:
                try:
                    parts = shlex.split(line)
                except ValueError as e:
                    print(yellow(f"Error al analizar el comando: {e}"))
                    continue

                if parts[0].lower() in ("start", "stop", "status", "note", "interrupt", "log", "show", "config", "completion"):
                    dispatch_command(parts)
                else:
                    print(yellow(f"Opción no reconocida: '{line}'. Escribe un número [1-8], un comando, o '?' para ver el menú."))

    finally:
        if HAVE_READLINE:
            try:
                HIST_FILE.parent.mkdir(parents=True, exist_ok=True)
                readline.write_history_file(str(HIST_FILE))
            except Exception:
                pass
