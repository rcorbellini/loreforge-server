"""O Motor / herbario (pacote, item 31 §3) — fachada do domínio (spec 054).

Reexporta a API por NOME; importar executores registra o @registro.handler.
"""
from .primitivas import (  # noqa: F401
    porcoes_de_erva,
    rebrota_s,
    roll_colher_check,
)
from .executores import (  # noqa: F401
    _apply_forage_ops,
    _h_forage,
)
from . import declaracao  # noqa: F401  (importar registra o ToolSpec de forage)
