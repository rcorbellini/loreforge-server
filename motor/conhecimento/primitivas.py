"""O Motor / conhecimento — PRIMITIVAS (item 31 §3: DDD por domínio).

Funções puras (validação, rolagem, helpers). Sem turno/LLM. Ver executores.py.
"""
from __future__ import annotations

import os
import random
import threading
import time
import uuid
import unicodedata
from pathlib import Path

import frontmatter
import validator

from .. import fisica, io, memoria, registro, rolagem, rotas
from ..fisica import (
    DOWN_CONDITIONS,
)
from ..io import (
    arquivos_em,
    arquivos_no_mundo,
    MotorError,
    _fail,
    _rejection,
    find_character_folder,
    read_doc,
)
from ..memoria import (
    ROTA,
    _is_alive,
    _record_hearsay,
    _remember_route,
    memory_involved,
    memory_kind,
    has_trauma_from,
)
from ..rolagem import (
    LEARN_ROUTE_DC,
    _roll_d20,
    attr_modifier,
    learn_dc_from,
    persuade_dc,
    persuade_tendencia,
)
from ..rotas import (
    find_route,
    knows_route,
)



def roll_disposicao(char_id: str, actor_fm: dict, informante_id: str,
                    nota: int, rolls: list | None = None) -> tuple[bool, dict]:
    """Ele quis contar? d20 + mod(CHA) vs `persuade_dc` — UMA vez por conversa.

    A CURVA é a da persuasão, deliberadamente: a aritmética de "quanto custa
    vencer uma relutância de grau N" não muda com o que se pede, e duas curvas
    para o mesmo formato de esforço seriam duas calibragens a manter em sincronia
    (a spec 011 reusou a mesma base pelo mesmo argumento). O que NÃO se reusa é a
    régua — `REGUA_DISPOSICAO` é ancorada alto, porque onde se vai é informação
    trivial e o normal é atender.

    Os extremos são deterministas e NÃO consomem dado: nota 0 é o sujeito em quem
    se bateu — ele não tem um mau dia de dado, simplesmente não fala; nota 10 é
    quem já ia dizendo.
    """
    nota = int(nota)
    # spec 020: portão DETERMINÍSTICO — quem apanhou não indica caminho. O Motor
    # confere a memória ATUAL da fonte (que, na fase única, já reflete um golpe
    # deste mesmo turno) e força a recusa, sem depender da nota que o Árbitro deu.
    if has_trauma_from(informante_id, actor_fm.get("id")):
        nota = 0
    if nota <= 0 or nota >= 10:
        passou = nota >= 10
        info = {"tipo": "disposicao", "personagem": char_id,
                "informante": informante_id, "nota": nota,
                "resultado": "sucesso" if passou else "falha",
                "virada": False, "critico": None, "rolagem": None}
        if rolls is not None:
            rolls.append(info)
        return passou, info
    d20 = rolagem._roll_d20()
    mod = attr_modifier((actor_fm.get("attributes") or {}).get("CHA", 10))
    dc = persuade_dc(nota)
    total = d20 + mod
    passou = total >= dc
    natural = persuade_tendencia(nota)
    info = {
        "tipo": "disposicao", "personagem": char_id,
        "informante": informante_id, "nota": nota,
        "resultado": "sucesso" if passou else "falha",
        # virada social: o desfecho contrariou a tendência natural do informante
        "virada": (natural == "ir" and not passou) or (natural == "ficar" and passou),
        "critico": ("sucesso" if (d20 == 20 and passou)
                    else "falha" if (d20 == 1 and not passou) else None),
        "rolagem": {"d20": d20, "mod": mod, "total": total, "dc": dc},
    }
    if rolls is not None:
        rolls.append(info)
    return passou, info


def roll_confidencia(char_id: str, actor_fm: dict, narrador_id: str,
                     nota: int, rolls: list | None = None) -> tuple[bool, dict]:
    """Ela quis contar o que sabe? d20 + mod(CHA do ator) vs `persuade_dc` (spec 017).

    Estrutura do `roll_disposicao`: a curva da persuasão, extremos deterministas
    (0 não conta, 10 conta, sem dado). O que muda é a RÉGUA — `REGUA_CONFIDENCIA`
    é ancorada BAIXO: o que se sabe de alguém é moeda e escudo, e se guarda por
    padrão. O oposto de indicar uma rua.
    """
    nota = int(nota)
    if nota <= 0 or nota >= 10:
        passou = nota >= 10
        info = {"tipo": "confidencia", "personagem": char_id,
                "informante": narrador_id, "nota": nota,
                "resultado": "sucesso" if passou else "falha",
                "virada": False, "critico": None, "rolagem": None}
        if rolls is not None:
            rolls.append(info)
        return passou, info
    d20 = rolagem._roll_d20()
    mod = attr_modifier((actor_fm.get("attributes") or {}).get("CHA", 10))
    dc = persuade_dc(nota)
    total = d20 + mod
    passou = total >= dc
    natural = persuade_tendencia(nota)
    info = {
        "tipo": "confidencia", "personagem": char_id,
        "informante": narrador_id, "nota": nota,
        "resultado": "sucesso" if passou else "falha",
        "virada": (natural == "ir" and not passou) or (natural == "ficar" and passou),
        "critico": ("sucesso" if (d20 == 20 and passou)
                    else "falha" if (d20 == 1 and not passou) else None),
        "rolagem": {"d20": d20, "mod": mod, "total": total, "dc": dc},
    }
    if rolls is not None:
        rolls.append(info)
    return passou, info


