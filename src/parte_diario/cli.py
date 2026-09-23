"""CLI ``parte``: gestiona el diario profesional (inicio/fin de trabajos y notas)."""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Type

from . import diary, state
from .config import get_vault_path, set_vault_path


def _today_file(vault: Path, when: Optional[datetime] = None) -> Path:
    when = when or datetime.now()
    return vault / f"{when:%Y-%m-%d}.md"


def _close_current(end_time: Optional[str] = None, verbose: bool = True) -> Optional[dict]:
    """Cierra el trabajo actualmente abierto, si lo hay. No falla si no hay ninguno."""
    open_task = state.load()
    vault = get_vault_path()
    now = datetime.now()
    close_time = end_time or f"{now:%H:%M}"

    if open_task is None:
        today_file = _today_file(vault, now)
        if today_file.exists():
            lines = diary.read_lines(today_file)
            open_info = diary.find_open_task_in_lines(lines)
            if open_info is not None:
                task_name, start_time = open_info
                new_lines = diary.close_open_line(lines, start_time, prefer_block_name=task_name, end_time=close_time)
                if new_lines is not None:
                    diary.write_lines(today_file, new_lines)
                    state.clear()
                    if verbose:
                        print(f"Cerrado: {task_name} ({start_time} - {close_time})")
                    return {
                        "name": task_name,
                        "url": None,
                        "start_time": start_time,
                        "end_time": close_time,
                    }
        return None

    task_file = Path(open_task.file)
    lines = diary.read_lines(task_file)
    new_lines = diary.close_open_line(lines, open_task.start_time, prefer_block_name=open_task.name, end_time=close_time)

    if new_lines is None:
        print(
            f"Aviso: no se encontró la línea abierta de '{open_task.name}' "
            f"({open_task.start_time} - ) en {task_file}. "
            "¿Se editó el fichero a mano? El estado se ha limpiado igualmente.",
            file=sys.stderr,
        )
        state.clear()
        return None

    diary.write_lines(task_file, new_lines)
    state.clear()
    if verbose:
        print(f"Cerrado: {open_task.name} ({open_task.start_time} - {close_time})")
    return {
        "name": open_task.name,
        "url": open_task.url,
        "start_time": open_task.start_time,
        "end_time": close_time,
    }


def do_start(
    nombre: str,
    url: Optional[str] = None,
    start_time: Optional[str] = None,
    use_latest_time: bool = False,
    verbose: bool = True,
) -> bool:
    vault = get_vault_path()
    now = datetime.now()
    now_str = f"{now:%H:%M}"

    today_file = _today_file(vault, now)
    lines = diary.read_lines(today_file) if today_file.exists() else []

    if use_latest_time:
        highest = diary.find_highest_time_in_lines(lines)
        chosen_start = highest or now_str
    elif start_time:
        chosen_start = start_time
    else:
        chosen_start = now_str

    _close_current(end_time=chosen_start, verbose=verbose)

    today_file = _today_file(vault, now)
    lines = diary.read_lines(today_file) if today_file.exists() else []
    open_line = f"{chosen_start} - "
    new_lines = diary.add_or_create_block_line(lines, nombre, url, open_line)
    diary.write_lines(today_file, new_lines)

    # Si no se pasó URL explícita pero el bloque ya tenía URL en el fichero, conservarla
    if not url:
        block = diary.find_block_by_name(new_lines, nombre)
        if block:
            m = diary.HEADER_LINK_RE.match(block.header)
            if m:
                url = m.group("url")

    state.save(
        state.OpenTask(
            name=nombre,
            url=url,
            file=str(today_file),
            date=f"{now:%Y-%m-%d}",
            start_time=chosen_start,
        )
    )

    if verbose:
        destino = f" ({url})" if url else ""
        print(f"Iniciado: {nombre}{destino} a las {chosen_start}")
    return True


def do_stop(verbose: bool = True) -> bool:
    open_task = state.load()
    if open_task is None:
        if verbose:
            print("No hay ningún trabajo abierto.", file=sys.stderr)
        return False
    _close_current(verbose=verbose)
    return True


