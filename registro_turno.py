"""O REGISTRO DO TURNO — append-only, e INVISÍVEL PARA O JOGO (spec 044).

Uma linha por turno, particionada por personagem, FORA de `world/`. Serve à
engenharia de prompt e ao troubleshooting: o que a Mente escolheu, o que o mundo
recusou e com que palavras, quanto custou, e — quando o jogador deixa — o que ela
pensou.

WRITE-ONLY PARA O JOGO, E ISSO É ESTRUTURA, NÃO PROMESSA.
=========================================================
Este módulo **não expõe nenhuma função de leitura**. Não há `ler`, não há
`carregar`, não há `buscar`. E nenhum módulo do caminho de jogo (`motor`,
`arbiter`, `face`) o importa — há um teste que afirma exatamente isso
(`selftest_phase47`), no mesmo molde do `selftest_phase46`.

O motivo é o invariante mais permanente do projeto: **o servidor nunca é dono da
agência do personagem**. Subir o racional da Mente ao mundo é útil para analisar
depois; deixar o mundo LER esse racional para arbitrar seria o mundo espiando o
foro íntimo do personagem. O risco real nunca foi um ataque — era alguém, num dia
de pressa, "dar uma espiadinha no que ele pensou" para melhorar uma decisão. Sem
trava estrutural, o invariante morreria assim, sem ninguém perceber.

FALHAR REGISTRANDO NUNCA DERRUBA O TURNO. Sem disco, sem permissão, sem nada: o
jogo segue. Mesma regra do `devlog.py`, e pelo mesmo motivo.

ENVELOPE + CORPO. O envelope é identidade e física (quem, quando, qual turno,
qual modelo, quanto custou). O corpo é PROSA. As métricas nascem de LEITURA
depois — porque as perguntas de amanhã ainda não foram feitas, e campo fixo
obrigaria a decidir hoje o que se vai querer saber.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from version import __version__

LIGADO = os.environ.get("LOREFORGE_REGISTRO", "1") != "0"
RAIZ = Path(os.environ.get("LOREFORGE_REGISTRO_DIR")
            or Path(__file__).resolve().parent.parent / "registro")

_LOCK = threading.Lock()


def _slug(texto: str) -> str:
    """Nome de arquivo seguro. Um `character_id` vem de fora; sem isto, um id
    com `../` escreveria fora da pasta."""
    limpo = "".join(c if (c.isalnum() or c in "-_") else "-" for c in str(texto))
    return limpo.strip("-") or "sem-personagem"


def _anexar(personagem: str, linha: dict) -> None:
    if not LIGADO:
        return
    try:
        RAIZ.mkdir(parents=True, exist_ok=True)
        alvo = RAIZ / f"{_slug(personagem)}.jsonl"
        with _LOCK, open(alvo, "a", encoding="utf-8") as f:
            f.write(json.dumps(linha, ensure_ascii=False) + "\n")
    except (OSError, TypeError, ValueError):
        pass  # registrar nunca derruba o jogo (FR-020)


def anotar_proposta(character_id: str, turno_id: str | None, capacidade: str,
                    alvos: dict, prosa: dict, resultado: dict,
                    aceito: bool) -> None:
    """A metade que O MUNDO sabe, escrita no CAMINHO ÚNICO (`resolver_proposta`).

    Um lugar só, nunca espalhada por capacidade — se cada tool tivesse de se
    lembrar de registrar, a que esquecesse sumiria do histórico em silêncio.

    `aceito` é PASSADO, não inferido. A primeira versão deduzia de
    `resultado.get("ok")`, e o desfecho de sucesso simplesmente não carrega essa
    chave — então todo turno aceito era gravado como recusado, com `aconteceu`
    logo ao lado dizendo o contrário. Um registro que mente envenena em silêncio
    toda análise futura, e ninguém descobriria a não ser lendo linha a linha.
    """
    ok = bool(aceito)
    _anexar(character_id, {
        "lado": "mundo",
        "turno_id": turno_id,
        "personagem": character_id,
        "instante": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "versao_mundo": __version__,
        "capacidade": capacidade,
        "alvos": alvos or {},
        "prosa_tentativa": (prosa or {}).get("acao"),
        "aceito": ok,
        # a recusa em LINGUAGEM DE MUNDO, com o motivo — recusa nunca é
        # silenciosa, nem no jogo nem aqui
        "recusa": None if ok else resultado.get("erro"),
        "aconteceu": resultado.get("aconteceu") or [],
        "viradas": resultado.get("viradas") or [],
    })


def anotar_corpo(linha: dict) -> None:
    """A metade que SÓ O CONECTOR sabe — o racional, o modelo, o custo.

    Chega por canal próprio, fora do caminho da proposta: o que sobe na proposta é
    lido pelo mundo para DECIDIR, e engordar aquilo degradaria todas as decisões
    do turno, não só esta.
    """
    if not isinstance(linha, dict):
        return
    _anexar(linha.get("personagem") or "sem-personagem",
            {**linha, "lado": "mente", "versao_mundo": __version__})
