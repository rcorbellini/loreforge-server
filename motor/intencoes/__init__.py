"""O Motor / intencoes (pacote, item 31 §3) — fachada do domínio.

Reexporta a API por NOME; importar executores registra os @registro.handler.
"""
from .primitivas import (  # noqa: F401
    _CRITERIO_POR_CAMPO,
    _INTENTION_CONTEXT_CAP,
    _INTENTION_STATUSES,
    abandonar,
    casar_e_riscar,
    close_intention,
    create_intention,
    criterio_cumprido,
    fechar_por_criterio,
    marcar_prazo,
    passos_do_plano,
    get_active_intentions,
    riscar_passo,
    rotulo_de_parada,
    update_intention,
)
from .executores import (  # noqa: F401
    _h_intentions,
)
from . import declaracao  # noqa: F401  (importar registra o ToolSpec de set_intention)
