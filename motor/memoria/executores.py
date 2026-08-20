"""O Motor / memoria — EXECUTORES (item 31 §3: DDD por domínio).

`_apply_*_ops` + `@registro.handler` `_h_*`. Chamam as primitivas do domínio.
"""
from __future__ import annotations

import math
import os
import random
import threading
import time
import uuid
import unicodedata
from pathlib import Path

import frontmatter
import validator

from .. import fisica, io, registro, rolagem, trabalho
from ..io import (
    find_character_folder,
    name_of,
    new_id,
    read_doc,
    write_doc,
)


_MEMORY_INTENSITIES = {"small", "medium", "large", "giant"}


# Domínio de memória (spec 029, item 9/16/18 do backlog): fonte ÚNICA em
# `validator.DOMAINS` — mesmo padrão que SIZES/SLOTS já seguem ("a régua é
# compartilhada... o Motor importa daqui", validator.py:25). O enum de
# `create_memory` (arbiter.py) e a tabela de retrofit (_DOMAIN_BY_EVENT,
# abaixo) leem `validator.DOMAINS`, nunca uma cópia local — evita duas
# listas divergentes. Ao contrário de `evento` (spec 028, campo aberto),
# este é FECHADO por decisão desta spec: o valor alimenta um cálculo
# (proficiência) que precisa ser estável entre consultas.
DOMAINS = validator.DOMAINS


_DEFAULT_TTL_SECONDS = 3600


ACONTECIMENTO = "acontecimento"


ROTA = "rota"


_TTL_BY_INTENSITY = {
    "small": 2 * 86400,
    "medium": 14 * 86400,
    "large": 90 * 86400,
    "giant": 365 * 86400,
}


_TTL_ROTA = 180 * 86400



_RASTRO_TTL_BASE = 43200      # 12h — teto curto da faixa baixa (bem < 48h)
_RASTRO_TTL_STEP = 14400      # 4h — quanto a rolagem desloca, prum lado ou outro
_RASTRO_TTL_MIN = 3600        # 1h — piso, nunca menos
_RASTRO_TTL_MAX = 172800      # 48h — teto absoluto (mesmo limite do validator)


_PERCENTUAL_BASE_POR_BANDA = {"media": 0.35, "alta": 0.15}
_PISO_PERCENTUAL_ESQUECIDO = 0.05


_INTENSITY_ORDER_DESC = {"giant": 0, "large": 1, "medium": 2, "small": 3}


POSITIVA, NEGATIVA = "positiva", "negativa"

# spec 038 (T016): `_RELEVANCE_BY_EVENT`/`_VALENCE_BY_EVENT` MORRERAM — a relevância
# e a valência de cada ato viajam COM o ato (ver `primitivas.remember`/`_rec`), não
# mais numa tabela central. (Estas cópias aqui já eram inertes desde o split do
# item 31 §3.)


# Domínio de memória (spec 029): mesmo formato de _RELEVANCE_BY_EVENT — todo
# evento fora daqui cai em "nenhuma" pelo default de _write_memory, nunca
# erro. Deliberadamente ausentes: "equip", "lock", "mutate", "wield" (ações
# utilitárias, ninguém progride nelas) e "promise" (fora do escopo decidido
# nesta spec — fica pra quando o item 22 for revisitado sob este eixo).
_DOMAIN_BY_EVENT = {
    # combate
    "attack": "combate", "defeat": "combate", "assaulted": "combate",
    "weapon_hit": "combate", "weapon_miss": "combate",
    "witness_attack": "combate",
    # crime
    "theft": "crime", "stolen": "crime", "stolen_from": "crime",
    "witness_theft": "crime", "theft_twist": "crime",
    # comercio
    "trade": "comercio", "transfer": "comercio",
    "gift_received": "comercio", "gift_given": "comercio",
    "gift_reluctant": "comercio", "witness_trade": "comercio",
    "witness_transfer": "comercio", "witness_persuade_give": "comercio",
    "emprestimo": "comercio", "witness_emprestimo": "comercio",
    # social
    "persuade": "social", "accuse": "social", "accused": "social",
    "witness_accuse": "social", "hearsay": "social",
    "hearsay_reconto": "social",
    # deslocamento
    "travel": "deslocamento", "learn_route": "deslocamento",
    "carry": "deslocamento", "learn": "deslocamento",
    "inform": "deslocamento", "taught": "deslocamento",
    # spec 034: deslocamento testemunhado (chegada/partida) — mesmo domínio
    # que travel/learn_route/carry já ocupam.
    "witness_departure": "deslocamento", "witness_arrival": "deslocamento",
    # cura (spec 032) — primeiro domínio de fase 2
    "heal": "cura", "healed": "cura", "witness_heal": "cura",
}


