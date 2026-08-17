"""O Motor / combate (pacote, item 31 §3) — fachada do domínio.

Reexporta a API por NOME; importar executores registra os @registro.handler.
"""
from .primitivas import (  # noqa: F401
    roll_attack_check,
    roll_push_check,
    roll_resist_check,
)
from .executores import (  # noqa: F401
    _apply_attack_ops,
    _h_attack,
)
from . import declaracao  # noqa: F401  (importar registra o ToolSpec de attack)
