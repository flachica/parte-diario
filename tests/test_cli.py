import io
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from parte_diario import cli, diary, state
from parte_diario.interactive import run_interactive


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.vault_dir = Path(self.temp_dir) / "vault"
        self.vault_dir.mkdir()
        self.state_file = Path(self.temp_dir) / "state.json"

        self.env_patch = patch.dict(
            os.environ,
            {
                "DIARIO_VAULT": str(self.vault_dir),
                "XDG_STATE_HOME": self.temp_dir,
                "XDG_DATA_HOME": self.temp_dir,
            },
        )
        self.env_patch.start()

        # Patch state.STATE_FILE
        self.state_file_patch = patch.object(state, "STATE_FILE", self.state_file)
        self.state_file_patch.start()

    def tearDown(self):
        self.state_file_patch.stop()
        self.env_patch.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_start_and_status_and_stop(self):
        # Start
        f = io.StringIO()
        with redirect_stdout(f):
            cli.main(["start", "Mi Tarea", "--url", "https://ejemplo.com"])
        self.assertIn("Iniciado: Mi Tarea", f.getvalue())

        open_task = state.load()
        self.assertIsNotNone(open_task)
        self.assertEqual(open_task.name, "Mi Tarea")
        self.assertEqual(open_task.url, "https://ejemplo.com")

        # Status
        f = io.StringIO()
        with redirect_stdout(f):
            cli.main(["status"])
        self.assertIn("Abierto: Mi Tarea", f.getvalue())

        # Stop
        f = io.StringIO()
        with redirect_stdout(f):
            cli.main(["stop"])
        self.assertIn("Cerrado: Mi Tarea", f.getvalue())

        self.assertIsNone(state.load())

    def test_start_closes_previous_task(self):
        f = io.StringIO()
        with redirect_stdout(f):
            cli.main(["start", "Tarea 1"])
            cli.main(["start", "Tarea 2"])
        output = f.getvalue()
        self.assertIn("Iniciado: Tarea 1", output)
        self.assertIn("Cerrado: Tarea 1", output)
        self.assertIn("Iniciado: Tarea 2", output)

        open_task = state.load()
        self.assertIsNotNone(open_task)
        self.assertEqual(open_task.name, "Tarea 2")

        # Verificar contenido en el fichero diario
        today_file = cli._today_file(self.vault_dir)
        lines = diary.read_lines(today_file)
        self.assertIsNone(diary.find_open_task_in_lines(lines[:2]))  # Tarea 1 debe estar cerrada

    def test_start_closes_task_when_state_missing_but_file_has_open_task(self):
        cli.main(["start", "Tarea Huérfana"])
        state.clear()
        self.assertIsNone(state.load())

        f = io.StringIO()
        with redirect_stdout(f):
            cli.main(["start", "Nueva Tarea"])
        output = f.getvalue()
        self.assertIn("Cerrado: Tarea Huérfana", output)
        self.assertIn("Iniciado: Nueva Tarea", output)

    def test_interactive_start_closes_previous_task_immediately(self):
        from parte_diario import interactive
        cli.main(["start", "Tarea Abierta"])

        # Simulamos seleccionar '1' (Iniciar tarea), luego 'Tarea Siguiente', URL vacía '', y luego '0' (salir)
        inputs = iter(["1", "Tarea Siguiente", "", "0"])
        f = io.StringIO()
        with patch("builtins.input", side_effect=lambda *args: next(inputs)), redirect_stdout(f):
            interactive.run_interactive()

        out = f.getvalue()
        self.assertIn("Cerrado: Tarea Abierta", out)
        self.assertIn("Iniciado: Tarea Siguiente", out)

    def test_start_with_hora_and_latest(self):
        # Iniciar con hora manual
        cli.main(["start", "Tarea Manual", "--hora", "08:15"])
        task = state.load()
        self.assertIsNotNone(task)
        self.assertEqual(task.start_time, "08:15")

        # Iniciar siguiente tarea desde la hora más alta registrada
        cli.main(["start", "Tarea Siguiente", "--latest"])
        task = state.load()
        self.assertIsNotNone(task)
        self.assertEqual(task.start_time, "08:15")

    def test_interactive_start_choose_highest_time_vs_default(self):
        from parte_diario import interactive
        today_file = cli._today_file(self.vault_dir)
        diary.write_lines(today_file, ["Tarea Pasada", "08:00 - 09:30"])

        # Elegimos opción 2 (última registrada: 09:30)
        inputs = iter(["1", "Tarea Nueva", "", "2", "0"])
        f = io.StringIO()
        with patch("builtins.input", side_effect=lambda *args: next(inputs)), redirect_stdout(f):
            interactive.run_interactive()

        task = state.load()
        self.assertIsNotNone(task)
        self.assertEqual(task.start_time, "09:30")
        cli.main(["stop"])

        # Ahora probamos la opción por defecto (Enter = hora del sistema)
        now_str = datetime.now().strftime("%H:%M")
        inputs = iter(["1", "Tarea Sistema", "", "", "0"])
        f = io.StringIO()
        with patch("builtins.input", side_effect=lambda *args: next(inputs)), redirect_stdout(f):
            interactive.run_interactive()

        task = state.load()
        self.assertIsNotNone(task)
        self.assertEqual(task.start_time, now_str)

    def test_interactive_edit_modify_url(self):
        from parte_diario import interactive
        cli.main(["start", "Mi Tarea"])
        cli.main(["stop"])

        # Date Enter (today), select block 1, name Enter, URL, line 1 start Enter, line 1 end Enter, add line Enter, exit c
        inputs = iter(["", "1", "", "https://ejemplo.com/modificado", "", "", "", "c"])
        f = io.StringIO()
        with patch("builtins.input", side_effect=lambda *args: next(inputs)), redirect_stdout(f):
            interactive.interactive_edit()

        today_file = cli._today_file(self.vault_dir)
        lines = diary.read_lines(today_file)
        self.assertIn("[Mi Tarea](https://ejemplo.com/modificado)", lines[0])

    def test_interactive_edit_modify_time_range(self):
        from parte_diario import interactive
        cli.main(["start", "Tarea Horas"])
        cli.main(["stop"])

        # Date Enter, select block 1, name Enter, URL Enter, start 08:00, end 09:30, add line Enter, exit c
        inputs = iter(["", "1", "", "", "08:00", "09:30", "", "c"])
        f = io.StringIO()
        with patch("builtins.input", side_effect=lambda *args: next(inputs)), redirect_stdout(f):
            interactive.interactive_edit()

        today_file = cli._today_file(self.vault_dir)
        lines = diary.read_lines(today_file)
        self.assertIn("08:00 - 09:30", lines[1])

    def test_interactive_edit_modify_name_and_text(self):
        from parte_diario import interactive
        cli.main(["start", "Tarea Vieja"])
        cli.main(["note", "texto viejo"])
        cli.main(["stop"])

        # Date Enter, select block 1, name Tarea Nueva, URL Enter, line 1 start Enter, line 1 end Enter, line 2 text, add line Enter, exit c
        inputs = iter(["", "1", "Tarea Nueva", "", "", "", "texto nuevo", "", "c"])
        f = io.StringIO()
        with patch("builtins.input", side_effect=lambda *args: next(inputs)), redirect_stdout(f):
            interactive.interactive_edit()

        today_file = cli._today_file(self.vault_dir)
        lines = diary.read_lines(today_file)
        self.assertEqual(lines[0], "Tarea Nueva")
        self.assertIn("texto nuevo", lines[2])

    def test_interactive_edit_quick_delete_task(self):
        from parte_diario import interactive
        cli.main(["start", "Tarea A Borrar"])
        cli.main(["stop"])

        today_file = cli._today_file(self.vault_dir)
        self.assertTrue(len(diary.read_lines(today_file)) > 0)

        # Date Enter, choice 'd 1', confirm 's'
        inputs = iter(["", "d 1", "s"])
        f = io.StringIO()
        with patch("builtins.input", side_effect=lambda *args: next(inputs)), redirect_stdout(f):
            interactive.interactive_edit()

        lines = diary.read_lines(today_file)
        self.assertEqual(len(lines), 0)

    def test_interactive_edit_delete_line_with_d(self):
        from parte_diario import interactive
        cli.main(["start", "Tarea Con Notas"])
        cli.main(["note", "nota a borrar"])
        cli.main(["stop"])

        # Date Enter, select block 1, name Enter, URL Enter, line 1 start Enter, line 1 end Enter, line 2 'd', add line Enter, exit c
        inputs = iter(["", "1", "", "", "", "", "d", "", "c"])
        f = io.StringIO()
        with patch("builtins.input", side_effect=lambda *args: next(inputs)), redirect_stdout(f):
            interactive.interactive_edit()

        today_file = cli._today_file(self.vault_dir)
        lines = diary.read_lines(today_file)
        self.assertNotIn("nota a borrar", "\n".join(lines))

    def test_interactive_edit_modify_name_and_finish_with_c(self):
        from parte_diario import interactive
        cli.main(["start", "Revisar CE"])
        cli.main(["stop"])

        # Date Enter, select block 1, name "Revisar Context Engineering", URL "c" (finish and save), exit "c"
        inputs = iter(["", "1", "Revisar Context Engineering", "c", "c"])
        f = io.StringIO()
        with patch("builtins.input", side_effect=lambda *args: next(inputs)), redirect_stdout(f):
            interactive.interactive_edit()

        today_file = cli._today_file(self.vault_dir)
        lines = diary.read_lines(today_file)
        self.assertEqual(lines[0], "Revisar Context Engineering")

    def test_note_and_show(self):
        cli.main(["start", "TareaConNotas"])
        cli.main(["note", "Primera nota"])
        cli.main(["note", "Nota suelta", "--loose"])
        cli.main(["stop"])

        f = io.StringIO()
        with redirect_stdout(f):
            cli.main(["show"])
        out = f.getvalue()
        self.assertIn("TareaConNotas", out)
        self.assertIn("* Primera nota", out)
        self.assertIn("Nota suelta", out)

    def test_log_and_interrupt(self):
        cli.main(["start", "TareaPrincipal"])
        cli.main(["interrupt", "Llamada", "15"])
        cli.main(["log", "TareaExtra", "30"])
        cli.main(["stop"])

        f = io.StringIO()
        with redirect_stdout(f):
            cli.main(["show"])
        out = f.getvalue()
        self.assertIn("TareaPrincipal", out)
        self.assertIn("-15", out)
        self.assertIn("Llamada", out)
        self.assertIn("+15", out)
        self.assertIn("TareaExtra", out)
        self.assertIn("+30", out)

    def test_interactive_mode_invocation(self):
        # When main is called with [] or no arguments, run_interactive is triggered
        with patch("parte_diario.interactive.run_interactive") as mock_run:
            cli.main([])
            mock_run.assert_called_once()

        with patch("parte_diario.interactive.run_interactive") as mock_run:
            cli.main(["-i"])
            mock_run.assert_called_once()

        with patch("parte_diario.interactive.run_interactive") as mock_run:
            cli.main(["interactive"])
            mock_run.assert_called_once()

    def test_interactive_session_execution(self):
        # Simulate entering interactive loop, executing 'status', and then '0' (exit)
        inputs = iter(["status", "0"])
        f = io.StringIO()
        with patch("builtins.input", side_effect=lambda *args: next(inputs)), redirect_stdout(f):
            run_interactive()

        out = f.getvalue()
        self.assertIn("PARTE DIARIO - MODO INTERACTIVO", out)
        self.assertIn("¡Hasta luego!", out)

    def test_completion_commands(self):
        f = io.StringIO()
        with redirect_stdout(f):
            cli.main(["completion", "bash"])
        self.assertIn("_parte_completions", f.getvalue())
        self.assertIn("complete -F _parte_completions parte", f.getvalue())

        f = io.StringIO()
        with redirect_stdout(f):
            cli.main(["completion", "zsh"])
        self.assertIn("#compdef parte", f.getvalue())

    def test_completion_no_args_shows_guide(self):
        f = io.StringIO()
        with redirect_stdout(f):
            cli.main(["completion"])
        out = f.getvalue()
        self.assertIn("Autocompletado de comandos para 'parte'", out)
        self.assertIn("parte completion --install", out)

    def test_completion_install(self):
        f = io.StringIO()
        with redirect_stdout(f):
            cli.main(["completion", "bash", "--install"])
        out = f.getvalue()
        self.assertIn("Autocompletado de Bash instalado", out)
        expected_file = Path(self.temp_dir) / "bash-completion" / "completions" / "parte"
        self.assertTrue(expected_file.exists())


    def test_interactive_completer(self):
        from parte_diario.interactive import InteractiveCompleter, COMMANDS

        completer = InteractiveCompleter(COMMANDS)
        # Mock readline line buffer
        with patch("readline.get_line_buffer", return_value="s"):
            matches = []
            idx = 0
            while True:
                res = completer.complete("s", idx)
                if res is None:
                    break
                matches.append(res)
                idx += 1
            self.assertIn("start", matches)
            self.assertIn("stop", matches)
            self.assertIn("status", matches)
            self.assertIn("show", matches)

        with patch("readline.get_line_buffer", return_value="config "):
            matches = []
            idx = 0
            while True:
                res = completer.complete("", idx)
                if res is None:
                    break
                matches.append(res)
                idx += 1
            self.assertIn("show", matches)
            self.assertIn("set-vault", matches)

        with patch("readline.get_line_buffer", return_value="r"):
            matches = []
            idx = 0
            while True:
                res = completer.complete("r", idx)
                if res is None:
                    break
                matches.append(res)
                idx += 1
            self.assertIn("review", matches)
            self.assertIn("repasar", matches)

    def test_review_today_and_specific_date(self):
        file_path = self.vault_dir / "2026-09-22.md"
        file_path.write_text(
            "[Todoencloud](https://odoo.sdi.es/task/1)\n"
            "+10\n\n"
            "daily hermes\n"
            "08:17 - 08:33\n\n"
            "biomag\n"
            "09:00 - 11:00\n",
            encoding="utf-8",
        )
        f = io.StringIO()
        with redirect_stdout(f):
            cli.main(["review", "--fecha", "2026-09-22"])
        out = f.getvalue()
        self.assertIn("https://odoo.sdi.es/task/1: 10 minutos", out)
        self.assertIn("daily hermes: 16 minutos", out)
        self.assertIn("biomag: 120 minutos (2h 00m)", out)
        self.assertIn("Total: 146 minutos (2h 26m)", out)

    def test_review_aliases_and_flags(self):
        file_path = self.vault_dir / "2026-09-22.md"
        file_path.write_text(
            "[Todoencloud](https://odoo.sdi.es/task/1)\n"
            "+10\n",
            encoding="utf-8",
        )
        # Test alias repasar
        f = io.StringIO()
        with redirect_stdout(f):
            cli.main(["repasar", "--fecha", "2026-09-22"])
        self.assertIn("https://odoo.sdi.es/task/1: 10 minutos", f.getvalue())

        # Test alias repaso
        f = io.StringIO()
        with redirect_stdout(f):
            cli.main(["repaso", "--fecha", "2026-09-22"])
        self.assertIn("https://odoo.sdi.es/task/1: 10 minutos", f.getvalue())

        # Test --con-nombre / --nombres
        f = io.StringIO()
        with redirect_stdout(f):
            cli.main(["review", "--fecha", "2026-09-22", "--nombres"])
        self.assertIn("https://odoo.sdi.es/task/1 (Todoencloud): 10 minutos", f.getvalue())

    def test_review_nonexistent_and_empty(self):
        with self.assertRaises(SystemExit) as cm:
            cli.main(["review", "--fecha", "1999-01-01"])
        self.assertEqual(cm.exception.code, 1)

        empty_file = self.vault_dir / "2026-09-22.md"
        empty_file.write_text("", encoding="utf-8")
        f = io.StringIO()
        with redirect_stdout(f):
            cli.main(["review", "--fecha", "2026-09-22"])
        self.assertIn("No hay tareas registradas para el 2026-09-22", f.getvalue())

    def test_interactive_review(self):
        from parte_diario import interactive
        file_path = self.vault_dir / "2026-09-22.md"
        file_path.write_text(
            "daily hermes\n"
            "08:17 - 08:33\n\n"
            "biomag\n"
            "09:00 - 09:30\n",
            encoding="utf-8",
        )
        # Inputs: 8 (menú review), fecha, Enter (siguiente tarea), 0 (salir)
        inputs = ["8", "2026-09-22", "", "0"]
        f = io.StringIO()
        with patch("builtins.input", side_effect=inputs), redirect_stdout(f):
            interactive.run_interactive()
        out = f.getvalue()
        self.assertIn("Repaso del parte: 2026-09-22", out)
        self.assertIn("[1/2] daily hermes: 16 minutos", out)
        self.assertIn("[2/2] biomag: 30 minutos", out)
        self.assertIn("Total: 46 minutos", out)

    def test_review_iterative_step_by_step(self):
        file_path = self.vault_dir / "2026-09-22.md"
        file_path.write_text(
            "[Todoencloud](https://odoo.sdi.es/task/1)\n"
            "+10\n\n"
            "daily hermes\n"
            "08:17 - 08:33\n",
            encoding="utf-8",
        )
        inputs = [""]  # Enter para avanzar
        f = io.StringIO()
        with patch("builtins.input", side_effect=inputs), redirect_stdout(f):
            cli.main(["review", "--fecha", "2026-09-22", "--iterativo"])
        out = f.getvalue()
        self.assertIn("[1/2] https://odoo.sdi.es/task/1: 10 minutos", out)
        self.assertIn("[2/2] daily hermes: 16 minutos", out)
        self.assertIn("Total: 26 minutos", out)

    def test_review_iterative_stop_early(self):
        file_path = self.vault_dir / "2026-09-22.md"
        file_path.write_text(
            "[Todoencloud](https://odoo.sdi.es/task/1)\n"
            "+10\n\n"
            "daily hermes\n"
            "08:17 - 08:33\n",
            encoding="utf-8",
        )
        inputs = ["q"]  # salir en la primera tarea
        f = io.StringIO()
        with patch("builtins.input", side_effect=inputs), redirect_stdout(f):
            cli.main(["review", "--fecha", "2026-09-22", "--iterativo"])
        out = f.getvalue()
        self.assertIn("[1/2] https://odoo.sdi.es/task/1: 10 minutos", out)
        self.assertNotIn("daily hermes", out)
        self.assertIn("Repaso interrumpido", out)
        self.assertIn("Total del día: 26 minutos", out)

    def test_review_todo_flag(self):
        file_path = self.vault_dir / "2026-09-22.md"
        file_path.write_text(
            "[Todoencloud](https://odoo.sdi.es/task/1)\n"
            "+10\n\n"
            "daily hermes\n"
            "08:17 - 08:33\n",
            encoding="utf-8",
        )
        f = io.StringIO()
        with redirect_stdout(f):
            cli.main(["review", "--fecha", "2026-09-22", "--todo"])
        out = f.getvalue()
        self.assertIn("https://odoo.sdi.es/task/1: 10 minutos", out)
        self.assertIn("daily hermes: 16 minutos", out)
    def test_interactive_dashboard_two_sections_and_help(self):
        from parte_diario import interactive
        inputs = iter(["?", "0"])
        f = io.StringIO()
        with patch("builtins.input", side_effect=lambda *args: next(inputs)), redirect_stdout(f):
            interactive.run_interactive()
        out = f.getvalue()
        # Sección 1 presente
        self.assertIn("PARTE DIARIO - MODO INTERACTIVO", out)
        self.assertIn("[1] Iniciar / reanudar tarea", out)
        self.assertIn("[2] Parar tarea abierta (stop)", out)
        self.assertIn("[0] Salir (q / exit)", out)
        # Sección 2 presente
        self.assertIn("RESULTADOS / ACTIVIDAD", out)
        self.assertIn("Comandos y atajos disponibles:", out)
        self.assertIn("¡Hasta luego!", out)

    def test_interactive_dashboard_result_in_section_2(self):
        from parte_diario import interactive
        # Ejecutar 'status' y luego '0' (salir)
        inputs = iter(["status", "0"])
        f = io.StringIO()
        with patch("builtins.input", side_effect=lambda *args: next(inputs)), redirect_stdout(f):
            interactive.run_interactive()
        out = f.getvalue()
        self.assertIn("RESULTADOS / ACTIVIDAD", out)
        self.assertIn("No hay ningún trabajo abierto.", out)

    def test_interactive_dashboard_active_task_in_section_1(self):
        from parte_diario import interactive
        cli.main(["start", "Mi Tarea Especial", "--url", "https://ejemplo.com/123"])
        inputs = iter(["note Nota de prueba", "0"])
        f = io.StringIO()
        with patch("builtins.input", side_effect=lambda *args: next(inputs)), redirect_stdout(f):
            interactive.run_interactive()
        out = f.getvalue()
        # Sección 1 debe mostrar la tarea activa y su URL
        self.assertIn("Mi Tarea Especial", out)
        self.assertIn("https://ejemplo.com/123", out)
        # Sección 2 debe mostrar el resultado de la nota añadida
        self.assertIn("RESULTADOS / ACTIVIDAD", out)
        self.assertIn("Nota añadida a 'Mi Tarea Especial': Nota de prueba", out)

    def test_interactive_clear_and_can_clear(self):
        from parte_diario import interactive
        # En redirect_stdout, sys.stdout no es tty, por lo que _can_clear() debe ser False
        self.assertFalse(interactive._can_clear())

        # clear_screen no debe imprimir secuencias ANSI cuando _can_clear() es False
        f = io.StringIO()
        with redirect_stdout(f):
            interactive.clear_screen()
        self.assertEqual(f.getvalue(), "")

    def test_interactive_menu_options_1_to_9_without_option_7_status(self):
        from parte_diario import interactive
        inputs = iter(["0"])
        f = io.StringIO()
        with patch("builtins.input", side_effect=lambda *args: next(inputs)), redirect_stdout(f):
            interactive.run_interactive()
        out = f.getvalue()
        self.assertIn("[1] Iniciar / reanudar tarea", out)
        self.assertIn("[6] Ver diario de hoy / fecha", out)
        self.assertIn("[7] Editar entradas (edit)", out)
        self.assertIn("[8] Repasar parte (review)", out)
        self.assertIn("[9] Configurar vault", out)
        self.assertNotIn("[7] Ver tarea abierta", out)
        self.assertNotIn("[10]", out)

    def test_resumed_task_shows_real_start_time_and_accumulated_minutes(self):
        from parte_diario import interactive
        today_file = cli._today_file(self.vault_dir)
        # Escribimos una tarea previa con varios slots cerrados
        diary.write_lines(
            today_file,
            [
                "Espartero",
                "08:45 - 10:00",  # 75 min
                "10:33 - 11:02",  # 29 min
                "11:20 - 11:52",  # 32 min
            ],
        )
        now_str = datetime.now().strftime("%H:%M")
        # Re-iniciamos la tarea a la hora actual (para que el tramo abierto empiece con 0m de ese slot)
        cli.main(["start", "Espartero", "--hora", now_str])

        open_task = state.load()
        self.assertIsNotNone(open_task)
        self.assertEqual(open_task.start_time, now_str)
        self.assertEqual(open_task.real_start_time, "08:45")

        info = cli.get_status_info()
        self.assertIsNotNone(info)
        # Debe haber pillado la hora de inicio real (08:45), no la del último slot
        self.assertEqual(info["start_time"], "08:45")
        self.assertEqual(info["slot_start_time"], now_str)
        # Los minutos acumulados deben ser al menos los 136 min previos de los slots anteriores
        self.assertEqual(info["total_minutes"], 136)
        self.assertEqual(info["hours"], 2)
        self.assertEqual(info["minutes"], 16)

        # En la línea de estado del dashboard
        status_line = interactive.format_status_line()
        self.assertIn("desde 08:45", status_line)
        self.assertIn("2h 16m", status_line)

        # En el comando status
        f = io.StringIO()
        with redirect_stdout(f):
            cli.main(["status"])
        out = f.getvalue()
        self.assertIn("Inicio:", out)
        self.assertIn("08:45", out)
        self.assertIn(f"último slot: {now_str}", out)
        self.assertIn("Duración:", out)

    def test_status_refresher_disabled_without_clear_or_small_terminal(self):
        from parte_diario import interactive
        refresher = interactive.StatusRefresher(check_interval=0.05)
        # Por defecto en tests sys.stdout no es tty -> _can_clear() es False
        refresher.start("Status inicial", total_lines=20, clear_used=True)
        self.assertFalse(refresher._can_update)
        self.assertIsNone(refresher._thread)
        refresher.stop()

    def test_status_refresher_updates_ansi_on_change(self):
        from parte_diario import interactive
        import os
        import time

        refresher = interactive.StatusRefresher(check_interval=0.01)
        writes = []

        with patch("parte_diario.interactive._can_clear", return_value=True), \
             patch("shutil.get_terminal_size", return_value=os.terminal_size((80, 25))), \
             patch("sys.stdout.write", side_effect=writes.append), \
             patch("sys.stdout.flush"):

            refresher.start("Status anterior", total_lines=20, clear_used=True)
            self.assertTrue(refresher._can_update)
            self.assertIsNotNone(refresher._thread)

            # Simular cambio en format_status_line
            with patch("parte_diario.interactive.format_status_line", return_value="Status NUEVO"):
                time.sleep(0.05)

            refresher.stop()

        self.assertIsNone(refresher._thread)
        # Comprobar que escribió la secuencia ANSI esperada
        combined_output = "".join(writes)
        self.assertIn("\0337\033[5;1H Estado: Status NUEVO\033[K\0338", combined_output)


if __name__ == "__main__":
    unittest.main()