_DONO_EVENTOS = {"transfer", "emprestimo", "witness_transfer", "witness_emprestimo"}


_PUBLICO = "publico"   # ruído de ato ostensivo: visto por todos os presentes


_APEGO_VITIMA_FORTE = 4.0


_LIMIAR_SONO_QUALIDADE = 0.5


_INTENSITY_ORDER = {"giant": 0, "large": 1, "medium": 2, "small": 3}


_DAY = 86400


_VIVID_WINDOW = {
    "small": 2 * _DAY,
    "medium": 14 * _DAY,
    "large": 60 * _DAY,
    "giant": 180 * _DAY,
}


_MEMORY_CONTEXT_CAP = 40


_MEMORY_WEIGHT = {"small": 1.0, "medium": 2.0, "large": 4.0, "giant": 8.0}


_FAMILIARIDADE_PISO = 0.5


_FADIGA_CORTES = (0.25, 0.5, 0.75, 1.0)
_FADIGA_PENALIDADES = (0, 1, 2, 4)


from .primitivas import (  # noqa: F401
    _char_name,
    _create_memories,
    _expire_memories,
    _forget_memories,
    _forgotten_percent,
    _intensify_commitments,
    _is_alive,
    _is_trace_active,
    _iter_memories,
    _leave_trace,
    _lower_intensity,
    _memory_salience,
    _perceive_dc,
    _proficiency_factor,
    _raise_intensity,
    _rec,
    _recency_label,
    _record_arma,
    _record_attack,
    _record_carry,
    _record_cura,
    _record_equip,
    _record_events,
    _record_hearsay,
    _record_hearsay_narrator,
    _record_learn,
    _record_lock,
    _record_mutations,
    _record_persuade,
    _record_persuade_give,
    _record_stolen,
    _record_trade,
    _record_transfer,
    _record_travel,
    _record_witness,
    _remember_route,
    _renew_memory,
    _roll_trace_d20,
    _short_summary,
    _weigh_memories,
    _witness_facts,
    _witness_intensity,
    _write_memory,
    dono,
    familiarity_label,
    familiarity_with,
    fatigue_label,
    fatigue_penalty,
    get_active_memories,
    has_trauma_from,
    memory_about,
    memory_involved,
    memory_kind,
    memory_ouvido_de,
    memory_valence,
    proficiencies_for,
    record_event,
    sentiment_label,
    sentiment_toward,
    ttl_for,
)

