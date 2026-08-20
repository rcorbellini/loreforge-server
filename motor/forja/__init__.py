"""O Motor / forja (pacote, item 31 §3) — fachada do domínio (spec 052).

Reexporta a API por NOME; importar executores registra o @registro.handler, e
importar declaracao registra as DUAS ToolSpec (`forge_weapon`, `forge_armor`).
"""
from .primitivas import (  # noqa: F401
    BANDAS,
    banda_final,
    bloco_mecanico,
    duracao_segundos_forja,
    favorabilidade,
    roll_forge_check,
    teto_por_maestria,
    teto_por_material,
)
from .executores import (  # noqa: F401
    _apply_forja_ops,
    _h_forja,
)
from . import declaracao  # noqa: F401  (importar registra as duas ToolSpec)
