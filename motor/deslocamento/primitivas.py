"""O Motor / deslocamento — PRIMITIVAS (item 31 §3: DDD por domínio).

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



def roll_persuasion_check(actor_fm: dict, char_id: str, alvo_id: str,
                          rota_id: str, vontade: int,
                          alvo_fm: dict | None = None) -> tuple[dict | None, dict | None]:
    """Teste de persuasão da zona 1–9 (spec 007). Retorna (rejeicao, roll_info).

    Vontade 10 é determinística (sem dado, sem registro): (None, None) — espelho da
    zona trivial do empurrar. A vontade NUNCA entra no roll_info nem nos valores da
    rejeição (segredo do mundo, FR-002); a tendência qualitativa entra no lugar.
    `critico` só quando o extremo do dado ALINHOU com o desfecho (20 e passou / 1 e
    falhou)."""
    if int(vontade) >= 10:
        return None, None
    d20 = rolagem._roll_d20()
    mod = attr_modifier((actor_fm.get("attributes") or {}).get("CHA", 10))
    dc = persuade_dc(vontade)
    # spec 030 (Frente B): persuadir alguém exausto a fazer algo que exigiria
    # esforço DELE (viajar) é mais difícil — só quando o pedido tem custo de
    # fadiga associado (_CUSTO_VIAGEM), nunca para persuasão sem esforço físico.
    if alvo_fm is not None and fisica._CUSTOS_FADIGA.get(_CUSTO_VIAGEM, 0) > 0:
        fadiga, teto = fisica.ensure_fatigue(alvo_fm)
        dc += memoria.fatigue_penalty(fadiga, teto)
    total = d20 + mod
    passou = total >= dc
    tendencia = persuade_tendencia(vontade)
    virada = (tendencia == "ir" and not passou) or (tendencia == "ficar" and passou)
    critico = ("sucesso" if (d20 == 20 and passou)
               else "falha" if (d20 == 1 and not passou) else None)
    info = {
        "tipo": "persuasao",
        "personagem": char_id, "alvo": alvo_id, "rota": rota_id,
        "tendencia": tendencia,
        "resultado": "sucesso" if passou else "falha",
        "virada": virada, "critico": critico,
        "rolagem": {"d20": d20, "mod": mod, "total": total, "dc": dc},
    }
    if passou:
        return None, info
    rej = _fail("persuasao_falhou", alvo=alvo_id, personagem=char_id, rota=rota_id,
                tendencia=tendencia, virada=virada, critico=critico,
                rolagem=info["rolagem"])
    return rej, info


def _interrupt_travels(character_id: str, present_chars: dict,
                       outcome: dict) -> list[dict]:
    """Quem foi ALVO de alguma ação neste turno tem a viagem cancelada (FR-008).

    Um ponto só, pelo mesmo argumento que a spec 013 usou em `_record_events`:
    instrumentar cada tool espalharia a regra por oito lugares e garantiria que
    a nona esquecesse.

    Lê os APLICADOS **e os REJEITADOS**, e essa é a parte fácil de errar: o
    golpe que ERRA interrompe a viagem do mesmo jeito, porque o que para o
    viajante é ser abordado, não ser ferido. Uma leitura só dos `_applied`
    deixaria passar exatamente o caso que a FR-008 cita por extenso.

    Viagem não é bolha: sem isto, quem atravessa o mapa seria intocável no
    caminho e o mundo deixaria de acontecer com ele.
    """
    alvos: set[str] = set()

    def colher(op):
        if not isinstance(op, dict):
            return
        for campo in ("alvo", "personagem", "parceiro", "to", "destino_personagem"):
            v = op.get(campo)
            if isinstance(v, str) and v != character_id:
                alvos.add(v)

    for canal in ("attack_ops_applied", "carry_ops_applied",
                  "persuade_ops_applied", "trade_ops_applied",
                  "item_transfers_applied"):
        for op in outcome.get(canal) or []:
            colher(op)
    # a ação NEGADA também abordou alguém
    for rej in outcome.get("rejected") or []:
        colher(rej)
        valores = rej.get("valores")
        if isinstance(valores, dict):
            colher(valores)

    interrompidas = []
    for alvo in sorted(alvos):
        folder = present_chars.get(alvo)
        if folder is None or not (folder / "character.md").exists():
            try:
                folder = find_character_folder(alvo)
            except Exception:
                continue
        if _cancel_travel(folder, "alguém o abordou no caminho"):
            interrompidas.append({"personagem": alvo})
    return interrompidas


def _cancel_travel(character_folder: Path, motivo: str) -> bool:
    """Descarta o plano de viagem preservando a POSIÇÃO (FR-008).

    Interromper não teleporta ninguém: ele fica exatamente onde estava, seja
    numa rota ou de passagem por um lugar. O que morre é o plano — e ninguém
    retoma sozinho. Quem quiser seguir, pede de novo.
    """
    char_file = character_folder / "character.md"
    if not char_file.exists():
        return False
    fm, body = read_doc(char_file)
    transit = fm.get("transit")
    if not isinstance(transit, dict) or not transit.get("plano"):
        return False  # não estava em viagem longa: nada a cancelar
    destino_final = transit.get("destino_final")
    transit["plano"] = []
    transit.pop("destino_final", None)
    fm["jornada_interrompida"] = {"destino_final": destino_final, "motivo": motivo}
    write_doc(char_file, fm, body)
    return True


def cancel_travel_plan(character_id: str, motivo: str) -> bool:
    """Cancelamento público do plano de viagem (adquire o lock). Ver _cancel_travel."""
    with WRITE_LOCK:
        try:
            folder = find_character_folder(character_id)
        except MotorError:
            return False
        return _cancel_travel(folder, motivo)


def set_travel_plan(char_folder: Path, destino: str, pernas: list) -> None:
    """Primitiva de ESTADO (spec 038): grava o PLANO de viagem DENTRO do `transit`
    já existente (destino_final + pernas restantes) e limpa `jornada_interrompida`
    (viagem nova, história limpa). NÃO cria `transit` — só o preenche se ele existe
    (o personagem acabou de entrar na 1ª perna). Assume o WRITE_LOCK."""
    fm, body = read_doc(char_folder / "character.md")
    if not isinstance(fm.get("transit"), dict):
        return
    fm["transit"]["destino_final"] = destino
    fm["transit"]["plano"] = pernas
    fm.pop("jornada_interrompida", None)
    write_doc(char_folder / "character.md", fm, body)


def lazy_evaluate() -> None:
    """Resolve chegadas em rota na consulta ao mundo.

    Sem processos de fundo: o tempo "passa" quando o mundo é consultado (FR-020).

    A expiração de memória saiu daqui (spec 013): varrer TODO o mundo a cada
    consulta era barato com 9 memórias e deixa de ser quando cada turno gera
    uma. Passou a rodar por personagem, em `_expire_memories`, no momento em
    que as memórias dele são lidas — que é o modelo preguiçoso aplicado onde
    ele de fato pertence (Princípio VII).
    """
    with WRITE_LOCK:
        _resolve_arrivals()


def directions_from(informante_id: str) -> dict:
    """Os caminhos que este personagem SABE explicar — consulta de SERVER (spec 015).

    Molde do `offered_by`: o que alguém tem a oferecer não está à vista, e
    ninguém adivinha o que não viu. Aqui o que não está à vista é o que ele
    conhece da região.

    Entra só o que `knows_route` aprova — memória de rota VIVA. Lembrança vaga
    (`recognizes_route` sem `knows_route`) fica DE FORA: quem já não sabe
    percorrer não sabe explicar, e essa é a mesma fronteira entre saber e
    reconhecer que a spec 013 desenhou.

    A prosa vai COMO ESTÁ, sem resumo — e não é só fidelidade: é ela que cai em
    `queue["lido"]` e vira o alvo da citação conferida. Uma fonte que devolvesse
    uma lista de ids seria INCONFERÍVEL, e reabriria por uma porta nova a brecha
    que a conferência fechou (dois falsos positivos medidos na spec 014).

    Caminho sem prosa nenhuma no `.md` fica fora: não haveria o que citar.
    """
    folder = find_character_folder(informante_id)
    fm, _ = read_doc(folder / "character.md")
    caminhos = []
    for route_id in all_route_ids():
        if not knows_route(informante_id, route_id):
            continue
        found = find_route(route_id)
        if not found:
            continue
        _path, rfm, body = found
        prosa = (body or "").strip()
        if not prosa:
            continue
        caminhos.append({"rota": route_id,
                         "nome": rfm.get("name") or route_id,
                         "prosa": prosa})
    return {"personagem": informante_id,
            "nome": fm.get("name") or informante_id,
            "caminhos": caminhos}


def route_plan(character_id: str, destino: str) -> list[str] | None:
    """O trajeto que ELE consegue fazer até o destino, ou None se não souber.

    Anda só as arestas que `knows_route` aprova — memória VIVA de rota. É o que
    separa comodidade de onisciência: quem não sabe o caminho explora perna a
    perna, como sempre.

    Escolhe o de MENOR TEMPO, e desempata pelo id da rota em ordem alfabética.
    O desempate não é preciosismo: sem ele a ordem viria do `rglob` do sistema
    de arquivos, que não é estável entre máquinas, e a FR-012 (mesmo pedido,
    mesmo trajeto) cairia sem nada acusar.

    Os modificadores pessoais (fadiga, carga, velocidade do que veste) e os
    PRÉ-REQUISITOS ficam de fora de propósito: mudam durante a viagem, e
    pré-aprová-los aqui quebraria a FR-005 em silêncio. A busca escolhe o
    trajeto; cada perna cobra e valida o próprio preço na hora de entrar.
    """
    folder = find_character_folder(character_id)
    loc_file = folder.parent / "location.md"
    if not loc_file.exists():
        return None  # já está em rota: não se planeja viagem de dentro do caminho
    origem_fm, _ = read_doc(loc_file)
    origem = origem_fm.get("id")
    if not origem or not destino or origem == destino:
        return None

    # arestas do grafo DELE: só rotas de que há memória viva
    saidas: dict[str, list[tuple[str, str, int]]] = {}
    for path in sorted(WORLD_DIR.rglob("route.md")):
        rfm, _ = read_doc(path)
        rid = rfm.get("id")
        if not rid or not knows_route(character_id, rid):
            continue
        base = int(rfm.get("travel_time_base") or 0)
        for de in (rfm.get("from"), rfm.get("to")):
            if not de:
                continue
            para = _route_destination(rfm, de)
            if para:
                saidas.setdefault(de, []).append((rid, para, base))

    # Dijkstra pequeno: (custo, trajeto de ids). Sem heap — o grafo tem dezenas
    # de arestas, e clareza vale mais que microssegundos aqui.
    melhor: dict[str, tuple[int, list[str]]] = {origem: (0, [])}
    fronteira = [origem]
    while fronteira:
        atual = fronteira.pop(0)
        custo_ate, trajeto = melhor[atual]
        for rid, para, base in sorted(saidas.get(atual, []), key=lambda a: a[0]):
            custo = custo_ate + base + _crossing_time_of(para)
            candidato = trajeto + [rid]
            atual_melhor = melhor.get(para)
            # empate desfeito pelo trajeto alfabético: determinismo (FR-012)
            if atual_melhor is None or (custo, candidato) < atual_melhor:
                melhor[para] = (custo, candidato)
                fronteira.append(para)
    achado = melhor.get(destino)
    return achado[1] if achado else None


def current_location_id(character_id: str) -> str | None:
    """O lugar onde o personagem está AGORA (spec 034, US2) — mesmo `aqui` que
    `reachable_destinations` já calcula por dentro, exposto para quem monta o
    enum de "sobre um lugar" de `ask_about` (soma cena atual + conhecidos)."""
    try:
        folder = find_character_folder(character_id)
    except MotorError:
        return None
    loc_file = folder.parent / "location.md"
    if not loc_file.exists():
        return None
    return (read_doc(loc_file)[0]).get("id")


def reachable_destinations(character_id: str) -> list[str]:
    """Lugares a que ele sabe chegar — enum de `travel_to`, consulta de SERVER.

    Não sai no contexto: o mapa do que ele sabe é memória de rota, que a spec
    013 manteve fora do client de propósito. Quem enxerga é o Árbitro, lendo o
    mundo — como já faz com `offered_by()` no comércio (Princípio IX).

    Efeito de desenho: destino que ele não sabe alcançar NÃO VIRA ENUM, então a
    regra "só se sabe o caminho" é cumprida pela montagem do manifest, antes de
    qualquer guarda. O modelo não pode pedir o que não vê.
    """
    try:
        folder = find_character_folder(character_id)
    except MotorError:
        return []
    loc_file = folder.parent / "location.md"
    if not loc_file.exists():
        return []
    aqui = (read_doc(loc_file)[0]).get("id")
    out = []
    for path in sorted(WORLD_DIR.rglob("location.md")):
        fm, _ = read_doc(path)
        lid = fm.get("id")
        if lid and lid != aqui and route_plan(character_id, lid):
            out.append(lid)
    return sorted(out)


def known_routes(character_id: str) -> dict:
    """O mapa que o personagem traz na cabeça — consulta de CLIENT (Princípio IX).

    Memória de rota não desce no contexto (é maquinaria de viagem, e a Mente não
    precisa dela para narrar), mas o que ELE sabe é percepção dele: cabe pedir.

    Anda o grafo a partir de onde está, atravessando SÓ os caminhos de que há
    lembrança — nunca os que existem no mundo e ele desconhece. Por isso o mapa
    é dele e não do mundo: dois personagens no mesmo lugar veem árvores
    diferentes.

    Cada trecho vem marcado `sabe` (memória viva) ou `vago` (memória vencida:
    esteve por lá, não confia mais no caminho) — a distinção que separa saber de
    reconhecer.
    """
    folder = find_character_folder(character_id)
    fm, _ = read_doc(folder / "character.md")

    transit = fm.get("transit") if isinstance(fm.get("transit"), dict) else None
    if transit:
        raiz = transit.get("destination")
        de_onde = "para onde vai"
    else:
        loc_fm, _ = read_doc(folder.parent / "location.md")
        raiz = loc_fm.get("id")
        de_onde = "onde está"

    # o que ele lembra, por rota: viva ganha de vencida
    lembradas: dict[str, bool] = {}
    for mem in _iter_memories(character_id):
        if memory_kind(mem) != ROTA:
            continue
        rid = memory_about(mem)
        if rid:
            lembradas[rid] = lembradas.get(rid, False) or _is_alive(mem)

    rotas = []
    for path in sorted(WORLD_DIR.rglob("route.md")):
        rfm, _ = read_doc(path)
        if rfm.get("id") in lembradas:
            rotas.append(rfm)

    def ramos(loc_id: str, visitados: set[str]) -> list[dict]:
        out = []
        for rfm in rotas:
            rid = rfm.get("id")
            dest = _route_destination(rfm, loc_id)
            if not dest or rid in visitados:
                continue
            filhos = ramos(dest, visitados | {rid})
            out.append({
                "route_id": rid,
                "route_name": rfm.get("name") or rid,
                "destination_id": dest,
                "destination_name": _location_name(dest),
                "certeza": "sabe" if lembradas.get(rid) else "vago",
                "ramos": filhos,
            })
        out.sort(key=lambda r: r["route_name"])
        return out

    return {
        "raiz_id": raiz,
        "raiz_nome": _location_name(raiz) if raiz else "",
        "raiz_rotulo": de_onde,
        "em_transito": bool(transit),
        "ramos": ramos(raiz, set()) if raiz else [],
        "total": len(lembradas),
    }


def _witness_movement(location_folder: Path, mover_id: str, evento: str,
                              outro_lugar_id: str | None = None,
                              excluir: frozenset[str] = frozenset()) -> None:
    """Espalha memória factual de PARTIDA/CHEGADA pelos presentes que já
    estão no lugar (spec 034, US1).

    Código PRÓPRIO de deslocamento (nível 1) — nunca uma entrada em
    `memoria._witness_facts`/`_record_witness` (o dispatcher transversal
    de fim-de-turno, que só conhece fatos de `outcome` de turno). Chama
    direto as primitivas de nível 0 já reusáveis (`_witness_intensity`,
    `_write_memory`), mesma relação de camadas que qualquer outra família
    já tem com `memoria.py` — sem depender de `turno.py`.

    Sempre PÚBLICO nesta v1 (sem variante furtiva de deslocamento): só o
    piso de saliência (`base="small"`) decide quem guarda — banal, só
    gruda em quem já tem vínculo com quem se moveu (mesma regra que
    golpe/furto/etc. já respeitam para fatos banais).

    `outro_lugar_id` é o destino (partida) ou a origem (chegada) — quem
    testemunha uma partida/chegada por uma rota especifica VÊ por onde
    foi/de onde veio (informação perceptível, não segredo). Entra tanto na
    PROSA ("rumo a"/"vindo de") quanto em `involved`, ao lado do lugar
    ATUAL (`location_folder`) — sem isso, perguntar sobre O LUGAR (US2)
    nunca encontraria estes episódios, contradizendo o próprio spec.md.
    """
    loc_fm, _ = read_doc(location_folder / "location.md")
    loc_id = loc_fm.get("id")
    nome = name_of(mover_id)
    involved = [mover_id] + [x for x in (loc_id, outro_lugar_id) if x]
    if evento == "witness_departure":
        cauda = f", rumo a {name_of(outro_lugar_id)}" if outro_lugar_id else ""
        verbo = "partir"
    else:
        cauda = f", vindo de {name_of(outro_lugar_id)}" if outro_lugar_id else ""
        verbo = "chegar"
    texto = f"Vi {nome} {verbo}{cauda}."
    characters, _objects, _items = io._scene_entities(location_folder)
    for wid, wfolder in characters.items():
        if wid == mover_id or wid in excluir:
            continue
        wfm, _ = read_doc(wfolder / "character.md")
        if not wfm or is_down(wfm):
            continue  # caído não testemunha (mesma regra G2 de _record_witness)
        intens = _witness_intensity(wid, "small", involved=[mover_id])
        if intens is None:
            continue
        _write_memory(wfolder, texto, kind=ACONTECIMENTO,
                      intensity=intens, involved=involved, evento=evento)


def enter_route(character_id: str, route_id: str) -> dict:
    """Entrada pública em rota (adquire o lock). Ver _enter_route_locked."""
    with WRITE_LOCK:
        return _enter_route_locked(character_id, route_id)


def carry_time_penalty(base: int, peso: float, capacidade: float) -> int:
    """Atraso por levar alguém junto (spec 010): quanto mais perto do limite do
    corpo, mais lento. Linear na fração da capacidade usada, no espírito do
    `_travel_modifier` (que soma 50% por fadiga alta). MVP revisável."""
    if base <= 0 or capacidade <= 0:
        return 0
    return round(base * min(2.0, peso / capacidade))


def _enter_route_locked(character_id: str, route_id: str,
                        passenger_id: str | None = None) -> dict:
    """Move o personagem para dentro da rota, se os prerequisites permitirem.

    A mudança de lugar é o rename atômico da pasta (nunca em dois lugares — SC-004).
    Retorna {"moved": bool, ...} com destino/tempo ou o motivo da negação.

    Com `passenger_id` (spec 010), leva OUTRO personagem junto: os prerequisites
    e o tempo saem de quem CARREGA (o passageiro é bagagem, não viajante), o
    tempo ganha a penalidade da carga, e o passageiro recebe um `transit` com o
    MESMO `arrive_ts` — é isso, e só isso, que faz os dois chegarem juntos, já
    que `_resolve_arrivals` move cada um pelo próprio prazo.
    """
    actor_folder = find_character_folder(character_id)
    place_folder = actor_folder.parent
    loc_file = place_folder / "location.md"
    if not loc_file.exists():
        return {"moved": False, "reason": "você já está a caminho."}
    loc_fm, _ = read_doc(loc_file)
    loc_id = loc_fm.get("id")

    found = find_route(route_id)
    if not found:
        return {"moved": False, "reason": "não há tal caminho a partir daqui."}
    route_folder, route_fm, _ = found
    dest = _route_destination(route_fm, loc_id)
    if not dest:
        return {"moved": False, "reason": "esse caminho não parte daqui."}
    dest_folder = _location_folder_by_id(dest)
    if dest_folder is None:
        return {"moved": False, "reason": "o destino não existe no mundo."}

    actor_fm, actor_body = read_doc(actor_folder / "character.md")
    denial = _check_prerequisites(route_fm, actor_folder, actor_fm)
    if denial:
        return {"moved": False, "reason": denial}

    passenger_folder = None
    if passenger_id is not None:
        passenger_folder = find_character_folder(passenger_id)
        if passenger_folder.parent != place_folder:
            return {"moved": False, "reason": "não está ao alcance."}

    base = int(route_fm.get("travel_time_base") or 0)
    travel = max(0, base + _travel_modifier(base, actor_fm))
    if passenger_folder is not None:
        travel += carry_time_penalty(base, total_weight_of(passenger_folder),
                                     carry_capacity(actor_fm))
    # o que ele VESTE encurta o caminho (spec 009): divide por último, sobre o
    # tempo que a viagem levaria de outro modo — fadiga e carga inclusive. A capa
    # de quem é CARREGADO não conta: quem caminha é o carregador.
    travel = apply_speed(travel, speed_multiplier_of(actor_folder))
    now = int(time.time())
    transit = {
        "route": route_id,
        "origin": loc_id,
        "destination": dest,
        "depart_ts": now,
        "arrive_ts": now + travel,
    }
    actor_fm["transit"] = dict(transit)
    # grava o trânsito ANTES de mover: se a pasta já está na rota, o estado é coerente
    write_doc(actor_folder / "character.md", actor_fm, actor_body)
    # usar renova (spec 013): quem percorre não esquece o caminho. Antes do
    # rename, enquanto a pasta ainda está no lugar conhecido.
    _remember_route(actor_folder, route_id, route_fm.get("name") or "")
    # spec 034 (US1/US4): testemunha da PARTIDA + marca física no lugar de
    # ORIGEM — sempre ANTES do rename, enquanto place_folder ainda reflete
    # quem estava lá. Incondicional (a marca nasce com ou sem plateia).
    _excluir_partida = frozenset({passenger_id}) if passenger_id else frozenset()
    _witness_movement(place_folder, character_id, "witness_departure",
                              outro_lugar_id=dest, excluir=_excluir_partida)
    _leave_trace(place_folder, character_id, route_id, "partida")
    io.move_entity(actor_folder, route_folder / actor_folder.name)  # rename atômico
    if passenger_folder is not None:
        p_fm, p_body = read_doc(passenger_folder / "character.md")
        p_fm["transit"] = dict(transit)  # MESMO arrive_ts: chegam juntos
        write_doc(passenger_folder / "character.md", p_fm, p_body)
        # quem é carregado também aprende o caminho: viu por onde foi
        _remember_route(passenger_folder, route_id, route_fm.get("name") or "")
        io.move_entity(passenger_folder, route_folder / passenger_folder.name)
    return {
        "moved": True,
        "route": route_id,
        "route_name": route_fm.get("name"),
        "destination": dest,
        "destination_name": _location_name(dest),
        "travel_time": travel,
        "arrive_ts": now + travel,
    }


def _resolve_arrivals() -> None:
    """Chegadas preguiçosas: quem cumpriu o tempo migra ao destino.

    Com a spec 012, é aqui também que a viagem LONGA avança — e é de propósito:
    esta função já roda a cada consulta ao mundo, já move pasta com rename
    atômico e já trata destino sumido. Avançar em qualquer outro lugar criaria
    um segundo relógio, e a FR-007 existe para impedir exatamente isso.

    Dois trânsitos passam por aqui, distinguidos pelo que o `transit` traz:
      - COM `route`: está numa rota, chega ao lugar do outro lado
      - SEM `route`: está de passagem POR um lugar, e ao fim parte na próxima
    """
    now = time.time()
    # em rota: a pasta está dentro da rota
    for route_path in list(WORLD_DIR.rglob("route.md")):
        route_folder = route_path.parent
        for child in list(route_folder.iterdir()):
            char_file = child / "character.md"
            if not child.is_dir() or not char_file.exists():
                continue
            fm, body = read_doc(char_file)
            transit = fm.get("transit")
            if not isinstance(transit, dict):
                continue
            if now < (transit.get("arrive_ts") or 0):
                continue
            dest_folder = _location_folder_by_id(transit.get("destination"))
            if dest_folder is None:
                continue  # destino sumiu do mundo: deixa em trânsito (defensivo)
            plano = [r for r in (transit.get("plano") or []) if isinstance(r, str)]
            destino_final = transit.get("destino_final")
            chegou_ao_fim = not plano
            status = fm.setdefault("status", {})
            if chegou_ao_fim or is_down(fm):
                # fim da linha (ou caiu no caminho: quem está caído não anda)
                fm.pop("transit", None)
                status["action"] = ("jaz onde o deixaram" if is_down(fm)
                                    else "acabou de chegar, ainda se ambientando ao lugar")
                # chegar a um lugar liga o lugar à história (spec 016): apego por
                # frequência, neutro. A memória vai na pasta AINDA no lugar antigo
                # e viaja junto no rename atômico abaixo. Só na chegada FINAL — de
                # passagem não se cria vínculo.
                if chegou_ao_fim and not is_down(fm):
                    destino_id = transit.get("destination")
                    _write_memory(
                        child, f"Cheguei a {name_of(destino_id)}.",
                        intensity="small", involved=[destino_id],
                        summary=f"cheguei a {name_of(destino_id)}")
            else:
                # ainda falta caminho: entra de PASSAGEM pelo lugar. Atravessá-lo
                # custa tempo, e é isso que faz o viajante existir aqui em vez de
                # saltar direto para a próxima rota.
                dest_fm, _ = read_doc(dest_folder / "location.md")
                travessia = crossing_time(dest_fm)
                fm["transit"] = {
                    "origin": transit.get("destination"),
                    "destination": transit.get("destination"),
                    "depart_ts": int(now),
                    "arrive_ts": int(now) + travessia,
                    "destino_final": destino_final,
                    "plano": plano,
                }
                status["action"] = "atravessa o lugar, de passagem"
            write_doc(char_file, fm, body)
            # spec 034 (US1/US4): testemunha da CHEGADA + marca física no
            # lugar de DESTINO — sempre ANTES do rename, enquanto
            # dest_folder ainda reflete quem já estava lá. Cobre os DOIS
            # ramos (chegada final e de passagem); pula só quem caiu no
            # caminho (não há chegada de pé a testemunhar/traçar).
            if not is_down(fm):
                cid = fm.get("id")
                if cid:
                    _witness_movement(dest_folder, cid, "witness_arrival",
                                              outro_lugar_id=transit.get("origin"))
                    _leave_trace(dest_folder, cid, transit.get("route"),
                                   "chegada")
            io.move_entity(child, dest_folder / child.name)  # rename atômico ao destino

    # de passagem por um lugar: a pasta já está na location, e o `transit` não
    # tem `route`. Cumprido o tempo de travessia, parte na próxima perna.
    for loc_path in list(WORLD_DIR.rglob("location.md")):
        loc_folder = loc_path.parent
        for child in list(loc_folder.iterdir()):
            char_file = child / "character.md"
            if not child.is_dir() or not char_file.exists():
                continue
            fm, body = read_doc(char_file)
            transit = fm.get("transit")
            if not isinstance(transit, dict) or transit.get("route"):
                continue
            if now < (transit.get("arrive_ts") or 0):
                continue
            plano = [r for r in (transit.get("plano") or []) if isinstance(r, str)]
            cid = fm.get("id")
            if is_down(fm) or not plano or not cid:
                # caiu no meio do caminho, ou não há mais o que andar
                fm.pop("transit", None)
                fm.setdefault("status", {})["action"] = (
                    "jaz onde o deixaram" if is_down(fm)
                    else "acabou de chegar, ainda se ambientando ao lugar")
                write_doc(char_file, fm, body)
                continue
            # limpa o trânsito ANTES de entrar na rota: _enter_route_locked
            # pressupõe alguém parado num lugar
            proxima, resto = plano[0], plano[1:]
            destino_final = transit.get("destino_final")
            fm.pop("transit", None)
            write_doc(char_file, fm, body)
            resultado = _enter_route_locked(cid, proxima)
            if not resultado.get("moved"):
                # perna negada NO MEIO (FR-006): para aqui, plano descartado. As
                # pernas anteriores aconteceram; as seguintes, não.
                fm2, body2 = read_doc(char_file)
                fm2.setdefault("status", {})["action"] = "parou no caminho"
                fm2["jornada_interrompida"] = {
                    "destino_final": destino_final,
                    "motivo": resultado.get("reason") or "o caminho não se abriu",
                }
                write_doc(char_file, fm2, body2)
                continue
            # entrou: repõe o resto do plano no trânsito novo
            novo_folder = find_character_folder(cid)
            fm3, body3 = read_doc(novo_folder / "character.md")
            if isinstance(fm3.get("transit"), dict):
                fm3["transit"]["plano"] = resto
                fm3["transit"]["destino_final"] = destino_final
                write_doc(novo_folder / "character.md", fm3, body3)


