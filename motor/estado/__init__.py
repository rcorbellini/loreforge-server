"""O Motor / estado (pacote, item 31 §3) — fachada do domínio.

Reexporta a API por NOME; importar executores registra os @registro.handler.
"""
from .primitivas import (  # noqa: F401
    _clear_condition,
    _set_condition,
    _set_field,
)
from .executores import (  # noqa: F401
    _apply_mutations,
    _h_mutations,
)
from . import declaracao  # noqa: F401  (importar registra o ToolSpec de mutate)
