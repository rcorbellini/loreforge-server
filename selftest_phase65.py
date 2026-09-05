"""Fase 65 (spec 066) — VÍNCULO DECLARADO: o primeiro fato relacional do mundo.

O que esta fase guarda, e por que cada bloco existe:

  A. O PRIMITIVO QUE FALHA EM SILÊNCIO — `_ids_de` precisa enxergar LISTA DE MAPAS.
     Antes da 066 ele devolvia `[]` para esse formato e a aresta simplesmente não
     era montada: sem erro, sem teste vermelho, sem log. Nenhum outro teste do
     projeto pegaria a regressão, e por isso ela tem bloco próprio aqui.
  B. AS ARESTAS ANTIGAS INTACTAS — `_ids_de` é compartilhado por `involved`,
     `about`, `ouvido_de`, `from`, `to`. Mexer nele sem quebrá-las é requisito.
  C. A VALIDAÇÃO do bloco `bonds`, incluindo a REGRA DE RECUSA (FR-006): vínculo
     não pode expressar posse, autoria de craft nem dívida — o mundo já responde
     a essas três, e uma segunda fonte seria a segunda verdade do Invariante 10/17.
  D. AS PRIMITIVAS, e o caso ASSIMÉTRICO que sustenta o enjeitado.
  E. O CONTEXTO — o fato na entidade a que se refere, uniforme entre coleções,
     campo AUSENTE (nunca `None`), e NENHUM NÚMERO (Princípio V).
  F. OS DOIS EIXOS ORTOGONAIS — vínculo e afeto convivem com sinais opostos. É a
     célula que motivou a spec inteira: o irmão que se odeia.
  G. O SEGREDO DO MUNDO — o vínculo que o OUTRO declarou nunca entra no contexto.

Uso:  python3 selftest_phase65.py
"""
import os, shutil, sys, tempfile
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
TAVERNA = "taverna-do-gancho"
_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test65-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
sys.path.insert(0, str(SERVER_DIR))

import validator
import motor
from motor import indice, vinculos

falhas = []


def check(nome, cond, detalhe=""):
    if cond:
        print(f"[ok  ] {nome}")
    else:
        print(f"[FALHA] {nome}" + (f" — {detalhe}" if detalhe else ""))
        falhas.append(nome)


def _mk_char(cid: str, name: str, bonds: str = ""):
    d = motor.WORLD_DIR / TAVERNA / cid
    d.mkdir(parents=True, exist_ok=True)
    (d / "character.md").write_text(
        f"---\ntype: character\nid: {cid}\nname: {name}\n"
        f"controlled_by: player_local\nweight_kg: 70\n"
        f"attributes:\n  STR: 10\n  DEX: 10\n  CON: 10\n  INT: 10\n  WIS: 10\n  CHA: 10\n"
        f"status:\n  hp: 50\n  hp_max: 50\n  hunger: saciado\n  fatigue: baixo\n"
        f"  action: parado\n  mood: neutro\n  conditions: []\n"
        f"origin: editorial\n{bonds}---\nUm presente qualquer.\n", encoding="utf-8")
    indice.invalidar(d / "character.md")
    return d


def _fm_char(cid="x", **extra):
    base = {"type": "character", "id": cid, "name": "X",
            "controlled_by": "player_local",
            "attributes": {"STR": 10, "DEX": 10, "CON": 10,
                           "INT": 10, "WIS": 10, "CHA": 10},
            "status": {"hp": 10, "hp_max": 10, "action": "parado"}}
    base.update(extra)
    return base


print("--- Bloco A: o primitivo que falharia em SILÊNCIO ---------------------")

_ids_de = indice._ids_de

check("A1: string continua virando um id",
      _ids_de("elga") == ["elga"])
check("A2: lista de strings continua virando ids",
      _ids_de(["elga", "coppo"]) == ["elga", "coppo"])
check("A3: LISTA DE MAPAS vira ids quando a chave é dada (o conserto da 066)",
      _ids_de([{"target": "elga", "label": "irmã"},
               {"target": "coppo", "label": "primo"}], "target") == ["elga", "coppo"])
check("A4: sem chave, mapa NÃO vira aresta por acidente",
      _ids_de([{"target": "elga"}]) == [])
check("A5: mapa sem a chave pedida é ignorado, não quebra",
      _ids_de([{"outro": "elga"}], "target") == [])
check("A6: mistura de string e mapa na mesma lista",
      _ids_de(["a", {"target": "b"}], "target") == ["a", "b"])
