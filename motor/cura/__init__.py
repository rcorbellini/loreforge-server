"""O Motor / cura (pacote, item 31 §3) — fachada do domínio.

Reexporta a API por NOME; importar executores registra os @registro.handler.
"""
from .primitivas import (  # noqa: F401
    _recovery_fraction,
    roll_cura_check,
)
from .executores import (  # noqa: F401
    _apply_cura_ops,
    _h_cura,
)
from . import declaracao  # noqa: F401  (importar registra o ToolSpec de heal)
