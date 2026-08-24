"""O Motor / fogo (pacote, item 31 §3) — fachada do domínio (spec 053).

Reexporta a API por NOME; importar executores registra o @registro.handler.
"""
from .primitivas import (  # noqa: F401
    duracao_fogo_s,
    roll_kindle_check,
)
from .executores import (  # noqa: F401
    _apply_fogo_ops,
    _h_fogo,
)
from . import declaracao  # noqa: F401  (importar registra o ToolSpec de kindle_fire)
