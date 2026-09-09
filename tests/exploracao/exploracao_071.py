"""EXPLORATÓRIO da spec 071 — o que a suíte não vê.

Roda em mundo tmp (o `world/` é save do jogador e não se muta em teste). Passa
pelas lentes da skill `loreforge-implement-review`: protagonista, combinação
cruzada, extremos, adversário, silêncio/assimetria, e a negação como conteúdo.

Não decide nada. Relata para o mantenedor decidir.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[2]
_tmp = Path(tempfile.mkdtemp(prefix="loreforge-expl71-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
os.environ["LOREFORGE_LOG"] = "0"
sys.path.insert(0, str(SERVER_DIR))
import motor  # noqa: E402
import arbiter  # noqa: E402
import app  # noqa: E402

TAV = "taverna-do-gancho"
LOC = motor.WORLD_DIR / TAV
achados: list[tuple[str, str, str]] = []


def anota(tipo, titulo, detalhe):
    achados.append((tipo, titulo, detalhe))
    print(f"  [{tipo}] {titulo}\n      {detalhe}")


def char(cid, nome, **st):
    d = LOC / cid
    d.mkdir(parents=True, exist_ok=True)
    cond = st.get("conditions", [])
    (d / "character.md").write_text(
        f"---\ntype: character\nid: {cid}\nname: {nome}\ncontrolled_by: player_local\n"
        f"weight_kg: 80\nattributes:\n  STR: 14\n  DEX: 10\n  CON: 12\n  INT: 10\n"
        f"  WIS: 10\n  CHA: 10\n"
        f"status:\n  hp: {st.get('hp', 20)}\n  hp_max: 20\n  hunger: sem fome\n"
        f"  fatigue: 0\n  action: parado\n  mood: neutro\n  conditions: {cond}\n"
        f"origin: editorial\n---\n{st.get('prosa', 'Alguém.')}\n", encoding="utf-8")
    return d


def obj(oid, nome, desc, pasta=None):
    d = (pasta or LOC) / oid
    d.mkdir(parents=True, exist_ok=True)
    (d / "object.md").write_text(
        f"---\ntype: object\nid: {oid}\nname: {nome}\norigin: editorial\n---\n{desc}\n",
        encoding="utf-8")
    return d


def item(pasta, iid, nome, desc, na_mao=True, peso=2):
    d = pasta / iid
    d.mkdir(parents=True, exist_ok=True)
    slot = "slot: hand\n" if na_mao else ""
    (d / "item.md").write_text(
        f"---\ntype: item\nid: {iid}\nname: {nome}\nsize: M\nweight_kg: {peso}\n{slot}"
        f"origin: editorial\n---\n{desc}\n", encoding="utf-8")
    return d


def op(cap, onde, **kw):
    base = {"onde": onde, "capacidade": cap, "alvo": 8, "ferramenta_nota": 9,
            "rendimento": 7, "renovacao": 9, "tamanho": "P",
            "nome_pobre": "Cascalho", "descricao_pobre": "lascas",
            "nome_comum": "Estanho", "descricao_comum": "metal bruto",
            "nome_rica": "Placa", "descricao_rica": "metal em placa",
            "descricao_extraida": "aberta e revirada",
            "urgencia": "", "descricao_vencida": ""}
    base.update(kw)
    return base


print("\n=== LENTE 1: o protagonista de ponta a ponta ==========================")
P = "brita-expl"
pb = char(P, "Brita, a Britadeira")
item(pb, "picareta-expl", "Picareta", "Picareta de bico vivo.")
obj("veio-expl", "Veio de Estanho", "Rocha lascada com veia de estanho exposta.")

r = motor.apply_resolution(P, {"extracao_ops": [op("mine", "veio-expl", ferramenta="picareta-expl")]})
itens = (r.get("extracao_ops_applied") or [{}])[0].get("itens") or []
anota("confirmação", "minerar -> pegar -> guardar -> dar: o encadeamento fecha",
      f"nasceram {len(itens)} porções; ids {itens[:2]}")

# a porção extraída atravessa os verbos antigos
if itens:
    r2 = motor.apply_resolution(P, {"item_transfers": [{"item": itens[0], "to": P}]})
    achou = motor.find_entity(itens[0])
    anota("confirmação", "a porção extraída é item comum: `take` a move sem caso especial",
          f"agora em {achou[0].parent.parent.name}" if achou else "sumiu")

print("\n=== LENTE 2: a combinação cruzada ====================================")
# extração -> craft (o percurso que originou a spec)
obj("carvalho-expl", "Carvalho Caído", "Um tronco de carvalho caído, madeira boa.")
item(pb, "machado-expl", "Machado", "Machado de lenhador, fio bom.")
r3 = motor.apply_resolution(P, {"extracao_ops": [
    op("chop", "carvalho-expl", ferramenta="machado-expl", tamanho="XG",
       nome_comum="Tora de Carvalho", descricao_comum="uma tora pesada")]})
toras = (r3.get("extracao_ops_applied") or [{}])[0].get("itens") or []
if toras:
    fm_t, _ = motor.io.read_doc(LOC / toras[0] / "item.md")
    cap = motor.fisica.carry_capacity(motor.io.read_doc(pb / "character.md")[0])
    anota("confirmação", "a tora XG excede a carga e fica no chão — obriga a arrastar",
          f"peso {fm_t.get('weight_kg')} kg vs capacidade {cap} kg; nasceu em {TAV}")
    # e o craft a enxerga como material
    ctx = arbiter.build_ctx(motor.get_context(P), prosa={"acao": "erguer um abrigo"})
    mat = ctx.cand.get("craft_materiais") or []
    anota("confirmação" if toras[0] in mat else "lacuna",
          "o craft enxerga a tora extraída como material",
          f"tora no enum de craft_materiais: {toras[0] in mat}")

# extração -> cozinha
r4 = motor.apply_resolution(P, {"extracao_ops": [
    op("forage", TAV, nome_comum="Raízes", descricao_comum="raízes lavadas",
       vencida="raízes murchas", urgencia="ainda estão firmes")]})
raizes = (r4.get("extracao_ops_applied") or [{}])[0].get("itens") or []
if raizes:
    ctx2 = arbiter.build_ctx(motor.get_context(P), prosa={"acao": "cozinhar"})
    ing = ctx2.cand.get("cook_ingredientes") or []
    anota("confirmação" if raizes[0] in ing else "lacuna",
          "o colhido entra como ingrediente de `cook` sem nada novo",
          f"raiz no enum de cook_ingredientes: {raizes[0] in ing}")

print("\n=== LENTE 3: extremos e degenerados ==================================")
# minerar o mesmo veio muitas vezes: a renovação segura?
obj("veio-teimoso", "Veio Teimoso", "Rocha com veia de estanho.")
n_ok = 0
for i in range(12):
    rr = motor.apply_resolution(P, {"extracao_ops": [
        op("mine", "veio-teimoso", ferramenta="picareta-expl", renovacao=5)]})
    if rr.get("extracao_ops_applied"):
        n_ok += 1
anota("confirmação" if n_ok == 1 else "lacuna",
      "insistir 12x no mesmo alvo: a renovação barra a partir da 2ª",
      f"{n_ok} de 12 tentativas renderam (esperado 1 — depois o alvo está em renovação)")

# porte extremo
obj("montanha-expl", "Montanha", "Rocha maciça, minério por toda parte.")
r5 = motor.apply_resolution(P, {"extracao_ops": [
    op("mine", "montanha-expl", ferramenta="picareta-expl", tamanho="XXXXXG")]})
ids5 = (r5.get("extracao_ops_applied") or [{}])[0].get("itens") or []
if ids5:
    fm5, _ = motor.io.read_doc(LOC / ids5[0] / "item.md")
    anota("calibragem", "porte fora da escala da régua ainda produz item carregável?",
          f"tamanho pedido XXXXXG -> gravado {fm5.get('size')}, {fm5.get('weight_kg')} kg")

print("\n=== LENTE 4: o adversário ============================================")
# minerar um PERSONAGEM
r6 = motor.apply_resolution(P, {"extracao_ops": [op("mine", P, ferramenta="picareta-expl")]})
anota("confirmação", "minerar um PERSONAGEM: recusa estrutural, sem chamar régua",
      str([x.get("regra") for x in (r6.get("rejected") or [])]))

# minerar com uma ferramenta que NÃO está com ele
r7 = motor.apply_resolution(P, {"extracao_ops": [
    op("mine", "veio-expl", ferramenta="ferramenta-que-nao-existe")]})
anota("confirmação", "ferramenta inexistente: o Motor revalida contra os arquivos",
      str([x.get("regra") for x in (r7.get("rejected") or [])]))

# minerar deitado/morto
D = "caido-expl"
char(D, "Caído", conditions=["incapacitado"], hp=0)
pd = LOC / D
item(pd, "picareta-caido", "Picareta", "Picareta.")
r8 = motor.apply_resolution(D, {"extracao_ops": [
    op("mine", "veio-expl", ferramenta="picareta-caido")]})
anota("lacuna" if r8.get("extracao_ops_applied") else "confirmação",
      "quem está INCAPACITADO consegue minerar?",
      f"aplicou={bool(r8.get('extracao_ops_applied'))} rejeitado={[x.get('regra') for x in (r8.get('rejected') or [])]}")

print("\n=== LENTE 5: silêncio e assimetria ===================================")
T = "teste-munha"
char(T, "Testemunha")
obj("veio-vis", "Veio Visível", "Rocha com veia de estanho.")
motor.apply_resolution(P, {"extracao_ops": [op("mine", "veio-vis", ferramenta="picareta-expl")]})
mems_t = [m.get("evento") for m in motor.memoria._iter_memories(T)]
mems_p = [m.get("evento") for m in motor.memoria._iter_memories(P)]
anota("confirmação" if "witness_mine" in mems_t else "lacuna",
      "quem VÊ minerar lembra de MINERAR (não de colher)",
      f"testemunha: {[m for m in mems_t if 'witness' in (m or '')][:3]}")
anota("confirmação", "quem minera lembra no domínio certo",
      f"ator: {[m for m in mems_p if m and ('mine' in m or 'chop' in m or 'forage' in m)][:4]}")

print("\n=== LENTE 6: a negação como conteúdo =================================")
for regra in ("sem_materia", "ferramenta_impropria", "nada_a_extrair",
              "extracao_nomeia_fonte", "ferramenta_inacessivel", "juizo_ausente"):
    frase = motor.io._WHY_BY_REGRA.get(regra, "(SEM FRASE)")
    ruim = any(p in frase.lower() for p in
               ("erro", "modelo", "sistema", "json", "nota", "régua", "id "))
    print(f"  [{'ok' if not ruim else 'REVER'}] {regra:26} -> {frase}")

# e a frase como o JOGADOR a lê, passando por inworld_failures
rej_fake = [{"regra": "ferramenta_impropria", "why": motor.io._WHY_BY_REGRA["ferramenta_impropria"],
             "valores": {"item": "colher-de-pau"}, "item": "colher-de-pau"},
            {"regra": "juizo_ausente", "why": motor.io._WHY_BY_REGRA["juizo_ausente"],
             "valores": {}, "item": ""}]
for f in app.inworld_failures(rej_fake):
    print(f"      jogador lê: {f['o_que_falhou']}")

print("\n" + "=" * 72)
print(f"{len(achados)} achados registrados.")
for tipo, titulo, _ in achados:
    print(f"  {tipo:14} {titulo}")
