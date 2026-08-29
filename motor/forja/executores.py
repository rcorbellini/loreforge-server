"""O Motor / forja — EXECUTORES (item 31 §3: DDD por domínio; spec 052).

`_apply_forja_ops` (valida contra os arquivos, rola, aplica) + o
`@registro.handler` `_h_forja`.

DOIS CAMINHOS, e a diferença entre eles é a spec inteira:

  ABERTURA   os quatro gates de mérito recusam (com memória embutida); passando
             todos, os materiais são consumidos NO ATO, a peça nasce na cena, a
             rolagem acontece UMA vez e tudo é congelado no arquivo dela.
  RETOMADA   nenhuma régua, nenhuma rolagem, nenhuma LLM. Credita o tempo
             efetivamente trabalhado (com clamp), aplica a catraca da banda e,
             se o trabalho se cumpriu, materializa a peça.

A catraca só toca a BANDA; o extremo natural do dado fica ao lado dela, imutável,
e só é pago na conclusão — por isso a obra excepcional sobrevive a qualquer
interrupção sem precisar de nenhuma exceção no rebaixamento.
"""
from __future__ import annotations

from pathlib import Path

from .. import fisica, io, memoria, registro, trabalho
from ..io import _fail, _rejection, name_of, read_doc

from .primitivas import (
    banda_final, bloco_mecanico, duracao_segundos_forja, favorabilidade, indice,
    menor, roll_forge_check, teto_por_maestria, teto_por_material,
)

_DOMINIO = {"arma": "ferraria", "armadura": "armaria"}
_EVENTO = {"arma": "forge_weapon", "armadura": "forge_armor"}
_ATRIBUTO = {"arma": "DEX", "armadura": "STR"}

# Os quatro gates de mérito, na ordem em que são perguntados. O primeiro que zerar
# recusa e os seguintes nem chegam a ser julgados.
_GATES = (
    ("forjabilidade", "nao_forjavel",
     "Tentei forjar, mas aquilo não vira peça nenhuma."),
    ("qualidade_material", "material_imprestavel",
     "Tentei forjar, mas o material não prestava para nada."),
    ("fogo_de_forja", "sem_calor_de_forja",
     "Tentei forjar, mas aquele fogo não trabalha metal."),
    ("ferramental", "sem_ferramental",
     "Tentei forjar, mas não havia ali com que trabalhar metal."),
)


def _memoria_peca(pasta: Path, content: str, evento: str, quem: str) -> None:
    """A PROCEDÊNCIA: a peça guarda quem passou por ela (spec 052, FR-036).

    É narrativa, não insumo de regra — a catraca lê a banda no frontmatter, nunca
    esta pasta. E ela NÃO aparece em `get_context` (FR-037): se a procedência de um
    objeto descesse de graça na percepção da cena, não sobraria nada para uma
    capacidade futura de investigar a origem de uma peça descobrir."""
    memoria._write_memory(pasta, content, intensity="small", involved=[quem],
                          evento=evento, domain="nenhuma")


def _apply_forja_ops(character_id: str, actor_folder: Path, resolution: dict,
                     rolls: list | None = None) -> tuple[list, list]:
    applied, rejected = [], []
    if not resolution.get("forja_ops"):
        return applied, rejected
    actor_fm, _ = read_doc(actor_folder / "character.md")
    if fisica.is_resting(actor_fm):  # spec 031: auto-suficiência, nível 0
        rejected.append(_fail("descansando"))
        return applied, rejected

    _, present_objects, present_items = io._scene_entities(actor_folder.parent)  # cena fresca (025)
    place_id = None
    for fname in ("location.md", "route.md"):
        place_file = actor_folder.parent / fname
        if place_file.exists():
            place_fm, _ = read_doc(place_file)
            place_id = place_fm.get("id")
            break
    pendente = trabalho.peca_pendente_de(actor_folder)

    for op in resolution.get("forja_ops") or []:
        tipo = op.get("tipo") or "arma"
        if op.get("retomada"):
            resultado = _retomar(character_id, actor_folder, actor_fm, op, tipo,
                                 present_items, pendente)
        else:
            resultado = _abrir(character_id, actor_folder, actor_fm, op, tipo,
                               present_objects, present_items, place_id, pendente,
                               rolls)
        ok, payload = resultado
        (applied if ok else rejected).append(payload)
    return applied, rejected