def roll_learn_check(char_id: str, actor_fm: dict, route_id: str,
                     rolls: list | None = None, dc: int | None = None
                     ) -> tuple[bool, dict]:
    """Decifrou este caminho? d20 + mod(INT) vs DC — UMA rolagem por rota.

    `dc` só é passado quando quem ensinou foi uma PESSOA (spec 015). Omitido, a
    DC é a fixa da spec 014, e é assim que material lido não regride.
    """
    dc = LEARN_ROUTE_DC if dc is None else dc
    # spec 030 (Frente B): fadiga alta piora a DC efetiva de decifrar um
    # caminho — determinístico, mesmos cortes de fatigue_label.
    fadiga, teto = fisica.ensure_fatigue(actor_fm)
    dc += memoria.fatigue_penalty(fadiga, teto)
    d20 = rolagem._roll_d20()
    mod = attr_modifier((actor_fm.get("attributes") or {}).get("INT", 10))
    total = d20 + mod
    passou = total >= dc
    info = {
        "tipo": "leitura",
        "personagem": char_id, "rota": route_id,
        "resultado": "sucesso" if passou else "falha",
        "virada": False,
        "critico": ("sucesso" if (d20 == 20 and passou)
                    else "falha" if (d20 == 1 and not passou) else None),
        "rolagem": {"d20": d20, "mod": mod, "total": total,
                    "dc": dc},
    }
    if rolls is not None:
        rolls.append(info)
    return passou, info


def _normalize_for_search(texto: str) -> str:
    """Achata o texto para comparação: minúsculas, sem acento, espaço único.

    A margem que a busca literal precisa ter. Sem isto, uma quebra de linha no
    meio da frase citada — que o `.md` tem e o modelo não copia — reprovaria uma
    citação correta.
    """
    import unicodedata
    t = unicodedata.normalize("NFKD", (texto or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(t.split())


def quote_matches(trecho: str, fonte: str, margem: int = 4) -> bool:
    """O trecho citado EXISTE na fonte? Presença literal, não sentido.

    Esta é a única contenção mecânica possível sobre a leitura, e ela é barata
    justamente por não julgar nada: não avalia se o texto "quer dizer" a rota —
    só se as palavras estão lá.

    Nasceu de uma medição. O modelo propunha rotas que o material não descrevia e
    inventava a citação para sustentá-las, sempre no mesmo formato: "A carta
    menciona: '...'". Reforçar a instrução no prompt não resolveu — ele repetiu a
    frase proibida ao pé da letra. O que a prosa não garante, a busca garante.

    A `margem` tolera o modelo cortar ou acrescentar palavras nas pontas: exige-se
    que uma JANELA do trecho apareça na fonte, não o trecho inteiro. Copiar mal é
    aceitável; inventar não.
    """
    alvo, texto = _normalize_for_search(trecho), _normalize_for_search(fonte)
    if not alvo or not texto:
        return False
    if alvo in texto:
        return True
    palavras = alvo.split()
    if len(palavras) <= margem:
        return False
    # janela deslizante: o miolo do que ele citou precisa existir na fonte
    janela = max(margem, len(palavras) - margem)
    for i in range(len(palavras) - janela + 1):
        if " ".join(palavras[i:i + janela]) in texto:
            return True
    return False


def _reject_all(rejected: list, op: dict, regra: str, **valores) -> None:
    """Recusa a op INTEIRA — usada quando o portão fecha antes das rotas.

    Não se recusa caminho a caminho aqui de propósito: quem não quis falar não
    falou de nada, e listar cada rota como um fracasso separado sugeriria ao
    jogador que houve tentativa em cada uma.
    """
    for route_id in op.get("rotas") or []:
        found = find_route(route_id)
        nome = (found[1].get("name") or route_id) if found else route_id
        rejected.append(_rejection({"rota": route_id, "nome": nome, **valores},
                                  _fail(regra, rota=route_id, **valores)))


def _find_hearsay_source(fonte_id: str, sobre: str, trecho: str) -> dict | None:
    """A memória VIVA de `fonte` que envolve `sobre` e cujo corpo contém o `trecho`.

    É contra ESTA memória que o reconto é gravado (grau, valência, sujeitos). A
    conferência da citação (feita pelo chamador contra `lido`) já garantiu que o
    trecho foi surfaçado; aqui achamos a memória concreta que o embasa.
    """
    try:
        folder = find_character_folder(fonte_id)
    except MotorError:
        return None
    mem_dir = folder / "memories"
    if not mem_dir.is_dir():
        return None
    for path in arquivos_em(mem_dir):
        fm, body = read_doc(path)
        if fm.get("type") != "memory" or memory_kind(fm) == ROTA:
            continue
        if not _is_alive(fm):
            continue
        if sobre not in memory_involved(fm):
            continue
        if quote_matches(trecho, body):
            return fm
    return None


