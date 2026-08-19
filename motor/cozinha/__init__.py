"""O Motor / cozinha (pacote, item 31 §3) — fachada do domínio (spec 048).

Reexporta a API por NOME; importar executores registra o @registro.handler.
"""
from .primitivas import (  # noqa: F401
    duracao_segundos,
    lazy_evaluate,
    roll_cook_check,
)
from .executores import (  # noqa: F401
    _apply_cozinha_ops,
    _h_cozinha,
)
from . import declaracao  # noqa: F401  (importar registra o ToolSpec de cook)
