"""Fase 71b — EXTRAÇÃO DE MATÉRIA-PRIMA (spec 071, US2).

`mine`, `chop` e `forage`: três faces, um executor, uma régua. O que este arquivo
protege — e cada item é um jeito conhecido de a feature morrer em silêncio:

1. **Os dois eixos de admissão são independentes.** Alvo certo + ferramenta errada
   recusa; alvo errado + ferramenta certa recusa. Medido: numa nota composta as
   cláusulas competem pelo mesmo número e a saliente vence.
2. **`mine`/`chop` SOMEM do manifest de mãos vazias.** Não é validação a mais — é a
   capacidade não existir para quem não pode exercê-la.
3. **Renovação 0 esgota PARA SEMPRE.** Nenhum bloco de prazo é instalado, e é a
   ausência de promessa de volta que significa esgotado — nunca um campo.
4. **Pedra e madeira ESTOCAM.** Sem `descricao_vencida`, sem prazo. É isto que
   torna possível reunir material para erguer alguma coisa — o percurso que
   originou a spec.
5. **O porte julgado vira peso**, e peso demais nasce no chão em vez da mão. É o
   que faz o tronco precisar de `shove` em vez de caber no bolso.
6. **Cada capacidade alimenta a SUA maestria.** Minerar não faz herbalismo crescer.
7. **A extração não pode se chamar como a fonte** (recusa determinística, 062).
8. **`location` nunca é escrita.**
9. **Nenhuma chave central nova** (T038): acrescentar duas capacidades não pode
   fazer `scene_candidates` crescer.

Uso:  python3 selftest_phase71b.py
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test71b-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
os.environ["LOREFORGE_LOG"] = "0"
sys.path.insert(0, str(SERVER_DIR))
import motor  # noqa: E402
import arbiter  # noqa: E402
from motor.extracao import primitivas as prim  # noqa: E402

FAILS: list[str] = []
TAVERNA = "taverna-do-gancho"


def check(nome, cond, detalhe=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {nome}"
          + (f" — {detalhe}" if detalhe and not cond else ""))
    if not cond:
        FAILS.append(nome)


def _mk_char(cid: str, name: str):
    d = motor.WORLD_DIR / TAVERNA / cid
    d.mkdir(parents=True, exist_ok=True)
    (d / "character.md").write_text(
        f"---\ntype: character\nid: {cid}\nname: {name}\n"
        f"controlled_by: player_local\nweight_kg: 70\n"
        f"attributes:\n  STR: 12\n  DEX: 10\n  CON: 10\n  INT: 10\n  WIS: 10\n  CHA: 10\n"
        f"status:\n  hp: 20\n  hp_max: 20\n  hunger: sem fome\n  fatigue: 0\n"
        f"  action: parado\n  mood: neutro\n  conditions: []\n"
        f"origin: editorial\n---\nUm presente qualquer.\n", encoding="utf-8")
    return d


def _mk_object(pasta_local: Path, oid: str, nome: str, descricao: str):
    d = pasta_local / oid
    d.mkdir(parents=True, exist_ok=True)
    (d / "object.md").write_text(
        f"---\ntype: object\nid: {oid}\nname: {nome}\norigin: editorial\n---\n"
        f"{descricao}\n", encoding="utf-8")
    return d


def _mk_item_na_mao(pasta_char: Path, iid: str, nome: str, descricao: str):
    d = pasta_char / iid
    d.mkdir(parents=True, exist_ok=True)
    (d / "item.md").write_text(
        f"---\ntype: item\nid: {iid}\nname: {nome}\nweight_kg: 2\nsize: M\n"
        f"slot: hand\norigin: editorial\n---\n{descricao}\n", encoding="utf-8")
    return d


def op(capacidade, onde, *, alvo=8, ferramenta=None, ferramenta_nota=9,
       rendimento=7, renovacao=9, tamanho="P", vencida=""):
    """O op que o corpo enfileira. Assinatura explícita de propósito: o teste
    escreve o JUÍZO à mão para poder variar UM eixo por vez — é o único jeito de
    provar que os dois eixos são independentes."""
    o = {"onde": onde, "capacidade": capacidade, "alvo": alvo,
         "ferramenta_nota": ferramenta_nota, "rendimento": rendimento,
         "renovacao": renovacao, "tamanho": tamanho,
         "nome_pobre": "Cascalho", "descricao_pobre": "lascas soltas",
         "nome_comum": "Estanho Bruto", "descricao_comum": "um punhado de metal",
         "nome_rica": "Placa de Estanho", "descricao_rica": "metal em placa",
         "descricao_extraida": "a parede, agora aberta e revirada",
         "urgencia": "", "descricao_vencida": vencida}
    if ferramenta:
        o["ferramenta"] = ferramenta
    return o


LOC = motor.WORLD_DIR / TAVERNA
MIN = "mineiro-p71"
pasta_min = _mk_char(MIN, "Mineiro de Teste")
_mk_object(LOC, "parede-veio-p71", "Parede de Veio",
           "Parede de rocha úmida onde uma veia de estanho aflora, exposta.")
_mk_item_na_mao(pasta_min, "picareta-p71", "Picareta",
                "Picareta de mineiro, bico de aço em ponta viva.")
_mk_item_na_mao(pasta_min, "colher-p71", "Colher de Pau",
                "Colher de pau de cozinha, larga e rasa.")

print("\n--- 1. os dois eixos de admissão são INDEPENDENTES -------------------")

r = motor.apply_resolution(MIN, {"extracao_ops": [
    op("mine", "parede-veio-p71", ferramenta="picareta-p71")]})
aplicados = r.get("extracao_ops_applied") or []
check("alvo certo + ferramenta certa: extrai", bool(aplicados), str(r.get("rejected")))
itens = (aplicados[0].get("itens") if aplicados else []) or []
check("nasceram porções", bool(itens), str(itens))

r2 = motor.apply_resolution(MIN, {"extracao_ops": [
    op("mine", "parede-veio-p71", ferramenta="colher-p71", ferramenta_nota=0)]})
rej = [x.get("regra") for x in (r2.get("rejected") or [])]
check("alvo certo + ferramenta ERRADA: recusa por ferramenta_impropria",
      "ferramenta_impropria" in rej, str(rej))

_mk_object(LOC, "moita-p71", "Moita de Amora", "Moita fechada de amoreiras.")
r3 = motor.apply_resolution(MIN, {"extracao_ops": [
    op("mine", "moita-p71", alvo=0, ferramenta="picareta-p71")]})
rej3 = [x.get("regra") for x in (r3.get("rejected") or [])]
check("alvo ERRADO + ferramenta certa: recusa por sem_materia",
      "sem_materia" in rej3, str(rej3))

print("\n--- 2. mãos vazias: a capacidade não existe --------------------------")

SEM = "semmao-p71"
_mk_char(SEM, "Sem Ferramenta")
faces = {f["name"] for f in arbiter.build_tools(motor.get_context(SEM))}
check("de mãos vazias, `mine` não é oferecida", "mine" not in faces)
check("de mãos vazias, `chop` não é oferecida", "chop" not in faces)
check("de mãos vazias, `forage` CONTINUA oferecida", "forage" in faces, str(sorted(faces)))

faces_min = {f["name"] for f in arbiter.build_tools(motor.get_context(MIN))}
check("com algo na mão, `mine` e `chop` aparecem",
      {"mine", "chop"} <= faces_min, str(sorted(faces_min)))

print("\n--- 3/4. renovação e perecibilidade ----------------------------------")

_mk_object(LOC, "veio-morto-p71", "Veio Morto", "Uma veia de estanho na rocha.")
motor.apply_resolution(MIN, {"extracao_ops": [
    op("mine", "veio-morto-p71", renovacao=0, ferramenta="picareta-p71")]})
fm_morto, _ = motor.io.read_doc(LOC / "veio-morto-p71" / "object.md")
check("renovação 0: NENHUM bloco de trabalho — esgotado para sempre",
      motor.trabalho.BLOCO not in fm_morto, str(fm_morto.get(motor.trabalho.BLOCO)))

_mk_object(LOC, "moita-viva-p71", "Moita Viva", "Moita cheia de folhas novas.")
motor.apply_resolution(MIN, {"extracao_ops": [
    op("forage", "moita-viva-p71", renovacao=10)]})
fm_viva, _ = motor.io.read_doc(LOC / "moita-viva-p71" / "object.md")
check("renovação > 0: bloco de trabalho instalado, com o texto ANTIGO guardado",
      isinstance(fm_viva.get(motor.trabalho.BLOCO), dict)
      and "Moita cheia" in (fm_viva[motor.trabalho.BLOCO]
                            .get("resultado", {}).get("description") or ""),
      str(fm_viva.get(motor.trabalho.BLOCO)))
check("renovacao_s(9) devolve exatamente as 3 h que a spec 054 usava fixo",
      prim.renovacao_s(9) == 3 * 3600, str(prim.renovacao_s(9)))
check("renovacao_s(0) é None — não é 'muito tempo', é NUNCA",
      prim.renovacao_s(0) is None)

_mk_object(LOC, "rocha-estoque-p71", "Rocha de Estoque", "Rocha cheia de minério.")
r_est = motor.apply_resolution(MIN, {"extracao_ops": [
    op("mine", "rocha-estoque-p71", ferramenta="picareta-p71", vencida="")]})
ids_est = (r_est.get("extracao_ops_applied") or [{}])[0].get("itens") or []
fm_pedra, _ = motor.io.read_doc(LOC / ids_est[0] / "item.md") if ids_est else ({}, "")
check("SEM descricao_vencida: pedra NÃO ganha prazo — ela ESTOCA",
      bool(ids_est) and "prazo" not in fm_pedra, str(fm_pedra.get("prazo")))

_mk_object(LOC, "moita-perec-p71", "Moita Perecível", "Moita de folhas tenras.")
r_per = motor.apply_resolution(MIN, {"extracao_ops": [
    op("forage", "moita-perec-p71", vencida="folhas murchas e escuras")]})
ids_per = (r_per.get("extracao_ops_applied") or [{}])[0].get("itens") or []
fm_erva, _ = motor.io.read_doc(LOC / ids_per[0] / "item.md") if ids_per else ({}, "")
check("COM descricao_vencida: a erva ganha prazo e murcha",
      bool(ids_per) and isinstance(fm_erva.get("prazo"), dict), str(fm_erva.get("prazo")))

print("\n--- 5. o porte julgado vira peso, e peso demais cai no chão ----------")

_mk_object(LOC, "carvalho-p71", "Carvalho", "Um carvalho antigo, tronco largo.")
r_tronco = motor.apply_resolution(MIN, {"extracao_ops": [
    op("chop", "carvalho-p71", ferramenta="picareta-p71", tamanho="XG")]})
ids_t = (r_tronco.get("extracao_ops_applied") or [{}])[0].get("itens") or []
fm_t, _ = motor.io.read_doc(LOC / ids_t[0] / "item.md") if ids_t else ({}, "")
check("porte XG vira peso pela física compartilhada, não 0,2 kg fixo",
      bool(ids_t) and fm_t.get("weight_kg") == prim.peso_da_porcao("XG")
      and fm_t.get("weight_kg") > 10, str(fm_t.get("weight_kg")))
check("a porção pesada nasce NO LUGAR (é o que obriga a arrastar)",
      bool(ids_t) and (LOC / ids_t[0] / "item.md").exists())

print("\n--- 6. cada capacidade alimenta a SUA maestria -----------------------")

# personagem NOVO, que só minera: o MIN acima já colheu ao longo do arquivo, e um
# `herbalismo` > 0 nele seria legítimo. Provar isolamento exige quem só fez uma coisa.
SO_MINA = "sominera-p71"
pasta_sm = _mk_char(SO_MINA, "Só Minera")
_mk_item_na_mao(pasta_sm, "picareta-sm-p71", "Picareta", "Picareta de bico vivo.")
_mk_object(LOC, "veio-sm-p71", "Veio Isolado", "Rocha com uma veia de estanho exposta.")
motor.apply_resolution(SO_MINA, {"extracao_ops": [
    op("mine", "veio-sm-p71", ferramenta="picareta-sm-p71")]})
profs_sm = motor.proficiencies_for(SO_MINA)
check("minerar alimentou `mineracao`", profs_sm.get("mineracao", 0) > 0, str(profs_sm))
check("minerar NÃO alimentou `herbalismo` — as maestrias são estanques",
      profs_sm.get("herbalismo", 0) == 0, str(profs_sm))
check("nem `lenha`", profs_sm.get("lenha", 0) == 0, str(profs_sm))
check("cortar alimentou `lenha` (no personagem que cortou)",
      motor.proficiencies_for(MIN).get("lenha", 0) > 0)

print("\n--- 7/8. recusa determinística e a location intocada -----------------")

r_nome = motor.apply_resolution(MIN, {"extracao_ops": [
    dict(op("mine", "parede-veio-p71", ferramenta="picareta-p71"),
         nome_comum="Parede de Veio")]})
check("o extraído não pode se chamar como a fonte",
      "extracao_nomeia_fonte" in [x.get("regra") for x in (r_nome.get("rejected") or [])],
      str(r_nome.get("rejected")))

antes = (LOC / "location.md").read_bytes()
motor.apply_resolution(MIN, {"extracao_ops": [op("forage", TAVERNA)]})
check("extrair do LUGAR não escreve uma linha em location.md",
      (LOC / "location.md").read_bytes() == antes)

print("\n--- 9. nenhuma chave central nova (T038) -----------------------------")

arb = (SERVER_DIR / "arbiter.py").read_text(encoding="utf-8")
i = arb.find("def _verb_candidates")
corpo = arb[i:arb.find("\ndef ", i + 10)]
chaves = set(re.findall(r'"(\w+)":', corpo))
check("`extracao_onde` é UMA chave para as TRÊS capacidades",
      "extracao_onde" in chaves and "forage_onde" not in chaves)
check("as duas chaves duplicadas de instrumento viraram UMA (`empunhavel`)",
      "empunhavel" in chaves
      and "sing_instrumento" not in chaves and "write_instrumento" not in chaves)
check("nenhuma chave por capacidade nova nasceu",
      not {"mine_onde", "chop_onde", "mine_ferramenta", "chop_ferramenta"} & chaves)

# =========================================================================== #
# US4 — o relógio: prazo que nunca vencia, e coisa pronta que apodrecia
# =========================================================================== #
print("\n--- US4. os dois consertos do relógio da spec 070 ---------------------")

import time  # noqa: E402
from motor import prazo, trabalho  # noqa: E402

# V4.1 — prazo em OBJECT vence. Até a 071 o gancho de leitura existia só no ramo
# do `item.md`, e `carimbar_se_houver` aceitava `filename` para nada.
OBS = "observador-p71"
_mk_char(OBS, "Observador")
_mk_object(LOC, "fogueira-p71", "Fogueira", "Chamas altas, lenha ainda inteira.")
prazo.carimbar(LOC / "fogueira-p71", -1, {"verbo": "virar"},
               urgencia="", descricao_vencida="Só cinzas frias e um cheiro de queimado.",
               filename="object.md")
motor.get_context(OBS)                       # é a LEITURA que faz o tempo passar
_, corpo_fog = motor.io.read_doc(LOC / "fogueira-p71" / "object.md")
check("V4.1: prazo carimbado num OBJECT vence quando alguém olha",
      "cinzas frias" in corpo_fog, corpo_fog.strip()[:70])

# V4.2 — a coisa PRONTA não apodrece. A janela é esforço x3 e o esforço nunca
# excede o relógio de parede: TODA peça concluída ficava com o prazo vivo.
peca_id, pasta_peca = trabalho.criar_peca(
    LOC, "Um alaúde ainda em processo.",
    {"tool": "craft", "tipo": "item", "tempo_necessario_s": 10,
     "tempo_trabalhado_s": 0, "banda": "comum", "nome_final": "Alaúde"},
    name="Alaúde (em processo)")
prazo.carimbar(pasta_peca, 30, {"verbo": "virar"}, urgencia="a cola ainda está fresca",
               descricao_vencida="Alaúde colado de forma indevida, que range.")
fm_antes, _ = motor.io.read_doc(pasta_peca / "item.md")
check("V4.2 (montagem): a peça em processo REALMENTE tinha prazo vivo",
      isinstance(fm_antes.get(prazo.BLOCO), dict))
trabalho.encerrar(pasta_peca, {"name": "Alaúde"}, "Um alaúde inteiro, bem colado.")
fm_pronto, corpo_pronto = motor.io.read_doc(pasta_peca / "item.md")
check("V4.2: concluir a peça leva o bloco `trabalho` embora",
      trabalho.BLOCO not in fm_pronto)
check("V4.2: e leva o `prazo` JUNTO — a coisa pronta não apodrece depois",
      prazo.BLOCO not in fm_pronto, str(fm_pronto.get(prazo.BLOCO)))
motor.get_context(OBS)
_, corpo_depois = motor.io.read_doc(pasta_peca / "item.md")
check("V4.2: e continua sendo o que foi terminado, depois de uma leitura",
      "bem colado" in corpo_depois, corpo_depois.strip()[:70])

print()
if FAILS:
    print(f"{len(FAILS)} FALHA(S): " + "; ".join(FAILS))
    sys.exit(1)
print("fase 71b: extração + relógio OK.")
