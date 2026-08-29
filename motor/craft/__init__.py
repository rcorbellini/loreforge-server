"""O Motor / craft (pacote) — fachada do domínio (spec 057).

Reexporta a API por NOME; importar executores registra o @registro.handler, e
importar declaracao registra a ToolSpec (`craft`).
"""
from .primitivas import (  # noqa: F401
    BANDAS,
    LIMIAR_SINCRONO_S,
    banda_final,
    duracao_segundos_craft,
    roll_craft_check,
    sanear_tamanho,
    sanear_tipo,
)
from .executores import (  # noqa: F401
    _apply_craft_ops,
    _h_craft,
)
from . import declaracao  # noqa: F401  (importar registra a ToolSpec)
