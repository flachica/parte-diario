"""Módulo para generación e instalación de autocompletado en shells (Bash, Zsh)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Tuple

BASH_COMPLETION_SCRIPT = """# Autocompletado Bash para 'parte' (diario profesional)
_parte_completions() {
    local cur prev words cword
    if declare -F _init_completion >/dev/null 2>&1; then
        _init_completion || return
    else
        COMPREPLY=()
        cur="${COMP_WORDS[COMP_CWORD]}"
        prev="${COMP_WORDS[COMP_CWORD-1]}"
        words=("${COMP_WORDS[@]}")
        cword=$COMP_CWORD
    fi

    local commands="start stop status note show log interrupt config interactive completion"
    local config_commands="show set-vault"

    if [[ $cword -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "$commands -i --interactive -h --help" -- "$cur") )
        return 0
    fi

    local cmd="${words[1]}"
    case "$cmd" in
        start)
            if [[ "$prev" == "--url" ]]; then
                return 0
            fi
            COMPREPLY=( $(compgen -W "--url" -- "$cur") )
            ;;
        stop|status|interactive)
            return 0
            ;;
        show)
            if [[ "$prev" == "--fecha" ]]; then
                return 0
            fi
            COMPREPLY=( $(compgen -W "--fecha" -- "$cur") )
            ;;
        note)
            COMPREPLY=( $(compgen -W "--loose --suelta" -- "$cur") )
            ;;
        log)
            if [[ "$prev" == "--url" ]]; then
                return 0
            fi
            COMPREPLY=( $(compgen -W "--url --resta" -- "$cur") )
            ;;
        interrupt)
            if [[ "$prev" == "--url" ]]; then
                return 0
            fi
            COMPREPLY=( $(compgen -W "--url" -- "$cur") )
            ;;
        config)
            if [[ $cword -eq 2 ]]; then
                COMPREPLY=( $(compgen -W "$config_commands" -- "$cur") )
            fi
            ;;
        completion)
            if [[ $cword -eq 2 ]]; then
                COMPREPLY=( $(compgen -W "bash zsh --install" -- "$cur") )
            fi
            ;;
        *)
            ;;
    esac
    return 0
}

complete -F _parte_completions parte
"""

ZSH_COMPLETION_SCRIPT = """#compdef parte
# Autocompletado Zsh para 'parte' (diario profesional)

_parte() {
    local -a commands
    commands=(
        'start:Inicia un trabajo (cierra el que estuviera abierto)'
        'stop:Cierra el trabajo abierto sin iniciar otro'
        'status:Muestra el trabajo actualmente abierto'
        'note:Añade una nota al trabajo abierto o suelta'
        'show:Muestra el contenido del diario de hoy o de otra fecha'
        'log:Anota una tarea usando solo minutos invertidos (+15 o -15)'
        'interrupt:Registra una interrupción en la tarea abierta'
        'config:Consulta o fija la ruta del vault'
        'interactive:Inicia el modo interactivo'
        'completion:Genera o instala el script de autocompletado'
    )

    _arguments -C \\
        '(-i --interactive --interactivo)'{-i,--interactive,--interactivo}'[Inicia el modo interactivo]' \\
        '(-h --help)'{-h,--help}'[Muestra la ayuda]' \\
        '1: :->command' \\
        '*:: :->args'

    case $state in
        command)
            _describe -t commands 'comando' commands
            ;;
        args)
            case $words[1] in
                start)
                    _arguments \\
                        '--url[URL asociada al trabajo]:url:' \\
                        '*:nombre:'
                    ;;
                stop|status|interactive)
                    ;;
                show)
                    _arguments \\
                        '--fecha[Fecha en formato YYYY-MM-DD]:fecha:'
                    ;;
                note)
                    _arguments \\
                        '(--loose --suelta)'{--loose,--suelta}'[Nota suelta, no asociada a tarea abierta]' \\
                        '*:texto:'
                    ;;
                log)
                    _arguments \\
                        '--url[URL asociada]:url:' \\
                        '--resta[Anota minutos en negativo]' \\
                        '1:nombre:' \\
                        '2:minutos:'
                    ;;
                interrupt)
                    _arguments \\
                        '--url[URL asociada a la interrupción]:url:' \\
                        '1:nombre:' \\
                        '2:minutos:'
                    ;;
                config)
                    local -a config_actions
                    config_actions=(
                        'show:Muestra la ruta actual del vault'
                        'set-vault:Fija la ruta del vault de forma persistente'
                    )
                    _describe -t config_actions 'acción config' config_actions
                    ;;
                completion)
                    _arguments \\
                        '--install[Instala el autocompletado automáticamente]' \\
                        '1:shell:(bash zsh)'
                    ;;
            esac
            ;;
    esac
}