def _abrir(character_id, actor_folder, actor_fm, op, tipo, present_objects,
           present_items, place_id, pendente, rolls):
    """Começar uma peça. É o único caminho que consulta réguas e rola dado."""
    materiais = list(op.get("materiais") or [])
    fonte_calor = op.get("fonte_calor")
    base = {"forjar": materiais, "fonte_calor": fonte_calor, "tipo": tipo}

    if not materiais:
        # ACHADO NO EXPLORATÓRIO (spec 052): sem esta linha, uma chamada com a lista
        # vazia criava uma peça DO NADA — nenhum material consumido, peça nascida,
        # peso default. O corpo da tool já barrava, mas o corpo é a face; quem entra
        # pela bancada HTTP ou por uma op malformada não passa por ele. Defesa em
        # profundidade, no mesmo espírito de `peca_de_outra_oficina`.
        return False, _rejection(base, _fail("sem_material"))
    if pendente is not None:
        return False, _rejection(base, _fail("ja_trabalhando"))
    # a fonte pode ser um object OU o próprio lugar (a forja costuma estar escrita
    # na prosa do ambiente, não instanciada)
    if present_objects.get(fonte_calor) is None and fonte_calor != place_id:
        return False, _rejection(base, _fail("fonte_calor_inacessivel",
                                             fonte_calor=fonte_calor))
    material_folders = []
    for mid in materiais:
        pasta = present_items.get(mid)
        if pasta is None:
            return False, _rejection(base, _fail("material_inacessivel", item=mid))
        material_folders.append((mid, pasta))

    # OS QUATRO GATES — nenhum material é consumido até todos passarem (FR-007).
    for campo, regra, lembranca in _GATES:
        if int(op.get(campo) or 0) <= 0:
            return False, {
                **base, "regra": regra, "valores": {"fonte_calor": fonte_calor},
                "why": io._WHY_BY_REGRA[regra],
                "memory": {"content": lembranca, "intensity": "small",
                           "involved": list(materiais),
                           "valence": {m: memoria.NEGATIVA for m in materiais},
                           "event": f"forge_refused_{campo}"}}

    peso_kg = 0.0
    for _mid, pasta in material_folders:
        item_fm, _ = read_doc(pasta / "item.md")
        try:
            peso_kg += float(item_fm.get("weight_kg") or 0)
        except (TypeError, ValueError):
            pass
    for _mid, pasta in material_folders:
        io.remove_entity(pasta)  # consumo total — metal batido não volta a ser barra

    teto_material = teto_por_material(op["qualidade_material"])
    fator = memoria.proficiencies_for(character_id).get(_DOMINIO[tipo], 0.0)
    fav = favorabilidade(op["qualidade_material"], op["fogo_de_forja"],
                         op["ferramental"])
    banda, extremo, _info = roll_forge_check(actor_fm, fav, _ATRIBUTO[tipo], rolls)
    # a catraca já age na abertura: o teto de quem começou vale desde a primeira
    # martelada, e o extremo fica FORA dela (é pago só na conclusão).
    banda = menor(menor(banda, teto_material), teto_por_maestria(fator))

    nome = (op.get("nome") or "").strip() or ("Peça" if tipo == "armadura" else "Lâmina")
    bloco = {
        "tool": _EVENTO[tipo], "tipo": tipo,
        "tempo_necessario_s": duracao_segundos_forja(op.get("duracao") or 0),
        "tempo_trabalhado_s": 0,
        "banda": banda, "teto_material": teto_material,
        "nome_final": nome,
        "descricao_alta": op.get("descricao_alta") or "Uma peça bem executada.",
        "descricao_baixa": op.get("descricao_baixa") or "Uma peça malfeita.",
    }
    if extremo:
        bloco["extremo"] = extremo
    if tipo == "armadura":
        bloco["slot"] = op.get("slot") or "torso"

    corpo = (f"{nome} ainda em trabalho: o metal já tomou forma, mas falta muito "
             "para estar pronta.")
    peca_id, pasta = trabalho.criar_peca(actor_folder.parent, corpo, bloco,
                                         name=f"{nome} (em trabalho)",
                                         weight_kg=peso_kg or 0.3)
    trabalho.abrir_sessao(pasta, character_id)
    _memoria_peca(pasta, f"{name_of(character_id)} começou esta peça.",
                  "forge_start", character_id)

    return True, {
        "peca": peca_id, "tipo": tipo, "materiais": materiais,
        "fonte_calor": fonte_calor, "retomada": False, "concluido": False,
        # ABRIR trabalho não é prática concluída: `domain: nenhuma` de propósito
        # (FR-034 — o que ensina o ofício é a peça terminada, não a tentativa).
        "memory": {"content": f"Comecei a forjar {nome}.", "intensity": "small",
                   "involved": [], "valence": None, "event": "forge_start",
                   "domain": "nenhuma"}}


