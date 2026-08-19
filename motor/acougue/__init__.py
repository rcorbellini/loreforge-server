"""O Motor / acougue (pacote, item 31 §3) — fachada do domínio (spec 050).

Reexporta a API por NOME; importar executores registra o @registro.handler.
"""
from .primitivas import (  # noqa: F401
    porcoes_de_carne,
    roll_esquartejar_check,
)
from .executores import (  # noqa: F401
    _apply_esquartejar_ops,
    _h_esquartejar,
)
from . import declaracao  # noqa: F401  (importar registra o ToolSpec de butcher)
