"""O Motor / percepcao (spec 021 — extraído de __init__).

Parte do pacote em níveis. Ver research.md (T001) para o grafo de dependências.
"""
from __future__ import annotations

import os
import random
import re
import threading
import time
import uuid
import unicodedata
from pathlib import Path

import frontmatter
import validator

from .. import (deslocamento, fisica, intencoes, io, memoria, registro,
                rotas, trabalho, vinculos)
from ..deslocamento import (
    lazy_evaluate,
)
from ..fisica import (
    hunger_label,
    thirst_label,
    fatigue_label,
    sono_label,
    sleep_state,
    _inside_closed,
    _direct_items,
    _is_wide_open,
    _walk_open_items,
    body_of,
    carried_item_ids,
    carried_weight,
    carry_capacity,
    effective_weight,
    grasp_slot_of,
    has_accessible_item,
    is_closed,
    is_currency,
    is_down,
    is_for_sale,
    is_negotiable,
    item_own_weight,
    item_size,
    item_slot,
    push_capacity,
    slot_capacity,
    slots_in_use,
    value_of,
)
from ..io import (
    arquivos_em,
    arquivos_no_mundo,
    MotorError,
    WORLD_DIR,
    _char_fm,
    _is_valid,
    find_character_folder,
    find_entity,
    read_doc,
)
from ..memoria import (
    ROTA,
    _FAMILIARIDADE_PISO,
    _INTENSITY_ORDER,
    _MEMORY_CONTEXT_CAP,
    _densidade_rastro,
    _expire_memories,
    _is_alive,
    _renew_memory,
    _resolver_rastros,
    alvos_investigaveis,
    alcance_consulta,
    alcance_contexto,
    _memory_salience,
    _recency_label,
    _short_summary,
    sentiment_label,
    dono,
    dono_reconhecido,
    familiarity_label,
    familiarity_with,
    get_active_memories,
    memory_involved,
    memory_kind,
    sentiment_toward,
)
from ..rotas import (
    _available_routes,
)


# spec 066: o corte abaixo do qual o afeto NÃO desce. É o MESMO 2 que `sentiment_label`
# usa como fronteira de "guarda um leve incômodo"/"nutre alguma simpatia", e o mesmo que
# o Árbitro já aplicava em `afeto_por_lugar`/`afeto_por_voce` — um lugar só decide o
# limiar. Abaixo dele a única faixa disponível seria "sem história que pese num sentido
# ou noutro", que não compõe frase e só inflaria o contexto.
_AFETO_PISO = 2


def item_physics(fm: dict, folder: Path | None = None) -> dict:
    """Bloco físico de um item para o contexto (Mente e guarda do Árbitro)."""
    container = fm.get("container")
    cont = None
    if isinstance(container, dict) and container.get("max_size"):
        cont = {
            "max_size": container.get("max_size"),
            "max_items": container.get("max_items"),
            "itens": len(_direct_items(folder)) if folder else 0,
            "fechado": is_closed(fm),
        }
    wearable = fm.get("wearable")
    bloco = {
        "size": item_size(fm),
        "weight_kg": round(effective_weight(folder) if folder else item_own_weight(fm), 3),
        "veste_em": wearable.get("slot") if isinstance(wearable, dict) else None,
        "container": cont,
        "slot": item_slot(fm),
    }
    # Comércio (spec 011). Estas marcas descem ao contexto pelo critério do
    # Princípio IX — PERCEPÇÃO, não conveniência: uma banca mostra o que está à
    # venda e por quanto, e o que não está exposto simplesmente não se vê como
    # disponível. Só aparecem quando declaradas; item sem marca não vira ruído.
    if is_for_sale(fm):
        bloco["for_sale"] = True
    if is_negotiable(fm):
        bloco["negotiable"] = True
    if is_currency(fm):
        bloco["currency"] = True
    preco = value_of(fm)
    if preco is not None:
        bloco["value"] = preco
    return bloco


def _character_summary(folder: Path, self_id: str) -> dict:
    fm, _ = read_doc(folder / "character.md")
    status = fm.get("status") or {}
    # spec 019: "mãos" na verdade é o SLOT DE PEGA deste corpo (a boca do cão), e
    # a capacidade sai dele. Os nomes maos_* seguem no contrato por estabilidade.
    pega = grasp_slot_of(fm)
    hands = (slots_in_use(folder).get(pega) or []) if pega else []
    cap_pega = slot_capacity(fm, pega) if pega else 0
    bloco = {
        "id": fm.get("id"),
        "name": fm.get("name"),
        "state": "self" if fm.get("id") == self_id else "idle",
        "action": status.get("action"),
        "mood": status.get("mood"),
        "conditions": status.get("conditions") or [],
        # O que os OUTROS veem: apenas o acoplado ao corpo (vestido/segurado).
        # Item guardado dentro de contêiner é invisível a terceiros (spec 004,
        # FR-009) — o que está no bolso não se vê. Pra SI MESMO (spec 036,
        # FR-010) a visão é a mesma que `self.inventory`/`get_inventory` já
        # usam — `_nested_item_refs`, recursiva e sem a opacidade de
        # terceiro — não `_visible_item_refs`, que ficaria incorreta pro
        # próprio personagem quando `visible_entities` virar simétrica.
        "carrying": (_nested_item_refs(folder) if fm.get("id") == self_id
                    else _visible_item_refs(folder)),
        # física visível do corpo: pega e folga de carga (a guarda do Árbitro
        # valida dar/receber sem expor atributos crus de terceiros)
        "body_status": {
            "free_hands": max(0, cap_pega - len(hands)),
            "total_hands": cap_pega,
            "grasp_slot": pega,
            "hands_holding": hands,
            "free_load_kg": round(carry_capacity(fm) - carried_weight(folder), 3),
        },
    }
    # spec 066 — O FATO NA ENTIDADE A QUE ELE SE REFERE.
    #
    # `bond` é a CAMADA 2 (fato declarado); `sentiment` é a CAMADA 3 (crença derivada).
    # Os dois eixos são ORTOGONAIS: o irmão que se odeia tem `bond` e `sentiment`
    # negativo ao mesmo tempo, e é a célula que motivou a spec. Nenhum dos dois soma no
    # outro, e nenhum entra em DC (FR-017, FR-018).
    #
    # Só desce o que ESTE personagem pode saber (o princípio do contrato 1). O que o
    # outro declarou sobre ele NÃO entra — é o que sustenta o enjeitado, e quem precisa
    # dos dois lados é o Árbitro, que chama `bonds_toward_me` por conta própria.
    #
    # AUSENTE, nunca `None`: campo que não se aplica não aparece. É o contrato de API
    # que `tests/contrato_get_context.py` guarda.
    if self_id and fm.get("id") and fm.get("id") != self_id:
        rotulo = vinculos.bond_toward(self_id, fm.get("id"))
        if rotulo:
            bloco["bond"] = rotulo
        # O NÚMERO MORRE AQUI (Princípio V): sai o rótulo, nunca o saldo. E só quando
        # PESA — a banda neutra é omitida, pelo mesmo corte que `afeto_por_lugar` já usa
        # no Árbitro. Isso enxuga o contexto e evita a única faixa de `sentiment_label`
        # que não compõe frase ("sem história que pese num sentido ou noutro").
        saldo = sentiment_toward(self_id, fm.get("id"))
        if abs(saldo) >= _AFETO_PISO:
            bloco["sentiment"] = sentiment_label(saldo)
    return bloco


# --------------------------------------------------------------------------- #
# Pertencimento por memória (spec 036) — primitivos de nível 0.
#
# Quatro perguntas, quatro funções, um consumidor cada: `carried_item_ids` (física
# pura), `is_blocked` (barreira física condicional), `reachable_entities` (furto/
# transferência), `visible_entities` (narração), `dono` (memória — a única que
# precisa dela) e `offerable_entities` (comércio, walk próprio). Ver
# specs/036-pertencimento-por-memoria/data-model.md para as fórmulas.
# --------------------------------------------------------------------------- #