def _retomar(character_id, actor_folder, actor_fm, op, tipo, present_items, pendente):
    """Continuar (ou terminar) uma peça. NENHUMA chamada ao Árbitro, nunca."""
    peca = op.get("peca")
    base = {"peca": peca, "tipo": tipo}
    pasta = present_items.get(peca)
    if pasta is None:
        return False, _rejection(base, _fail("peca_inacessivel", item=peca))
    bloco = trabalho.ler(pasta)
    if not bloco:
        # conserto pós-057: "sem bloco" quase sempre é "já concluiu" (o bloco
        # morre em `encerrar()`), não "inacessível" — a frase antiga soava como
        # problema de alcance, não "não há mais o que retomar" (achado da
        # exploração da spec 057, aplicado aqui também por pedido do mantenedor).
        regra = "peca_ja_concluida" if trabalho.origin_de(pasta) == "emergente" \
            else "peca_inacessivel"
        return False, _rejection(base, _fail(regra, item=peca))
    if bloco.get("tool") != _EVENTO[tipo]:
        # recusa ESTRUTURAL, zero LLM: chamar a tool de armadura sobre uma lâmina
        # meio pronta é erro de escolha, e o mundo sabe disso lendo o arquivo.
        return False, _rejection(base, _fail("peca_de_outra_oficina", item=peca))
    if pendente is not None and pendente[0] != pasta:
        return False, _rejection(base, _fail("ja_trabalhando"))

    # 1. credita o que foi efetivamente trabalhado (o clamp mora na primitiva)
    bloco = trabalho.creditar_e_fechar(pasta)
    # 2. A CATRACA: quem põe a mão numa peça acima do que sustenta a rebaixa, e ela
    #    nunca sobe de novo. Mão única, e é isso que faz uma peça de banda alta um
    #    objeto biográfico em vez de um resultado de dado.
    fator = memoria.proficiencies_for(character_id).get(_DOMINIO[tipo], 0.0)
    teto_mao = teto_por_maestria(fator)
    banda_antes = bloco.get("banda") or "comum"
    banda_agora = menor(banda_antes, teto_mao)
    rebaixou = indice(banda_agora) < indice(banda_antes)
    if rebaixou:
        bloco = trabalho.atualizar(pasta, banda=banda_agora)

    nome = bloco.get("nome_final") or "Peça"
    _memoria_peca(pasta, f"{name_of(character_id)} trabalhou nesta peça.",
                  "forge_session", character_id)

    if not trabalho.concluido(bloco):
        trabalho.abrir_sessao(pasta, character_id)
        out = {"peca": peca, "tipo": tipo, "retomada": True, "concluido": False,
               "rebaixou": rebaixou}
        if rebaixou:
            # RÓTULO, nunca número (FR-039): o ferreiro sente que a peça pedia mais
            # do que ele sabe dar; a banda e os tetos morrem no servidor.
            out["memory"] = {"content": f"Trabalhei em {nome}, e senti que a peça "
                                        "pedia mais do que sei dar.",
                             "intensity": "small", "involved": [], "valence": None,
                             "event": "forge_downgrade", "domain": "nenhuma"}
        return True, out

    # 3. CONCLUSÃO — e é aqui, só aqui, que o extremo do dado é pago.
    final = banda_final(banda_agora, bloco.get("extremo"), bloco.get("teto_material")
                        or "lendario")
    descricao = (bloco.get("descricao_alta") if indice(final) >= indice("incomum")
                 else bloco.get("descricao_baixa"))
    item_fm, _ = read_doc(pasta / "item.md")
    novo = {"name": nome, "rarity": final,
            **bloco_mecanico(tipo, final, item_fm.get("weight_kg"),
                             bloco.get("slot"))}
    trabalho.encerrar(pasta, novo, descricao or "Uma peça terminada.")
    _memoria_peca(pasta, f"{name_of(character_id)} terminou esta peça.",
                  "forge_done", character_id)

    excepcional = indice(final) >= indice("raro")
    evento = (f"{_EVENTO[tipo]}_falha" if final == "falha" else
              f"{_EVENTO[tipo]}_excepcional" if excepcional else _EVENTO[tipo])
    content = (f"Terminei {nome}, e saiu melhor do que eu esperava." if excepcional
               else f"Terminei {nome}, mas não presta para nada." if final == "falha"
               else f"Terminei {nome}.")
    return True, {
        "peca": peca, "tipo": tipo, "retomada": True, "concluido": True,
        "banda": final, "rebaixou": rebaixou,
        # SÓ a peça CONCLUÍDA carimba domínio — é o que alimenta a proficiência.
        "memory": {"content": content,
                   "intensity": "medium" if excepcional else "small",
                   "involved": [], "valence": None, "event": evento,
                   "domain": _DOMINIO[tipo]}}


@registro.handler("forja_ops")
def _h_forja(cid, af, res, rolls):
    applied, rejected = _apply_forja_ops(cid, af, res, rolls)
    return applied, rejected, []  # memória (ator, applied E rejected) via react_actor_memory
