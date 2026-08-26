"""O Motor / botica (pacote, item 31 §3) — fachada do domínio (spec 055).

Reexporta a API por NOME; importar executores registra o @registro.handler.
"""
from .primitivas import (  # noqa: F401
    duracao_segundos_preparo,
    roll_preparar_check,
)
from .executores import (  # noqa: F401
    _apply_botica_ops,
    _h_botica,
)
from . import declaracao  # noqa: F401  (importar registra o ToolSpec de brew)