def is_blocked(personagem_id: str, no_folder: Path, no_fm: dict) -> bool:
    """Barreira física: fechado E sem chave acessível. `is_closed` sozinho
    NÃO basta — um contêiner fechado cuja chave o ator carrega não bloqueia
    (reusa `has_accessible_item`, spec 005, a mesma checagem que a ação de
    abrir já usa)."""
    if not is_closed(no_fm):
        return False
    locks = no_fm.get("locks") if isinstance(no_fm.get("locks"), dict) else {}
    camadas = locks.get("open") or []
    if not camadas:
        return True  # fechado, sem trava declarada: nenhuma chave possível
    try:
        actor_folder = find_character_folder(personagem_id)
    except MotorError:
        return True
    for lock in camadas:
        if not isinstance(lock, dict) or lock.get("type") != "item":
            continue
        required = lock.get("required")
        if not required or not has_accessible_item(actor_folder, required, no_folder):
            return True
    return False


def _walk_scene(location_folder: Path, para_em, incluir_barrado: bool = True) -> dict[str, dict]:
    """Anda pela cena inteira (personagens presentes, objects, itens soltos) e
    recursivamente pelo que cada um contém, parando de descer sempre que
    `para_em(pasta, fm, tipo)` for True.

    `incluir_barrado` distingue dois usos: `reachable_entities`/`visible_entities` querem o nó
    BARRADO ainda assim visível como objeto — só o que está DENTRO dele que
    some (a mochila fechada continua ali, opaca por dentro). `offerable_entities`
    quer o oposto — barrado por `dono` significa EXCLUÍDO de vez, não só
    "recursão parada" (não é seu, não aparece, ponto). `tipo` é
    'character', 'object' ou 'item'."""
    out: dict[str, dict] = {}

    def _no(child: Path, fm: dict, tipo: str) -> None:
        eid = fm.get("id")
        if not eid:
            return
        barrado = para_em(child, fm, tipo)
        if not barrado or incluir_barrado:
            out[eid] = {"folder": child, "fm": fm, "tipo": tipo}
        if not barrado:
            for neto, nfm in _direct_items(child):
                _no(neto, nfm, "item")

    for child in sorted(location_folder.iterdir()):
        if not child.is_dir():
            continue
        if (child / "character.md").exists():
            fm, _ = read_doc(child / "character.md")
            _no(child, fm, "character")
        elif (child / "object.md").exists():
            fm, _ = read_doc(child / "object.md")
            # spec 053, ponto 2 de 3: entidade extinta some do alcance/visão. O
            # arquivo continua no disco como vestígio datado (Princípio IV) — some
            # da LEITURA, não do mundo. Irmão de `_is_alive` para memória.
            if io.esta_extinto(fm):
                continue
            _no(child, fm, "object")
        elif (child / "item.md").exists():
            fm, _ = read_doc(child / "item.md")
            _no(child, fm, "item")
    return out


def _location_folder_of(personagem_id: str) -> Path | None:
    try:
        folder = find_character_folder(personagem_id)
    except MotorError:
        return None
    return folder.parent


def reachable_entities(personagem_id: str) -> dict[str, dict]:
    """O que `personagem_id` consegue TOCAR fisicamente na cena atual — walk
    parando SÓ em `is_blocked`. Nenhuma checagem de dono; QUALQUER personagem
    presente (o próprio ou outro) é atravessado pela mesma regra — um
    personagem só barra a recursão se ELE MESMO estiver bloqueado (hoje
    nenhum declara isso). Consumidor: `itens._find_item_folder_in_scene`
    (alvo de `item_transfers`/`steal`) — amplia o alvo hoje possível para
    dentro do conteúdo guardado (aberto) de terceiros."""
    loc = _location_folder_of(personagem_id)
    if loc is None:
        return {}
    return _walk_scene(loc, lambda f, fm, t: is_blocked(personagem_id, f, fm))


def _is_imperceptible(personagem_id: str, no_folder: Path, no_fm: dict) -> bool:
    """Um recipiente VESTIDO/SEGURADO (`state.slot` presente) por QUALQUER
    personagem — o próprio incluído — é opaco por dentro, independente de
    aberto/fechado — EXCETO se declarado ESCANCARADO (`state.fechado:
    false` explícito, spec 011): aí o gesto deliberado de exibir vence, e o
    conteúdo se vê como qualquer contêiner aberto. Sem slot (location/
    object), a percepção usa `is_blocked` como proxy."""
    if item_slot(no_fm):
        return not _is_wide_open(no_fm)
    return is_blocked(personagem_id, no_folder, no_fm)


def visible_entities(personagem_id: str) -> dict[str, dict]:
    """O que `personagem_id` PERCEBE/nomeia na cena atual — walk parando em
    não-perceptível. Simétrico: nem o próprio dono percebe o conteúdo do
    que veste/segura (sabe por `dono`, memória, nunca por percepção).
    Consumidor: `_visible_item_refs` (contexto de cena/narração)."""
    loc = _location_folder_of(personagem_id)
    if loc is None:
        return {}
    return _walk_scene(
        loc, lambda f, fm, t: _is_imperceptible(personagem_id, f, fm)
    )


def offerable_entities(personagem_id: str) -> dict[str, dict]:
    """O que `personagem_id` pode OFERECER — walk PRÓPRIO (não interseção de
    outros primitivos: uma interseção ingênua reabriria o furo que esta
    checagem fecha, ver research.md §6/§10), parando em `is_blocked` OU em
    `dono(nó, personagem_id) != personagem_id` — a MESMA checagem pra
    qualquer tipo de nó. `object` nunca aciona a segunda condição (nunca é
    alvo de `dono` de ninguém — não é tipo possuível); `location` nem chega
    a ser nó, é só a raiz do walk. Consumidor: `comercio.py`, exclusivamente."""
    loc = _location_folder_of(personagem_id)
    if loc is None:
        return {}

    def _para(f: Path, fm: dict, tipo: str) -> bool:
        if is_blocked(personagem_id, f, fm):
            return True
        if tipo == "object":
            return False
        return dono(fm.get("id"), personagem_id) != personagem_id

    return _walk_scene(loc, _para, incluir_barrado=False)


def craftable_entities(personagem_id: str) -> dict[str, dict]:
    """O que `personagem_id` pode CONSUMIR COMO MATERIAL sem tomar de ninguém —
    um TERCEIRO primitivo, distinto dos outros dois (spec 057, achado da
    exploração pós-implementação de craft): nem `reachable_entities`
    (`alcançável`, o que `steal`/pegar usa — sem checagem de dono NENHUMA, de
    propósito, é o que faz roubar funcionar), nem `offerable_entities`
    (`disponível`, o que `comercio.py` usa, exclusivamente — para em
    `dono(nó, você) != você`, que também é `True` pra item SEM dono nenhum,
    porque `None != você`; oferecer exige posse COMPROVADA, e isso bloquearia
    pegar uma fibra solta que ninguém nunca reivindicou).

    Aqui a condição de parada é `dono(nó, personagem_id) not in (None,
    personagem_id)` — passa por posse LIVRE (`dono() is None`) e pela própria,
    para só em posse RECONHECIDA de outro. É o meio-termo que craft precisa:
    pegar o que está solto no mundo, sem pedir licença pro que já é de alguém.

    Consumidor: `craft_materiais`/`forge_materiais`/`cook_ingredientes`/
    `brew_ingredientes`/`kindle_materiais` (`arbiter.py::scene_candidates`) —
    as cinco tools de trabalho que consomem material da cena real. Antes desta
    função, todas as cinco liam um índice físico bruto sem filtro de posse
    nenhum (confirmado na exploração: dava pra consumir o que outro
    personagem presente carregava na mão, sem checagem)."""
    loc = _location_folder_of(personagem_id)
    if loc is None:
        return {}

    def _para(f: Path, fm: dict, tipo: str) -> bool:
        if is_blocked(personagem_id, f, fm):
            return True
        if tipo == "object":
            return False
        return dono(fm.get("id"), personagem_id) not in (None, personagem_id)

    return _walk_scene(loc, _para, incluir_barrado=False)


