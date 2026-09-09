"""O Motor / extracao (pacote, item 31 §3) — fachada do domínio (specs 054/071).

Reexporta a API por NOME; importar executores registra o @registro.handler.
"""
from .primitivas import (  # noqa: F401
    MATERIAS,
    peso_da_porcao,
    porcoes_de_erva,
    renovacao_s,
    roll_colher_check,
    sanear_tamanho,
)
from .executores import (  # noqa: F401
    _apply_extracao_ops,
    _h_extracao,
)
from . import declaracao  # noqa: F401  (importar registra os ToolSpec de mine/chop/forage)
