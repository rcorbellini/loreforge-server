"""Auto-teste da Fase 37 — Pertencimento por memória (spec 036, US4).

Sem nenhum modelo/LLM — exercita `motor.percepcao` direto. Cobre os seis
primitivos (`carried_item_ids`, `is_blocked`, `reachable_entities`, `visible_entities`, `dono`,
`offerable_entities`) e a migração comportamento-preservante de
`_find_item_folder_in_scene` (alvo de furto/transferência amplia pro
conteúdo guardado de terceiro) e `_character_summary` (campo `carrying` do
próprio personagem usa a visão completa, não a restrita de terceiros).

Uso:  python3 server/selftest_phase37.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
os.environ["LOREFORGE_LOG"] = "0"
sys.path.insert(0, str(SERVER_DIR))
import motor  # noqa: E402
from motor import percepcao  # noqa: E402

FAILS = []
TAVERNA = "taverna-do-gancho"


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _mk_char(cid: str, name: str, loc: str = TAVERNA) -> Path:
    d = motor.WORLD_DIR / loc / cid
    d.mkdir(parents=True, exist_ok=True)
    (d / "character.md").write_text(
        f"---\ntype: character\nid: {cid}\nname: {name}\n"
        f"controlled_by: player_local\nweight_kg: 70\n"
        f"attributes:\n  STR: 10\n  DEX: 10\n  CON: 10\n  INT: 10\n  WIS: 10\n  CHA: 10\n"
        f"skills:\n  geral: 1\n"
        f"status:\n  hp: 50\n  hp_max: 50\n  hunger: saciado\n  fatigue: 0\n"
        f"  action: parado\n  mood: neutro\n  conditions: []\n"
        f"origin: editorial\n---\nUm presente qualquer.\n", encoding="utf-8")
    return d


def _mk_object(parent_folder: Path, obj_id: str, name: str = "Object") -> Path:
    d = parent_folder / obj_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "object.md").write_text(
        f"---\ntype: object\nid: {obj_id}\nname: {name}\norigin: editorial\n"
        f"---\nUm object qualquer.\n", encoding="utf-8")
    return d


def _mk_item(parent_folder: Path, item_id: str, name: str = "Item", *,
            slot: str | None = None, container: dict | None = None,
            closed: bool = False, locks: dict | None = None) -> Path:
    d = parent_folder / item_id
    d.mkdir(parents=True, exist_ok=True)
    state_lines = []
    if slot:
        state_lines.append(f"  slot: {slot}")
    if closed:
        state_lines.append("  fechado: true")
    body = f"---\ntype: item\nid: {item_id}\nname: {name}\nsize: P\nweight_kg: 0.5\n"
    if container:
        body += f"container:\n  max_size: {container.get('max_size', 'M')}\n  max_items: {container.get('max_items', 5)}\n"
    if state_lines:
        body += "state:\n" + "\n".join(state_lines) + "\n"
    if locks:
        body += "locks:\n"
        for phase, camadas in locks.items():
            body += f"  {phase}:\n"
            for c in camadas:
                req = c.get("required")
                body += f"    - {{type: item, required: {req}}}\n"
    body += "origin: editorial\n---\nUm item qualquer.\n"
    (d / "item.md").write_text(body, encoding="utf-8")
    return d


def _write_owner_memory(char_id: str, item_id: str, evento: str, alvo: str,
                        involved_extra: list[str] | None = None) -> None:
    """Crafta uma memória de reivindicação diretamente em disco — testa o
    lado de LEITURA (`dono`) isolado do lado de escrita (US1/US2, ainda não
    implementado neste ponto da suíte)."""
    folder = motor.find_character_folder(char_id)
    involved = [char_id, item_id] + (involved_extra or [])
    motor.memoria._write_memory(
        folder, f"Memória de teste: {evento} sobre {item_id}.",
        involved=involved, evento=evento, about=alvo,
    )


# --------------------------------------------------------------------------- #
# carried_item_ids — física pura, aberto E fechado
# --------------------------------------------------------------------------- #
_mk_char("carried_item_ids-dono-p37", "CarregaDono")
CD = "carried_item_ids-dono-p37"
cd_folder = motor.find_character_folder(CD)
_mk_item(cd_folder, "cd-mochila-p37", "Mochila", slot="costas",
        container={"max_size": "M", "max_items": 5}, closed=True)
_mk_item(cd_folder / "cd-mochila-p37", "cd-dentro-p37", "Moeda")
check("carried_item_ids: inclui o que está DENTRO de contêiner FECHADO (física pura)",
      "cd-dentro-p37" in percepcao.carried_item_ids(CD))
check("carried_item_ids: inclui o próprio contêiner fechado",
      "cd-mochila-p37" in percepcao.carried_item_ids(CD))

# --------------------------------------------------------------------------- #
# is_blocked — condicional: fechado SEM chave bloqueia; COM chave, não
# --------------------------------------------------------------------------- #
_mk_char("chaveiro-p37", "Chaveiro")
CHAVEIRO = "chaveiro-p37"
chaveiro_folder = motor.find_character_folder(CHAVEIRO)
loc_folder = chaveiro_folder.parent
_mk_item(loc_folder, "cofre-p37", "Cofre", container={"max_size": "P", "max_items": 3},
        closed=True, locks={"open": [{"required": "chave-mestra-p37"}]})
_mk_item(loc_folder / "cofre-p37", "joia-p37", "Joia")
cofre_fm, _ = motor.read_doc(loc_folder / "cofre-p37" / "item.md")
check("is_blocked: fechado SEM chave acessível bloqueia",
      percepcao.is_blocked(CHAVEIRO, loc_folder / "cofre-p37", cofre_fm))
_mk_item(chaveiro_folder, "chave-mestra-p37", "Chave Mestra")
check("is_blocked: fechado COM chave acessível NÃO bloqueia (has_accessible_item reusado)",
      not percepcao.is_blocked(CHAVEIRO, loc_folder / "cofre-p37", cofre_fm))

# --------------------------------------------------------------------------- #
# reachable_entities — amplia pro conteúdo guardado (aberto) de terceiro
# --------------------------------------------------------------------------- #
_mk_char("dono-mochila-p37", "DonoMochila")
_mk_char("curioso-p37", "Curioso")
DM, CUR = "dono-mochila-p37", "curioso-p37"
dm_folder = motor.find_character_folder(DM)
_mk_item(dm_folder, "dm-bolsa-aberta-p37", "Bolsa Aberta", slot="cintura",
        container={"max_size": "P", "max_items": 3})  # sem 'closed' => aberta
_mk_item(dm_folder / "dm-bolsa-aberta-p37", "dm-moeda-p37", "Moeda")
alcancavel_cur = percepcao.reachable_entities(CUR)
check("reachable_entities: alcança o conteúdo GUARDADO ABERTO de outro personagem presente (US4, FR-008)",
      "dm-moeda-p37" in alcancavel_cur)
_mk_item(dm_folder, "dm-bolsa-fechada-p37", "Bolsa Fechada", slot="mao",
        container={"max_size": "P", "max_items": 3}, closed=True)
_mk_item(dm_folder / "dm-bolsa-fechada-p37", "dm-segredo-p37", "Segredo")
check("reachable_entities: NÃO alcança conteúdo de contêiner FECHADO de terceiro sem chave",
      "dm-segredo-p37" not in percepcao.reachable_entities(CUR))
check("reachable_entities: alcança o que está na PRÓPRIA estrutura, aberto",
      "dm-moeda-p37" in percepcao.reachable_entities(DM))

# --------------------------------------------------------------------------- #
# visible_entities — simétrico (nem o próprio dono percebe o que veste/segura por dentro)
# --------------------------------------------------------------------------- #
check("visible_entities: terceiro NÃO percebe conteúdo guardado (mesmo aberto) de outro presente",
      "dm-moeda-p37" not in percepcao.visible_entities(CUR))
check("visible_entities: o PRÓPRIO dono TAMBÉM não percebe o conteúdo do que veste/segura (simetria, FR-004)",
      "dm-moeda-p37" not in percepcao.visible_entities(DM))
check("visible_entities: o contêiner em si (a bolsa) é perceptível como objeto, pro terceiro",
      "dm-bolsa-aberta-p37" in percepcao.visible_entities(CUR))
# escancarado (spec 011) é exceção preservada: contêiner deliberadamente aberto expõe conteúdo
_mk_item(dm_folder, "dm-caixa-escancarada-p37", "Caixa Escancarada", slot="mao",
        container={"max_size": "P", "max_items": 3})
esc_folder = dm_folder / "dm-caixa-escancarada-p37"
esc_fm, esc_body = motor.read_doc(esc_folder / "item.md")
esc_fm["state"] = {"slot": "mao", "fechado": False}
motor.write_doc(esc_folder / "item.md", esc_fm, esc_body)
_mk_item(esc_folder, "dm-mostra-p37", "À Mostra")
check("visible_entities: EXCEÇÃO escancarado (state.fechado: false) preserva conteúdo visível a terceiro (SC-005)",
      "dm-mostra-p37" in percepcao.visible_entities(CUR))

# --------------------------------------------------------------------------- #
# dono — relação (não conjunto); fallback de carried_item_ids; base de si mesmo;
# witness_theft NUNCA participa
# --------------------------------------------------------------------------- #
check("dono: personagem sempre 'tem' a si mesmo, sem memória (base da própria estrutura)",
      percepcao.dono(DM, DM) == DM)
_mk_char("orfa-p37", "Orfã")
_mk_item(motor.find_character_folder("orfa-p37"), "orfa-item-p37", "Item Órfão")
check("dono: sem memória reconhecida, cai no fallback de carried_item_ids (posse é o padrão)",
      percepcao.dono("orfa-item-p37", "orfa-p37") == "orfa-p37")
check("dono: sem memória e sem carried_item_ids, indefinido",
      percepcao.dono("orfa-item-p37", CUR) is None)

_mk_char("emprestador-p37", "Emprestador")
_mk_char("receptor-p37", "Receptor")
EMP, REC = "emprestador-p37", "receptor-p37"
_mk_item(motor.find_character_folder(REC), "emprestimo-item-p37", "Item Emprestado")
_write_owner_memory(REC, "emprestimo-item-p37", "emprestimo", EMP, involved_extra=[EMP])
check("dono: memória evento=emprestimo aponta o EMPRESTADOR, mesmo o item estando com o RECEPTOR",
      percepcao.dono("emprestimo-item-p37", REC) == EMP)

_mk_char("testemunha-furto-p37", "TestemunhaFurto")
TF = "testemunha-furto-p37"
_write_owner_memory(TF, "emprestimo-item-p37", "witness_theft", "ladrao-inventado-p37")
check("dono: evento=witness_theft NUNCA participa — não sobrescreve indefinido",
      percepcao.dono("emprestimo-item-p37", TF) is None)
_write_owner_memory(TF, "emprestimo-item-p37", "witness_emprestimo", EMP, involved_extra=[EMP, REC])
check("dono: witness_emprestimo participa — testemunha pura sabe o dono real",
      percepcao.dono("emprestimo-item-p37", TF) == EMP)
time.sleep(0.01)
_write_owner_memory(TF, "emprestimo-item-p37", "witness_theft", "ladrao-inventado-p37")
check("dono: witness_theft POSTERIOR ainda assim não sobrescreve o dono já sabido (só muda posse)",
      percepcao.dono("emprestimo-item-p37", TF) == EMP)

# --------------------------------------------------------------------------- #
# offerable_entities — walk próprio: para em is_blocked OU dono(nó,P)!=P; object nunca
# cria parede sozinho; personagem-terceiro sempre cria parede (item 8 ausente)
# --------------------------------------------------------------------------- #
check("offerable_entities: item emprestado (dono=outro) NÃO aparece pro receptor, mesmo carregando",
      "emprestimo-item-p37" not in percepcao.offerable_entities(REC))
check("offerable_entities: mesmo item emprestado NÃO aparece pro emprestador (parede no personagem receptor)",
      "emprestimo-item-p37" not in percepcao.offerable_entities(EMP))

_mk_char("vendedor-banca-p37", "VendedorBanca")
VB = "vendedor-banca-p37"
vb_folder = motor.find_character_folder(VB)
vb_loc = vb_folder.parent
_mk_object(vb_loc, "vb-banca-p37", "Banca")
_mk_item(vb_loc / "vb-banca-p37", "vb-frasco-p37", "Frasco")
_write_owner_memory(VB, "vb-frasco-p37", "transfer", VB)
check("offerable_entities: object (banca) NUNCA cria parede sozinho — item com dono correto passa",
      "vb-frasco-p37" in percepcao.offerable_entities(VB))
_mk_item(vb_loc / "vb-banca-p37", "vb-sem-dono-p37", "Sem Dono")
check("offerable_entities: item na mesma banca SEM memória de dono fica de fora",
      "vb-sem-dono-p37" not in percepcao.offerable_entities(VB))

_mk_char("ladrao-propria-mochila-p37", "LadraoPropriaMochila")
LPM = "ladrao-propria-mochila-p37"
lpm_folder = motor.find_character_folder(LPM)
_mk_item(lpm_folder, "lpm-mochila-p37", "Mochila Aberta", slot="costas",
        container={"max_size": "M", "max_items": 5})
_mk_item(lpm_folder / "lpm-mochila-p37", "lpm-furtado-p37", "Item Furtado")
check("offerable_entities: SEM memória contrária, o que se carried_item_ids conta como dono de fato (posse é o padrão)",
      "lpm-furtado-p37" in percepcao.offerable_entities(LPM))

# --------------------------------------------------------------------------- #
# Regressão: _find_item_folder_in_scene (steal/item_transfers) via reachable_entities
# --------------------------------------------------------------------------- #
achou = motor.itens._find_item_folder_in_scene("dm-moeda-p37", motor.find_character_folder(CUR))
check("_find_item_folder_in_scene: alvo AMPLIADO — acha item guardado (aberto) de terceiro (FR-008)",
      achou is not None and achou.name == "dm-moeda-p37")
achou_fechado = motor.itens._find_item_folder_in_scene("dm-segredo-p37", motor.find_character_folder(CUR))
check("_find_item_folder_in_scene: NÃO acha item em contêiner fechado de terceiro sem chave",
      achou_fechado is None)

# --------------------------------------------------------------------------- #
# Regressão: _character_summary — campo `carrying` do PRÓPRIO usa visão completa
# --------------------------------------------------------------------------- #
resumo_self = percepcao._character_summary(dm_folder, DM)
ids_self = {r["id"] for r in resumo_self["carrying"]}
check("_character_summary (self): carrying mostra o conteúdo do que o PRÓPRIO veste/segura",
      "dm-moeda-p37" in ids_self, f"ids: {ids_self}")
resumo_terceiro = percepcao._character_summary(dm_folder, CUR)
ids_terceiro = {r["id"] for r in resumo_terceiro["carrying"]}
check("_character_summary (terceiro): carrying continua ocultando o guardado (comportamento-preservante)",
      "dm-moeda-p37" not in ids_terceiro, f"ids: {ids_terceiro}")

# --------------------------------------------------------------------------- #
# US1 — contestação no instante da tomada, fim a fim via apply_resolution
# --------------------------------------------------------------------------- #
def force(v):
    motor._roll_d20 = lambda: v


_mk_char("nerissa-p37", "Nerissa")
_mk_char("tomador-p37", "Tomador")
_mk_char("sabe-p37", "QuemSabe", loc=TAVERNA)
_mk_char("nao-sabe-p37", "QuemNaoSabe", loc=TAVERNA)
NER, TOM, SABE, NSABE = "nerissa-p37", "tomador-p37", "sabe-p37", "nao-sabe-p37"
# todos precisam estar juntos — reposiciona pra mesma location de Nerissa
ner_loc = motor.find_character_folder(NER).parent
for cid in (TOM, SABE, NSABE):
    velho = motor.find_character_folder(cid)
    novo = ner_loc / cid
    if velho != novo:
        shutil.move(str(velho), str(novo))

_mk_item(motor.find_character_folder(NER), "frasco-us1-p37", "Frasco US1")
loc_id_us1 = motor.read_doc(ner_loc / "location.md")[0].get("id")
motor.apply_resolution(NER, {"item_transfers": [{"item": "frasco-us1-p37", "to": loc_id_us1}]})
check("US1 setup: frasco foi deixado no lugar, Nerissa sabe que é dela",
      percepcao.dono("frasco-us1-p37", NER) == NER)
motor.memoria._write_memory(motor.find_character_folder(SABE), "eu soube",
                            involved=[SABE, "frasco-us1-p37", NER], evento="witness_transfer",
                            about=NER)
force(20)  # rolagem de percepção sempre passa
out_us1 = motor.apply_resolution(TOM, {"item_transfers": [{"item": "frasco-us1-p37", "to": TOM}]})
check("US1: pegar pra si move o item (mesmo sem passar por steal)",
      "frasco-us1-p37" in percepcao.carried_item_ids(TOM))
check("US1: Nerissa (dona de fato) ganha memória de furto",
      any(fm.get("evento") == "witness_theft" and "frasco-us1-p37" in motor.memoria.memory_involved(fm)
          for fm in motor.memoria._iter_memories(NER)))
check("US1: QuemSabe (só testemunhou uma doação anterior) TAMBÉM ganha memória de furto",
      any(fm.get("evento") == "witness_theft" and "frasco-us1-p37" in motor.memoria.memory_involved(fm)
          for fm in motor.memoria._iter_memories(SABE)))
check("US1: QuemNaoSabe (sem memória nenhuma sobre o frasco) NÃO ganha memória de furto",
      not any(fm.get("evento") == "witness_theft" and "frasco-us1-p37" in motor.memoria.memory_involved(fm)
              for fm in motor.memoria._iter_memories(NSABE)))
qtd_intentions = len(list((motor.find_character_folder(NER) / "intentions").glob("*.md"))) \
    if (motor.find_character_folder(NER) / "intentions").exists() else 0
check("US1: nenhuma intenção nasce automaticamente em quem ganhou a memória (FR-015)",
      qtd_intentions == 0)

# --------------------------------------------------------------------------- #
# US2 — emprestar sem doar, fim a fim via apply_resolution
# --------------------------------------------------------------------------- #
_mk_char("elga-p37", "Elga")
_mk_char("torvin-p37", "Torvin", loc=TAVERNA)
_mk_char("bystander-p37", "Bystander", loc=TAVERNA)
ELGA37, TORVIN37, BY37 = "elga-p37", "torvin-p37", "bystander-p37"
elga_loc = motor.find_character_folder(ELGA37).parent
for cid in (TORVIN37, BY37):
    velho = motor.find_character_folder(cid)
    novo = elga_loc / cid
    if velho != novo:
        shutil.move(str(velho), str(novo))
_mk_item(motor.find_character_folder(ELGA37), "casaco-us2-p37", "Casaco US2", slot="costas")
# Bystander precisa de alguma vivência prévia com Elga — eventos "small"
# (o leque de testemunha do empréstimo é small) só grudam em quem já tem
# laço (piso de saliência, spec 016/024) — sem isso, a esmagadora maioria
# dos presentes corretamente NÃO forma memória nenhuma, e testar o "sabe
# de cor" exigiria simular esse laço primeiro, como qualquer cena real faria.
motor.memoria._write_memory(motor.find_character_folder(BY37), "Já vi Elga por aí antes.",
                            involved=[BY37, ELGA37], evento="witness_trade", intensity="medium")
force(20)
motor.apply_resolution(ELGA37, {"item_transfers": [
    {"item": "casaco-us2-p37", "to": TORVIN37, "emprestimo": True}]})
check("US2: o casaco passou fisicamente às mãos de Torvin",
      "casaco-us2-p37" in percepcao.carried_item_ids(TORVIN37))
mem_elga = [fm for fm in motor.memoria._iter_memories(ELGA37) if fm.get("evento") == "emprestimo"]
mem_torvin = [fm for fm in motor.memoria._iter_memories(TORVIN37) if fm.get("evento") == "emprestimo"]
check("US2: Elga (emprestador) ganha memória evento=emprestimo",
      len(mem_elga) == 1)
check("US2: Torvin (receptor) ganha memória evento=emprestimo",
      len(mem_torvin) == 1)
mem_by = [fm for fm in motor.memoria._iter_memories(BY37) if fm.get("evento") == "witness_emprestimo"]
check("US2: quem testemunha o empréstimo ganha evento=witness_emprestimo (não witness_transfer)",
      len(mem_by) == 1)
check("US2: dono(casaco, Elga) == Elga — ela ainda é a dona, mesmo sem carregar mais",
      percepcao.dono("casaco-us2-p37", ELGA37) == ELGA37)
check("US2: dono(casaco, Torvin) == Elga — ele carried_item_ids, mas SABE que não é dele",
      percepcao.dono("casaco-us2-p37", TORVIN37) == ELGA37)
check("US2: dono(casaco, Bystander) == Elga — testemunha pura também sabe",
      percepcao.dono("casaco-us2-p37", BY37) == ELGA37)
check("US2: Torvin (receptor) NÃO consegue oferecer o casaco à venda (offerable_entities exclui)",
      "casaco-us2-p37" not in percepcao.offerable_entities(TORVIN37))
check("US2: Elga (emprestador) TAMBÉM não — o casaco está com Torvin agora, fora do alcance de posse dela",
      "casaco-us2-p37" not in percepcao.offerable_entities(ELGA37))

# --------------------------------------------------------------------------- #
# US3 — comprar direto da banca, fim a fim via offered_by/apply_resolution
# --------------------------------------------------------------------------- #
_mk_char("mercador-p37", "Mercador")
_mk_char("comprador-p37", "Comprador")
MERC, COMP = "mercador-p37", "comprador-p37"
merc_loc = motor.find_character_folder(MERC).parent
comp_folder_velho = motor.find_character_folder(COMP)
if comp_folder_velho.parent != merc_loc:
    shutil.move(str(comp_folder_velho), str(merc_loc / COMP))
_mk_object(merc_loc, "banca-us3-p37", "Banca US3")
_mk_item(merc_loc / "banca-us3-p37", "frasco-us3-p37", "Frasco US3")
frasco_fm, frasco_body = motor.read_doc(merc_loc / "banca-us3-p37" / "frasco-us3-p37" / "item.md")
frasco_fm["value"] = 10
frasco_fm["for_sale"] = True
motor.write_doc(merc_loc / "banca-us3-p37" / "frasco-us3-p37" / "item.md", frasco_fm, frasco_body)
motor.memoria._write_memory(motor.find_character_folder(MERC), "coloquei na banca",
                            involved=[MERC, "frasco-us3-p37"], evento="transfer", about=MERC)
oferta = motor.offered_by(MERC)
check("US3: offered_by inclui item da banca com dono reconhecido (mesmo fora da própria pasta)",
      any(r["id"] == "frasco-us3-p37" for r in oferta["a_venda"]))

_mk_item(motor.find_character_folder(COMP), "moeda-us3-p37", "Moeda US3")
moeda_fm, moeda_body = motor.read_doc(motor.find_character_folder(COMP) / "moeda-us3-p37" / "item.md")
moeda_fm["value"] = 10
moeda_fm["currency"] = True
motor.write_doc(motor.find_character_folder(COMP) / "moeda-us3-p37" / "item.md", moeda_fm, moeda_body)
out_compra = motor.apply_resolution(COMP, {"trade_ops": [
    {"modo": "buy", "parceiro": MERC, "dou": ["moeda-us3-p37"], "recebo": ["frasco-us3-p37"]}]})
check("US3: compra direto da banca funciona numa chamada só (sem o mercador segurar antes)",
      "frasco-us3-p37" in percepcao.carried_item_ids(COMP),
      f"applied={out_compra.get('trade_ops_applied')} rejected={out_compra.get('trade_ops_rejected')}")
check("US3: pagamento foi creditado ao parceiro (mercador), não a quem segurava o frasco",
      "moeda-us3-p37" in percepcao.carried_item_ids(MERC))

print()
if FAILS:
    print(f"FALHOU ({len(FAILS)}): " + "; ".join(FAILS)); sys.exit(1)
print("Fase 37 (Pertencimento por memória, spec 036, US4) OK.")