def _visible_item_refs(char_folder: Path) -> list[dict]:
    """Itens visíveis de um personagem para TERCEIROS: os filhos diretos
    (vestidos/segurados), com o slot e a física de cada um. O conteúdo dos
    contêineres fica oculto (FR-009), mas a existência do contêiner não.

    EXCEÇÃO — o contêiner ESCANCARADO (spec 011): quem declara `state.fechado:
    false` deixou a coisa aberta DE PROPÓSITO, e o que está dentro se vê. É a
    banca do mascate com a caixa aberta na praça: não precisa perguntar, está à
    mostra. Estar à venda continua não bastando — o que basta é estar aberto.

    Por que a marca explícita e não a mera ausência: `fechado` ausente é o estado
    de toda bolsa do mundo (ninguém declara), então tratar ausência como "à
    mostra" tornaria público o dinheiro que cada um carrega no bolso. Ausente
    segue privado-mas-usável; `false` é o gesto deliberado de escancarar.
    """
    refs = []
    for child, fm in _direct_items(char_folder):
        if not _is_valid(fm):
            continue
        refs.append({"id": fm.get("id"), "name": fm.get("name"),
                     **item_physics(fm, child)})
        if _is_wide_open(fm):
            for neto, nfm in _walk_open_items(child):
                if not _is_valid(nfm):
                    continue
                refs.append({"id": nfm.get("id"), "name": nfm.get("name"),
                             "a_mostra_em": fm.get("id"),
                             **item_physics(nfm, neto)})
    return refs


def _nested_item_refs(container_folder: Path) -> list[dict]:
    """Itens aninhados dentro de um contêiner — object (loot de um baú) ou personagem
    (inventário), com aninhamento arbitrário.

    Não vão para `items_present` (ficam fora da lista ambiente — spec 002, Decisão 2), mas
    A Mente e o Árbitro precisam desta referência para poder revelar/transferir o item
    quando uma ação o justificar. Para o PRÓPRIO personagem, cada entrada traz a física e
    o estado (vestido/segurado/guardado); para terceiros use _visible_item_refs (FR-009).
    """
    is_char = (container_folder / "character.md").exists()
    # spec 019: "segurado" é o que está no slot de PEGA deste corpo (ou legado sem
    # slot), o resto é "vestido".
    pega = grasp_slot_of(_char_fm(container_folder)) if is_char else None
    refs = []
    # atravessa só contêineres ABERTOS: o que está em contêiner fechado é
    # invisível até para o portador (spec 005, FR-002)
    for child, fm in _walk_open_items(container_folder):
        if not _is_valid(fm):
            continue
        ref = {"id": fm.get("id"), "name": fm.get("name"),
               **item_physics(fm, child)}
        if is_char:
            if child.parent == container_folder:
                slot = item_slot(fm)
                ref["estado"] = "segurado" if slot in (pega, None) else "vestido"
            else:
                ref["estado"] = "guardado"
        refs.append(ref)
    return refs


def _conhecidos_por_memoria(memorias: list, presentes: set) -> dict:
    """id -> nome de quem ele SABE NOMEAR mas não está aqui (spec 060).

    Sai do `involved` das lembranças vivas, que já descia no contexto — o que
    faltava era o NOME, e ele não é segredo: está escrito no texto da própria
    lembrança. Serve ao conector para converter "Ossa, a Cavadora" em id e deixar
    a proposta CHEGAR ao mundo, que recusa com frase de mundo ("não é alguém a
    quem você possa perguntar agora") em vez de o cliente engolir a tentativa.

    É o item 53.1 tendo o que precisa: a memória estende o alcance, e quem recusa
    é a execução, não um pré-filtro.
    """
    fora = {}
    for mem in memorias or []:
        for ref in (mem.get("involved") or []):
            if not ref or ref in presentes or ref in fora:
                continue
            nome = io.name_of(ref)
            # `name_of` cai no id cru quando não acha — e aí não há nome a
            # oferecer: registrar o id como se fosse nome só criaria ruído.
            if nome and nome != ref:
                fora[ref] = nome
    return fora


def _location_lineage(place_folder: Path) -> dict | None:
    """A location mais PRÓXIMA que contém `place_folder`, com um ponteiro
    recursivo `belongs_to` pra quem contém ELA — mesma forma da árvore de
    pastas de verdade (spec 035: região contém cidade, cidade contém lugar,
    lugar contém quarto). É uma ESTRUTURA aninhada, não uma lista: quem lê não
    precisa de nenhuma convenção de ordem pra saber quem está dentro de quem,
    é literal — `belongs_to.belongs_to.belongs_to...` até `None` (o lugar não
    está aninhado em nada, ou chegou ao topo da árvore). A chave se repete de
    propósito em cada nível: é a MESMA relação (X pertence a Y) aplicada de
    novo a Y, não uma relação diferente — dois nomes pra isso só confundiria
    quem lê sem ganhar nada.

    Puramente derivado da árvore de pastas para exibição (Fluxo 2, leitura):
    não é dado novo em frontmatter algum. Carrega também o `narrative` (body)
    de cada nível — não só pra UI (que só precisa de `name`), mas pra A Mente
    poder tecer a cidade/região na narração sem repetir prosa em cada location
    filha (mesmo canal de `location.narrative`, um nível acima).
    """
    cur = place_folder.parent
    while cur != WORLD_DIR and cur.parent != cur:
        loc_file = cur / "location.md"
        if loc_file.exists():
            fm, body = read_doc(loc_file)
            if fm.get("id"):
                return {
                    "id": fm["id"],
                    "name": fm.get("name"),
                    "narrative": body,
                    "belongs_to": _location_lineage(cur),
                }
        cur = cur.parent
    return None


