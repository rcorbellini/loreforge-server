"""O Motor / compromisso (pacote, item 31 §3) — fachada do domínio.

Reexporta a API por NOME; importar executores registra os @registro.handler.
"""
from .executores import (  # noqa: F401
    _apply_promise,
    _h_promise,
)
from . import declaracao  # noqa: F401  (importar registra o ToolSpec de promise)
