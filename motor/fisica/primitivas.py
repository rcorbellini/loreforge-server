"""O Motor / fisica (spec 021 — extraído de __init__).

Parte do pacote em níveis. Ver research.md (T001) para o grafo de dependências.
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

from .. import io, rolagem
from ..io import (
    MotorError,
    _char_fm,
    _fail,
    _marca,
    find_character_folder,
    read_doc,
    write_doc,
)
from ..rolagem import (
    IMPROVISED_ATTRIBUTE,
    IMPROVISED_DAMAGE,
    attr_modifier,
)


DEFAULT_WEIGHT_BY_SIZE = {"PP": 0.1, "P": 1.0, "M": 5.0, "G": 25.0,
                          "XG": 100.0, "XXG": 5000.0, "XXXG": 1e9}


CARRY_KG_PER_STR = 7


PUSH_KG_PER_STR = 14


HAND_SLOT = "mao"


def item_size(fm: dict) -> str:
    """Tamanho canônico do item; ausente/inválido ⇒ P (compatibilidade legada)."""
    size = fm.get("size")
    return size if size in validator.SIZE_ORDER else "P"


def item_own_weight(fm: dict) -> float:
    """Peso próprio em kg; ausente ⇒ padrão da classe de tamanho."""
    weight = fm.get("weight_kg")
    if isinstance(weight, (int, float)) and not isinstance(weight, bool) and weight > 0:
        return float(weight)
    return DEFAULT_WEIGHT_BY_SIZE[item_size(fm)]


def effective_weight(item_folder: Path) -> float:
    """Peso efetivo: o próprio + tudo que está aninhado dentro (recursivo).

    `rglob` inclui o próprio `item_folder/item.md`, então a soma já cobre o
    peso próprio do contêiner.
    """
    total = 0.0
    for path in item_folder.rglob("item.md"):
        fm, _ = read_doc(path)
        total += item_own_weight(fm)
    return total


def carry_capacity(char_fm: dict) -> float:
    strength = (char_fm.get("attributes") or {}).get("STR", 10)
    return int(strength) * CARRY_KG_PER_STR


def push_capacity(char_fm: dict) -> float:
    strength = (char_fm.get("attributes") or {}).get("STR", 10)
    return int(strength) * PUSH_KG_PER_STR


def _direct_items(folder: Path):
    """(pasta, frontmatter) de cada item filho DIRETO de `folder`."""
    out = []
    for child in sorted(folder.iterdir()):
        if child.is_dir() and (child / "item.md").exists():
            fm, _ = read_doc(child / "item.md")
            out.append((child, fm))
    return out


def item_slot(fm: dict) -> str | None:
    state = fm.get("state")
    return state.get("slot") if isinstance(state, dict) else None


def body_of(char_fm: dict) -> dict:
    """O corpo de um personagem: mapa slot -> capacidade (spec 019).

    Fonte ÚNICA da capacidade de partes do corpo. Se a ficha declara `body`, ele
    é a verdade COMPLETA daquele personagem (slots omitidos são ausentes, não
    herdados do humano — só assim se expressa um centauro sem `pes`). Sem `body`,
    herda o corpo humano padrão (`validator.DEFAULT_BODY`), e é isso que mantém
    todo character.md anterior a esta spec com o comportamento de sempre.

    Puro e determinístico: só lê o dict já carregado, nunca interpreta prosa.
    """
    body = char_fm.get("body")
    if isinstance(body, dict):
        return body
    return validator.DEFAULT_BODY


def _slot_cap(valor) -> int:
    """Capacidade de um valor de slot: `int` cru, ou o `capacidade` da forma rica
    `{capacidade: n, pega: bool}` (spec 019)."""
    if isinstance(valor, bool):
        return 0
    if isinstance(valor, int):
        return valor
    if isinstance(valor, dict):
        cap = valor.get("capacidade", 0)
        return cap if isinstance(cap, int) and not isinstance(cap, bool) else 0
    return 0


def _slot_pega(valor) -> bool:
    """Se este slot é de PEGA (onde os itens pegos vão parar). Só a forma rica
    `{..., pega: true}` marca; um int cru nunca é pega por si."""
    return isinstance(valor, dict) and valor.get("pega") is True


def slot_capacity(char_fm: dict, slot: str) -> int:
    """Quantas peças o corpo deste personagem comporta neste slot (0 se não tem)."""
    return _slot_cap(body_of(char_fm).get(slot, 0))


def grasp_slot_of(char_fm: dict) -> str | None:
    """O slot de PEGA do corpo: onde os itens pegos/recebidos vão (spec 019).

    A mão do humano, a boca do cachorro. Regra: o primeiro slot marcado
    `pega: true` vence; na ausência de marca, cai na MÃO (`mao`) quando o corpo a
    tem com capacidade — é isso que mantém humano e qualquer corpo subtrativo que
    ainda tenha mãos (a perna de pau) funcionando sem precisar declarar nada. Um
    corpo sem mãos e sem marca de pega (um peixe) simplesmente não segura nada.
    """
    body = body_of(char_fm)
    for slot, valor in body.items():
        if _slot_pega(valor):
            return slot
    if _slot_cap(body.get(HAND_SLOT, 0)) > 0:
        return HAND_SLOT
    return None


def is_closed(fm: dict) -> bool:
    """Contêiner fechado (spec 005). Ausência do campo ⇒ aberto (legado)."""
    state = fm.get("state")
    return isinstance(state, dict) and state.get("fechado") is True


def _walk_open_items(folder: Path):
    """Itens alcançáveis sob `folder` atravessando SÓ contêineres abertos.

    Gera (pasta, frontmatter) de cada item filho direto e, recursivamente, do
    conteúdo dos que não estão fechados. É o walker de LEITURA/alcance da spec
    005 — a física (peso/vagas) continua varrendo tudo com rglob."""
    for child, fm in _direct_items(folder):
        yield child, fm
        if not is_closed(fm):
            yield from _walk_open_items(child)


def has_accessible_item(actor_folder: Path, item_id: str,
                        exclude_folder: Path | None = None) -> bool:
    """Quem age TEM o item? Alcançável na própria estrutura via contêineres
    ABERTOS e fora de `exclude_folder` (o contêiner alvo da ação — a chave dentro
    do próprio baú nunca o abre nem fecha; anti-deadlock estrutural, FR-005).

    Movida de `itens.py` (spec 036) para `fisica.py`: é nível 0 puro (só usa
    `_walk_open_items`, já deste módulo) — `percepcao.is_blocked` também precisa
    dela, e nível 0 não pode importar de nível 1 (spec 021)."""
    for sub, fm in _walk_open_items(actor_folder):
        if fm.get("id") != item_id:
            continue
        if exclude_folder is not None and \
                (sub == exclude_folder or exclude_folder in sub.parents):
            continue
        return True
    return False


def carried_item_ids(personagem_id: str) -> set[str]:
    """Toda a estrutura própria de `personagem_id`, recursiva, ABERTA e
    FECHADA — física pura, mesmo escopo que já sustenta `carried_weight`
    (spec 036). Não filtra por dono nem por percepção.

    Vive aqui, não em `percepcao.py`: `memoria.dono` (nível 0) precisa dela
    no fallback de posse, e `memoria.py` não pode importar `percepcao.py`
    (que já importa `memoria` — ciclo). `fisica.py` não depende de nenhum
    dos dois, então é o piso comum."""
    try:
        folder = find_character_folder(personagem_id)
    except MotorError:
        return set()
    out: set[str] = set()

    def _walk(f: Path) -> None:
        for child, fm in _direct_items(f):
            if fm.get("id"):
                out.add(fm["id"])
            _walk(child)

    _walk(folder)
    return out


def slots_in_use(char_folder: Path) -> dict:
    """Ocupação de partes do corpo: slot -> [ids] dos filhos diretos acoplados.

    Item legado filho direto SEM state.slot é "segurado de cortesia" (migração):
    não conta contra slots nem contra a carga (contracts/world-schema-equipment.md).
    """
    body = body_of(_char_fm(char_folder))
    used: dict[str, list] = {}
    for _, fm in _direct_items(char_folder):
        slot = item_slot(fm)
        if slot in body:  # spec 019: acoplado a um slot que ESTE corpo tem
            used.setdefault(slot, []).append(fm.get("id"))
    return used


def carried_weight(char_folder: Path) -> float:
    """Peso total efetivo que o personagem carrega (itens acoplados + conteúdo)."""
    body = body_of(_char_fm(char_folder))
    total = 0.0
    for child, fm in _direct_items(char_folder):
        if item_slot(fm) in body:  # spec 019: só o acoplado a um slot deste corpo
            total += effective_weight(child)
    return total


def porter_of(folder: Path) -> Path | None:
    """Personagem no topo da cadeia de contenção de um item, ou None (chão/object).

    Sobe pasta a pasta: item dentro de item continua subindo; personagem é o
    portador final; object/location/route encerram a cadeia sem portador.
    """
    cur = folder.parent
    while True:
        if (cur / "character.md").exists():
            return cur
        if (cur / "item.md").exists():
            cur = cur.parent
            continue
        return None


def check_encaixe(item_id: str, item_sz: str, cont_id: str, max_size: str) -> dict | None:
    if validator.SIZE_ORDER[item_sz] > validator.SIZE_ORDER[max_size]:
        return _fail("tamanho_excede_container", item=item_id, tamanho_item=item_sz,
                     container=cont_id, max_size=max_size)
    return None


def check_vaga(cont_id: str, max_items: int, atuais: int) -> dict | None:
    if atuais >= max_items:
        return _fail("container_lotado", container=cont_id,
                     max_items=max_items, atuais=atuais)
    return None


def open_container_for(portador: Path, item_fm: dict, item_folder: Path,
                       vagas: dict | None = None) -> Path | None:
    """Primeiro contêiner ABERTO de `portador` que comporta este item (tamanho e
    vaga). Devolve a pasta do contêiner, ou None se não houver onde.

    Nasceu privada no comércio, onde é indispensável: comprar com três moedas seria
    fisicamente impossível se cada uma custasse uma mão — ninguém tem três. Subiu
    para cá (item 44) porque a mesma pergunta — "onde isto cabe, sem eu ter de
    escolher?" — é feita pela entrega, pelo furto e pelo `stow` sem destino.

    `vagas` é o contador CORRENTE de ocupação por contêiner, para quem enfileira
    várias colocações antes de escrever (o N↔N da troca). Omitido, cada chamada lê
    a ocupação do disco.

    Nunca devolve o chão: perder um item sem perceber é pior que a recusa que este
    caminho evita. Quem não acha lugar recebe None e decide o que dizer.
    """
    if vagas is None:
        vagas = {}
    for cont_folder, cont_fm in _direct_items(portador):
        cont = cont_fm.get("container")
        if not isinstance(cont, dict) or is_closed(cont_fm):
            continue
        # nem dentro de si mesmo, nem dentro do que ele já contém
        if item_folder == cont_folder or cont_folder in item_folder.parents:
            continue
        atuais = vagas.get(cont_folder)
        if atuais is None:
            atuais = len(_direct_items(cont_folder))
        if check_encaixe(item_fm.get("id"), item_size(item_fm),
                         cont_fm.get("id"), cont.get("max_size")):
            continue
        if check_vaga(cont_fm.get("id"), int(cont.get("max_items") or 0), atuais):
            continue
        vagas[cont_folder] = atuais + 1
        return cont_folder
    return None


def check_mao(char_id: str, ocupantes: list, capacidade: int) -> dict | None:
    # spec 019: a capacidade de mão vem do CORPO do personagem, não do global.
    # Capacidade 0 (um corpo sem mãos, p.ex. um cachorro) é recusa própria.
    if capacidade <= 0:
        return _fail("corpo_sem_slot", personagem=char_id, slot=HAND_SLOT)
    if len(ocupantes) >= capacidade:
        return _fail("maos_ocupadas", personagem=char_id,
                     ocupantes=list(ocupantes), multiplicidade=capacidade)
    return None


def check_slot(item_id: str, slot: str, ocupantes: list, capacidade: int) -> dict | None:
    # spec 019: a capacidade vem do CORPO do alvo. Slot ausente do corpo
    # (capacidade 0) é recusa PRÓPRIA — a peça não tem onde ir —, distinta de
    # "slot ocupado" (que pressupõe o slot existir e estar cheio).
    if capacidade <= 0:
        return _fail("corpo_sem_slot", item=item_id, slot=slot)
    if len(ocupantes) >= capacidade:
        return _fail("slot_ocupado", item=item_id, slot=slot,
                     ocupantes=list(ocupantes), multiplicidade=capacidade)
    return None


def check_carga(char_id: str, item_id: str, peso_item: float,
                total_apos: float, capacidade: float) -> dict | None:
    if total_apos > capacidade:
        return _fail("peso_excede_carga", item=item_id,
                     peso_item=round(peso_item, 3),
                     peso_total_resultante=round(total_apos, 3),
                     capacidade_carga=capacidade, personagem=char_id)
    return None


def check_carga_livre(char_id: str, item_id: str, peso_item: float,
                      livre_kg: float) -> dict | None:
    """Variante relativa de check_carga para a guarda do Árbitro, que enxerga a
    FOLGA de carga (contexto) em vez do total absoluto (arquivos). Mesmo limiar:
    peso_item > folga ⟺ total_apos > capacidade."""
    if peso_item > livre_kg + 1e-9:
        return _fail("peso_excede_carga", item=item_id,
                     peso_item=round(peso_item, 3),
                     free_load_kg=round(livre_kg, 3), personagem=char_id)
    return None


PUSH_TRIVIAL_RATIO = 0.5


PUSH_IMPOSSIBLE_RATIO = 2.0


def check_empurrar(char_id: str, item_id: str, peso_item: float,
                   capacidade: float) -> dict | None:
    """Checagem de LIMITES do empurrar (guarda e Motor): só nega a zona
    impossível (> 2× capacidade). A zona de rolagem passa por aqui — quem rola é
    a aplicação autoritativa (single roll, spec 006 FR-003)."""
    if peso_item > capacidade * PUSH_IMPOSSIBLE_RATIO:
        return _fail("peso_excede_empurrar", item=item_id,
                     peso_item=round(peso_item, 3),
                     capacidade_empurrar=capacidade,
                     limite_com_sorte=round(capacidade * PUSH_IMPOSSIBLE_RATIO, 3),
                     personagem=char_id)
    return None


INCAPACITATED = "incapacitado"


DEAD = "morto"


DOWN_CONDITIONS = (INCAPACITATED, DEAD)


def _conditions_of(char_fm: dict) -> list:
    conds = (char_fm.get("status") or {}).get("conditions")
    return list(conds) if isinstance(conds, list) else []


def is_dead(char_fm: dict) -> bool:
    return DEAD in _conditions_of(char_fm)


def is_down(char_fm: dict) -> bool:
    """Caído = fora de combate como agente: não age e não defende."""
    return any(c in DOWN_CONDITIONS for c in _conditions_of(char_fm))


def default_hp_max(char_fm: dict) -> int:
    """Vitalidade de quem nunca teve `hp` registrado — derivada do vigor."""
    return max(1, 10 + attr_modifier((char_fm.get("attributes") or {}).get("CON", 10)))


def ensure_hp(char_fm: dict) -> tuple[int, int]:
    """Lê (hp, hp_max) preenchendo preguiçosamente quem nunca foi tocado pelo
    combate (FR-007) — sem migração, sem passe no mundo (Princípio VII)."""
    status = char_fm.get("status") or {}
    try:
        hp_max = int(status["hp_max"])
    except (KeyError, TypeError, ValueError):
        hp_max = default_hp_max(char_fm)
    hp_max = max(1, hp_max)
    try:
        hp = int(status["hp"])
    except (KeyError, TypeError, ValueError):
        hp = hp_max
    return max(0, min(hp, hp_max)), hp_max


def apply_damage(alvo_folder: Path, dano: int) -> tuple[int, str | None]:
    """Primitiva de ESTADO (spec 038, molde de `spend_fatigue`): APLICA um dano já
    calculado ao hp do alvo (piso 0) e persiste; se zerar, acrescenta INCAPACITATED.
    A REGRA de combate (quanto de dano) é do executor `attack`; MEXER no estado do
    alvo é daqui. Devolve (novo_hp, derrota|None). Assume o WRITE_LOCK."""
    fm, body = read_doc(alvo_folder / "character.md")
    hp, hp_max = ensure_hp(fm)
    novo_hp = max(0, hp - dano)
    status = dict(fm.get("status") or {})
    status["hp"] = novo_hp
    status["hp_max"] = hp_max
    derrota = None
    if novo_hp == 0:
        conds = [c for c in _conditions_of(fm)]
        if INCAPACITATED not in conds:
            conds.append(INCAPACITATED)
        status["conditions"] = conds
        derrota = INCAPACITATED
    fm["status"] = status
    write_doc(alvo_folder / "character.md", fm, body)
    return novo_hp, derrota


def apply_healing(alvo_folder: Path, recuperado: int) -> int:
    """Primitiva de ESTADO (spec 038, par de `apply_damage`): APLICA uma cura já
    calculada ao hp do alvo (teto `hp_max`) e persiste. A REGRA (quanto cura) é do
    executor `curar`. Devolve o hp novo. Assume o WRITE_LOCK. NB: a condição
    `incapacitado` é limpa à parte pelo executor (`clear_condition`) — outra escrita,
    outro sentido."""
    fm, body = read_doc(alvo_folder / "character.md")
    hp, hp_max = ensure_hp(fm)
    hp_novo = min(hp_max, hp + recuperado)
    status = dict(fm.get("status") or {})
    status["hp"] = hp_novo
    status["hp_max"] = hp_max
    fm["status"] = status
    write_doc(alvo_folder / "character.md", fm, body)
    return hp_novo


def start_rest(char_folder: Path, timestamp: float) -> None:
    """Primitiva de ESTADO (spec 038): marca o INÍCIO do descanso
    (`status.descansando_desde`). O relógio é do executor `dormir`; gravar o
    marcador é daqui. Assume o WRITE_LOCK."""
    fm, body = read_doc(char_folder / "character.md")
    status = dict(fm.get("status") or {})
    status["descansando_desde"] = timestamp
    fm["status"] = status
    write_doc(char_folder / "character.md", fm, body)


def finish_rest(char_folder: Path, fatigue: int, fatigue_max_val: int) -> None:
    """Primitiva de ESTADO (spec 038): fecha o descanso — grava a fadiga recuperada e
    APAGA `descansando_desde` (acordou). A REGRA (quanto recuperou) é do executor
    `dormir`. Assume o WRITE_LOCK."""
    fm, body = read_doc(char_folder / "character.md")
    status = dict(fm.get("status") or {})
    status["fatigue"] = fatigue
    status["fatigue_max"] = fatigue_max_val
    status.pop("descansando_desde", None)
    fm["status"] = status
    write_doc(char_folder / "character.md", fm, body)


def fatigue_max(char_fm: dict) -> int:
    """Teto de fadiga de quem nunca declarou `fatigue_max` — derivado do
    vigor, mesmo molde de `default_hp_max` (spec 030). Escala própria
    (fadiga acumula mais rápido que dano): base 100, piso 20.

    Campo `status.fatigue`/`fatigue_max` (INGLÊS — nome já estabelecido
    pelo projeto: `rotas.py:_travel_modifier` e o `mutate` do Árbitro já
    usavam `fatigue`; achado ao validar contra `world/` real, T030 —
    `fadiga`/`spend_fatigue` são só os nomes de FUNÇÃO em português, como
    `ensure_hp` já lê a chave inglesa `hp`)."""
    status = char_fm.get("status") or {}
    declarado = status.get("fatigue_max")
    if isinstance(declarado, (int, float)) and declarado > 0:
        return int(declarado)
    return max(20, 100 + 10 * attr_modifier(
        (char_fm.get("attributes") or {}).get("CON", 10)))


def ensure_fatigue(char_fm: dict) -> tuple[int, int]:
    """Lê (fadiga, fatigue_max) de `status.fatigue`/`fatigue_max`, molde de
    `ensure_hp`. Valor não-numérico (texto legado, `"alto"`/`"baixo"`) lê
    como `0` — nunca erro, compatibilidade com fichas anteriores a esta
    spec (FR-001)."""
    teto = fatigue_max(char_fm)
    status = char_fm.get("status") or {}
    bruta = status.get("fatigue")
    fadiga = int(bruta) if isinstance(bruta, (int, float)) else 0
    return max(0, min(fadiga, teto)), teto


# --------------------------------------------------------------------------- #
# NECESSIDADE EM RÓTULO — o que o personagem SENTE, não o que o mundo mede.
#
# Existe porque a segunda bússola do tick autônomo estava desligada. O prompt de
# autonomia tem uma seção inteira lendo `status_sobrevivencia` numa "escala de 0 a
# 10" — e o conector alimentava isso com `status.survival_level || 0`, campo que
# NUNCA existiu em lugar nenhum do mundo. Constante zero para todo personagem,
# desde sempre. Pior: com 0 na mão o modelo concluiu "focado em resolver problemas
# imediatos, como encontrar comida" — leu o zero como urgência.
#
# E `hunger`/`fatigue` não chegavam à Mente por nenhuma outra via: o payload dela
# tem personalidade, cena, memórias, rotas e capacidades, e nada de status. Ou
# seja: o personagem não tinha como saber que estava com fome. Seis do mundo
# estavam, no momento em que isto foi escrito.
#
# POR QUE RÓTULO E NÃO ESCALA. Pedir 0-10 já era o erro, e contra a regra do
# projeto: "fato vai em RÓTULO, não número — 'guarda mágoa', não -4; o número é
# segredo do mundo e morre no server". A Mente É o personagem, e um personagem sabe
# que está faminto, não que está em 7 de 10. Rótulo também não permite a inversão
# que o modelo fez com o zero.
#
# O vocabulário do mundo é INCONSISTENTE de propósito (autoria é livre): `saciado`,
# `satisfeito`, `satisfeita`, `faminto`, `faminta`, `com fome`, `extremo`. A
# normalização mora AQUI, na leitura, e não numa migração das fichas — o mesmo
# princípio de `ensure_fatigue`, que tolera texto legado em vez de exigir migração.

_FOME_CANONICA = (
    # (marcas no texto da ficha, rótulo canônico) — a ordem importa: o mais
    # específico primeiro, senão "com fome" casaria em "sem fome".
    (("extremo", "faminta", "faminto", "morrendo"), "faminto"),
    (("com fome", "fome"), "com fome"),
    (("saciad", "satisfeit", "cheio"), "sem fome"),
)


# spec 049: decadência por tempo real. `eat`/`drink` gravam, ao lado do
# rótulo escrito na hora, uma ÂNCORA interna (`status.hunger_ts`/
# `thirst_ts` — epoch de quando comeu/bebeu — e `status.hunger_note`/
# `thirst_note` — a nota 0-10 de saciedade/hidratação daquele ato). Quando a
# âncora existe, o rótulo passa a ser DERIVADO do tempo real decorrido, não
# mais lido do texto estático — puro cálculo na lane de consulta (mesmo
# molde de `tempo.py::current_moment()`, sem escrita, sem WRITE_LOCK, porque
# `hunger_label`/`thirst_label` têm um único leitor: `get_context`).
def _stage_by_time(ts: float, note: int, limiar1_fn, limiar2_fn,
                    rotulos: tuple[str, str, str]) -> str:
    """3 estágios a partir do tempo real decorrido desde `ts`, contra dois
    limiares (em horas) que dependem de `note` — quanto maior a nota, mais
    tempo cada limiar segura. Satura no rótulo mais severo (`rotulos[2]`);
    não existe um 4º estágio."""
    horas = (time.time() - ts) / 3600.0
    if horas >= limiar2_fn(note):
        return rotulos[2]
    if horas >= limiar1_fn(note):
        return rotulos[1]
    return rotulos[0]


def _hunger_note_de(status: dict) -> int:
    nota = status.get("hunger_note")
    return int(nota) if isinstance(nota, (int, float)) and not isinstance(nota, bool) else 0


def _horas_ate_com_fome(nota: int) -> float:
    return 3 + nota * 1.5


def _horas_ate_faminto(nota: int) -> float:
    return 10 + nota * 4


def hunger_label(char_fm: dict) -> str:
    """O que ele SENTE de fome, em rótulo canônico. Com `status.hunger_ts`
    presente (já comeu via `eat` pelo menos uma vez), o rótulo é DERIVADO do
    tempo real decorrido desde então, escalado pela nota daquele ato (spec
    049) — ignora o texto estático de `status.hunger`. Sem `hunger_ts`
    (nunca comeu via tool, ou ficção autorada à mão com texto livre), o
    comportamento é o de sempre: ficha sem `hunger` (ou com palavra que não
    se reconhece) lê como `sem fome` — ausência não é urgência, e inventar
    necessidade onde o autor não escreveu seria o mundo pondo fome em quem
    não tem."""
    status = char_fm.get("status") or {}
    ts = status.get("hunger_ts")
    if isinstance(ts, (int, float)) and not isinstance(ts, bool):
        return _stage_by_time(ts, _hunger_note_de(status),
                               _horas_ate_com_fome, _horas_ate_faminto,
                               ("sem fome", "com fome", "faminto"))
    bruto = str(status.get("hunger") or "").strip().lower()
    if not bruto:
        return "sem fome"
    for marcas, rotulo in _FOME_CANONICA:
        if any(m in bruto for m in marcas):
            return rotulo
    return "sem fome"


_SEDE_CANONICA = (
    # (marcas no texto da ficha, rótulo canônico) — mesma forma de
    # `_FOME_CANONICA` (spec 047, `drink`): mais específico primeiro. `status.
    # thirst` é campo NOVO (nunca existiu antes de `drink` — ao contrário de
    # `hunger`, que já existia morto antes de `eat`), então esta função nasce
    # sem dívida de migração — mas herda a FORMA de `hunger_label` para que a
    # PRÓXIMA tool que precisar ler sede encontre o mesmo vocabulário livre.
    (("desidratad", "sedenta", "sedento", "morrendo de sede"), "sedento"),
    (("com sede", "sede"), "com sede"),
    (("hidratad", "saciad", "satisfeit"), "sem sede"),
)


def _thirst_note_de(status: dict) -> int:
    nota = status.get("thirst_note")
    return int(nota) if isinstance(nota, (int, float)) and not isinstance(nota, bool) else 0


def _horas_ate_com_sede(nota: int) -> float:
    return 2 + nota * 1


def _horas_ate_sedento(nota: int) -> float:
    return 6 + nota * 2


def thirst_label(char_fm: dict) -> str:
    """O que ele SENTE de sede, em rótulo canônico — mesmo mecanismo de
    `hunger_label` (spec 049): `status.thirst_ts` presente deriva o rótulo
    do tempo real decorrido, com limiares próprios SEMPRE mais curtos que os
    de fome na mesma nota (sede aperta antes). Sem `thirst_ts`, mesmo
    espírito de sempre: texto livre ausente ou não reconhecido lê como `sem
    sede` — ausência não é urgência."""
    status = char_fm.get("status") or {}
    ts = status.get("thirst_ts")
    if isinstance(ts, (int, float)) and not isinstance(ts, bool):
        return _stage_by_time(ts, _thirst_note_de(status),
                               _horas_ate_com_sede, _horas_ate_sedento,
                               ("sem sede", "com sede", "sedento"))
    bruto = str(status.get("thirst") or "").strip().lower()
    if not bruto:
        return "sem sede"
    for marcas, rotulo in _SEDE_CANONICA:
        if any(m in bruto for m in marcas):
            return rotulo
    return "sem sede"


def fatigue_label(char_fm: dict) -> str:
    """O que ele SENTE de cansaço, em rótulo canônico.

    Lê o NÚMERO por `ensure_fatigue` (que já tolera o texto legado como 0) e o
    traduz em faixa do PRÓPRIO teto — porque 60 de fadiga é coisa muito diferente
    num teto de 100 e num de 120, e o teto varia por corpo.

    DÍVIDA VISÍVEL: 25 das 44 fichas do mundo têm `fatigue` como PALAVRA
    (`leve`, `alto`, `moderado`…), e a spec 030 (FR-001) manda ler palavra como 0.
    Então metade do mundo é mecanicamente descansada para sempre — e agora também
    SENTE-SE descansada, porque este rótulo sai do mesmo número. Migrar as fichas é
    pré-requisito do item 51 do backlog, não desta função.
    """
    fadiga, teto = ensure_fatigue(char_fm)
    if teto <= 0:
        return "descansado"
    fracao = fadiga / teto
    if fracao >= 0.9:
        return "exausto"
    if fracao >= 0.65:
        return "muito cansado"
    if fracao >= 0.35:
        return "cansado"
    if fracao >= 0.15:
        return "um pouco cansado"
    return "descansado"


def is_resting(char_fm: dict) -> bool:
    """Nível 0 (spec 031): ÚNICA definição de "está descansando" no
    código — lê `status.descansando_desde`. Quem precisa bloquear uma
    ação enquanto o ator dorme CHAMA esta função na própria validação
    (mesmo molde de `spend_fatigue`: capacidade nível 0, nunca um hook
    central); ninguém reimplementa a checagem do campo."""
    return bool((char_fm.get("status") or {}).get("descansando_desde"))


# Teto de recuperação plena de `dormir` (spec 031): 8h reais — mesma escala
# 1:1 de tempo real que viagem já usa (nenhum relógio próprio, Princípio VII).
_TETO_SONO_PLENO_S = 8 * 3600


def rest_fraction(decorrido_s: float) -> float:
    """Fração de recuperação plena atingida por `decorrido_s` de descanso
    real — nunca ultrapassa 1.0 (dormir além do teto não recupera mais que
    tudo)."""
    if decorrido_s <= 0:
        return 0.0
    return min(1.0, decorrido_s / _TETO_SONO_PLENO_S)


# Piso de "sono de qualidade" (spec 031): a fração a partir da qual o descanso
# CONTA — pesa em compromisso alheio e, desde 2026-08-20, autoriza acordar. Mora
# aqui, junto de `rest_fraction`, porque virou regra de DOIS consumidores (o
# executor de `wake_up` e o rótulo que desce à Mente) e um limiar em dois lugares
# é um limiar que diverge.
_LIMIAR_SONO_QUALIDADE = 0.5


def sleep_state(char_fm: dict) -> dict:
    """O estado do sono AGORA — a única fonte sobre dormir, para todo mundo.

    Existe porque três consumidores precisam da MESMA resposta e discordar entre
    eles é o bug: o executor de `wake_up` (pode acordar?), o contexto que desce à
    Mente (que rótulo ela lê) e o conector (chama o modelo ou não?). Com a regra
    escrita três vezes, um deles diria "sono leve" enquanto outro recusaria
    acordar.

    "Dorme até se recuperar OU ser acordado" (decisão do mantenedor, 2026-08-20).
    Então PODE acordar quando o sono já rendeu tudo o que havia para render — a
    fadiga zerou — ou quando cruzou o piso de qualidade. Sem a primeira condição,
    quem deitasse quase descansado ficaria preso 4h por causa de 10 de fadiga.

    Devolve rótulo em PROSA e booleanos de estado; NUNCA a fração, o tempo ou a
    fadiga (Princípios V/IX) — o número morre aqui dentro.
    """
    if not is_resting(char_fm):
        return {"dormindo": False, "pode_acordar": True, "rotulo": None}
    inicio = (char_fm.get("status") or {}).get("descansando_desde") or 0
    fracao = rest_fraction(time.time() - inicio)
    fadiga, teto = ensure_fatigue(char_fm)
    ja_rendeu_tudo = round(fracao * teto) >= fadiga
    pode = ja_rendeu_tudo or fracao >= _LIMIAR_SONO_QUALIDADE
    if ja_rendeu_tudo:
        rotulo = "o sono já rendeu tudo o que tinha a render"
    elif fracao >= 0.85:
        rotulo = "o sono está quase no fim, o corpo já quer levantar"
    elif pode:
        rotulo = "o sono está leve"
    else:
        rotulo = "sono profundo, longe de acordar"
    return {"dormindo": True, "pode_acordar": pode, "rotulo": rotulo}


def sono_label(char_fm: dict) -> str | None:
    """O rótulo do sono para a Mente — `None` para quem está acordado."""
    return sleep_state(char_fm)["rotulo"]


# Categoria de esforço de uma ação, "T-shirt size" — cada tool escolhe a
# PRÓPRIA categoria no PRÓPRIO call site (spec 030, FR-002). A tradução
# categoria→fração é a ÚNICA coisa centralizada aqui; QUAL tool custa
# QUANTO nunca mora numa tabela externa (research.md §4).
_CUSTOS_FADIGA = {"nenhum": 0.0, "baixo": 0.02, "medio": 0.05,
                  "alto": 0.08, "altissimo": 0.10}

# A TENTATIVA FRACASSADA TAMBÉM CANSA (spec 043) — um bote errado atrás de uma bolsa
# cansa, e é justamente a falha que um repetidor repete. Mas cansa MENOS: um degrau
# abaixo do sucesso, com piso em `baixo` (nunca `nenhum`, senão a tentativa volta a
# ser de graça e a repetição não custa nada).
#
# A TENTATIVA SOCIAL FRACASSADA TAMBÉM COBRA (spec 043, decisão do mantenedor) —
# SUPERA a spec 030, FR-003 ("nunca de quem apenas iniciou/persuadiu"). O motivo: com
# as travas anti-repetição removidas, nada limitaria re-rolar persuasão/pergunta na
# mesma cena, e o social é justamente onde insistir é barato. `CUSTO_TENTATIVA_SOCIAL`
# é cobrado de QUEM TENTOU (o persuasor, quem perguntou) e SÓ na falha — o SUCESSO
# segue exatamente como a 030 desenhou: quem entrega é que gasta o corpo.
CUSTO_TENTATIVA_SOCIAL = "baixo"
_DEGRAU_ABAIXO = {"altissimo": "alto", "alto": "medio", "medio": "baixo",
                  "baixo": "baixo", "nenhum": "nenhum"}


def custo_da_falha(custo_do_sucesso: str) -> str:
    """A categoria de fadiga de uma tentativa que se resolveu e NÃO deu certo.

    Um degrau abaixo do sucesso, piso em `baixo`. Recusa da CHECAGEM (alvo ausente,
    campo faltando) não passa por aqui: não chegou a ser tentativa, e não cobra nada.
    """
    return _DEGRAU_ABAIXO.get(custo_do_sucesso, "baixo")


def spend_fatigue(character_id: str, custo: str) -> None:
    """Debita uma fração de `fatigue_max` de quem FISICAMENTE agiu —
    capacidade de nível 0 (mesmo idioma de `attr_modifier`/`ensure_hp`):
    esta função não sabe, nem precisa saber, qual tool a está chamando.
    Cada executor decide sozinho o `character_id` (o ator físico da
    PRÓPRIA op — nem sempre quem iniciou a cena, spec 030 FR-003) e a
    `custo` (a categoria da PRÓPRIA ação)."""
    fracao = _CUSTOS_FADIGA.get(custo, 0.0)
    if fracao <= 0:
        return
    folder = find_character_folder(character_id)
    fm, body = read_doc(folder / "character.md")
    fadiga, teto = ensure_fatigue(fm)
    status = dict(fm.get("status") or {})
    status["fatigue"] = min(teto, fadiga + round(fracao * teto))
    status["fatigue_max"] = teto
    fm["status"] = status
    write_doc(folder / "character.md", fm, body)


def weapon_of(item_fm: dict | None) -> tuple[int, str]:
    """(dano-base, atributo) da arma. Item sem bloco `weapon` — ou mão vazia —
    é improvisado: o golpe vale o mínimo e sai da força."""
    weapon = (item_fm or {}).get("weapon")
    if not isinstance(weapon, dict):
        return IMPROVISED_DAMAGE, IMPROVISED_ATTRIBUTE
    try:
        damage = int(weapon["damage"])
    except (KeyError, TypeError, ValueError):
        return IMPROVISED_DAMAGE, IMPROVISED_ATTRIBUTE
    attribute = weapon.get("attribute")
    if attribute not in validator.WEAPON_ATTRIBUTES:
        attribute = IMPROVISED_ATTRIBUTE
    return max(1, damage), attribute


def protection_of(char_folder: Path) -> int:
    """Absorção do personagem: soma de `armor.protection` do que está VESTIDO.

    Só peças acopladas ao corpo em slot que não seja a mão contam — armadura
    guardada num contêiner ou segurada na mão não protege ninguém.
    """
    char_fm = _char_fm(char_folder)
    body, pega = body_of(char_fm), grasp_slot_of(char_fm)
    total = 0
    for _, fm in _direct_items(char_folder):
        slot = item_slot(fm)
        if slot not in body or slot == pega:  # spec 019: vestido no corpo, salvo o de pega
            continue
        armor = fm.get("armor")
        if not isinstance(armor, dict):
            continue
        try:
            total += max(0, int(armor["protection"]))
        except (KeyError, TypeError, ValueError):
            continue
    return total


DEFAULT_BODY_WEIGHT_KG = 70.0


def value_of(item_fm: dict | None) -> float | None:
    """Preço declarado do item, ou None quando não há. None NÃO é zero: é a
    ausência que impede a compra (o Árbitro não estima — spec 011, FR-005a)."""
    v = (item_fm or {}).get("value")
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
        return None
    return float(v)


def is_currency(item_fm: dict | None) -> bool:
    return _marca(item_fm, "currency")


def is_for_sale(item_fm: dict | None) -> bool:
    return _marca(item_fm, "for_sale")


def is_negotiable(item_fm: dict | None) -> bool:
    return _marca(item_fm, "negotiable")


def total_value(item_fms: list) -> float | None:
    """Soma dos preços. Devolve None se QUALQUER item não declara preço — um
    conjunto com uma peça sem valor não tem total, e a compra não acontece."""
    total = 0.0
    for fm in item_fms:
        v = value_of(fm)
        if v is None:
            return None
        total += v
    return total


def body_weight_of(char_fm: dict) -> float:
    """Peso do CORPO — sem o que ele veste ou carrega."""
    peso = char_fm.get("weight_kg")
    if isinstance(peso, bool) or not isinstance(peso, (int, float)) or peso <= 0:
        return DEFAULT_BODY_WEIGHT_KG
    return float(peso)


def total_weight_of(char_folder: Path) -> float:
    """Quanto pesa levar esta pessoa: o corpo mais tudo que vai junto com ela.

    `carried_weight` já soma recursivamente o vestido e o guardado — ninguém
    viaja sem os próprios pertences (a pasta inteira se move).
    """
    fm, _ = read_doc(char_folder / "character.md")
    return body_weight_of(fm) + carried_weight(char_folder)


def speed_multiplier_of(char_folder: Path) -> float:
    """Multiplicador de velocidade de viagem do personagem (spec 009).

    Vale o MAIOR entre as peças VESTIDAS — nunca o produto nem a soma: vestir mais
    itens rápidos jamais supera vestir o melhor deles (FR-003). Segurar não é
    vestir, e o que está guardado num contêiner não acelera ninguém. Valores
    ausentes, ilegíveis ou ≤ 1 são inertes: equipamento não atrasa (FR-006).
    """
    char_fm = _char_fm(char_folder)
    body, pega = body_of(char_fm), grasp_slot_of(char_fm)
    melhor = 1.0
    for _, fm in _direct_items(char_folder):
        slot = item_slot(fm)
        if slot not in body or slot == pega:  # spec 019: vestido no corpo, salvo o de pega
            continue
        wearable = fm.get("wearable")
        if not isinstance(wearable, dict):
            continue
        mult = wearable.get("speed_multiplier")
        if isinstance(mult, bool) or not isinstance(mult, (int, float)):
            continue
        if mult > melhor:
            melhor = float(mult)
    return melhor


def apply_speed(travel: int, multiplicador: float) -> int:
    """Divide o tempo de viagem pelo multiplicador — ÚLTIMA etapa do cálculo.

    Arredonda com round() (a mesma convenção do _travel_modifier, que já usa
    round(base * 0.5) — uma só regra de arredondamento no deslocamento). O piso de
    1 vale apenas quando havia tempo a percorrer: equipamento nunca torna a viagem
    instantânea (FR-005), mas também não cria viagem onde não havia.
    """
    if multiplicador <= 1 or travel <= 0:
        return travel
    return max(1, round(travel / multiplicador))


def _is_wide_open(item_fm: dict) -> bool:
    """Contêiner deixado aberto DE PROPÓSITO: `state.fechado` declarado como
    false. Diferente de ausente, que é o padrão de qualquer bolsa."""
    state = item_fm.get("state")
    return isinstance(state, dict) and state.get("fechado") is False


def _reachable_item_folder(item_id: str, actor_folder: Path, present_items: dict,
                           present_objects: dict, present_chars: dict) -> Path | None:
    """Pasta de um item ao alcance do ator: no inventário dele ou solto na cena.

    Contêiner fechado esconde o conteúdo aqui como esconde em todo caminho de
    leitura (spec 005) — `_nested_item_refs` já respeita o fecho.
    """
    if not item_id:
        return None
    for base in (actor_folder, actor_folder.parent):
        for path in base.rglob("item.md"):
            fm, _ = read_doc(path)
            if fm.get("id") != item_id:
                continue
            if _inside_closed(path.parent, base):
                return None
            return path.parent
    return None


def _inside_closed(folder: Path, base: Path) -> bool:
    """Algum contêiner entre `folder` e `base` está fechado? (spec 005)"""
    cur = folder.parent
    while cur != base and cur != cur.parent:
        for filename in ("object.md", "item.md"):
            f = cur / filename
            if f.exists():
                fm, _ = read_doc(f)
                if is_closed(fm):
                    return True
        cur = cur.parent
    return False


_CROSSING_BY_SIZE = {
    "PP": 1, "P": 3, "M": 8, "G": 20, "XG": 50,
    "XXG": 110, "XXXG": 200, "XXXXG": 450, "XXXXXG": 900,
}
