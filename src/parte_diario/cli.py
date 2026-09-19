"""CLI ``parte``: gestiona el diario profesional (inicio/fin de trabajos y notas)."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import diary, state
from .config import get_vault_path, set_vault_path


def _today_file(vault: Path, when: Optional[datetime] = None) -> Path:
    when = when or datetime.now()
    return vault / f"{when:%Y-%m-%d}.md"


def _close_current(verbose: bool = True) -> None:
    """Cierra el trabajo actualmente abierto, si lo hay. No falla si no hay ninguno."""
    open_task = state.load()
    if open_task is None:
        return

    task_file = Path(open_task.file)
    lines = diary.read_lines(task_file)
    new_lines = diary.close_open_line(lines, open_task.start_time, prefer_block_name=open_task.name)

    if new_lines is None:
        print(
            f"Aviso: no se encontró la línea abierta de '{open_task.name}' "
            f"({open_task.start_time} - ) en {task_file}. "
            "¿Se editó el fichero a mano? El estado se ha limpiado igualmente.",
            file=sys.stderr,
        )
        state.clear()
        return

    diary.write_lines(task_file, new_lines)
    state.clear()
    if verbose:
        now = datetime.now()
        print(f"Cerrado: {open_task.name} ({open_task.start_time} - {now:%H:%M})")


def cmd_start(args: argparse.Namespace) -> None:
    vault = get_vault_path()
    now = datetime.now()

    _close_current()

    today_file = _today_file(vault, now)
    lines = diary.read_lines(today_file)
    open_line = f"{now:%H:%M} - "
    new_lines = diary.add_or_create_block_line(lines, args.nombre, args.url, open_line)
    diary.write_lines(today_file, new_lines)

    state.save(
        state.OpenTask(
            name=args.nombre,
            url=args.url,
            file=str(today_file),
            date=f"{now:%Y-%m-%d}",
            start_time=f"{now:%H:%M}",
        )
    )

    destino = f" ({args.url})" if args.url else ""
    print(f"Iniciado: {args.nombre}{destino} a las {now:%H:%M}")


def cmd_stop(args: argparse.Namespace) -> None:
    open_task = state.load()
    if open_task is None:
        print("No hay ningún trabajo abierto.", file=sys.stderr)
        raise SystemExit(1)
    _close_current()


def cmd_status(args: argparse.Namespace) -> None:
    open_task = state.load()
    if open_task is None:
        print("No hay ningún trabajo abierto.")
        return

    start_dt = datetime.strptime(f"{open_task.date} {open_task.start_time}", "%Y-%m-%d %H:%M")
    elapsed = datetime.now() - start_dt
    minutes = int(elapsed.total_seconds() // 60)
    horas, mins = divmod(max(minutes, 0), 60)

    destino = f" ({open_task.url})" if open_task.url else ""
    print(f"Abierto: {open_task.name}{destino}")
    print(f"Inicio: {open_task.date} {open_task.start_time}")
    print(f"Duración: {horas}h {mins:02d}m")
    print(f"Fichero: {open_task.file}")


def cmd_note(args: argparse.Namespace) -> None:
    vault = get_vault_path()
    text = " ".join(args.texto).strip()
    if not text:
        print("La nota no puede estar vacía.", file=sys.stderr)
        raise SystemExit(1)

    open_task = None if args.loose else state.load()

    if open_task is not None:
        task_file = Path(open_task.file)
        lines = diary.read_lines(task_file)
        new_lines = diary.add_note_to_block(lines, open_task.name, text)
        if new_lines is not None:
            diary.write_lines(task_file, new_lines)
            print(f"Nota añadida a '{open_task.name}': {text}")
            return
        print(
            f"Aviso: no se encontró el bloque de '{open_task.name}'; "
            "se guarda como nota suelta.",
            file=sys.stderr,
        )

    today_file = _today_file(vault)
    lines = diary.read_lines(today_file)
    new_lines = diary.append_free_block(lines, [text])
    diary.write_lines(today_file, new_lines)
    print(f"Nota suelta añadida: {text}")


def cmd_log(args: argparse.Namespace) -> None:
    """Anota una tarea usando solo minutos invertidos, sin horas de inicio/fin."""
    vault = get_vault_path()
    today_file = _today_file(vault)
    lines = diary.read_lines(today_file)

    minutos = abs(args.minutos)
    resta = args.resta or args.minutos < 0
    signo = "-" if resta else "+"
    ajuste = f"{signo}{minutos}"
    new_lines = diary.add_or_create_block_line(lines, args.nombre, args.url, ajuste)
    diary.write_lines(today_file, new_lines)
    print(f"Anotado: {args.nombre} {ajuste} minutos")


def cmd_interrupt(args: argparse.Namespace) -> None:
    """Registra una interrupción: resta minutos a la tarea abierta (sin cerrarla)
    y se los suma a la tarea que ha causado la interrupción."""
    vault = get_vault_path()
    open_task = state.load()
    if open_task is None:
        print("No hay ninguna tarea abierta a la que restar tiempo.", file=sys.stderr)
        raise SystemExit(1)

    minutos = abs(args.minutos)
    today_file = _today_file(vault)
    task_file = Path(open_task.file)

    if task_file == today_file:
        lines = diary.read_lines(today_file)
        block = diary.find_block_by_name(lines, open_task.name)
        if block is None:
            print(
                f"Aviso: no se encontró el bloque de '{open_task.name}'; "
                "no se le resta tiempo, solo se anota la interrupción.",
                file=sys.stderr,
            )
        else:
            lines = diary.append_line_to_block(lines, block, f"-{minutos}")
        lines = diary.add_or_create_block_line(lines, args.nombre, args.url, f"+{minutos}")
        diary.write_lines(today_file, lines)
    else:
        # La tarea abierta viene de un día anterior (p. ej. sigue abierta desde ayer).
        task_lines = diary.read_lines(task_file)
        block = diary.find_block_by_name(task_lines, open_task.name)
        if block is None:
            print(
                f"Aviso: no se encontró el bloque de '{open_task.name}' en {task_file}; "
                "no se le resta tiempo, solo se anota la interrupción.",
                file=sys.stderr,
            )
        else:
            task_lines = diary.append_line_to_block(task_lines, block, f"-{minutos}")
            diary.write_lines(task_file, task_lines)

        today_lines = diary.read_lines(today_file)
        today_lines = diary.add_or_create_block_line(today_lines, args.nombre, args.url, f"+{minutos}")
        diary.write_lines(today_file, today_lines)

    print(f"Interrupción: -{minutos} en '{open_task.name}' (sigue abierta), +{minutos} en '{args.nombre}'")


def cmd_config(args: argparse.Namespace) -> None:
    if args.config_action == "show":
        print(f"Vault actual: {get_vault_path()}")
    elif args.config_action == "set-vault":
        path = Path(args.ruta).expanduser().resolve()
        set_vault_path(path)
        print(f"Vault configurado: {path}")


def cmd_show(args: argparse.Namespace) -> None:
    vault = get_vault_path()
    if args.fecha:
        when = datetime.strptime(args.fecha, "%Y-%m-%d")
    else:
        when = datetime.now()
    path = _today_file(vault, when)
    if not path.exists():
        print(f"No existe {path}", file=sys.stderr)
        raise SystemExit(1)
    print(path.read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="parte", description="Gestor del diario profesional / parte de horas")
    sub = parser.add_subparsers(dest="comando", required=True)

    p_start = sub.add_parser("start", help="Inicia un trabajo (cierra el que estuviera abierto)")
    p_start.add_argument("nombre", help="Nombre del trabajo")
    p_start.add_argument("--url", help="URL asociada al trabajo (opcional)", default=None)
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

    return parser


def main(argv: Optional[list] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
