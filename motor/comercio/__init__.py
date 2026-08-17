"""O Motor / comercio (pacote, item 31 §3) — fachada do domínio.

Reexporta a API por NOME; importar executores registra os @registro.handler.
"""
from .primitivas import (  # noqa: F401
    _open_container_for,
    _validate_negotiation,
    check_availability,
    check_purchase_affordable,
    offered_by,
    roll_persuade_give_check,
    roll_trade_check,
    trade_terms,
)
from .executores import (  # noqa: F401
    _apply_persuade_give_ops,
    _apply_trade_ops,
    _h_persuade_give,
    _h_trade,
)
from . import declaracao  # noqa: F401  (importar registra os ToolSpec de comércio)
