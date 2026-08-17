"""O Motor / tempo (spec 040) — a consulta de MOMENTO do dia.

Deriva a faixa do dia do RELÓGIO REAL do servidor (`time.localtime`), avaliada no
instante da consulta (Princípio VII, preguiçoso — sem processo de fundo). Devolve
PROSA de período; NUNCA a hora numérica nem o timestamp (Princípios V/IX). Read-only:
consultar não é executar. Lane de consulta paralela — não toca o caminho de mutação.

NÍVEL 0: importa só `registro` (a lane) e a stdlib. Importar este módulo popula o
registro de consulta (igual ao `tool_spec`).
"""
from __future__ import annotations

import time

from . import registro

# Faixas grosseiras (research R2). Fim exclusivo. Prosa in-world, sem número.
_FAIXAS = [
    (5, "madrugada"),
    (12, "manhã"),
    (14, "meio-dia"),
    (18, "tarde"),
    (20, "fim de tarde"),
    (24, "noite"),
]


def _periodo(hora: int) -> str:
    for limite, nome in _FAIXAS:
        if hora < limite:
            return nome
    return "noite"


def current_moment(character_id: str | None = None, args: dict | None = None) -> dict:
    """Que momento do dia é agora, em prosa. `character_id`/`args` ignorados (a hora
    é do mundo, não de quem pergunta) — a assinatura casa com o despacho genérico."""
    hora = time.localtime(time.time()).tm_hour
    return {"momento": _periodo(hora)}


registro.consult_spec(registro.ConsultSpec(
    name="consultar_momento",
    description=(
        "Descobre que momento do dia é agora (manhã, fim de tarde, noite…). "
        "Chame quando uma intenção depende do momento ('ao anoitecer', 'no fim do dia')."
    ),
    params={},
    query=current_moment,
))
