"""O Motor / conteiner (pacote, item 31 §3) — fachada do domínio.

Reexporta a API por NOME; importar executores registra os @registro.handler.
"""
from .primitivas import (  # noqa: F401
    _find_lockable,
    check_trava_item,
)
from .executores import (  # noqa: F401
    _apply_lock_ops,
    _h_lock,
)
from . import declaracao  # noqa: F401  (importar registra os ToolSpec de open/close)