def get_context(character_id: str) -> dict:
    """Monta o proximity_context do lugar atual do personagem.

    O "lugar" pode ser uma location OU uma route (personagem em trânsito). Nos dois
    casos, quem estiver na mesma pasta coexiste e pode interagir (FR-021).

    Roda a avaliação preguiçosa antes de montar o bundle (FR-020, FR-022, FR-028).
    Spec 053: a segunda família virou GENÉRICA — `trabalho.resolver_vencidas`
    resolve todo prazo vencido do mundo (prato, fonte de fogo, o que vier),
    no mesmo ponto e no mesmo padrão que `deslocamento.lazy_evaluate` estabeleceu.
    Revisão pós-057: `trabalho.resolver_esforco_pendente` é a MESMA ideia pro
    outro relógio (craft/forja) — critério de tempo ACUMULADO em vez de uma
    data fixa, mas a mesma resolução preguiçosa, no mesmo lugar.
    """
    lazy_evaluate()
    trabalho.resolver_vencidas()
    trabalho.resolver_esforco_pendente()

    char_folder = find_character_folder(character_id)
    place_folder = char_folder.parent
    route_file = place_folder / "route.md"
    loc_file = place_folder / "location.md"
    in_transit = route_file.exists()
    place_file = route_file if in_transit else loc_file
    if place_file.exists():
        place_fm, place_body = read_doc(place_file)
    else:
        place_fm, place_body = {}, ""

    characters_present = []
    items_present = []
    objects_present = []
    for child in sorted(place_folder.iterdir()):
        if not child.is_dir():
            continue
        if (child / "character.md").exists():
            fm_c, _ = read_doc(child / "character.md")
            if not _is_valid(fm_c):  # inválido: fora do mundo jogável (FR-010)
                continue
            characters_present.append(_character_summary(child, character_id))
        elif (child / "object.md").exists():
            obj_fm, _ = read_doc(child / "object.md")
            if not _is_valid(obj_fm):
                continue
            if io.esta_extinto(obj_fm):   # spec 053, ponto 3 de 3: o bundle da Mente
                continue
            # itens aninhados dentro deste object (ex.: loot de um baú) não entram em
            # items_present — ficam ocultos da lista ambiente até uma ação os liberar
            # (spec 002, Decisão 2). Mas o Árbitro precisa SABER que existem para poder
            # revelá-los/transferi-los — "contains" carrega essa referência interna.
            obj_body = read_doc(child / "object.md")[1].strip()
            objects_present.append({
                "id": obj_fm.get("id"),
                "name": obj_fm.get("name"),
                # spec 053: a PROSA do object desce à cena. Antes, A Mente via só o
                # nome — e uma entidade cujo significado inteiro vive na descrição
                # (uma fonte de fogo) seria muda para ela. As réguas do Árbitro já
                # liam por `io.descricao_de`; quem não lia era quem interpreta.
                # Custo medido no mundo: 12 objects, no máximo 4 numa location,
                # prosa média de 243 bytes — ~240 tokens na pior cena.
                "description": obj_body or None,
                "interactions": obj_fm.get("interactions"),
                # spec 054: um object com bloco `trabalho` pendente (a panela no fogo,
                # a fonte de chama, um canteiro recém-colhido) É visivelmente uma coisa
                # em processo — mesmo booleano que item já expõe (`em_trabalho`
                # abaixo). É o que permite `forage_onde` excluir do enum um alvo ainda
                # não rebrotado sem custar chamada nenhuma ao Árbitro (FR-003).
                "em_trabalho": ((obj_fm.get(trabalho.BLOCO) or {}).get("tool")
                                if isinstance(obj_fm.get(trabalho.BLOCO), dict)
                                else None),
                # fechado esconde o conteúdo até do Árbitro-contexto (spec 005)
                "contains": [] if is_closed(obj_fm) else _nested_item_refs(child),
                "fechado": is_closed(obj_fm),
                # tem fecho declarado? (para o manifest de open/close)
                "tem_fecho": ("fechado" in (obj_fm.get("state") or {})
                              or bool(obj_fm.get("locks"))),
            })
        elif (child / "item.md").exists():
            item_fm, _ = read_doc(child / "item.md")
            if not _is_valid(item_fm):
                continue
            entry = {
                "id": item_fm.get("id"),
                "name": item_fm.get("name"),
                "interactions": item_fm.get("interactions"),
                **item_physics(item_fm, child),
            }
            # spec 052: uma peça em processo é VISIVELMENTE uma peça em processo —
            # uma lâmina meio batida na bigorna, uma panela no fogo. O booleano é o
            # que permite ao manifesto oferecer a retomada; o CONTEÚDO do bloco
            # (banda, tetos, tempos) fica fora, porque é segredo do mundo.
            _bloco_trab = item_fm.get(trabalho.BLOCO)
            if isinstance(_bloco_trab, dict):
                # a CAPACIDADE que criou a peça, não um booleano: é o que permite ao
                # manifesto oferecer a retomada só à tool certa. Não é segredo — é
                # visível que uma lâmina meio batida é uma lâmina. O CONTEÚDO do
                # bloco (banda, tetos, tempos) continua fora.
                entry["em_trabalho"] = _bloco_trab.get("tool") or True
            # contêiner ABERTO no chão expõe o que tem (spec 005); fechado, nada
            if isinstance(item_fm.get("container"), dict):
                entry["contains"] = [] if is_closed(item_fm) \
                    else _nested_item_refs(child)
            items_present.append(entry)

    self_fm, self_body = read_doc(char_folder / "character.md")
    _self_pega = grasp_slot_of(self_fm)  # spec 019: slot de pega do ator (mão/boca)
    routes = [] if in_transit else _available_routes(place_fm.get("id"))
    # a cena EVOCA: quem está presente e onde se está decidem o que volta à
    # mente, junto com o que está vívido por si (spec 013)
    memorias_ativas = get_active_memories(
        char_folder,
        evoked_by={c["id"] for c in characters_present if c.get("id")}
        | ({place_fm.get("id")} if place_fm.get("id") else set()),
    )
    # spec 062, US4: mesmo conjunto que `_conhecidos_por_memoria` já usava,
    # nomeado para também alimentar os destinos alcançáveis sem memória.
    _presentes_para_conhecidos = (
        {c["id"] for c in characters_present if c.get("id")}
        | {i["id"] for i in items_present if i.get("id")}
        | {o["id"] for o in objects_present if o.get("id")})

    # spec 066 — O VÍNCULO EM TODA ENTIDADE, num lugar só.
    #
    # Carimbado aqui, e não dentro de cada laço, de propósito: é o que faz `bond`
    # significar EXATAMENTE a mesma coisa em `characters_present`, `items_present`,
    # `objects_present` e `location`, sem três implementações para divergirem depois
    # (FR-008; guardado por `tests/contrato_get_context.py`).
    #
    # `characters_present` já foi carimbado em `_character_summary`, junto do
    # `sentiment` — lá o vínculo anda com a crença, e aqui só com o fato.
    local = {
        "id": place_fm.get("id"),
        "name": place_fm.get("name"),
        "narrative": place_body,
        "belongs_to": _location_lineage(place_folder),
    }
    for entrada in (*items_present, *objects_present, local):
        alvo = entrada.get("id")
        if not alvo:
            continue
        rotulo = vinculos.bond_toward(character_id, alvo)
        if rotulo:                     # AUSENTE, nunca None (contrato de API)
            entrada["bond"] = rotulo

    return {
        "location": local,
        "in_transit": in_transit,
        "routes": routes,
        "characters_present": characters_present,
        "items_present": items_present,
        "objects_present": objects_present,
        # a cena EVOCA: quem está presente e onde se está decidem o que volta à
        # mente, junto com o que está vívido por si (spec 013)
        "memories": memorias_ativas,
        # o que o personagem PRETENDE — nunca o que viveu (spec 026). Consultivo
        # de client (Princípio IX nível 2), disponível à Mente antes de decidir,
        # por sussurro ou pelo gatilho autônomo.
        "intentions": intencoes.get_active_intentions(char_folder),
        # QUEM ELE SABE NOMEAR, mesmo não estando aqui (spec 060, 2026-08-31).
        #
        # O par id -> nome de tudo que aparece no `involved` das memórias vivas
        # dele e que NÃO está na cena. Não é informação nova: o id já descia no
        # `involved`, e o nome ele conhece — está escrito no texto da própria
        # lembrança ("Vi Ossa, a Cavadora partir, rumo a Forja de Ferro").
        #
        # PARA QUE SERVE, e o caso que a criou: a memória ESTENDE O ALCANCE (item
        # 53.1) — o personagem propõe sobre quem ele LEMBRA, e o desfecho certo é
        # o mundo recusar na execução, com frase de mundo, não alguém pré-filtrar
        # a proposta. A Elga tem intenção ativa de ajudar a Ossa e uma lembrança
        # de tê-la visto PARTIR; ao tentar agir sobre ela, o conector não
        # conseguia sequer converter o nome em id, e a recusa saía como "isso não
        # corresponde a nada" — falha de nomear — em vez de "ela não está aqui",
        # que é fato do mundo e diz a ela o que fazer a seguir.
        #
        # Não fere o Princípio IX: nome não é juízo, e o id nunca chega à LLM —
        # ele para no conector, que é quem converte.
        #
        # + OS DESTINOS ALCANÇÁVEIS SEM MEMÓRIA (spec 062, US4). O enum de
        # `travel_to.destino` já expõe esses ids (`reachable_destinations`,
        # mesma função) — só faltava o NOME de quem nunca foi mencionado em
        # memória nenhuma, e por isso `_conhecidos_por_memoria` não os pegava.
        # Nenhum conhecimento NOVO desce à Mente: o id já estava no enum que
        # ela vê; só a etiqueta estava faltando (`registrarNomes`, no conector,
        # caía no fallback nome=id). Memória por cima em caso de colisão — não
        # muda o comportamento já testado dessa fonte.
        "known": {
            **{d: io.name_of(d) for d in deslocamento.reachable_destinations(character_id)
               if d not in _presentes_para_conhecidos and io.name_of(d) != d},
            **_conhecidos_por_memoria(memorias_ativas, _presentes_para_conhecidos),
        },
        "self": {
            "id": self_fm.get("id"),
            "name": self_fm.get("name"),
            "attributes": self_fm.get("attributes") or {},
            "skills": self_fm.get("skills") or {},
            "status": self_fm.get("status") or {},
            # A NECESSIDADE EM RÓTULO (item 51, fatia 1). ADITIVO: `status` segue
            # cru ao lado, porque a régua do Motor precisa do número. Isto é o que
            # desce à Mente — e o que faltava para o personagem poder SABER que
            # está com fome. Ver `fisica.hunger_label`.
            "necessidade": {
                "fome": hunger_label(self_fm),
                "sede": thirst_label(self_fm),
                "cansaco": fatigue_label(self_fm),
                # `None` para quem está acordado. Prosa, nunca a fração nem o
                # tempo (Princípios V/IX) — o mesmo contrato de `consultar_momento`,
                # que devolve "fim de tarde" e jamais a hora.
                "sono": sono_label(self_fm),
            },
            # DERIVADO e BOOLEANO, no mesmo molde de `ocupado` logo abaixo: é o
            # sinal que o CONECTOR lê para não acionar A Mente em sono profundo
            # (dormir não é decidir a cada minuto se já deu). Separado do rótulo
            # de propósito: o rótulo é prosa para o personagem ler, isto é estado
            # para a máquina decidir — casar decisão com substring de prosa seria
            # frágil. Os dois saem da MESMA `fisica.sleep_state`, então não podem
            # divergir.
            "sono_profundo": (sleep_state(self_fm)["dormindo"]
                              and not sleep_state(self_fm)["pode_acordar"]),
            "body": self_body,
            # spec 052 — OCUPADO, DERIVADO. Substitui a leitura de
            # `status.cozinhando`, que era um campo no personagem: o fato passou a
            # morar na peça (a panela no fogo), e isto é recalculado a cada leitura,
            # nunca persistido — mesmo espírito de `familiarity_with`/
            # `proficiencies_for`. Um BOOLEANO, nada mais: nenhum tempo, nenhuma
            # banda, nenhum número desce por aqui.
            "ocupado": trabalho.is_busy(char_folder),
            "inventory": _nested_item_refs(char_folder),
            # física do corpo (spec 004): a Mente narra esforço, a guarda valida
            "body_status": {
                "capacidade_carga_kg": carry_capacity(self_fm),
                "capacidade_empurrar_kg": push_capacity(self_fm),
                "peso_carregado_kg": round(carried_weight(char_folder), 3),
                # spec 019: "mãos" = o slot de pega do corpo (mão / boca / ...)
                "free_hands": max(0, slot_capacity(self_fm, _self_pega)
                               - len(slots_in_use(char_folder).get(_self_pega) or []))
                               if _self_pega else 0,
                "total_hands": slot_capacity(self_fm, _self_pega) if _self_pega else 0,
                "grasp_slot": _self_pega,
                # spec 019: o próprio corpo do ator (mapa slot->capacidade). É a
                # anatomia dele — expô-la ao próprio dono não é metagaming, e o
                # guard de equipar precisa da capacidade de um slot QUALQUER.
                "corpo": body_of(self_fm),
                "slots_ocupados": {s: ids for s, ids
                                   in slots_in_use(char_folder).items()},
            },
        },
    }


