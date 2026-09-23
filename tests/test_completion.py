import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from parte_diario import completion
from parte_diario.cli import build_parser, main


class TestCompletion(unittest.TestCase):
    def test_detect_user_shell(self):
        with patch.dict(os.environ, {"SHELL": "/usr/bin/zsh"}):
            self.assertEqual(completion.detect_user_shell(), "zsh")

        with patch.dict(os.environ, {"SHELL": "/bin/bash"}):
            self.assertEqual(completion.detect_user_shell(), "bash")

    def test_get_completion_script(self):
        bash_script = completion.get_completion_script("bash")
        self.assertIn("complete -F _parte_completions parte", bash_script)
        self.assertIn("review", bash_script)
        self.assertIn("repasar", bash_script)

        zsh_script = completion.get_completion_script("zsh")
        self.assertIn("#compdef parte", zsh_script)
        self.assertIn("compdef _parte parte", zsh_script)
        self.assertIn("review", zsh_script)
        self.assertIn("repasar", zsh_script)

        with self.assertRaises(ValueError):
            completion.get_completion_script("fish")

    def test_install_completion_bash(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"XDG_DATA_HOME": tmpdir}):
                ok, msg = completion.install_completion("bash")
                self.assertTrue(ok)
                target = Path(tmpdir) / "bash-completion" / "completions" / "parte"
                self.assertTrue(target.exists())
                self.assertIn("complete -F _parte_completions parte", target.read_text(encoding="utf-8"))

    def test_install_completion_zsh(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            omz_custom = Path(tmpdir) / ".oh-my-zsh" / "custom"
            omz_custom.mkdir(parents=True)
            with patch.dict(os.environ, {"ZSH_CUSTOM": str(omz_custom)}):
                ok, msg = completion.install_completion("zsh")
                self.assertTrue(ok)
                target = omz_custom / "completions" / "_parte"
                self.assertTrue(target.exists())
                self.assertIn("#compdef parte", target.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