def get_status_info() -> Optional[dict]:
    open_task = state.load()
    if open_task is None:
        vault = get_vault_path()
        today_file = _today_file(vault)
        if today_file.exists():
            lines = diary.read_lines(today_file)
            open_info = diary.find_open_task_in_lines(lines)
            if open_info is not None:
                task_name, start_time = open_info
                block = diary.find_block_by_name(lines, task_name)
                url = None
                if block:
                    m = diary.HEADER_LINK_RE.match(block.header)
                    if m:
                        url = m.group("url")
                now = datetime.now()
                open_task = state.OpenTask(
                    name=task_name,
                    url=url,
                    file=str(today_file),
                    date=f"{now:%Y-%m-%d}",
                    start_time=start_time,
                )
                state.save(open_task)

    if open_task is None:
        return None

    try:
        start_dt = datetime.strptime(f"{open_task.date} {open_task.start_time}", "%Y-%m-%d %H:%M")
        elapsed = datetime.now() - start_dt
        minutes = int(elapsed.total_seconds() // 60)
        horas, mins = divmod(max(minutes, 0), 60)
    except Exception:
        horas, mins = 0, 0

    return {
        "name": open_task.name,
        "url": open_task.url,
        "date": open_task.date,
        "start_time": open_task.start_time,
        "hours": horas,
        "minutes": mins,
        "file": open_task.file,
    }


def do_status() -> None:
    info = get_status_info()
    if info is None:
        print("No hay ningún trabajo abierto.")
        return

    destino = f" ({info['url']})" if info["url"] else ""
    print(f"Abierto: {info['name']}{destino}")
    print(f"Inicio: {info['date']} {info['start_time']}")
    print(f"Duración: {info['hours']}h {info['minutes']:02d}m")
    print(f"Fichero: {info['file']}")


def do_note(texto: str, loose: bool = False, verbose: bool = True) -> bool:
    vault = get_vault_path()
    text = texto.strip()
    if not text:
        if verbose:
            print("La nota no puede estar vacía.", file=sys.stderr)
        return False

    open_task = None if loose else state.load()

    if open_task is not None:
        task_file = Path(open_task.file)
        lines = diary.read_lines(task_file)
        new_lines = diary.add_note_to_block(lines, open_task.name, text)
        if new_lines is not None:
            diary.write_lines(task_file, new_lines)
            if verbose:
                print(f"Nota añadida a '{open_task.name}': {text}")
            return True
        if verbose:
            print(
                f"Aviso: no se encontró el bloque de '{open_task.name}'; "
                "se guarda como nota suelta.",
                file=sys.stderr,
            )

    today_file = _today_file(vault)
    lines = diary.read_lines(today_file)
    new_lines = diary.append_free_block(lines, [text])
    diary.write_lines(today_file, new_lines)
    if verbose:
        print(f"Nota suelta añadida: {text}")
    return True


def do_log(nombre: str, minutos: int, resta: bool = False, url: Optional[str] = None, verbose: bool = True) -> bool:
    vault = get_vault_path()
    today_file = _today_file(vault)
    lines = diary.read_lines(today_file)

    minutos = abs(minutos)
    signo = "-" if resta else "+"
    ajuste = f"{signo}{minutos}"
    new_lines = diary.add_or_create_block_line(lines, nombre, url, ajuste)
    diary.write_lines(today_file, new_lines)
    if verbose:
        print(f"Anotado: {nombre} {ajuste} minutos")
    return True


def do_interrupt(nombre: str, minutos: int, url: Optional[str] = None, verbose: bool = True) -> bool:
    vault = get_vault_path()
    open_task = state.load()
    if open_task is None:
        if verbose:
            print("No hay ninguna tarea abierta a la que restar tiempo.", file=sys.stderr)
        return False

    minutos = abs(minutos)
    today_file = _today_file(vault)
    task_file = Path(open_task.file)

    if task_file == today_file:
        lines = diary.read_lines(today_file)
        block = diary.find_block_by_name(lines, open_task.name)
        if block is None:
            if verbose:
                print(
                    f"Aviso: no se encontró el bloque de '{open_task.name}'; "
                    "no se le resta tiempo, solo se anota la interrupción.",
                    file=sys.stderr,
                )
        else:
            lines = diary.append_line_to_block(lines, block, f"-{minutos}")
        lines = diary.add_or_create_block_line(lines, nombre, url, f"+{minutos}")
        diary.write_lines(today_file, lines)
    else:
        # La tarea abierta viene de un día anterior (p. ej. sigue abierta desde ayer).
        task_lines = diary.read_lines(task_file)
        block = diary.find_block_by_name(task_lines, open_task.name)
        if block is None:
            if verbose:
                print(
                    f"Aviso: no se encontró el bloque de '{open_task.name}' en {task_file}; "
                    "no se le resta tiempo, solo se anota la interrupción.",
                    file=sys.stderr,
                )
        else:
            task_lines = diary.append_line_to_block(task_lines, block, f"-{minutos}")
            diary.write_lines(task_file, task_lines)

        today_lines = diary.read_lines(today_file)
        today_lines = diary.add_or_create_block_line(today_lines, nombre, url, f"+{minutos}")
        diary.write_lines(today_file, today_lines)

    if verbose:
        print(f"Interrupción: -{minutos} en '{open_task.name}' (sigue abierta), +{minutos} en '{nombre}'")
    return True


def do_show(fecha: Optional[str] = None, verbose: bool = True) -> Optional[str]:
    vault = get_vault_path()
    if fecha:
        try:
            when = datetime.strptime(fecha, "%Y-%m-%d")
        except ValueError:
            if verbose:
                print(f"Formato de fecha no válido: '{fecha}'. Se espera YYYY-MM-DD.", file=sys.stderr)
            return None
    else:
        when = datetime.now()
    path = _today_file(vault, when)
    if not path.exists():
        if verbose:
            print(f"No existe {path}", file=sys.stderr)
        return None
    content = path.read_text(encoding="utf-8")
    if verbose:
        print(content)
    return content


def _can_color() -> bool:
    return sys.stdout.isatty() and "NO_COLOR" not in os.environ and os.environ.get("TERM") != "dumb"


def format_navigable_url(url: str, text: Optional[str] = None, color: Optional[bool] = None) -> str:
    """Devuelve la URL formateada como hipervínculo navegable OSC 8 para la terminal."""
    display_text = text if text is not None else url
    use_color = _can_color() if color is None else color
    if not use_color:
        return display_text
    hyperlink = f"\033]8;;{url}\033\\{display_text}\033]8;;\033\\"
    return f"\033[4;36m{hyperlink}\033[0m"


def format_review_item(
    item: diary.TaskReviewItem,
    color: Optional[bool] = None,
    show_names: bool = False,
) -> str:
    """Formatea una tarea para el repaso: URL navegable si la tiene, o nombre si no."""
    use_color = _can_color() if color is None else color
    if item.url:
        target = format_navigable_url(item.url, color=use_color)
        if show_names and item.name and item.name != item.url:
            name_part = f"\033[90m({item.name})\033[0m" if use_color else f"({item.name})"
            target = f"{target} {name_part}"
    else:
        target = f"\033[1m{item.name}\033[0m" if use_color else item.name

    open_str = " (en curso)" if item.is_open else ""
    if abs(item.minutes) >= 60:
        horas, rem = divmod(abs(item.minutes), 60)
        signo = "-" if item.minutes < 0 else ""
        dur = f" ({signo}{horas}h {rem:02d}m{open_str})"
    elif item.is_open:
        dur = " (en curso)"
    else:
        dur = ""

    return f"{target}: {item.minutes} minutos{dur}"


def do_review(
    fecha: Optional[str] = None,
    verbose: bool = True,
    show_names: bool = False,
    color: Optional[bool] = None,
    iterative: Optional[bool] = None,
) -> Optional[dict]:
    vault = get_vault_path()
    if fecha:
        try:
            when = datetime.strptime(fecha, "%Y-%m-%d")
        except ValueError:
            if verbose:
                print(f"Formato de fecha no válido: '{fecha}'. Se espera YYYY-MM-DD.", file=sys.stderr)
            return None
    else:
        when = datetime.now()

    fecha_str = f"{when:%Y-%m-%d}"
    path = _today_file(vault, when)
    if not path.exists():
        if verbose:
            print(f"No existe {path}", file=sys.stderr)
        return None

    lines = diary.read_lines(path)
    items = diary.get_tasks_summary(lines, file_date=fecha_str)
    total_minutes = sum(item.minutes for item in items)
    use_color = _can_color() if color is None else color

    if iterative is None:
        do_iterate = sys.stdin.isatty() and sys.stdout.isatty()
    else:
        do_iterate = iterative

    if verbose:
        if not items:
            print(f"No hay tareas registradas para el {fecha_str}.")
        else:
            total_items = len(items)
            stopped_early = False

            for idx, item in enumerate(items, 1):
                item_str = format_review_item(item, color=use_color, show_names=show_names)
                if do_iterate:
                    idx_prefix = f"\033[1m[{idx}/{total_items}]\033[0m " if use_color else f"[{idx}/{total_items}] "
                    print(f"\n{idx_prefix}{item_str}" if idx > 1 else f"{idx_prefix}{item_str}")
                    if idx < total_items:
                        prompt = "Mostrar siguiente [Enter] o salir [q]: "
                        while True:
                            try:
                                ans = input(prompt).strip().lower()
                            except (KeyboardInterrupt, EOFError):
                                print("\nRepaso finalizado.")
                                stopped_early = True
                                break

                            if ans in ("", "s", "si", "sí", "y", "yes", "sig", "siguiente"):
                                break
                            elif ans in ("q", "quit", "exit", "salir", "c", "cancel", "cancelar"):
                                stopped_early = True
                                break
                            else:
                                print("Opción no válida. Pulsa [Enter] para mostrar el siguiente o [q] para salir.")
                        if stopped_early:
                            break
                else:
                    print(item_str)

            total_h, total_rem = divmod(abs(total_minutes), 60)
            total_sign = "-" if total_minutes < 0 else ""
            total_dur = f" ({total_sign}{total_h}h {total_rem:02d}m)" if total_h > 0 else ""
            if stopped_early:
                print(f"\n(Repaso interrumpido. Total del día: {total_minutes} minutos{total_dur})")
            else:
                print(f"\nTotal: {total_minutes} minutos{total_dur}")

    return {
        "date": fecha_str,
        "file": str(path),
        "tasks": items,
        "total_minutes": total_minutes,
    }


def do_config_set_vault(ruta: Path | str) -> Path:
    path = Path(ruta).expanduser().resolve()
    set_vault_path(path)
    return path


def cmd_start(args: argparse.Namespace) -> None:
    do_start(
        args.nombre,
        url=args.url,
        start_time=args.hora,
        use_latest_time=args.latest,
    )


def cmd_stop(args: argparse.Namespace) -> None:
    if not do_stop():
        raise SystemExit(1)


def cmd_status(args: argparse.Namespace) -> None:
    do_status()


def cmd_note(args: argparse.Namespace) -> None:
    text = " ".join(args.texto).strip()
    if not do_note(text, loose=args.loose):
        raise SystemExit(1)


def cmd_log(args: argparse.Namespace) -> None:
    resta = args.resta or args.minutos < 0
    do_log(args.nombre, args.minutos, resta=resta, url=args.url)


def cmd_interrupt(args: argparse.Namespace) -> None:
    if not do_interrupt(args.nombre, args.minutos, url=args.url):
        raise SystemExit(1)


def cmd_config(args: argparse.Namespace) -> None:
    if args.config_action == "show":
        print(f"Vault actual: {get_vault_path()}")
    elif args.config_action == "set-vault":
        path = do_config_set_vault(args.ruta)
        print(f"Vault configurado: {path}")


def cmd_show(args: argparse.Namespace) -> None:
    content = do_show(args.fecha)
    if content is None:
        raise SystemExit(1)


def cmd_review(args: argparse.Namespace) -> None:
    iterative = False if args.todo else (True if args.iterativo else None)
    res = do_review(
        args.fecha,
        show_names=getattr(args, "nombres", False),
        iterative=iterative,
    )
    if res is None:
        raise SystemExit(1)


def cmd_edit(args: argparse.Namespace) -> None:
    from .interactive import _open_in_editor, _refresh_state_from_file, interactive_edit

    if args.editor:
        when = datetime.strptime(args.fecha, "%Y-%m-%d") if args.fecha else datetime.now()
        path = _today_file(get_vault_path(), when)
        if not path.exists():
            print(f"No existe {path}", file=sys.stderr)
            raise SystemExit(1)
        _open_in_editor(path)
        if not args.fecha or args.fecha == datetime.now().strftime("%Y-%m-%d"):
            _refresh_state_from_file(path)
    else:
        interactive_edit(fecha_param=args.fecha)


def cmd_completion(args: argparse.Namespace) -> None:
    from . import completion

    shell = args.shell
    if args.install:
        ok, msg = completion.install_completion(shell)
        print(msg)
        if not ok:
            raise SystemExit(1)
    elif shell:
        print(completion.get_completion_script(shell))
    else:
        detected = completion.detect_user_shell()
        print(
            "Autocompletado de comandos para 'parte':\n\n"
            "El autocompletado te permite pulsar la tecla <TAB> al escribir 'parte' para sugerir\n"
            "comandos y argumentos automáticamente en tu terminal.\n"
            "(Nota: no necesitas escribir 'parte completion' para autocompletar tus tareas diarias,\n"
            "solo se usa para configurar la terminal una vez).\n\n"
            f"Tu shell detectada es: {detected}\n\n"
            "Para instalar el autocompletado permanentemente:\n"
            "  parte completion --install\n\n"
            "Para activarlo puntualmente en la terminal actual:\n"
            f"  source <(parte completion {detected})"
        )


def cmd_interactive(args: argparse.Namespace) -> None:
    from .interactive import run_interactive
    run_interactive()


class CLIParserExit(Exception):
    def __init__(self, status: int = 0):
        self.status = status
        super().__init__(f"Exit {status}")


class CLIParserError(Exception):
    pass


class InteractiveParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CLIParserError(message)

    def exit(self, status: int = 0, message: Optional[str] = None) -> None:
        if message:
            print(message)
        raise CLIParserExit(status)


def build_parser(parser_cls: Type[argparse.ArgumentParser] = argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser = parser_cls(prog="parte", description="Gestor del diario profesional / parte de horas")
    parser.add_argument(
        "-i", "--interactive", "--interactivo",
        action="store_true",
        help="Inicia el modo interactivo",
    )
    sub = parser.add_subparsers(dest="comando", required=False)

    p_start = sub.add_parser("start", help="Inicia un trabajo (cierra el que estuviera abierto)")
    p_start.add_argument("nombre", help="Nombre del trabajo")
    p_start.add_argument("--url", help="URL asociada al trabajo (opcional)", default=None)
    p_start.add_argument("--hora", "--time", help="Hora de inicio manual (HH:MM)", default=None)
    p_start.add_argument(
        "--latest", "--ultima", "--desde-ultima",
        action="store_true",
        help="Inicia el tiempo desde la hora más alta registrada en lugar de la del sistema",
    )
    p_start.set_defaults(func=cmd_start)

    p_stop = sub.add_parser("stop", help="Cierra el trabajo abierto sin iniciar otro")
    p_stop.set_defaults(func=cmd_stop)

    p_status = sub.add_parser("status", help="Muestra el trabajo actualmente abierto")
    p_status.set_defaults(func=cmd_status)

    p_note = sub.add_parser("note", help="Añade una nota (al trabajo abierto, o suelta con --loose)")
    p_note.add_argument("texto", nargs="+", help="Texto de la nota")
    p_note.add_argument("--loose", "--suelta", dest="loose", action="store_true", help="Nota suelta, no asociada al trabajo abierto")
    p_note.set_defaults(func=cmd_note)

    p_show = sub.add_parser("show", help="Muestra el contenido del diario de hoy (o de --fecha)")
    p_show.add_argument("--fecha", help="Fecha en formato YYYY-MM-DD", default=None)
    p_show.set_defaults(func=cmd_show)

    p_review = sub.add_parser(
        "review",
        aliases=["repasar", "repaso"],
        help="Repasa el parte del día mostrando URLs o tareas y minutos totales",
    )
    p_review.add_argument("--fecha", help="Fecha en formato YYYY-MM-DD (por defecto: hoy)", default=None)
    p_review.add_argument(
        "--con-nombre", "--nombres",
        dest="nombres",
        action="store_true",
        help="Muestra también el nombre de la tarea si tiene URL asociada",
    )
    p_review.add_argument(
        "--todo", "--all",
        dest="todo",
        action="store_true",
        help="Muestra todas las tareas de golpe sin pausar de una en una",
    )
    p_review.add_argument(
        "--iterativo", "-s", "--step",
        dest="iterativo",
        action="store_true",
        help="Fuerza el modo iterativo de una en una",
    )
    p_review.set_defaults(func=cmd_review)

    p_edit = sub.add_parser(
        "edit",
        help="Edita entradas del diario (nombre, url, horas de inicio/fin, textos, notas)",
    )
    p_edit.add_argument("--fecha", help="Fecha en formato YYYY-MM-DD (por defecto: hoy)", default=None)
    p_edit.add_argument("-e", "--editor", action="store_true", help="Abre directamente el fichero en el editor de texto ($EDITOR)")
    p_edit.set_defaults(func=cmd_edit)

    p_log = sub.add_parser(
        "log",
        help="Anota una tarea usando solo minutos invertidos, sin horas (p.ej. tareas sueltas tipo 'Alondra +15')",
    )
    p_log.add_argument("nombre", help="Nombre de la tarea")
    p_log.add_argument("minutos", type=int, help="Minutos invertidos (número positivo)")
    p_log.add_argument("--url", help="URL asociada (opcional)", default=None)
    p_log.add_argument("--resta", action="store_true", help="Anota los minutos en negativo (-N) en vez de en positivo")
    p_log.set_defaults(func=cmd_log)

    p_interrupt = sub.add_parser(
        "interrupt",
        help=(
            "Registra una interrupción de la tarea abierta (p.ej. una llamada): "
            "resta minutos a la tarea abierta sin cerrarla y se los suma a la tarea interruptora"
        ),
    )
    p_interrupt.add_argument("nombre", help="Nombre de la tarea/motivo de la interrupción")
    p_interrupt.add_argument("minutos", type=int, help="Minutos que ha durado la interrupción")
    p_interrupt.add_argument("--url", help="URL asociada a la interrupción (opcional)", default=None)
    p_interrupt.set_defaults(func=cmd_interrupt)

    p_config = sub.add_parser("config", help="Consulta o fija la ruta del vault del diario")
    config_sub = p_config.add_subparsers(dest="config_action", required=True)
    config_sub.add_parser("show", help="Muestra la ruta del vault en uso").set_defaults(func=cmd_config)
    p_set_vault = config_sub.add_parser("set-vault", help="Fija la ruta del vault de forma persistente")
    p_set_vault.add_argument("ruta", help="Ruta del vault del diario")
    p_set_vault.set_defaults(func=cmd_config)

    p_completion = sub.add_parser(
        "completion",
        help="Genera o instala el script de autocompletado para la shell (Bash o Zsh)",
    )
    p_completion.add_argument(
        "shell",
        nargs="?",
        default=None,
        choices=["bash", "zsh"],
        help="Shell para la que generar el script de autocompletado (por defecto: detecta tu shell)",
    )
    p_completion.add_argument(
        "--install",
        action="store_true",
        help="Instala el autocompletado automáticamente para el usuario actual",
    )
    p_completion.set_defaults(func=cmd_completion)

    p_interactive = sub.add_parser("interactive", help="Inicia el modo interactivo")
    p_interactive.set_defaults(func=cmd_interactive)

    try:
        import argcomplete
        argcomplete.autocomplete(parser)
    except Exception:
        pass

    return parser


def dispatch_command(argv: list[str]) -> bool:
    """Ejecuta un comando en modo interactivo sin terminar el proceso en caso de error."""
    parser = build_parser(parser_cls=InteractiveParser)
    try:
        args = parser.parse_args(argv)
    except CLIParserExit:
        return True
    except CLIParserError as e:
        print(f"Error: {e}")
        return False
    except Exception as e:
        print(f"Error al analizar el comando: {e}")
        return False

    try:
        if hasattr(args, "func"):
            args.func(args)
            return True
        print("Comando no reconocido.")
        return False
    except SystemExit as e:
        return e.code == 0
    except Exception as e:
        print(f"Error al ejecutar comando: {e}")
        return False


def main(argv: Optional[list] = None) -> None:
    raw_args = sys.argv[1:] if argv is None else argv

    # Si no se pasan argumentos, entrar en modo interactivo
    if not raw_args:
        from .interactive import run_interactive
        run_interactive()
        return

    parser = build_parser()
    args = parser.parse_args(raw_args)

    if getattr(args, "interactive", False) or getattr(args, "comando", None) == "interactive":
        from .interactive import run_interactive
        run_interactive()
        return

    if not hasattr(args, "func"):
        from .interactive import run_interactive
        run_interactive()
        return

    args.func(args)


if __name__ == "__main__":
    main()