def get_character(character_id: str) -> dict:
    folder = find_character_folder(character_id)
    fm, body = read_doc(folder / "character.md")
    return {"frontmatter": fm, "body": body}


def list_characters() -> list[dict]:
    """Lista todos os personagens do mundo (para o seletor do client)."""
    chars = []
    for path in arquivos_no_mundo("character.md"):
        fm, _ = read_doc(path)
        if not _is_valid(fm):  # personagem inválido não entra no seletor (FR-010)
            continue
        location = path.parent.parent
        loc_file = location / "location.md"
        loc_name = None
        if loc_file.exists():
            loc_fm, _ = read_doc(loc_file)
            loc_name = loc_fm.get("name")
        chars.append({
            "id": fm.get("id"),
            "name": fm.get("name"),
            "location": loc_name,
            "owner": fm.get("owner"),
            "image_url": fm.get("image_url"),
        })
    return chars


def _inventory_nodes(folder: Path) -> list[dict]:
    """Coleta recursivamente os itens (pastas com item.md) sob `folder`."""
    nodes = []
    for child in sorted(folder.iterdir()):
        if not child.is_dir() or child.name == "memories":
            continue
        item_file = child / "item.md"
        if item_file.exists():
            fm, body = read_doc(item_file)
            if not _is_valid(fm):  # item inválido some da árvore (FR-010)
                continue
            nodes.append({
                "id": fm.get("id"),
                "name": fm.get("name"),
                "kind": "item",
                # acoplamento ao corpo (spec 004): presente só nos filhos diretos
                # do personagem — o HUD rotula "às costas", "na mão" etc.
                "slot": item_slot(fm),
                # fechado esconde os filhos até do dono (spec 005)
                "fechado": is_closed(fm),
                "children": [] if is_closed(fm) else _inventory_nodes(child),
            })
    return nodes


def get_inventory(character_id: str) -> dict:
    folder = find_character_folder(character_id)
    fm, _ = read_doc(folder / "character.md")
    return {
        "id": fm.get("id"),
        "name": fm.get("name"),
        "kind": "character",
        "children": _inventory_nodes(folder),
    }


def get_entity_detail(entity_id: str) -> dict:
    found = find_entity(entity_id)
    if found is None:
        raise MotorError(f"entidade não encontrada: '{entity_id}'.")
    _, fm, body = found
    detail = {"name": fm.get("name"), "kind": fm.get("type"), "description": body}
    # atributos/skills/status são in-world para um personagem
    if fm.get("type") == "character":
        detail["attributes"] = fm.get("attributes") or {}
        detail["skills"] = fm.get("skills") or {}
        detail["status"] = fm.get("status") or {}
    return detail


def _observer_can_look(character_id: str) -> None:
    """Quem está CAÍDO não observa (spec 018, bug de percepção): um incapacitado ou
    morto não olha em volta. Barra a consulta na origem — o olho não é ação, mas
    percepção, e a percepção também cessa quando se cai.
    """
    try:
        fm, _ = read_doc(find_character_folder(character_id) / "character.md")
    except MotorError:
        return
    if is_down(fm):
        raise MotorError("não há como observar enquanto se está caído.")


def _perceivable_ids(ctx: dict) -> set:
    """Os ids que o personagem PERCEBE agora (anti-metagaming): o lugar, as saídas,
    quem/o que está presente, o que ele carrega, e o conteúdo de contêiner aberto.

    Extraído do `observe_entity` para o reconhecer (spec 018) reusar o MESMO
    recorte — o reconhecimento nunca alcança o que o olhar não alcança.
    """
    allowed = {(ctx.get("location") or {}).get("id")}
    for r in ctx.get("routes", []):
        allowed.add(r.get("id"))
    for c in ctx.get("characters_present", []):
        allowed.add(c.get("id"))
    for o in ctx.get("objects_present", []):
        allowed.add(o.get("id"))
    for it in ctx.get("items_present", []):
        allowed.add(it.get("id"))
        for sub in it.get("contains") or []:  # contêiner aberto no chão (spec 005)
            allowed.add(sub.get("id"))
    for it in (ctx.get("self") or {}).get("inventory") or []:
        allowed.add(it.get("id"))
    allowed.discard(None)
    return allowed


def observe_entity(character_id: str, entity_id: str) -> dict:
    """Descreve uma entidade que o personagem PERCEBE agora — leitura pura, sem LLM.

    Recorte de percepção (anti-metagaming): só o lugar atual, as saídas, quem/o que
    está presente na cena e os próprios pertences. Conteúdo de contêiner fechado e
    entidades de outros lugares são negados — o que o jogador lê nunca ultrapassa o
    que o personagem vê. Nenhuma escrita: é a face consultiva da fronteira do server.
    """
    _observer_can_look(character_id)
    ctx = get_context(character_id)
    if entity_id not in _perceivable_ids(ctx):
        raise MotorError("isso não está ao alcance do seu olhar agora.")
    detail = get_entity_detail(entity_id)
    status = detail.get("status") or {}
    rec = recognition_of(character_id, entity_id)  # o mesmo recorte já validou o alcance
    return {
        "observer": (ctx.get("self") or {}).get("name"),
        "name": detail.get("name"),
        "kind": detail.get("kind"),
        "description": detail.get("description") or "",
        "action": status.get("action"),
        "mood": status.get("mood"),
        # spec 018: o olho passa a levar o RECONHECIMENTO (vivência) para A Mente
        # tecer. Rótulos + episódios, nunca número.
        "familiaridade": rec["familiaridade"],
        "afeto": rec["afeto"],
        "grau": rec["grau"],
        "memorias_vivas": rec["memorias_vivas"],
    }


# _scene_entities MUDOU para io.py (nível 0, spec 025), reexportado aqui para os
# chamadores antigos (`from .percepcao import _scene_entities`) seguirem válidos.
from ..io import _scene_entities  # noqa: E402,F401


