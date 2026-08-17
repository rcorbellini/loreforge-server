"""O Motor / conhecimento (pacote, item 31 §3) — fachada do domínio.

Reexporta a API por NOME; importar executores registra os @registro.handler.
"""
from .primitivas import (  # noqa: F401
    _find_hearsay_source,
    _normalize_for_search,
    _reject_all,
    quote_matches,
    roll_confidencia,
    roll_disposicao,
    roll_learn_check,
)
from .executores import (  # noqa: F401
    _apply_hearsay_ops,
    _apply_learn_ops,
    _h_hearsay,
    _h_learn,
)
from . import declaracao  # noqa: F401  (importar registra os ToolSpec de conhecimento)