if [[ -n "$ZSH_EVAL_CONTEXT" && "$ZSH_EVAL_CONTEXT" == *:shfunc* ]]; then
    _parte "$@"
else
    compdef _parte parte 2>/dev/null || true
fi
"""


def detect_user_shell() -> str:
    """Detecta la shell del usuario (zsh o bash) inspeccionando el entorno."""
    shell_env = os.environ.get("SHELL", "")
    if "zsh" in shell_env:
        return "zsh"
    return "bash"


def get_completion_script(shell: str) -> str:
    sh = shell.lower().strip()
    if sh == "bash":
        return BASH_COMPLETION_SCRIPT
    if sh == "zsh":
        return ZSH_COMPLETION_SCRIPT
    raise ValueError(f"Shell no soportada: '{shell}'. Las opciones válidas son 'bash' o 'zsh'.")


def install_completion(shell: Optional[str] = None) -> Tuple[bool, str]:
    target_shell = shell if shell else detect_user_shell()
    sh = target_shell.lower().strip()

    if sh == "bash":
        # Estándar XDG para completados de usuario en bash
        xdg_data = os.environ.get("XDG_DATA_HOME")
        base_dir = Path(xdg_data) if xdg_data else Path.home() / ".local" / "share"
        target_dir = base_dir / "bash-completion" / "completions"
        target_file = target_dir / "parte"

        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            target_file.write_text(BASH_COMPLETION_SCRIPT, encoding="utf-8")
            return (
                True,
                f"✓ Autocompletado de Bash instalado con éxito en:\n  {target_file}\n\n"
                "Para activarlo en esta misma sesión de terminal, ejecuta:\n"
                f"  source \"{target_file}\"\n\n"
                "En las nuevas terminales de Bash estará disponible automáticamente con la tecla <TAB>.",
            )
        except Exception as e:
            return False, f"Error al instalar el autocompletado de Bash: {e}"

    if sh == "zsh":
        # En Oh My Zsh, custom/completions ya está en el $fpath por defecto
        omz_custom = Path(os.environ.get("ZSH_CUSTOM", Path.home() / ".oh-my-zsh" / "custom"))
        if omz_custom.parent.exists() or omz_custom.exists():
            target_dir = omz_custom / "completions"
        else:
            target_dir = Path.home() / ".zsh" / "completion"

        target_file = target_dir / "_parte"

        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            target_file.write_text(ZSH_COMPLETION_SCRIPT, encoding="utf-8")

            # Limpiar caché de completado de zsh para refrescar inmediatamente
            import glob
            for dump in glob.glob(str(Path.home() / ".zcompdump*")):
                try:
                    os.remove(dump)
                except OSError:
                    pass

            return (
                True,
                f"✓ Autocompletado de Zsh instalado con éxito en:\n  {target_file}\n\n"
                "Para activarlo inmediatamente en la terminal actual, ejecuta:\n"
                "  source <(parte completion zsh)\n\n"
                "En cualquier nueva ventana o pestaña de terminal estará disponible automáticamente con la tecla <TAB>.",
            )
        except Exception as e:
            return False, f"Error al instalar el autocompletado de Zsh: {e}"

    return False, f"Shell no soportada: '{target_shell}'"

