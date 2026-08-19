"""O Motor / deslocamento — EXECUTORES (item 31 §3: DDD por domínio).

`_apply_*_ops` + `@registro.handler` `_h_*`. Chamam as primitivas do domínio.
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

from .. import combate, fisica, io, memoria, registro, rolagem, rotas
from ..combate import (
    roll_push_check,
    roll_resist_check,
)
from ..fisica import (
    apply_speed,
    carry_capacity,
    check_empurrar,
    is_down,
    push_capacity,
    speed_multiplier_of,
    total_weight_of,
)
from ..io import (
    MotorError,
    WORLD_DIR,
    WRITE_LOCK,
    _fail,
    _rejection,
    find_character_folder,
    name_of,
    read_doc,
    write_doc,
)
from ..memoria import (
    ACONTECIMENTO,
    ROTA,
    _leave_trace,
    _is_alive,
    _iter_memories,
    _remember_route,
    _witness_intensity,
    _write_memory,
    memory_about,
    memory_kind,
)
from ..rolagem import (
    _roll_d20,
    attr_modifier,
    persuade_dc,
    persuade_tendencia,
)
from ..rotas import (
    _check_prerequisites,
    _crossing_time_of,
    _location_folder_by_id,
    _location_name,
    _route_destination,
    _travel_modifier,
    all_route_ids,
    crossing_time,
    find_route,
    knows_route,
)


# spec 030: categoria de esforço de VIAJAR — mora aqui, no módulo que já é
# parte da física de viagem, não numa tabela externa. `_apply_travel_ops` E
# `_apply_persuade_ops` (quando a persuasão bem-sucedida move o alvo) chamam
# fisica.spend_fatigue com esta MESMA categoria; roll_persuasion_check lê a
# mesma constante pra saber SE penaliza por fadiga do alvo (research.md §4/5).
_CUSTO_VIAGEM = "alto"




from .primitivas import (  # noqa: F401
    _cancel_travel,
    _enter_route_locked,
    _interrupt_travels,
    _resolve_arrivals,
    _witness_movement,
    cancel_travel_plan,
    carry_time_penalty,
    current_location_id,
    directions_from,
    enter_route,
    known_routes,
    lazy_evaluate,
    reachable_destinations,
    roll_persuasion_check,
    route_plan,
    set_travel_plan,
)

def _apply_travel_ops(character_id: str, actor_folder: Path,
                      resolution: dict) -> tuple[list[dict], list[dict]]:
    """Inicia uma viagem longa: calcula o trajeto e parte na primeira perna.

    O plano vive DENTRO do `transit` (FR-011). Um registro separado poderia
    divergir da posição real — que é o bug que a FR-011 proíbe. Aqui não há
    como: quem apaga o trânsito apaga o plano junto.
    """
    applied, rejected = [], []
    if not resolution.get("travel_ops"):
        return applied, rejected
    actor_fm, _ = read_doc(actor_folder / "character.md")
    if fisica.is_resting(actor_fm) or fisica.is_cooking(actor_fm):  # spec 031/048: auto-suficiência, nível 0
        rejected.append(_fail("descansando"))
        return applied, rejected
    for op in resolution.get("travel_ops") or []:
        if not isinstance(op, dict):
            continue
        destino = op.get("destino")
        loc_file = actor_folder.parent / "location.md"
        aqui = (read_doc(loc_file)[0]).get("id") if loc_file.exists() else None
        if destino and destino == aqui:
            rejected.append(_rejection(op, _fail("ja_esta_la", destino=destino)))
            continue
        plano = route_plan(character_id, destino) if destino else None
        if not plano:
            rejected.append(_rejection(op, _fail("caminho_desconhecido",
                                                destino=destino)))
            continue
        resultado = _enter_route_locked(character_id, plano[0])
        if not resultado.get("moved"):
            rejected.append(_rejection(op, _fail("rota_indisponivel",
                                                rota=plano[0],
                                                motivo=resultado.get("reason"))))
            continue
        novo_folder = find_character_folder(character_id)
        set_travel_plan(novo_folder, destino, plano[1:])  # spec 038: estado vira primitiva
        applied.append({"destino_final": destino, "pernas": plano})
        fisica.spend_fatigue(character_id, _CUSTO_VIAGEM)  # spec 030
    return applied, rejected


def _apply_carry_ops(character_id: str, actor_folder: Path, resolution: dict,
                     rolls: list | None = None) -> tuple[list, list]:
    """Levar OUTRO personagem por uma rota (`carry_ops`, spec 010).

    O REGIME sai do estado do alvo, não do Árbitro: quem está caído é peso morto e
    resolve por carga; quem está de pé se debate e resolve por disputa de força.
    Rolagem ÚNICA e autoritativa aqui. Assume o WRITE_LOCK já em mãos.

    Nota de física: o limiar de arrasto trivial (metade da capacidade de empurrar)
    é EXATAMENTE a capacidade de carregar — `STR×14 / 2 == STR×7`. Logo, quem não
    cabe nos braços cai sempre na faixa de rolagem do arrasto; não existe arrasto
    trivial. É consequência das constantes da spec 004, não uma escolha nova.
    """
    applied, rejected = [], []
    if not resolution.get("carry_ops"):
        return applied, rejected
    actor_fm_sono, _ = read_doc(actor_folder / "character.md")
    if fisica.is_resting(actor_fm_sono) or fisica.is_cooking(actor_fm_sono):  # spec 031/048: auto-suficiência, nível 0
        rejected.append(_fail("descansando"))
        return applied, rejected
    present_chars, _, _ = io._scene_entities(actor_folder.parent)  # cena fresca (025)
    for op in resolution.get("carry_ops") or []:
        alvo = op.get("alvo") or op.get("personagem")
        rota = op.get("rota")
        base = {"carregar": alvo, "rota": rota}
        if alvo == character_id:
            rejected.append({**base, "why": "ninguém carrega a si mesmo"})
            continue
        if alvo not in present_chars:
            rejected.append(_rejection(base, _fail("personagem_inacessivel", alvo=alvo)))
            continue

        alvo_folder = present_chars[alvo]
        alvo_fm, _ = read_doc(alvo_folder / "character.md")
        actor_fm, _ = read_doc(actor_folder / "character.md")

        if is_down(alvo_fm):
            # regime PESO: não resiste; só o corpo de quem leva decide
            peso = total_weight_of(alvo_folder)
            if peso <= carry_capacity(actor_fm):
                modo = "carregado"
            else:
                modo = "arrastado"
                rej = check_empurrar(character_id, alvo, peso,
                                     push_capacity(actor_fm))
                if rej:
                    rejected.append(_rejection(base, _fail(
                        "peso_excede_arrasto", alvo=alvo, personagem=character_id,
                        peso_alvo=round(peso, 3),
                        capacidade_arrastar=push_capacity(actor_fm))))
                    continue
                rej, info = roll_push_check(actor_fm, character_id, alvo, peso)
                if info is not None:
                    info = {**info, "tipo": "transporte", "regime": "peso",
                            "alvo": alvo}
                    if rolls is not None:
                        rolls.append(info)
                if rej:
                    rejected.append(_rejection(base, rej))
                    continue
        else:
            # regime DISPUTA: está de pé e não quer ir — a força DELE é o obstáculo
            modo = "arrastado"
            rej, info = roll_resist_check(actor_fm, alvo_fm, character_id, alvo)
            if info is not None and rolls is not None:
                rolls.append(info)
            if rej:
                rejected.append(_rejection(base, rej))
                # spec 043: perder a disputa de força cansa — menos que vencê-la.
                fisica.spend_fatigue(character_id, fisica.custo_da_falha("alto"))
                continue

        result = _enter_route_locked(character_id, rota, passenger_id=alvo)
        if not result.get("moved"):
            rejected.append(_rejection(base, _fail(
                "rota_indisponivel", rota=rota, alvo=alvo,
                motivo=result.get("reason") or "o caminho não se abriu")))
            continue
        applied.append({"alvo": alvo, "rota": rota, "modo": modo,
                        "destino": result.get("destination"),
                        "travel_time": result.get("travel_time")})
        fisica.spend_fatigue(character_id, "alto")  # spec 030: carregar cansa
    return applied, rejected


def _apply_persuade_ops(character_id: str, actor_folder: Path, resolution: dict,
                        rolls: list | None = None) -> tuple[list, list]:
    """Persuadir outro personagem a partir por uma rota (`persuade_ops`, spec 007).

    Rolagem ÚNICA e autoritativa aqui (a guarda só valida o determinístico). O
    deslocamento em si é o MESMO da movimentação própria: `_enter_route_locked`
    avaliando pré-requisitos e tempo de viagem contra o ALVO. A vontade (0–10,
    decidida pelo Árbitro pela régua canônica) é efêmera e secreta: clampada,
    usada no DC e descartada — nunca gravada, nunca nos valores devolvidos.
    Assume o WRITE_LOCK já em mãos.
    """
    applied, rejected = [], []
    if not resolution.get("persuade_ops"):
        return applied, rejected
    actor_fm_sono, _ = read_doc(actor_folder / "character.md")
    if fisica.is_resting(actor_fm_sono) or fisica.is_cooking(actor_fm_sono):  # spec 031/048: auto-suficiência, nível 0
        rejected.append(_fail("descansando"))
        return applied, rejected
    present_chars, _, _ = io._scene_entities(actor_folder.parent)  # cena fresca (025)
    moved: set[str] = set()
    for op in resolution.get("persuade_ops") or []:
        alvo = op.get("personagem")
        rota = op.get("rota")
        base = {"persuadir": alvo, "rota": rota}
        if alvo == character_id:
            rejected.append({**base, "why": "é ele quem fala — para ir, basta partir"})
            continue
        if alvo not in present_chars:
            rejected.append(_rejection(base, _fail("personagem_inacessivel", alvo=alvo)))
            continue
        if alvo in moved:
            rejected.append({**base, "why": "já foi movimentado neste turno"})
            continue
        alvo_fm, _ = read_doc(present_chars[alvo] / "character.md")
        if is_down(alvo_fm):
            # spec 010: não se convence quem não ouve. Para tirá-lo do lugar,
            # carrega-se — a persuasão não alcança um desacordado.
            rejected.append(_rejection(base, _fail("alvo_desacordado", alvo=alvo)))
            continue
        try:
            vontade = int(op.get("vontade"))
        except (TypeError, ValueError):
            vontade = 5  # sem nota legível: indiferente (a conversa decide)
        vontade = max(0, min(10, vontade))
        if vontade == 0:
            rejected.append(_rejection(base, _fail("recusa_absoluta", alvo=alvo)))
            continue
        actor_fm, _ = read_doc(actor_folder / "character.md")
        rej, info = roll_persuasion_check(actor_fm, character_id, alvo, rota,
                                          vontade, alvo_fm=alvo_fm)
        if info is not None and rolls is not None:
            rolls.append(info)
        if rej:
            rejected.append(_rejection(base, rej))
            # spec 043: convencer e não conseguir cobra de QUEM TENTOU (supera a
            # spec 030 FR-003) — senão insistir na mesma pessoa sai de graça.
            fisica.spend_fatigue(character_id, fisica.CUSTO_TENTATIVA_SOCIAL)
            continue
        result = _enter_route_locked(alvo, rota)
        if not result.get("moved"):
            # o teste social passou, mas o mundo negou o caminho — os dois
            # motivos são narráveis (contracts/persuade-tool.md)
            rejected.append(_rejection(base, _fail(
                "rota_indisponivel", rota=rota, alvo=alvo,
                motivo=result.get("reason") or "o caminho não se abriu")))
            continue
        moved.add(alvo)
        applied.append({"personagem": alvo, "rota": rota,
                        "destino": result.get("destination"),
                        "travel_time": result.get("travel_time")})
        # spec 030 (FR-003): quem VIAJA gasta a fadiga — o ALVO persuadido,
        # nunca quem persuadiu (character_id fica de fora de propósito).
        fisica.spend_fatigue(alvo, _CUSTO_VIAGEM)
    return applied, rejected


@registro.handler("carry_ops")
def _h_carry(cid, af, res, rolls):
    applied, rejected = _apply_carry_ops(cid, af, res, rolls)
    return applied, rejected, []  # memória do ator via react_actor_memory (spec 038)


def _apply_expel_ops(character_id: str, actor_folder: Path, resolution: dict,
                     rolls: list | None = None) -> tuple[list, list]:
    """Pôr OUTRO para fora à força (`expel_ops`, spec 041).

    REUSA a resolução do levar-à-força (spec 010): de pé → disputa de força
    (`roll_resist_check`); caído → peso (`roll_push_check`, com a banda trivial).
    A DIFERENÇA vs. `carry`: move SÓ o ALVO (`_enter_route_locked` no alvo, sem
    passageiro) — o ATOR permanece no lugar (é isso que faz "pôr para fora", não
    "levar consigo"). Assume o WRITE_LOCK. A MEMÓRIA punitiva/de testemunha é a
    fatia US3 (à parte); aqui só o movimento."""
    applied, rejected, created = [], [], []
    if not resolution.get("expel_ops"):
        return applied, rejected, created
    actor_fm_sono, _ = read_doc(actor_folder / "character.md")
    if fisica.is_resting(actor_fm_sono) or fisica.is_cooking(actor_fm_sono):  # spec 031/048
        rejected.append(_fail("descansando"))
        return applied, rejected, created
    present_chars, _, _ = io._scene_entities(actor_folder.parent)  # cena fresca (025)
    for op in resolution.get("expel_ops") or []:
        alvo = op.get("alvo") or op.get("personagem")
        rota = op.get("rota")
        base = {"expulsar": alvo, "rota": rota}
        if alvo == character_id:
            rejected.append({**base, "why": "ninguém põe a si mesmo para fora"})
            continue
        if alvo not in present_chars:
            rejected.append(_rejection(base, _fail("personagem_inacessivel", alvo=alvo)))
            continue
        alvo_folder = present_chars[alvo]
        alvo_fm, _ = read_doc(alvo_folder / "character.md")
        actor_fm, _ = read_doc(actor_folder / "character.md")

        if is_down(alvo_fm):
            # regime PESO: não resiste; sai por arrasto se couber (banda trivial =
            # cabe nos braços). Mesmas faixas do carry de um caído.
            peso = total_weight_of(alvo_folder)
            if peso > carry_capacity(actor_fm):
                rej = check_empurrar(character_id, alvo, peso, push_capacity(actor_fm))
                if rej:
                    rejected.append(_rejection(base, _fail(
                        "peso_excede_arrasto", alvo=alvo, personagem=character_id,
                        peso_alvo=round(peso, 3),
                        capacidade_arrastar=push_capacity(actor_fm))))
                    continue
                rej, info = roll_push_check(actor_fm, character_id, alvo, peso)
                if info is not None:
                    info = {**info, "tipo": "expulsao", "regime": "peso", "alvo": alvo}
                    if rolls is not None:
                        rolls.append(info)
                if rej:
                    rejected.append(_rejection(base, rej))
                    continue
        else:
            # regime DISPUTA: de pé e resiste — a força DELE é o obstáculo
            rej, info = roll_resist_check(actor_fm, alvo_fm, character_id, alvo)
            if info is not None:
                info = {**info, "tipo": "expulsao", "regime": "disputa", "alvo": alvo}
                if rolls is not None:
                    rolls.append(info)
            if rej:
                rejected.append(_rejection(base, rej))
                # spec 043: falhar em pôr alguém para fora cansa — menos que conseguir.
                fisica.spend_fatigue(character_id, fisica.custo_da_falha("alto"))
                continue

        # move SÓ o alvo — o ator FICA (diferença central vs. carry, que leva os dois)
        result = _enter_route_locked(alvo, rota)
        if not result.get("moved"):
            rejected.append(_rejection(base, _fail(
                "rota_indisponivel", rota=rota, alvo=alvo,
                motivo=result.get("reason") or "o caminho não se abriu")))
            continue
        # memória do ATOR: caminho GENÉRICO (spec 038 — react_actor_memory lê
        # op["memory"], sem editar a reação; expel_ops não está em _ACTOR_CANAIS).
        # Neutra: pôr alguém para fora não é logística, mas o ator não guarda
        # rancor de si — a valência que importa é a do expulso e das testemunhas.
        applied.append({"alvo": alvo, "rota": rota,
                        "destino": result.get("destination"),
                        "travel_time": result.get("travel_time"),
                        "memory": {"content": f"Pus {io.name_of(alvo)} para fora.",
                                   "intensity": "medium",
                                   "involved": [character_id, alvo], "event": "expel"}})
        # RANCOR do EXPULSO — memória grande negativa dirigida ao ator (dispara o
        # portão de trauma: expulsar faz inimigos). SÓ se PERCEBEU: um caído não
        # forma memória (inconsciente não viu — memória é percepção).
        if not is_down(alvo_fm):
            mid = memoria.remember(
                alvo, f"{io.name_of(character_id)} me pôs para fora à força.",
                intensity="large", involved=[character_id, alvo],
                valence={character_id: "negativa"}, evento="expelled")
            if mid:
                created.append({"target": alvo, "id": mid, "event": "expelled"})
        fisica.spend_fatigue(character_id, "alto")  # pôr para fora à força cansa
    return applied, rejected, created


@registro.handler("expel_ops")
def _h_expel(cid, af, res, rolls):
    applied, rejected, created = _apply_expel_ops(cid, af, res, rolls)
    return applied, rejected, created  # rancor do expulso; testemunhas via react_witness


@registro.handler("persuade_ops")
def _h_persuade(cid, af, res, rolls):
    applied, rejected = _apply_persuade_ops(cid, af, res, rolls)
    return applied, rejected, []  # memória do ator via react_actor_memory (spec 038)


@registro.handler("travel_ops")
def _h_travel(cid, af, res, rolls):
    applied, rejected = _apply_travel_ops(cid, af, res)
    return applied, rejected, []  # memória do ator via react_actor_memory (spec 038)