def _apply_accuse(character_id: str, actor_folder: Path,
                  res: dict, rolls=None) -> tuple[list, list, list]:
    """Por op (`alvo`, `memoria_id`): valida que a memória referenciada é da
    PRÓPRIA pasta do ator, está VIVA, e envolve o `alvo` — só então escreve
    as duas memórias diretas (Decisão 3, research.md). Qualquer checagem que
    falhar rejeita a op inteira; nada nasce de uma referência inválida
    (FR-004 do spec)."""
    applied, rejected, created = [], [], []
    if not res.get("accuse_ops"):
        return applied, rejected, created
    actor_fm, _ = read_doc(actor_folder / "character.md")
    if fisica.is_resting(actor_fm) or trabalho.is_busy(actor_folder):  # spec 031/048/052: auto-suficiência, nível 0
        rejected.append(io._fail("descansando"))
        return applied, rejected, created
    now = time.time()
    for op in res.get("accuse_ops") or []:
        alvo = op.get("alvo")
        memoria_id = op.get("memoria_id")
        if not alvo or not memoria_id:
            rejected.append({**op, "why": "'alvo' e 'memoria_id' são obrigatórios"})
            continue
        mem_path = actor_folder / "memories" / f"{memoria_id}.md"
        if not mem_path.exists():
            rejected.append({**op, "why": "essa lembrança não existe (ou não é sua)"})
            continue
        fm, body = read_doc(mem_path)
        if fm.get("type") != "memory" or not _is_alive(fm, now):
            rejected.append({**op, "why": "essa lembrança já não está viva o bastante"})
            continue
        if alvo not in memory_involved(fm):
            rejected.append({**op, "why": "essa lembrança não envolve quem se quer acusar"})
            continue

        eu = _char_name(character_id)
        alvo_nome = _char_name(alvo)
        mem_id_acusador = _write_memory(
            actor_folder, f"Acusei {alvo_nome}: {body.strip()}",
            involved=[alvo], evento="accuse")
        created.append({"target": character_id, "id": mem_id_acusador})
        alvo_folder = find_character_folder(alvo)
        mem_id_acusado = _write_memory(
            alvo_folder, f"{eu} me acusou: {body.strip()}",
            involved=[character_id], evento="accused")
        created.append({"target": alvo, "id": mem_id_acusado})
        applied.append({"alvo": alvo, "memoria_id": memoria_id})
    return applied, rejected, created


@registro.handler("accuse_ops")
def _h_accuse(character_id, actor_folder, res, rolls):
    return _apply_accuse(character_id, actor_folder, res, rolls)


# --------------------------------------------------------------------------- #
# Dormir (spec 030, alternador desde spec 031) — determinístico: sem régua,
# sem rolagem (mesmo molde de `prometer`/`acusar`). Sem parâmetros — age
# sempre sobre o PRÓPRIO ator (`[[server-never-owns-character-agency]]`).
# `_apply_rest_ops` (abaixo) ramifica por ESTADO (iniciar/acordar); ao
# acordar, intensifica compromissos pendentes (Frente D,
# `_intensify_commitments`) SÓ SE o descanso foi de qualidade.
# --------------------------------------------------------------------------- #

