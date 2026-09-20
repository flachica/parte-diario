import io
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from parte_diario import cli, state
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


if __name__ == "__main__":
    unittest.main()