def prose_of(character_id: str, entity_id: str) -> str | None:
    """O texto descritivo de uma entidade ao alcance — a prosa, como está escrita.

    Este é o encanamento que faltava. Até a spec 014, a descrição de um item era
    DESCARTADA antes de chegar a quem arbitra: `get_context` não a punha em
    `items_present`, e o prompt recortava de novo. Só `location` levava texto.
    O projeto dependia de campo declarado porque a alternativa era fisicamente
    impossível (Princípio XI).

    Vai SOB DEMANDA, nunca no contexto de toda cena: a taverna tem 26 itens
    presentes, e embutir a descrição de todos degradaria as decisões de todo
    turno, não só as de leitura.

    O texto vai COMO ESTÁ — sem resumo e sem interpretação prévia. Resumir seria
    decidir por quem lê, e a prosa é justamente o insumo da decisão.

    Devolve None se não houver nada ao alcance com esse id, ou se o que há não
    tiver texto nenhum.
    """
    if not entity_id:
        return None
    try:
        actor = find_character_folder(character_id)
    except MotorError:
        return None
    place = actor.parent

    # o lugar onde ele está, e as entidades dentro dele ou dele mesmo
    for filename in ("location.md", "route.md"):
        f = place / filename
        if f.exists():
            fm, body = read_doc(f)
            if fm.get("id") == entity_id:
                return (body or "").strip() or None

    for base in (actor, place):
        for filename in ("item.md", "object.md", "character.md"):
            for path in base.rglob(filename):
                fm, body = read_doc(path)
                if fm.get("id") != entity_id:
                    continue
                # o fecho esconde o conteúdo de TODOS os caminhos de leitura,
                # e este não é exceção (FR-018)
                if _inside_closed(path.parent, base):
                    return None
                return (body or "").strip() or None
    return None


def investigar(character_id: str, args: dict | None = None) -> dict:
    """Le o RASTRO do lugar atual + a memoria do proprio investigador sobre ele
    e os itens presentes (spec 065, item 14-gama do backlog).

    CONSULTA pura (spec 040) — nao muta, nao gasta turno do Arbitro, zero
    chamada de modelo no server. A DENSIDADE de rastro (US1) e SEMPRE gratuita:
    "saber se tem pegada nao exige maestria". So a EXTRACAO de detalhe
    (identidade, rota) escala com uma unica rolagem — e os dois sao EIXOS
    INDEPENDENTES: rota pode sair sem nome (decisao de 2026-09-02, ver
    data-model.md Sec.3), nunca o contrario.

    `args["alvo"]` chega como STRING LIVRE (a lane de consulta não tem enum
    dinamico por cena — ver o comentario logo abaixo) e e VALIDADA aqui contra
    `alvos_investigaveis(character_id)` — nunca texto resolvido contra o `quem`
    real do rastro (research R2), o ground-truth secreto. Fora do conjunto
    conhecido, degrada para varredura ampla (US2), sem erro.

    Alem do rastro, evoca a memoria do investigador sobre o LUGAR e os ITENS
    presentes, no alcance de CONSULTA (viva+vencida, spec 064) — e essa
    evocacao RENOVA as memorias, pelo MESMO mecanismo de desgaste que qualquer
    evocacao deliberada ja usa (`_renew_memory(modo="evocacao")`).
    """
    alvo_bruto = (args or {}).get("alvo") or None
    try:
        ator_folder = find_character_folder(character_id)
    except MotorError:
        return {"densidade": "nenhum", "rastros": [],
               "memorias_do_lugar": [], "memorias_dos_itens": {}}
    ator_fm, _ = read_doc(ator_folder / "character.md")
    # `alvo` chega como STRING LIVRE — a lane de consulta (spec 040) nao tem
    # enum dinamico por cena (ConsultSpec.params e schema fixo; `face.py::_consultas`
    # manda `alvos: {}` sempre, por desenho). Em vez de estender essa arquitetura
    # so para isto, o servidor VALIDA aqui: `alvo` so vale se casar EXATO com um id
    # que o investigador ja tem memoria sobre (`alvos_investigaveis`) — nunca texto
    # resolvido contra o `quem` do rastro (o ground-truth secreto). Fora do
    # conjunto conhecido, degrada para varredura ampla (US2), sem erro.
    alvo_id = alvo_bruto if alvo_bruto in alvos_investigaveis(character_id) else None
    local_folder = _location_folder_of(character_id)
    if local_folder is None:
        return {"densidade": "nenhum", "rastros": [],
               "memorias_do_lugar": [], "memorias_dos_itens": {}}

    densidade, ativos = _densidade_rastro(local_folder)
    rastros = _resolver_rastros(character_id, ator_fm, ativos, alvo_id)

    # A memoria do LUGAR e dos ITENS presentes (US5) — reuso puro de
    # remembered_about no alcance de CONSULTA, com a mesma renovacao da 064.
    ctx = get_context(character_id)
    local_id = (ctx.get("location") or {}).get("id")
    evocadas_ids: set[str] = set()
    memorias_do_lugar = []
    if local_id:
        memorias_do_lugar = _remembered_about_por_alcance(character_id, local_id,
                                                          alcance_consulta)
        evocadas_ids |= {m["id"] for m in memorias_do_lugar if m.get("id")}
    memorias_dos_itens: dict[str, list] = {}
    for item in (ctx.get("items_present") or []):
        item_id = item.get("id")
        if not item_id:
            continue
        mems = _remembered_about_por_alcance(character_id, item_id, alcance_consulta)
        if mems:
            memorias_dos_itens[item_id] = mems
            evocadas_ids |= {m["id"] for m in mems if m.get("id")}
    if evocadas_ids:
        _renew_memory(ator_folder, memoria_ids=evocadas_ids, modo="evocacao")

    return {"densidade": densidade, "rastros": rastros,
           "memorias_do_lugar": memorias_do_lugar,
           "memorias_dos_itens": memorias_dos_itens}


def recognition_of(character_id: str, entity_id: str) -> dict:
    """O RECONHECIMENTO de uma entidade percebida (spec 018) — leitura pura, sem LLM.

    Compõe o que 013/015/016 já produzem: a PROSA (o que a coisa é), a
    FAMILIARIDADE e o AFETO (peso e rumo, em RÓTULO — nunca número) e as MEMÓRIAS
    VIVAS (o porquê). É material para A MENTE tecer; o servidor não interpreta, e
    o número não sai. Respeita o mesmo recorte de percepção do `observe_entity`.

    GRADUADO (saber/reconhecer da 013): memória viva → NÍTIDO (com episódios);
    familiaridade acima do piso mas sem memória viva → VAGO (a história desbotou);
    senão → AUSENTE (só o estático).
    """
    _observer_can_look(character_id)
    ctx = get_context(character_id)
    if entity_id not in _perceivable_ids(ctx):
        raise MotorError("isso não está ao alcance do seu olhar agora.")
    detail = get_entity_detail(entity_id)
    fam = familiarity_with(character_id, entity_id)
    saldo = sentiment_toward(character_id, entity_id)
    vivas = remembered_about(character_id, entity_id)
    if vivas:
        grau = "nitido"
    elif fam > _FAMILIARIDADE_PISO:
        grau = "vago"
    else:
        grau = "ausente"
    afeto = sentiment_label(saldo)
    # A POSSE GRADUADA (spec 064), no MESMO eixo que este retorno já usa para o
    # reconhecimento da entidade. Não é padrão novo: a spec 018 já graduava
    # nitido/vago/ausente aqui, e a 064 só estende à pergunta "de quem é isto".
    #
    #   nitido  -> lembrança VIVA de posse: sei de quem é
    #   vago    -> só VENCIDA: reconheço, com dúvida ("acho que era do Torvin")
    #   ausente -> esquecida ou nenhuma: não sei — e `familiaridade` continua vindo,
    #              porque não saber de quem é não apaga o apego pelo objeto (FR-011)
    #
    # NUNCA desce número: nem certeza, nem probabilidade. A dúvida É o rótulo, e A
    # Mente a narra. Mesmo contrato do `sentiment_label` — "o número morre no server".
    posse_de = dono(entity_id, character_id)
    if posse_de:
        posse = {"de": posse_de, "grau": "nitido"}
    else:
        reconhecido = dono_reconhecido(entity_id, character_id)
        posse = ({"de": reconhecido, "grau": "vago"} if reconhecido
                 else {"de": None, "grau": "ausente"})
    return {
        "posse": posse,
        "id": entity_id,   # para o client deduplicar (ambiente + tool) e referenciar
        "name": detail.get("name"),
        "kind": detail.get("kind"),
        "prosa": detail.get("description") or "",
        "familiaridade": familiarity_label(fam),
        # None quando não pende, para A Mente não inventar sentimento
        "afeto": afeto if abs(saldo) >= 2 else None,
        "grau": grau,
        # o porquê: só no nítido, e só o texto e a recência (nunca número)
        "memorias_vivas": ([{"conteudo": m.get("content") or m.get("summary") or "",
                             "recencia": m.get("recency")} for m in vivas]
                           if grau == "nitido" else []),
    }