# Piso de "sono de qualidade" (spec 031): a Frente D só dispara se a MESMA
# fração calculada pra fadiga (`fisica.rest_fraction`) atingir isto — um
# descanso curto não pesa em compromisso alheio.
def _apply_rest_ops(character_id: str, actor_folder: Path,
                    resolution: dict, rolls: list | None = None) -> tuple[list, list]:
    """Duas ações, não um alternador (item 50). A intenção vem no `op` da própria
    op — `sleep` ou `wake_up` — e aqui ela é VALIDADA contra o estado, não adivinhada:

    - `op: sleep` — grava o timestamp real de agora, não mexe em fadiga, não
      intensifica nada. Recusado com `ja_dormindo` se já houver timestamp.
    - `op: wake_up` — calcula a fração de recuperação plena (`fisica.rest_fraction`)
      pelo tempo real decorrido (teto 8h, `fisica._TETO_SONO_PLENO_S`), aplica a
      fadiga proporcional, apaga o timestamp, e intensifica compromissos pendentes SÓ
      SE a fração foi >= 50% ("sono de qualidade", `_LIMIAR_SONO_QUALIDADE` — Frente
      D, spec 030). Recusado com `nao_esta_dormindo` se não houver timestamp.

    ANTES a decisão era do ESTADO DO ARQUIVO e não havia recusa possível: quem
    chamasse `sleep` já dormindo acordava, e quem chamasse acordado ia dormir. O gate
    da face esconde o caso errado, mas gate é UX — a autoridade é esta função, e uma
    chamada direta (ou uma face velha de um turno atrás) chegava aqui e virava a ação
    OPOSTA à pedida, calada. Agora ela é recusada em linguagem de mundo."""
    applied, rejected, created = [], [], []
    ops = resolution.get("rest_ops")
    if not ops:
        return applied, rejected, created
    # a op é uma lista de payloads; o `op` do PRIMEIRO diz o que se quis fazer.
    # É OBRIGATÓRIO. Deixar um fallback "sem op, deduz pelo estado" manteria o
    # alternador vivo por uma porta lateral — e o item 50 existe justamente para
    # matá-lo. Quem chama sem dizer o que quer é bug de chamador, e um `KeyError`
    # silencioso seria pior: recusa-se com regra própria, que aparece no relato.
    pedido = None
    for p in ops:
        if isinstance(p, dict) and p.get("op"):
            pedido = p["op"]
            break
    if pedido not in ("sleep", "wake_up"):
        rejected.append({"acao": "rest", "regra": "rest_sem_op",
                         "valores": {"personagem": character_id, "op": pedido}})
        return applied, rejected, created
    fm, _ = read_doc(actor_folder / "character.md")
    inicio = (fm.get("status") or {}).get("descansando_desde")
    if pedido == "sleep" and inicio:
        rejected.append({"acao": "sleep", "regra": "ja_dormindo",
                         "valores": {"personagem": character_id}})
        return applied, rejected, created
    if pedido == "wake_up" and not inicio:
        rejected.append({"acao": "wake_up", "regra": "nao_esta_dormindo",
                         "valores": {"personagem": character_id}})
        return applied, rejected, created
    if pedido == "sleep":
        fisica.start_rest(actor_folder, time.time())  # spec 038: estado vira primitiva
        applied.append({"iniciou_descanso": True})
        # ITEM 52.6 (decisão do mantenedor): dormir/acordar/decidir são o MESMO caso do
        # `mutate` — mudança de ESTADO, não vivência. Então derivam o mesmo evento e
        # herdam o mesmo ciclo: vida curta (6h) e imune à renovação. Sem escritor sob
        # medida para cada um; sem memória permanente de que às 14h07 ele deitou.
        _rec(created, character_id, "Deitei para dormir.", "mutate", [character_id])
        return applied, rejected, created
    decorrido = time.time() - inicio
    fracao = fisica.rest_fraction(decorrido)
    fadiga_antes, teto = fisica.ensure_fatigue(fm)
    recuperada = round(fracao * teto)
    fisica.finish_rest(actor_folder, max(0, fadiga_antes - recuperada), teto)  # spec 038
    intensificadas = []
    if fracao >= _LIMIAR_SONO_QUALIDADE:
        intensificadas = _intensify_commitments(character_id, actor_folder)
    # A QUALIDADE é rótulo, não número (Princípios V/IX): é ela que a frase
    # in-world lê. Sem isto o construtor teria de reimportar o limiar daqui, e o
    # `aconteceu` voltava vazio — que foi exatamente o defeito: 61 ciclos de
    # sono da Elga em 2026-08-20, todos com `fadiga_recuperada: 0`, e A Mente
    # nunca soube. Quem conhece a regra é o executor; o construtor só renderiza.
    qualidade = ("inteiro" if fracao >= _LIMIAR_SONO_QUALIDADE
                 else "pouco" if recuperada > 0 else "nenhum")
    applied.append({"acordou": True, "fadiga_recuperada": recuperada,
                    "fracao_dormida": round(fracao, 2), "qualidade": qualidade,
                    "compromissos_intensificados": intensificadas})
    # o DESFECHO do sono entra no texto porque o mundo já o conhece (a mesma fração que
    # decide se o compromisso pesa mais). Acordar inteiro e acordar moído são coisas
    # diferentes, e quem lembra é quem dormiu.
    _rec(created, character_id,
         "Acordei inteiro." if fracao >= _LIMIAR_SONO_QUALIDADE
         else "Acordei ainda moído.", "mutate", [character_id])
    return applied, rejected, created


@registro.handler("rest_ops")
def _h_dormir(character_id, actor_folder, res, rolls):
    return _apply_rest_ops(character_id, actor_folder, res, rolls)


