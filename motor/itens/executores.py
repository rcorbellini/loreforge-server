"""O Motor / itens — EXECUTORES (item 31 §3: DDD por domínio).

`_apply_*_ops` (valida contra os arquivos, rola, aplica) e os `@registro.handler`
`_h_*` (encadeiam memória). Chamam as primitivas do domínio. Sem LLM/turno.
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

from .. import (combate, deslocamento, estado, fisica, intencoes, io, memoria, percepcao, registro, rolagem, trabalho)
from ..combate import (
    roll_push_check,
)
from ..deslocamento import (
    _enter_route_locked,
)
from ..estado import (
    _set_field,
)
from ..fisica import (
    HAND_SLOT,
    _direct_items,
    _walk_open_items,
    carried_weight,
    carry_capacity,
    check_carga,
    check_empurrar,
    check_encaixe,
    check_mao,
    check_slot,
    check_vaga,
    effective_weight,
    porter_of,
    grasp_slot_of,
    has_accessible_item,
    is_closed,
    item_size,
    item_slot,
    push_capacity,
    slot_capacity,
    slots_in_use,
)
from ..io import (
    MotorError,
    _GROUND_WORDS,
    _char_fm,
    _fail,
    _rejection,
    _slugify,
    find_character_folder,
    read_doc,
    write_doc,
)
from ..memoria import (
    _write_memory,
)



from .primitivas import (  # noqa: F401
    _corrigivel_reject,
    _equippable_items,
    _equipped_items,
    _find_item_folder_in_scene,
    _find_item_under,
    _held_items,
    _loose_items,
    _match_scene_ref,
    _set_item_slot,
    _validate_move,
    roll_embriaguez_check,
    roll_steal_check,
    roll_toxicidade_check,
    transfer_item,
)

def _apply_movement(character_id: str, route_id: str) -> dict:
    """Deslocamento como resolução: entra na rota, ou registra a tentativa negada.

    Assume o WRITE_LOCK já em mãos (chamado de dentro de apply_resolution).
    Inclui um narrative_hint próprio, pois o desfecho real (partiu / não partiu)
    só é conhecido aqui — não no Árbitro.
    """
    result = _enter_route_locked(character_id, route_id)
    if result.get("moved"):
        hint = (
            f"Você deixa o lugar e segue pela {result['route_name']} "
            f"rumo a {result['destination_name']}."
        )
        # ANDAR é a ação mais comum do jogo, e não deixava lembrança nenhuma:
        # este caminho faz early-return de `apply_resolution`, então
        # `_record_events` nunca rodava aqui. A viagem era narrada (o hint acima)
        # e esquecida no mesmo instante.
        try:
            _write_memory(
                find_character_folder(character_id),
                f"Segui pela {result['route_name']} rumo a "
                f"{result['destination_name']}.",
                intensity="small",  # spec 038 (T016): ex-_RELEVANCE_BY_EVENT["travel"]
            )
        except MotorError:
            pass
        return {
            "applied": [{
                "target": character_id, "movement": route_id,
                "destination": result["destination"], "reason": "entrou na rota",
            }],
            "rejected": [],
            "movement": result,
            "narrative_hint": hint,
        }

    # negado: FR-014 — há consequência, mas sem sair do lugar.
    reason = result.get("reason") or "o caminho não se abriu"
    actor_folder = find_character_folder(character_id)
    action = f"tentou partir, mas {reason}"
    _set_field(actor_folder, "status.action", action)
    return {
        "applied": [{
            "target": character_id, "path": "status.action", "value": action,
            "reason": "tentativa de deslocamento negada (FR-014)",
        }],
        "rejected": [{"movement": route_id, "why": reason}],
        "movement": result,
        "narrative_hint": action[0].upper() + action[1:],
    }


def _apply_equip_ops(
    character_id: str, actor_folder: Path, resolution: dict,
    rolls: list | None = None,
) -> tuple[list[dict], list[dict]]:
    """Aplica as operações de vestir/tirar decididas pelo Árbitro (`equip_ops`),
    revalidando o pipeline físico contra os arquivos reais (autoritativo).

    - equip {item}: acopla no slot declarado no `wearable.slot` do próprio item;
      move a pasta para o personagem quando o item vem de fora da estrutura dele.
    - unequip {item, to}: libera o slot; `to` = o próprio ator (vai para a mão,
      pasta não se move), um contêiner com vaga, ou o chão (id do lugar).
    """
    applied, rejected = [], []
    if not resolution.get("equip_ops"):
        return applied, rejected
    location_folder = actor_folder.parent
    present_chars, present_objects, present_items = io._scene_entities(location_folder)  # cena fresca (025)
    actor_fm, _ = read_doc(actor_folder / "character.md")
    if fisica.is_resting(actor_fm) or trabalho.is_busy(actor_folder):  # spec 031/048/052: auto-suficiência, nível 0
        rejected.append(_fail("descansando"))
        return applied, rejected

    for op in resolution.get("equip_ops") or []:
        if not isinstance(op, dict) or op.get("op") not in ("equip", "unequip"):
            continue
        kind = op.get("op")
        item_id = op.get("item")
        item_folder = _find_item_folder_in_scene(item_id, actor_folder) if item_id else None
        if item_folder is None:
            rejected.append(_rejection(op, _fail("item_inacessivel", item=item_id)))
            continue
        item_fm, _ = read_doc(item_folder / "item.md")

        if kind == "equip":
            # AUTORIDADE ÚNICA (item 31): não se veste o que está com OUTRA pessoa —
            # regra que era pré-voo da tool. Recusa corrigível, com os vestíveis à mão.
            if porter_of(item_folder) not in (None, actor_folder):
                rejected.append(_corrigivel_reject(op, "item_alheio",
                                                   _equippable_items(actor_folder, present_items)))
                continue
            wearable = item_fm.get("wearable")
            slot = wearable.get("slot") if isinstance(wearable, dict) else None
            # spec 019: "não se veste" é o item SEM slot declarado. Se ele declara
            # um slot mas o corpo do ator não o tem, isso é recusa de check_slot
            # (`corpo_sem_slot`), não "não vestível".
            if not isinstance(slot, str) or not slot:
                rejected.append(_rejection(op, _fail("item_nao_vestivel", item=item_id)))
                continue
            in_use = slots_in_use(actor_folder).get(slot) or []
            if item_id in in_use:
                continue  # já vestido — nada a fazer
            rej = check_slot(item_id, slot, in_use, slot_capacity(actor_fm, slot))
            if rej is None and porter_of(item_folder) != actor_folder:
                peso = effective_weight(item_folder)
                total_apos = carried_weight(actor_folder) + peso
                rej = check_carga(character_id, item_id, peso, total_apos,
                                  carry_capacity(actor_fm))
            if rej:
                rejected.append(_rejection(op, rej))
                continue
            dest = actor_folder / item_folder.name
            if dest != item_folder:
                if dest.exists():
                    rejected.append({**op, "why": "colisão de nome no destino"})
                    continue
                io.move_entity(item_folder, dest)
            _set_item_slot(dest, slot)
            applied.append({"op": "equip", "item": item_id, "slot": slot})
            continue

        # unequip — só se tira o que está VESTIDO em quem age (item 31: autoridade
        # única, era pré-voo da tool). Recusa corrigível, com os vestidos como validos.
        # Item na mão (slot de pega) não conta como vestido — não há o que "tirar".
        hand = grasp_slot_of(actor_fm) or HAND_SLOT
        slot_atual = item_slot(item_fm)
        if item_folder.parent != actor_folder or not slot_atual or slot_atual == hand:
            rejected.append(_corrigivel_reject(op, "nao_vestido_em_voce",
                                               _equipped_items(actor_folder, present_items)))
            continue
        to = op.get("to") or character_id
        if to == character_id:  # para o slot de pega (mão/boca): só o state.slot muda
            pega = grasp_slot_of(actor_fm)
            hands = slots_in_use(actor_folder).get(pega) or [] if pega else []
            if item_id in hands:
                continue  # já está na mão/boca
            rej = check_mao(character_id, hands,
                            slot_capacity(actor_fm, pega) if pega else 0)
            if rej:
                rejected.append(_rejection(op, rej))
                continue
            _set_item_slot(item_folder, pega)
            applied.append({"op": "unequip", "item": item_id, "to": character_id})
            continue
        # para um contêiner ou para o chão: mesma física de qualquer movimentação
        place_fm = {}
        for fname in ("location.md", "route.md"):
            if (location_folder / fname).exists():
                place_fm, _ = read_doc(location_folder / fname)
                break
        if to == place_fm.get("id"):
            dest_root, dest_kind = location_folder, "place"
        else:
            dest_root = _find_item_folder_in_scene(to, actor_folder)
            dest_kind = "container"
        if dest_root is None:
            rejected.append(_rejection(op, _fail("destino_inacessivel", destino=to)))
            continue
        if dest_root == item_folder or item_folder in dest_root.parents:
            rejected.append({**op, "why": "um contêiner não pode entrar em si mesmo"})
            continue
        rej = _validate_move(actor_folder, item_folder, item_fm, dest_kind,
                             dest_root, rolls)
        if rej:
            rejected.append(_rejection(op, rej))
            continue
        dest = dest_root / item_folder.name
        if dest.exists():
            rejected.append({**op, "why": "colisão de nome no destino"})
            continue
        io.move_entity(item_folder, dest)
        _set_item_slot(dest, None)
        applied.append({"op": "unequip", "item": item_id, "to": to})
    return applied, rejected


def _apply_item_transfers(
    character_id: str, actor_folder: Path, resolution: dict,
    rolls: list | None = None,
) -> tuple[list[dict], list[dict]]:
    """`give`/`take`/`stow`/`drop` — ORQUESTRA `transfer_item` (spec 037). Este corpo
    é o SENTIDO da tool `give`: resolve as referências FROUXAS do Árbitro
    ('Frasco de Tintura Vermelha', 'chão da praça') para ids exatos, chama a primitiva
    `transfer_item` para a física, e faz `intention_id`/`emprestimo` atravessarem até o
    applied (a memória e o dono-de-fato moram em `memoria._record_transfer`, no wrapper
    `_h_transfer`). `item` MUST estar presente; `to` MUST ser personagem, contêiner ou
    o próprio lugar. Entradas inválidas voltam em `rejected` (devlog), nunca descarte
    silencioso.
    """
    applied, rejected = [], []
    if not resolution.get("item_transfers"):
        return applied, rejected
    actor_fm, _ = read_doc(actor_folder / "character.md")
    if fisica.is_resting(actor_fm) or trabalho.is_busy(actor_folder):  # spec 031/048/052: auto-suficiência, nível 0
        rejected.append(_fail("descansando"))
        return applied, rejected
    location_folder = actor_folder.parent
    place_id, place_name = None, ""
    for fname in ("location.md", "route.md"):
        place_file = location_folder / fname
        if place_file.exists():
            place_fm, _ = read_doc(place_file)
            place_id = place_fm.get("id")
            place_name = place_fm.get("name") or ""
            break

    # spec 025 (Fase C): a cena é LIDA FRESCA aqui, não recebida congelada.
    present_chars, present_objects, present_items = io._scene_entities(location_folder)
    scene = {"chars": present_chars, "objects": present_objects,
             "items": present_items, "location_folder": location_folder,
             "place_id": place_id}

    # índice id+nome da cena para resolver referências frouxas do Árbitro.
    def _entries(folders: dict, filename: str) -> list[tuple[str, str]]:
        out = []
        for eid, folder in folders.items():
            fm, _ = read_doc(folder / filename)
            out.append((eid, fm.get("name") or ""))
        return out

    item_entries = _entries(present_items, "item.md")
    dest_entries = (
        _entries(present_chars, "character.md")
        + _entries(present_objects, "object.md")
        + item_entries
        + ([(place_id, place_name)] if place_id else [])
    )

    for transfer in resolution.get("item_transfers") or []:
        if not isinstance(transfer, dict):
            continue
        item_ref = transfer.get("item")
        to_ref = transfer.get("to")
        if not item_ref or not to_ref:
            continue
        # "chão"/"solo" na referência ganham precedência (intenção de largar).
        if place_id and (_GROUND_WORDS & set(_slugify(to_ref).split("-"))):
            to = place_id
        else:
            to = _match_scene_ref(to_ref, dest_entries)
        item_id = _match_scene_ref(item_ref, item_entries)
        if item_id is None:
            # a referência era um OBJECT da cena? mobília, não item portável (spec 002/004)
            obj_entries = _entries(present_objects, "object.md")
            obj_ref = _match_scene_ref(item_ref, obj_entries)
            if obj_ref is not None:
                rejected.append(_rejection({**transfer, "item": obj_ref},
                                          _fail("objeto_fixo", objeto=obj_ref)))
                continue
            rejected.append({**transfer,
                             "why": "item não existe na cena nem em inventário presente"})
            continue
        # AUTORIDADE ÚNICA (item 31): a posse/slot/soltura que a tool pré-checava mora
        # aqui agora, no executor, e a recusa é CORRIGÍVEL — leva os `validos` (o que é
        # possível) para o modelo trocar de item sem re-tentar às cegas.
        # give/drop: só o que o ATOR tem na mão · give/drop/stow: item DESVESTIDO ·
        # shove: só o que NINGUÉM carrega (empurra-se o solto, larga-se o que se segura).
        mode = transfer.get("mode")
        if mode in ("give", "drop", "stow", "shove"):
            item_folder = present_items.get(item_id)
            hand = grasp_slot_of(actor_fm) or HAND_SLOT
            if mode in ("give", "drop") and porter_of(item_folder) != actor_folder:
                rejected.append(_corrigivel_reject(transfer, "nao_possui_item",
                                                   _held_items(actor_folder, present_items)))
                continue
            if mode == "shove" and porter_of(item_folder) is not None:
                rejected.append(_corrigivel_reject(transfer, "item_carregado",
                                                   _loose_items(present_items)))
                continue
            it_fm, _ = read_doc(item_folder / "item.md")
            slot = (it_fm.get("state") or {}).get("slot")
            if mode != "shove" and slot and slot != hand:
                rejected.append(_corrigivel_reject(transfer, "item_vestido",
                                                   _held_items(actor_folder, present_items)))
                continue
        ap, rej = transfer_item(item_id, actor_folder, to, scene, rolls)
        if rej is not None:
            rejected.append(rej)
            continue
        if ap is None:
            continue  # já está no destino — nada a fazer
        # SENTIDO do give: intention_id (spec 027) e emprestimo (spec 036) atravessam
        # até o applied; a física em si não sabe nada deles.
        if transfer.get("intention_id"):
            ap["intention_id"] = transfer["intention_id"]
        if transfer.get("emprestimo"):
            ap["emprestimo"] = True
        applied.append(ap)
    return applied, rejected


# --------------------------------------------------------------------------- #
# Roubar (spec 023) — subtrair um item de outro presente SEM consentimento.
# Furtividade (DEX) vs a exposição do furto (nota do Árbitro, lida da prosa).
# Três desfechos por distância à DC: limpo · flagrado-mas-levou · flagrado-vazio.
# --------------------------------------------------------------------------- #

def _apply_steal_ops(character_id: str, actor_folder: Path, resolution: dict,
                     rolls: list | None = None) -> tuple[list, list]:
    """Furtar itens de outros presentes (spec 023). LIMPO/FLAGRADO-levou movem o
    item ao ladrão; FLAGRADO-vazio não move. O flagrante vira memória negativa no
    DONO (large → portão de trauma), gravada em _record_stolen. Assume WRITE_LOCK."""
    applied, rejected = [], []
    if not resolution.get("steal_ops"):
        return applied, rejected
    present_chars, present_objects, present_items = io._scene_entities(actor_folder.parent)  # cena fresca (025)
    actor_fm, _ = read_doc(actor_folder / "character.md")
    if fisica.is_resting(actor_fm) or trabalho.is_busy(actor_folder):  # spec 031/048/052: auto-suficiência, nível 0
        rejected.append(_fail("descansando"))
        return applied, rejected
    for op in resolution.get("steal_ops") or []:
        alvo = op.get("alvo")
        item_id = op.get("item")
        exposicao = op.get("exposicao")
        base = {"roubar": item_id, "de": alvo}
        if alvo == character_id:
            rejected.append({**base, "why": "não se rouba de si mesmo"})
            continue
        if alvo not in present_chars:
            rejected.append(_rejection(base, _fail("personagem_inacessivel", alvo=alvo)))
            continue
        if _find_item_under(present_chars[alvo], item_id) is None:
            rejected.append(_rejection(base, _fail("item_nao_e_do_alvo", item=item_id, alvo=alvo)))
            continue
        # spec 051: a prática de furtar volta como bônus. Todo furto já carimbava
        # `domain: "crime"` (spec 029) e ninguém lia o acúmulo de volta — agora lê,
        # pelo MESMO mecanismo dinâmico de `cura`/`cozinha`/`acougue` (nunca um campo
        # estático `skills.*`). Soma direto no total, decidindo o próprio desfecho.
        nivel_crime = memoria.proficiencies_for(character_id).get("crime", 0.0)
        desfecho, info = roll_steal_check(
            actor_fm, character_id, alvo, item_id, exposicao, nivel_crime, rolls)
        if desfecho == "impossivel":
            rejected.append(_rejection(base, _fail("furto_impossivel", item=item_id)))
            continue
        levou = desfecho in ("limpo", "flagrado_levou")
        flagrado = desfecho in ("flagrado_levou", "flagrado_vazio")
        if levou:
            # spec 037: reusa a PRIMITIVA de transferência (nunca a tool give). O
            # SENTIDO do furto (memória negativa no dono, se flagrado) mora em
            # _record_stolen — a primitiva não grava nada.
            scene = {"chars": present_chars, "objects": present_objects,
                     "items": present_items, "location_folder": actor_folder.parent,
                     "place_id": None}
            t_ap, t_rej = transfer_item(item_id, actor_folder, character_id, scene, rolls)
            if t_ap is None:
                why = (t_rej or {}).get("why", "não coube na mão do ladrão")
                rejected.append({**base, "why": why})
                continue
        applied.append({"de": alvo, "item": item_id, "flagrado": flagrado,
                        "levou": levou, "virada": bool(info.get("virada")),
                        "exposicao": exposicao})   # spec 024: ruído do leque de testemunha
        # spec 030: tensão/agilidade. spec 043: o furto que FALHOU (flagrado sem levar)
        # já cansava o CHEIO — agora cansa um degrau abaixo, para não punir demais quem
        # tentou e não levou nada.
        fisica.spend_fatigue(character_id,
                             "medio" if levou else fisica.custo_da_falha("medio"))
    return applied, rejected


@registro.handler("equip_ops")
def _h_equip(cid, af, res, rolls):
    applied, rejected = _apply_equip_ops(cid, af, res, rolls)
    return applied, rejected, []  # memória do ator via react_actor_memory (spec 038)


@registro.handler("item_transfers")
def _h_transfer(cid, af, res, rolls):
    applied, rejected = _apply_item_transfers(cid, af, res, rolls)
    for ap in applied:
        # spec 027: fechar a PRÓPRIA intenção é um bônus sobre a transferência,
        # NUNCA pode virar `rejected` — `give` aplica por-op via _apply_op_now
        # (arbiter.py), que trata QUALQUER rejeição como "a op inteira foi
        # negada", mas a transferência real já aconteceu neste ponto. Falha
        # aqui fica só anotada dentro do próprio applied (contracts/, FR-007).
        intention_id = ap.pop("intention_id", None)
        if intention_id:
            ap["intention_closed"] = intencoes.close_intention(af, intention_id)
    # memória do ator (e do receptor/dono-de-fato) via react_actor_memory (spec 038):
    # a reação recompõe a cena com o MESMO `io._scene_entities(af.parent)`.
    return applied, rejected, []


@registro.handler("steal_ops")
def _h_steal(cid, af, res, rolls):
    applied, rejected = _apply_steal_ops(cid, af, res, rolls)
    return applied, rejected, []  # memória (ladrão e dono flagrado) via react_actor_memory (spec 038)


# --------------------------------------------------------------------------- #
# Comer (spec 046) — consumir um item comestível, julgado por QUATRO réguas já
# resolvidas pela guarda (`itens/declaracao._eat`): comestibilidade, saciedade,
# toxicidade, consumo+nova_descricao. Este executor VALIDA e APLICA; a ÚNICA
# decisão não-determinística é o teste de toxicidade (roll_toxicidade_check) — o
# Árbitro julgou o RISCO, o Motor decide se de fato adoeceu.
# --------------------------------------------------------------------------- #

def _apply_eat_ops(character_id: str, actor_folder: Path, resolution: dict,
                   rolls: list | None = None) -> tuple[list, list]:
    """Comer um item (spec 046). Comestibilidade 0 rejeita — COM memória embutida
    (`op["memory"]`, small/negativa — a correção do mantenedor: recusa de mérito
    também vira lembrança, ou a Mente re-tenta em loop sem saber que já tentou).
    Comestibilidade > 0 aplica: saciedade -> rótulo de status.hunger; toxicidade ->
    teste de resistência (mod CON vs toxin_dc) -> condição 'doente' se falhar;
    consumo -> `io.remove_entity` (nota 0, item devorado por completo — exceção
    escopada ao Princípio IV, emenda 2.1.0) ou description reescrita em lugar
    (nota 1-9)."""
    applied, rejected = [], []
    if not resolution.get("eat_ops"):
        return applied, rejected
    _, _, present_items = io._scene_entities(actor_folder.parent)  # cena fresca (025)
    actor_fm, _ = io.read_doc(actor_folder / "character.md")
    for op in resolution.get("eat_ops") or []:
        item_id = op.get("item")
        base = {"comer": item_id}
        item_folder = present_items.get(item_id)
        if item_folder is None:
            rejected.append(io._rejection(base, io._fail("item_inacessivel", item=item_id)))
            continue
        if int(op.get("comestibilidade") or 0) <= 0:
            rejected.append({
                **base, "regra": "nao_comestivel", "valores": {"item": item_id},
                "why": io._WHY_BY_REGRA["nao_comestivel"],
                "memory": {
                    "content": f"Tentei comer {io.name_of(item_id)}, mas não era comida.",
                    "intensity": "small", "involved": [item_id],
                    "valence": {item_id: memoria.NEGATIVA}, "event": "eat_refused"}})
            continue
        saciedade = int(op.get("saciedade") or 0)
        # GUARDA DE COERÊNCIA (decisão do mantenedor, 2026-08-20): as quatro notas
        # não são independentes. `comestibilidade > 0` com `saciedade 0` é uma
        # combinação sem sentido — a própria régua define 0 como "zero valor
        # nutricional, a ação não alimenta em nada". Aceitá-la fechava um laço:
        # `saciedade 0` faz o executor gravar `hunger: "com fome"` (comer REAFIRMA
        # a fome) e `consumo > 0` preserva o item, então o mesmo alvo continua ali,
        # apetecível para sempre. A Elga comeu a MESMA moeda de prata 17 vezes em
        # 12h assim (juízo real: comestibilidade 3, saciedade 0, consumo 9).
        #
        # Recusar aqui, e não por uma regra sobre `currency`, é o que generaliza:
        # vale para a moeda, a pedra e o cabo de faca sem lista de tipos. O custo
        # é que a recusa gasta uma chamada de juízo — aceito de propósito, em
        # troca de uma regra só. A memória é obrigatória: sem ela A Mente re-tenta
        # em laço sem saber que já tentou (mesmo motivo de `nao_comestivel`).
        if saciedade <= 0:
            rejected.append({
                **base, "regra": "nao_alimenta", "valores": {"item": item_id},
                "why": io._WHY_BY_REGRA["nao_alimenta"],
                "memory": {
                    "content": (f"Pensei em comer {io.name_of(item_id)}, mas vi que "
                                "não ia resolver minha fome e desisti."),
                    "intensity": "small", "involved": [item_id],
                    "valence": {item_id: memoria.NEGATIVA}, "event": "eat_refused"}})
            continue
        toxicidade = int(op.get("toxicidade") or 0)
        consumo = int(op.get("consumo") or 0)
        nova_descricao = (op.get("nova_descricao") or "").strip()
        adoeceu, roll_info = roll_toxicidade_check(
            actor_fm, character_id, item_id, toxicidade, rolls)
        if adoeceu:
            estado._set_condition(actor_folder, "doente")
        rotulo_fome = ("com fome" if saciedade <= 2 else
                       "saciado" if saciedade >= 7 else "sem fome")
        _set_field(actor_folder, "status.hunger", rotulo_fome)
        # spec 049: âncora de decadência por tempo real — junto do rótulo
        # escrito na hora, grava QUANDO comeu e O QUANTO satisfez, pra
        # `hunger_label` derivar o rótulo certo em consultas futuras sem
        # esperar um novo `eat`. Cada ato sobrescreve o par inteiro.
        _set_field(actor_folder, "status.hunger_ts", time.time())
        _set_field(actor_folder, "status.hunger_note", saciedade)
        item_fm, _ = io.read_doc(item_folder / "item.md")
        # capturado ANTES de possivelmente apagar o arquivo (emenda 2.1.0 ao
        # Princípio IV): depois de `remove_entity`, `io.name_of(item_id)` não
        # acha mais o item e cairia no id cru ("maca-03") na memória.
        nome_item = item_fm.get("name") or io.name_of(item_id)
        if consumo <= 0:
            io.remove_entity(item_folder)
        else:
            # nova_descricao pode vir vazia (raro: a resposta combinada pode
            # falhar em dar o texto mesmo com a nota certa). Sem fallback, o
            # item ficaria sem NENHUM sinal de ter sido mordido — silencioso,
            # o que o Princípio X proíbe.
            texto_novo = nova_descricao or f"{nome_item}, parcialmente consumida."
            io.rewrite_description(item_folder, "item.md", texto_novo)
        extremo_bom = saciedade >= 7
        valence = ({item_id: memoria.NEGATIVA} if adoeceu else
                   {item_id: memoria.POSITIVA} if extremo_bom else None)
        intensity = "medium" if (adoeceu or extremo_bom) else "small"
        content = (f"Comi {nome_item} e fiquei doente." if adoeceu else
                   f"Comi {nome_item}: matou a fome." if extremo_bom else
                   f"Comi {nome_item}.")
        applied.append({
            "item": item_id, "adoeceu": adoeceu, "saciedade": saciedade,
            "consumo": consumo, "virada": bool(roll_info.get("virada")),
            "memory": {"content": content, "intensity": intensity,
                       "involved": [item_id], "valence": valence,
                       "event": "eat_sick" if adoeceu else "eat"}})
    return applied, rejected


@registro.handler("eat_ops")
def _h_eat(cid, af, res, rolls):
    applied, rejected = _apply_eat_ops(cid, af, res, rolls)
    return applied, rejected, []  # memória (ator, applied E rejected) via react_actor_memory


# --------------------------------------------------------------------------- #
# Beber (spec 047) — consumir líquido de um item OU de uma fonte ambiental,
# julgado por CINCO réguas já resolvidas pela guarda (`itens/declaracao._drink`):
# bebibilidade, hidratação, embriaguez, toxicidade, e (só para item) consumo+
# nova_descricao. Este executor VALIDA e APLICA; as ÚNICAS decisões não-
# determinísticas são os testes de embriaguez e toxicidade (INDEPENDENTES um do
# outro — o mesmo alvo pode falhar nos dois). Diverge de `eat` em UM ponto
# central (R3 do plano): NUNCA chama `io.remove_entity`, mesmo em consumo 0 —
# sempre `io.rewrite_description`, porque bebida quase sempre tem um
# RECIPIENTE reutilizável que a comida não tem. Um alvo `object` (fonte
# ambiental) NUNCA sofre escrita nenhuma — é inesgotável por definição.
# --------------------------------------------------------------------------- #

def _apply_drink_ops(character_id: str, actor_folder: Path, resolution: dict,
                     rolls: list | None = None) -> tuple[list, list]:
    """Beber de um item ou de uma fonte ambiental (spec 047). Bebibilidade 0
    rejeita — COM memória embutida (small/negativa, mesmo padrão de `eat`).
    Bebibilidade > 0 aplica: hidratação -> rótulo de status.thirst; embriaguez
    -> teste de resistência (mod CON vs alcohol_dc) -> condição 'bêbado' se
    falhar; toxicidade -> MESMO teste (mod CON vs toxin_dc) -> condição
    'doente' se falhar, INDEPENDENTE do de embriaguez; consumo (só ITEM) ->
    `io.rewrite_description` SEMPRE (nunca remove_entity — R3); alvo OBJECT
    (fonte ambiental) nunca sofre escrita nenhuma."""
    applied, rejected = [], []
    if not resolution.get("drink_ops"):
        return applied, rejected
    present_chars, present_objects, present_items = io._scene_entities(actor_folder.parent)  # cena fresca (025)
    actor_fm, _ = io.read_doc(actor_folder / "character.md")
    for op in resolution.get("drink_ops") or []:
        alvo_id = op.get("alvo")
        base = {"beber": alvo_id}
        item_folder = present_items.get(alvo_id)
        object_folder = present_objects.get(alvo_id) if item_folder is None else None
        if item_folder is None and object_folder is None:
            rejected.append(io._rejection(base, io._fail("alvo_inacessivel", alvo=alvo_id)))
            continue
        e_item = item_folder is not None
        if int(op.get("bebibilidade") or 0) <= 0:
            rejected.append({
                **base, "regra": "nao_bebivel", "valores": {"alvo": alvo_id},
                "why": io._WHY_BY_REGRA["nao_bebivel"],
                "memory": {
                    "content": f"Tentei beber de {io.name_of(alvo_id)}, mas não era bebida.",
                    "intensity": "small", "involved": [alvo_id],
                    "valence": {alvo_id: memoria.NEGATIVA}, "event": "drink_refused"}})
            continue
        hidratacao = int(op.get("hidratacao") or 0)
        embriaguez = int(op.get("embriaguez") or 0)
        toxicidade = int(op.get("toxicidade") or 0)
        embebedou, roll_emb = roll_embriaguez_check(
            actor_fm, character_id, alvo_id, embriaguez, rolls)
        adoeceu, roll_tox = roll_toxicidade_check(
            actor_fm, character_id, alvo_id, toxicidade, rolls)
        if embebedou:
            estado._set_condition(actor_folder, "bêbado")
        if adoeceu:
            estado._set_condition(actor_folder, "doente")
        rotulo_sede = ("com sede" if hidratacao <= 2 else
                       "hidratado" if hidratacao >= 7 else "sem sede")
        _set_field(actor_folder, "status.thirst", rotulo_sede)
        # spec 049: âncora de decadência por tempo real — mesmo par de `eat`
        # (`status.hunger_ts`/`hunger_note`), espelhado para sede. Cada ato
        # de beber sobrescreve o par inteiro.
        _set_field(actor_folder, "status.thirst_ts", time.time())
        _set_field(actor_folder, "status.thirst_note", hidratacao)
        # capturado ANTES de qualquer reescrita, no mesmo espírito de `eat`
        # (ainda que aqui o alvo NUNCA seja removido — R3 — o nome vem do
        # frontmatter atual, não do id cru).
        if e_item:
            item_fm, _ = io.read_doc(item_folder / "item.md")
            nome_alvo = item_fm.get("name") or io.name_of(alvo_id)
            consumo = int(op.get("consumo") or 0)
            nova_descricao = (op.get("nova_descricao") or "").strip()
            # texto sem número correspondente não pode virar "vazio" calado —
            # mesmo achado que `eat` já registrou para a régua de consumo.
            texto_novo = nova_descricao or f"{nome_alvo}, vazio."
            io.rewrite_description(item_folder, "item.md", texto_novo)
        else:
            nome_alvo = io.name_of(alvo_id)
            consumo = None  # fonte ambiental: régua de consumo não existe (R1/R4)
        extremo_bom = hidratacao >= 7
        valence = ({alvo_id: memoria.NEGATIVA} if (adoeceu or embebedou) else
                   {alvo_id: memoria.POSITIVA} if extremo_bom else None)
        intensity = "medium" if (adoeceu or embebedou or extremo_bom) else "small"
        # memória COMBINADA quando os dois testes falham no mesmo consumo —
        # nunca duas memórias do mesmo ato (FR-014/R9).
        if adoeceu and embebedou:
            content = f"Bebi de {nome_alvo}, fiquei bêbado e passei mal."
            event = "drink_sick_drunk"
        elif adoeceu:
            content = f"Bebi de {nome_alvo} e passei mal."
            event = "drink_sick"
        elif embebedou:
            content = f"Bebi de {nome_alvo} e fiquei bêbado."
            event = "drink_drunk"
        elif extremo_bom:
            content = f"Bebi de {nome_alvo} e me senti ótimo."
            event = "drink_sated"
        else:
            content = f"Bebi de {nome_alvo}."
            event = "drink"
        applied.append({
            "alvo": alvo_id, "adoeceu": adoeceu, "embebedou": embebedou,
            "hidratacao": hidratacao, "consumo": consumo,
            "virada": bool(roll_tox.get("virada") or roll_emb.get("virada")),
            "memory": {"content": content, "intensity": intensity,
                       "involved": [alvo_id], "valence": valence, "event": event}})
    return applied, rejected


@registro.handler("drink_ops")
def _h_drink(cid, af, res, rolls):
    applied, rejected = _apply_drink_ops(cid, af, res, rolls)
    return applied, rejected, []  # memória (ator, applied E rejected) via react_actor_memory