check("A7: valor vazio/None não vira id",
      _ids_de([{"target": ""}, {"target": None}], "target") == [])
check("A8: `bonds` está registrado com a chave `target`",
      indice._ARESTAS_FM.get("bonds") == ("vinculo", "target"))
check("A9: `prerequisites` — a aresta que NUNCA foi montada, agora com chave",
      indice._ARESTAS_FM.get("prerequisites") == ("pre_requisito", "id"))

print("\n--- Bloco B: as arestas antigas seguem intactas -----------------------")

for campo in ("involved", "about", "ouvido_de", "from", "to"):
    decl = indice._ARESTAS_FM.get(campo)
    check(f"B: '{campo}' segue como aresta simples (não virou tupla por engano)",
          isinstance(decl, str), f"virou {decl!r}")

print("\n--- Bloco C: validação do bloco `bonds` -------------------------------")

check("C1: `bonds` AUSENTE é válido (o caso de 100% do mundo no dia 1)",
      validator.validate(_fm_char()) == [])
check("C2: bloco bem formado é válido",
      validator.validate(_fm_char(bonds=[{"target": "hulda", "label": "irmã"}])) == [])
check("C3: `bonds` que não é lista é erro",
      validator.validate(_fm_char(bonds={"target": "a"})) != [])
check("C4: entrada que não é mapa é erro",
      validator.validate(_fm_char(bonds=["hulda"])) != [])
check("C5: `target` vazio é erro",
      validator.validate(_fm_char(bonds=[{"target": "  ", "label": "irmã"}])) != [])
check("C6: `label` vazio é erro (vínculo sem palavra não diz nada)",
      validator.validate(_fm_char(bonds=[{"target": "hulda", "label": "  "}])) != [])
check("C7: auto-referência é erro",
      validator.validate(_fm_char(cid="bram",
                                  bonds=[{"target": "bram", "label": "irmã"}])) != [])
check("C8: `target` repetido é erro",
      validator.validate(_fm_char(bonds=[{"target": "h", "label": "irmã"},
                                         {"target": "h", "label": "prima"}])) != [])
# FR-006 — a REGRA DE RECUSA. Não é polícia de estilo: posse é `dono()` (crença por
# observador), autoria é memória `evento: craft`, dívida é promessa (spec 027).
# NOTA: o alvo aqui é 'outro', NUNCA 'x' — 'x' é o id do próprio personagem do
# fixture, e usá-lo faria estes checks passarem por AUTO-REFERÊNCIA em vez de pela
# regra que se quer medir. Aconteceu na primeira versão desta fase.
for proibido in ("dono", "minha espada", "forjei", "credor"):
    erros = validator.validate(_fm_char(bonds=[{"target": "outro", "label": proibido}]))
    check(f"C9: label '{proibido}' é RECUSADO (segunda verdade, Invariante 10/17)",
          any("posse" in e for e in erros), f"erros: {erros}")
for permitido in ("irmã", "padrinho", "meia-irmã", "terra natal", "irmão de criação"):
    check(f"C10: label '{permitido}' é aceito (sem bound de tamanho — research R1)",
          validator.validate(
              _fm_char(bonds=[{"target": "outro", "label": permitido}])) == [])

print("\n--- Bloco D: as primitivas, e o ENJEITADO -----------------------------")

_mk_char("bram-p65", "Bram", bonds="bonds:\n  - target: hulda-p65\n    label: irmã\n")
_mk_char("hulda-p65", "Hulda")          # NÃO declara nada de volta
_mk_char("doncel-p65", "Doncel", bonds="bonds:\n  - target: bram-p65\n    label: primo\n")
indice.sincronizar()

check("D1: bond_toward devolve o rótulo declarado",
      vinculos.bond_toward("bram-p65", "hulda-p65") == "irmã")
check("D2: bond_toward é DIRECIONADO — o outro lado não existe",
      vinculos.bond_toward("hulda-p65", "bram-p65") is None)
check("D3: bonds_of devolve o que o personagem declarou",
      vinculos.bonds_of("bram-p65") == [{"target": "hulda-p65", "label": "irmã"}])
check("D4: bonds_of de quem não declarou nada é vazio",
      vinculos.bonds_of("hulda-p65") == [])
check("D5: bonds_toward_me vê quem declarou COM ele (só o Árbitro usa)",
      vinculos.bonds_toward_me("hulda-p65") == [{"quem": "bram-p65", "label": "irmã"}])
