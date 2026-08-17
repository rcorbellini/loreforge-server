"""O Motor / intencoes (pacote, item 31 §3) — fachada do domínio.

Reexporta a API por NOME; importar executores registra os @registro.handler.
"""
from .primitivas import (  # noqa: F401
    _INTENTION_CONTEXT_CAP,
    _INTENTION_STATUSES,
    close_intention,
    create_intention,
    get_active_intentions,
    update_intention,
)
from .executores import (  # noqa: F401
    _h_intentions,
)
from . import declaracao  # noqa: F401  (importar registra o ToolSpec de set_intention)