_RECOGNITION_SCENE_CAP = 6


def scene_recognitions(character_id: str) -> list[dict]:
    """Os reconhecimentos das entidades PERCEBIDAS com vivência (spec 018).

    Cor ambiente: A Mente tinge a narração de cada turno com a história do
    personagem. Só entra quem PESA (grau nítido, ou vago com familiaridade
    acima de um piso mais alto) — a maioria dos itens de uma cena não gera nada,
    e a narração não incha. Teto de N.
    """
    try:
        _observer_can_look(character_id)
    except MotorError:
        return []   # caído não reconhece nada — a cena não se tinge
    ctx = get_context(character_id)
    self_id = (ctx.get("self") or {}).get("id")
    out = []
    for eid in _perceivable_ids(ctx):
        if eid == self_id:
            continue
        try:
            pac = recognition_of(character_id, eid)
        except MotorError:
            continue
        if pac["grau"] == "nitido" or (
                pac["grau"] == "vago"
                and familiarity_with(character_id, eid) >= 3 * _FAMILIARIDADE_PISO):
            out.append(pac)
    # os mais fortes primeiro; teto
    out.sort(key=lambda p: (p["grau"] != "nitido", ))
    return out[:_RECOGNITION_SCENE_CAP]


def remembered_about(quem_id: str, sobre_id: str) -> list[dict]:
    """O que `quem` guarda A RESPEITO DE `sobre`, no alcance de CONTEXTO — fachada
    publica sobre `_remembered_about_por_alcance` (spec 065): mantida INTACTA,
    porque e o que o Arbitro le para julgar uma relacao NO MOMENTO DO ATO — nunca
    devia alargar (spec 064, data-model Sec.2). `investigar` (spec 065, US5) e o
    primeiro chamador que precisa do alcance de CONSULTA (viva+vencida) para
    evocar memoria vencida do lugar/item; ele usa `_remembered_about_por_alcance`
    diretamente, sem tocar aqui.

    O que segue e a assinatura ORIGINAL, intocada (spec 015):

    Este é o encanamento que faltava, e é a terceira vez que o projeto esbarra
    na mesma parede: `_character_summary` entrega de cada presente apenas id,
    nome, ação, humor, condições e o que ele veste — nada do que ele lembra. O
    Árbitro era, portanto, INCAPAZ de saber que o homem a quem se pergunta o
    caminho é o mesmo que levou uma surra de quem pergunta, ainda que o mundo
    tenha gravado a surra fielmente. A nota de disposição sairia do nada.

    O recorte é pela RELAÇÃO, nunca a mente inteira: só as memórias que envolvem
    `sobre`. Mandar tudo viraria dump da vida interior alheia e ainda diminuiria
    o sinal — o modelo teria de achar a agressão no meio de trinta lembranças de
    taverna.

    Só as VIVAS. É o que faz o rancor esfriar sem nenhum mecanismo de perdão: o
    relógio da spec 013 já faz esse trabalho, e uma segunda regra de
    esquecimento seria duas verdades sobre a mesma relação.

    Irmã textual de `familiarity_with`, que já lê a mesma interseção para medir
    intimidade por volume. Aquela devolve um número; esta devolve o que foi
    vivido, porque quem vai ler é uma inteligência e não uma fórmula.

    Genérica de propósito (FR-007d): persuadir, negociar e atacar podem passar a
    ler a relação por aqui, sem campo novo e sem duplicar a predicação de vida.
    """
    return _remembered_about_por_alcance(quem_id, sobre_id, alcance_contexto)


def _remembered_about_por_alcance(quem_id: str, sobre_id: str, alcance) -> list[dict]:
    """O corpo de `remembered_about`, parametrizado pelo ALCANCE (spec 065) — mesmo
    refactor que `dono`/`_dono_por_alcance` ja fez na spec 064: a funcao publica
    fica intacta (alcance_contexto), e quem precisa de mais (investigar, US5)
    chama esta com `alcance_consulta`, sem duplicar o corpo."""
    try:
        folder = find_character_folder(quem_id)
    except MotorError:
        return []
    mem_dir = folder / "memories"
    if not mem_dir.is_dir():
        return []
    _expire_memories(folder)  # preguiçoso, no escopo de quem está sendo lido
    now = time.time()
    out = []
    candidatos = io.arquivos_envolvendo(mem_dir, sobre_id)
    if candidatos is None:
        candidatos = arquivos_em(mem_dir)
    for path in candidatos:
        fm, body = read_doc(path)
        if fm.get("type") != "memory" or memory_kind(fm) == ROTA:
            continue
        if not alcance(fm, now):
            continue
        if sobre_id not in memory_involved(fm):
            continue
        ts_start = fm.get("timestamp_start") or now
        age = max(0.0, now - ts_start)
        out.append({
            "id": fm.get("id"),
            "intensity": fm.get("intensity"),
            "summary": (fm.get("summary") or "").strip() or _short_summary(body),
            "content": body,
            "timestamp_start": ts_start,
            "recency": _recency_label(age),
            "salience": _memory_salience(fm.get("intensity"), age),
        })
    out.sort(key=lambda m: (
        0 if m.get("salience") == "vivida" else 1,
        _INTENSITY_ORDER.get(m.get("intensity"), 99),
        -(m.get("timestamp_start") or 0),
    ))
    return out[:_MEMORY_CONTEXT_CAP]


def own_memories(character_id: str, require_sobre: bool = True) -> list[dict]:
    """As memórias VIVAS de tipo ACONTECIMENTO que o próprio personagem guarda —
    consulta de SERVER (spec 058). Base do enum de `sing`: só se canta o que se
    lembra.

    Irmã de `remembered_about`, e a diferença é o que motiva a existência dela:
    `remembered_about(quem, sobre)` exige um `sobre` já escolhido ("o que penso
    de fulano"); aqui não há fulano — o cantor pode cantar sobre um herói que
    nunca esteve na cena, e o enum precisa oferecer TODAS as lembranças, cada
    uma com o PRÓPRIO sujeito. `sobre` sai do `involved` de cada memória: o
    primeiro envolvido que não é o narrador.

    `require_sobre` (spec 059, default `True` — preserva `sing` byte a byte):
    uma memória SEM nenhum outro envolvido (rara para cantar — a vivência é só
    dele) fica de fora quando `True`, porque não há sujeito para a canção. Mas
    é justamente o caso comum de um preparo/colheita solitário (`brew`/`cook`/
    `forage`) — o boticário sozinho na botica —, e `write` (spec 059) precisa
    dessas memórias no enum: `require_sobre=False` as inclui, com `sobre=None`.

    Sem CAP e sem ordenação por saliência (ao contrário de `remembered_about`):
    é o Árbitro, lendo a `description` da tool com a listagem inteira, quem
    escolhe — cortar a lista aqui esconderia lembranças que o jogador queria
    ver oferecidas.
    """
    try:
        folder = find_character_folder(character_id)
    except MotorError:
        return []
    mem_dir = folder / "memories"
    if not mem_dir.is_dir():
        return []
    _expire_memories(folder)
    now = time.time()
    out = []
    for path in arquivos_em(mem_dir):
        fm, body = read_doc(path)
        if fm.get("type") != "memory" or memory_kind(fm) == ROTA:
            continue
        if not _is_alive(fm, now):
            continue
        sobre = next((x for x in memory_involved(fm) if x and x != character_id),
                     None)
        if not sobre and require_sobre:
            continue
        out.append({
            "id": fm.get("id"), "sobre": sobre,
            "resumo": (fm.get("summary") or "").strip() or _short_summary(body),
            "conteudo": body.strip() or (fm.get("summary") or ""),
            "intensity": fm.get("intensity"),
        })
    return out


# --------------------------------------------------------------------------- #
# consultar_memoria (spec 040) — a Mente PUXA um fato da própria memória.
#
# Co-localizada aqui porque reusa o MESMO maquinário de `remembered_about`/
# `get_active_memories` (vida, saliência, recência, `memory_involved`). LEITURA:
# devolve PROSA, nunca número/valência (Princípios V/IX); a escrita segue no
# Árbitro (Princípio III). Lane de consulta paralela — não toca a mutação.
# --------------------------------------------------------------------------- #