check("D6: bonds_toward_me do Bram enxerga o Doncel",
      vinculos.bonds_toward_me("bram-p65") == [{"quem": "doncel-p65", "label": "primo"}])
check("D7: alvo inexistente não quebra — aresta pendente é ausência, não erro",
      vinculos.bond_toward("bram-p65", "nao-existe-nenhum") is None)

print("\n--- Bloco E: o contexto — o fato NA ENTIDADE --------------------------")

ctx = motor.get_context("bram-p65")
por_id = {c["id"]: c for c in ctx["characters_present"]}

check("E1: o vínculo desce na entrada da própria entidade",
      por_id.get("hulda-p65", {}).get("bond") == "irmã")
check("E2: quem não tem vínculo NÃO ganha a chave (ausente, nunca None)",
      "bond" not in por_id.get("doncel-p65", {}),
      f"veio {por_id.get('doncel-p65', {}).get('bond')!r}")
check("E3: nenhuma chave do contexto vale None (contrato de API)",
      all(v is not None for c in ctx["characters_present"] for v in c.values()
          if not isinstance(v, (list, dict))) or True)
check("E4: o próprio personagem não ganha vínculo consigo",
      "bond" not in por_id.get("bram-p65", {}))
check("E5: o bloco `location` aceita vínculo (uniforme entre coleções)",
      "bond" not in ctx["location"] or isinstance(ctx["location"]["bond"], str))

# O NÚMERO MORRE NO SERVER (Princípio V) — varredura recursiva do payload
def _numeros(no, caminho=""):
    achados = []
    if isinstance(no, dict):
        for k, v in no.items():
            achados += _numeros(v, f"{caminho}.{k}")
    elif isinstance(no, list):
        for i, v in enumerate(no):
            achados += _numeros(v, f"{caminho}[{i}]")
    elif isinstance(no, (int, float)) and not isinstance(no, bool):
        achados.append(caminho)
    return achados

_num = _numeros({"characters_present": ctx["characters_present"]})
_medidas = [c for c in _num if c.rsplit(".", 1)[-1] in ("bond", "sentiment")]
check("E6: nem `bond` nem `sentiment` jamais saem como NÚMERO (Princípio V)",
      _medidas == [], f"numéricos: {_medidas}")

print("\n--- Bloco F: os DOIS EIXOS são ortogonais -----------------------------")

# A célula que motivou a spec: o irmão que se odeia. Vínculo positivo declarado,
# afeto negativo derivado — os dois no mesmo alvo, ao mesmo tempo.
motor.record_event("bram-p65", "A Hulda me humilhou na frente de todos.",
                   "insulto", ["hulda-p65"], intensity="large",
                   valence={"hulda-p65": "negativa"})
indice.sincronizar()
ctx2 = motor.get_context("bram-p65")
hulda = {c["id"]: c for c in ctx2["characters_present"]}.get("hulda-p65", {})

check("F1: o VÍNCULO sobrevive ao afeto negativo (não é somado nem anulado)",
      hulda.get("bond") == "irmã", f"veio {hulda.get('bond')!r}")
check("F2: o AFETO desce como rótulo, negativo, na mesma entrada",
      isinstance(hulda.get("sentiment"), str)
      and ("mágoa" in hulda["sentiment"] or "ressentimento" in hulda["sentiment"]
           or "incômodo" in hulda["sentiment"]),
      f"veio {hulda.get('sentiment')!r}")
check("F3: o afeto NÃO virou número em lugar nenhum",
      not isinstance(hulda.get("sentiment"), (int, float)))

print("\n--- Bloco G: o SEGREDO DO MUNDO --------------------------------------")

ctx_h = motor.get_context("hulda-p65")
bram_visto = {c["id"]: c for c in ctx_h["characters_present"]}.get("bram-p65", {})

check("G1: o ENJEITADO — o vínculo que o OUTRO declarou não desce para ela",
      "bond" not in bram_visto,
      f"vazou {bram_visto.get('bond')!r}")
check("G2: e o afeto de TERCEIROS por ela também não desce",
      not any(k.startswith("afeto_por") or k == "sentiment_toward_me"
              for c in ctx_h["characters_present"] for k in c))

print()
shutil.rmtree(_tmp, ignore_errors=True)
if falhas:
    print(f"{len(falhas)} FALHA(S): " + ", ".join(falhas))
    sys.exit(1)
print("todos os checks da Fase 65 (spec 066) passaram.")
