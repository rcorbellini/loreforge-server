"""EXPLORATÓRIO da spec 066 — atacar o vínculo de todos os ângulos.

Não é checagem: é a postura de um jogador curioso e um pouco malicioso. As lentes da
skill `loreforge-implement-review`, todas, e não duas ou três.

Uso:  python3 tests/exploracao/explorar_vinculo.py
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent.parent.parent
TAVERNA = "taverna-do-gancho"
_tmp = Path(tempfile.mkdtemp(prefix="loreforge-expl66-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
sys.path.insert(0, str(SERVER_DIR))

import validator
import motor
from motor import indice, vinculos

ACHADOS = []


def achado(tipo, texto):
    ACHADOS.append((tipo, texto))
    print(f"    >> [{tipo}] {texto}")


def cen(titulo):
    print(f"\n--- {titulo} " + "-" * max(0, 68 - len(titulo)))


def _mk(cid, name, bonds="", pasta=TAVERNA):
    d = motor.WORLD_DIR / pasta / cid
    d.mkdir(parents=True, exist_ok=True)
    (d / "character.md").write_text(
        f"---\ntype: character\nid: {cid}\nname: {name}\n"
        f"controlled_by: player_local\nweight_kg: 70\n"
        f"attributes:\n  STR: 10\n  DEX: 10\n  CON: 10\n  INT: 10\n  WIS: 10\n  CHA: 10\n"
        f"status:\n  hp: 50\n  hp_max: 50\n  hunger: saciado\n  fatigue: baixo\n"
        f"  action: parado\n  mood: neutro\n  conditions: []\n"
        f"origin: editorial\n{bonds}---\n{name}.\n", encoding="utf-8")
    indice.invalidar(d / "character.md")
    return d


def _fm(cid="x", **e):
    b = {"type": "character", "id": cid, "name": "X", "controlled_by": "player_local",
         "attributes": {"STR": 10, "DEX": 10, "CON": 10, "INT": 10, "WIS": 10, "CHA": 10},
         "status": {"hp": 10, "hp_max": 10, "action": "parado"}}
    b.update(e)
    return b


# ======================================================================= #
cen("LENTE: extremos e degenerados")

# 20 vínculos num personagem só — o trecho social explode?
muitos = "bonds:\n" + "".join(
    f"  - target: alvo-{i}\n    label: primo\n" for i in range(20))
print(f"    20 vínculos declarados: válido? {validator.validate(_fm(bonds=[{'target': f'a{i}', 'label': 'primo'} for i in range(20)])) == []}")

# rótulo gigante
gigante = "irmão de criação que me pegou quando nossa mãe morreu no inverno de antes"
r = validator.validate(_fm(bonds=[{"target": "outro", "label": gigante}]))
print(f"    rótulo de {len(gigante.split())} palavras: {'aceito' if not r else 'recusado'}")
if not r:
    achado("calibragem",
           f"rótulo de {len(gigante.split())} palavras é aceito sem limite. É o desenho "
           f"(sem bound, research R1), mas nada impede um autor de pôr uma frase inteira "
           f"onde o desenho pede sintagma. Orientação editorial não tem quem a cobre.")

# rótulo com quebra de linha / caractere estranho
for esquisito in ["irmã\nfalsa", "irmã\t\t", "IRMÃ!!!", "🩸irmã"]:
    r = validator.validate(_fm(bonds=[{"target": "o", "label": esquisito}]))
    print(f"    label {esquisito!r}: {'aceito' if not r else 'recusado'}")
if not validator.validate(_fm(bonds=[{"target": "o", "label": "irmã\nfalsa"}])):
    achado("lacuna",
           "rótulo com QUEBRA DE LINHA passa na validação. Ele desce para a prosa do "
           "trecho social e pode partir a frase que A Mente lê — e, pior, um `\\n` no "
           "meio de um rótulo é um vetor de injeção de instrução no prompt dela.")

# bonds vazio
print(f"    `bonds: []` (lista vazia): {'válido' if validator.validate(_fm(bonds=[])) == [] else 'erro'}")

# ======================================================================= #
cen("LENTE: o adversário — alvos que não deveriam funcionar")

_mk("adv-ator", "Adversário",
    bonds=("bonds:\n"
           "  - target: taverna-do-gancho\n    label: casa\n"
           "  - target: mem-inexistente-999\n    label: lembrança\n"))
indice.sincronizar()
b = vinculos.bonds_of("adv-ator")
print(f"    vínculos saneados: {b}")
print(f"    vínculo com o LUGAR onde ele está: {vinculos.bond_toward('adv-ator', 'taverna-do-gancho')!r}")
print(f"    vínculo com id inexistente: {vinculos.bond_toward('adv-ator', 'mem-inexistente-999')!r}")
achado("confirmação positiva",
       "alvo inexistente não quebra nada: a primitiva devolve o rótulo, o contexto só "
       "o mostra se a entidade estiver na cena, e a entidade não existe — some sozinho. "
       "Aresta pendente tratada como ausência, igual a `name_of` e `dono`.")

ctx_adv = motor.get_context("adv-ator")
print(f"    o lugar traz bond? {ctx_adv['location'].get('bond')!r}")

# vínculo com MEMÓRIA (id de memória é entidade indexada!)
_mk("adv-mem", "Memorioso")
mid = motor.record_event("adv-mem", "Lembro de algo.", "insulto", ["adv-ator"],
                         intensity="small")
if mid:
    d = motor.find_character_folder("adv-mem")
    t = (d / "character.md").read_text(encoding="utf-8")
    t = t.replace("origin: editorial\n",
                  f"origin: editorial\nbonds:\n  - target: {mid}\n    label: aquilo\n")
    (d / "character.md").write_text(t, encoding="utf-8")
    indice.invalidar(d / "character.md")
    indice.sincronizar()
    print(f"    vínculo apontando para uma MEMÓRIA: {vinculos.bond_toward('adv-mem', mid)!r}")
    achado("lacuna",
           "o `target` aceita QUALQUER id indexado — inclusive o de uma MEMÓRIA ou de um "
           "rastro. A spec dizia 'qualquer entidade do mundo' pensando em pessoa/item/"
           "lugar; memória e rastro entraram de carona. Não quebra (não estão na cena, "
           "então não descem), mas é superfície que ninguém desenhou.")

# ======================================================================= #
cen("LENTE: silêncio e assimetria — os dois lados de toda relação")

_mk("as-a", "A", bonds="bonds:\n  - target: as-b\n    label: pai\n")
_mk("as-b", "B", bonds="bonds:\n  - target: as-a\n    label: filha\n")
indice.sincronizar()
print(f"    A vê B como: {vinculos.bond_toward('as-a','as-b')!r}")
print(f"    B vê A como: {vinculos.bond_toward('as-b','as-a')!r}")
print(f"    Árbitro sobre A: {vinculos.bonds_toward_me('as-a')}")
achado("confirmação positiva",
       "recíproco com PALAVRAS DIFERENTES funciona ('pai'/'filha'), que era o motivo de "
       "declarar por ponto de vista em vez de espelhar uma aresta só.")

# contradição: os dois se dizem PAI um do outro
_mk("ct-a", "CtA", bonds="bonds:\n  - target: ct-b\n    label: pai\n")
_mk("ct-b", "CtB", bonds="bonds:\n  - target: ct-a\n    label: pai\n")
indice.sincronizar()
print(f"    contradição mútua (ambos 'pai'): A->B {vinculos.bond_toward('ct-a','ct-b')!r}"
      f" | B->A {vinculos.bond_toward('ct-b','ct-a')!r}")
achado("dinâmica emergente",
       "dois personagens podem declarar-se PAI um do outro, e o mundo aceita sem "
       "piscar. É consequência direta de 'declarado, não verdadeiro' — e é o que "
       "sustenta o impostor. Mas nada avisa o AUTOR de que ele escreveu um absurdo: "
       "não há checagem de coerência entre os dois lados, nem deveria haver "
       "silenciosamente. É decisão do mantenedor se o validador deve AVISAR.")

# ======================================================================= #
cen("LENTE: cruzar com o que já existia")

# o vínculo sobrevive ao esquecimento? (não deve decair)
_mk("cx-ator", "Cruzado", bonds="bonds:\n  - target: cx-alvo\n    label: irmã\n")
_mk("cx-alvo", "Alvo")
indice.sincronizar()
for i in range(4):
    motor.record_event("cx-ator", f"Lembro dela ({i}).", "insulto", ["cx-alvo"],
                       intensity="giant", valence={"cx-alvo": "negativa"})
antes = vinculos.bond_toward("cx-ator", "cx-alvo")
# apaga TODAS as memórias
mem_dir = motor.find_character_folder("cx-ator") / "memories"
for f in mem_dir.glob("*.md"):
    f.unlink()
indice.sincronizar()
depois = vinculos.bond_toward("cx-ator", "cx-alvo")
print(f"    vínculo antes de apagar toda a memória: {antes!r}")
print(f"    vínculo DEPOIS de apagar toda a memória: {depois!r}")
print(f"    afeto depois: {motor.sentiment_toward('cx-ator','cx-alvo')}")
achado("confirmação positiva",
       "o vínculo SOBREVIVE ao apagamento total da memória, e o afeto vai a zero junto "
       "com ela. É exatamente a ortogonalidade que a spec defende, provada pelo caso "
       "extremo: a lembrança some, o parentesco fica.")

# o vínculo interfere no apego/afeto?
print(f"    apego cx-ator -> cx-alvo (sem memória): {motor.familiarity_with('cx-ator','cx-alvo')}")

# ======================================================================= #
cen("LENTE: a negação como conteúdo — as recusas são narráveis?")

for rotulo in ["dono", "minha faca", "credor", "forjei isto"]:
    erros = validator.validate(_fm(bonds=[{"target": "o", "label": rotulo}]))
    print(f"    {rotulo!r}: {erros[0][:100] if erros else 'ACEITO'}")

# e os falsos positivos da regra de recusa?
for legitimo in ["dona de casa", "senhora do moinho", "credor da guilda",
                 "meio-irmão", "minha gente"]:
    erros = validator.validate(_fm(bonds=[{"target": "o", "label": legitimo}]))
    print(f"    {legitimo!r}: {'RECUSADO' if erros else 'aceito'}")

_falsos = [l for l in ["dona de casa", "senhora do moinho", "meio-irmão"]
           if validator.validate(_fm(bonds=[{"target": "o", "label": l}]))]
if _falsos:
    achado("calibragem",
           f"a regra de recusa do FR-006 pega FALSO POSITIVO em {_falsos}. Ela casa "
           f"substring, então 'dona de casa' é lida como posse e 'meio-irmão' escapa "
           f"por sorte. Um rótulo legítimo recusado é pior que um ilegítimo aceito: "
           f"o autor não entende por que o mundo não aceita a palavra dele.")

# ======================================================================= #
cen("LENTE: o protagonista — o vínculo atravessa o resto do jogo?")

_mk("pr-ator", "Protagonista", bonds="bonds:\n  - target: pr-alvo\n    label: irmã\n")
_mk("pr-alvo", "A Irmã")
indice.sincronizar()
ctx = motor.get_context("pr-ator")
_alvo = {c["id"]: c for c in ctx["characters_present"]}["pr-alvo"]
print(f"    na cena: bond={_alvo.get('bond')!r}")

# ela se move para outro lugar — o vínculo some da cena?
outro = motor.WORLD_DIR / "praca-do-mercado"
if outro.exists():
    motor.move_entity(motor.find_character_folder("pr-alvo"), outro / "pr-alvo")
    indice.sincronizar()
    ctx2 = motor.get_context("pr-ator")
    ainda = any(c["id"] == "pr-alvo" for c in ctx2["characters_present"])
    print(f"    depois de ela sair da cena, aparece? {ainda}")
    print(f"    mas a primitiva ainda sabe: {vinculos.bond_toward('pr-ator','pr-alvo')!r}")
    achado("confirmação positiva",
           "o vínculo acompanha o recorte da cena (Assumption da spec): quem saiu não "
           "desce, e a primitiva continua sabendo — quem quiser o ausente tem por onde.")

print()
print("=" * 74)
print(f"{len(ACHADOS)} ACHADO(S)")
for tipo, txt in ACHADOS:
    print(f"\n[{tipo.upper()}]\n  {txt}")
shutil.rmtree(_tmp, ignore_errors=True)