_THEME_EVENTS = ("witness_theft", "theft", "steal")


def _recall_com_ids(character_id: str, args: dict | None = None) -> tuple[dict, list]:
    """O que o personagem lembra a respeito de `sobre` (prosa livre). Filtra as
    PRÓPRIAS memórias vivas por SUJEITO (id/nome citado em `sobre`) e por TEMA
    (domínio/evento — ex.: furto→crime). Devolve `{sobre, lembra}` em prosa;
    ausência é reportada como ausência, nunca inventada."""
    sobre = ((args or {}).get("sobre") or "").strip()
    low = sobre.lower()
    ausencia = {"sobre": sobre, "lembra": "Você não guarda nenhuma lembrança sobre isso."}
    try:
        folder = find_character_folder(character_id)
    except MotorError:
        return ausencia, []
    mem_dir = folder / "memories"
    if not mem_dir.is_dir():
        return ausencia, []
    _expire_memories(folder)
    now = time.time()
    quer_tema = any(k in low for k in ("furt", "roub", "ladr", "crime"))
    hits = []
    for path in arquivos_em(mem_dir):
        fm, body = read_doc(path)
        if fm.get("type") != "memory" or memory_kind(fm) == ROTA:
            continue
        # spec 064 — O ALCANCE DA CONSULTA, e é a maior mudança desta feature.
        #
        # Era `_is_alive`: EXATAMENTE o alcance de `get_context`. "Parar para lembrar"
        # não alcançava nada além do que já estava na cabeça — medido, 1.106 de 2.692
        # memórias, e as outras 1.585 (59%) eram inconsultáveis. O mantenedor nomeou o
        # buraco antes de eu medi-lo: "se eu parar pra lembrar, eu vou lembrar".
        #
        # Agora alcança a VENCIDA — "não está na minha cabeça" não é "não consigo
        # puxar". A `esquecida` segue de fora: é justamente o que não se consegue mais
        # evocar, e é o que mantém o custo da cura (spec 032) definitivo.
        #
        # As OUTRAS duas leituras deste arquivo (`remembered_about` na 1016,
        # `own_memories` na 1077) continuam em `_is_alive`, e isso é desenho: elas são
        # CONTEXTO — o que o Árbitro lê para julgar no momento do ato.
        if not alcance_consulta(fm, now):
            continue
        sujeito = False
        for inv in memory_involved(fm):
            for tok in str(inv).lower().split("-"):
                if len(tok) >= 3 and tok in low:
                    sujeito = True
                    break
            if sujeito:
                break
        tema = quer_tema and (fm.get("domain") == "crime"
                              or str(fm.get("evento") or "") in _THEME_EVENTS)
        # PELO TEXTO também (item 52.2). Antes só `involved` (ids) e tema casavam — e
        # aí o que a memória diz EM PALAVRAS era inconsultável. Ficou evidente com a
        # memória de pergunta-sem-resposta: o ASSUNTO ("o deus do santuário") não é
        # entidade, então não pode estar em `involved`; ele mora no texto. Sem isto o
        # personagem gravava "já perguntei isso" e não conseguia achar de volta —
        # metade do conserto do laço, e a metade que faltava.
        #
        # Piso de 4 letras e no mínimo DUAS palavras casando: com 3 letras, "que"/
        # "com"/"uma" faziam qualquer pergunta casar qualquer memória, e um recall que
        # devolve tudo é igual a um que devolve nada.
        texto_mem = ((fm.get("summary") or "") + " " + (body or "")).lower()
        palavras = {w for w in re.findall(r"[a-záàâãéêíóôõúç]{4,}", low)}
        casadas = sum(1 for w in palavras if w in texto_mem)
        pelo_texto = casadas >= 2
        if not (sujeito or tema or pelo_texto):
            continue
        ts_start = fm.get("timestamp_start") or now
        age = max(0.0, now - ts_start)
        hits.append({
            "id": fm.get("id"),          # spec 064: o handler da lane precisa saber o
                                         # que foi evocado, para renovar só isso
            "salience": _memory_salience(fm.get("intensity"), age),
            "recency": _recency_label(age),
            "intensity": fm.get("intensity"),
            "timestamp_start": ts_start,
            "text": (fm.get("summary") or "").strip() or _short_summary(body) or body.strip(),
        })
    if not hits:
        return ausencia, []
    hits.sort(key=lambda m: (
        0 if m["salience"] == "vivida" else 1,
        _INTENSITY_ORDER.get(m["intensity"], 99),
        -(m["timestamp_start"] or 0),
    ))
    mostrados = hits[:_MEMORY_CONTEXT_CAP]
    linhas = "\n".join(f"- ({m['recency']}) {m['text']}" for m in mostrados)
    return ({"sobre": sobre, "lembra": "Sobre isso, você lembra:\n" + linhas},
            [m["id"] for m in mostrados if m.get("id")])


def recall(character_id: str, args: dict | None = None) -> dict:
    """O que o personagem lembra a respeito de `sobre`. **LEITURA PURA.**

    Fachada pública sobre `_recall_com_ids`. A separação existe por uma razão só, e ela
    é o coração da spec 064 (research R1): quem RENOVA é o handler da lane de consulta,
    não esta função. `recall` é — e vai continuar sendo — lida por quem PERGUNTA, e a
    fachada do Motor já anuncia um segundo leitor ("reúso pelo Árbitro"). Se a renovação
    morasse aqui, o mundo renovaria memória porque o ÁRBITRO olhou, não porque o
    personagem lembrou.

    E devolve o dicionário LIMPO, sem chave privada de ids: uma versão anterior
    devolvia `_evocadas` para o handler consumir, e isso quebrou a fase 42 — que compara
    o despacho com esta função. Chave que precisa ser removida por convenção é vazamento
    esperando acontecer."""
    return _recall_com_ids(character_id, args)[0]


def _consultar_memoria(character_id: str, args: dict | None = None) -> dict:
    """A lane de consulta: lê por `recall` e RENOVA o que foi evocado (spec 064).

    É o único ponto do projeto onde uma CONSULTA escreve, e a escrita é escopada: o
    prazo das memórias que o personagem acabou de evocar, com a extensão fracionária que
    `_renew_memory` já aplicava quando alguém REENCONTRA outro (spec 030). Não move
    entidade, não muda posse, não toca `status` — é o relógio de uma lembrança, da mesma
    família do que `_expire_memories` já faz na leitura (Princípio VII).

    Por que aqui e não dentro de `recall`: `recall` é lido por quem PERGUNTA e poderá,
    um dia, ser lido por uma RÉGUA (a fachada já anuncia esse reúso). Renovar lá faria o
    mundo renovar memória porque o Árbitro olhou, não porque o personagem lembrou.
    **A renovação é de quem pergunta, não do que é lido.**
    """
    resposta, evocadas = _recall_com_ids(character_id, args)
    evocadas = set(evocadas or ())
    if evocadas:
        try:
            folder = find_character_folder(character_id)
            _renew_memory(folder, modo="evocacao", memoria_ids=evocadas)
        except MotorError:
            pass          # sem pasta não há o que renovar; a leitura já foi entregue
    return resposta


registro.consult_spec(registro.ConsultSpec(
    name="investigar",
    description=(
        "Examina o CHÃO e os ARREDORES do lugar onde você está, à procura de "
        "sinais de passagem recente — pegadas, marcas de quem esteve aqui — e "
        "puxa o que você mesmo já sabe sobre este lugar e o que está nele. Chame "
        "para saber se alguém passou por aqui recentemente, ou para procurar "
        "sinais de alguém específico (passe 'alvo' com o id de quem você já "
        "conhece ou já ouviu falar). Ver se há sinais não exige nenhuma perícia; "
        "identificar QUEM e PARA ONDE pode falhar."
    ),
    params={"alvo": {"type": "string"}},
    query=investigar,
))


registro.consult_spec(registro.ConsultSpec(
    name="consultar_memoria",
    description=(
        "Consulta a SUA MEMÓRIA sobre um fato — o que você viu, viveu ou soube. "
        "Chame quando precisar confirmar algo antes de decidir: se alguém roubou, se "
        "houve furto num lugar, o que você sabe de uma pessoa. Passe 'sobre' com a "
        "pergunta em prosa."
    ),
    params={"sobre": {"type": "string"}},
    query=_consultar_memoria,
))
