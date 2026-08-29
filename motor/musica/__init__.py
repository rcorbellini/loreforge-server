"""O Motor / musica (pacote, item 31 §3) — fachada do domínio (spec 058).

Reexporta a API por NOME; importar executores registra o @registro.handler.
"""
from .primitivas import (  # noqa: F401
    roll_sing_check,
    degraus_por_desfecho,
    bonus_instrumento,
    registro_de_intensidade,
)
from .executores import (  # noqa: F401
    _apply_sing_ops,
    _h_sing,
)
from . import declaracao  # noqa: F401  (importar registra o ToolSpec de sing)
