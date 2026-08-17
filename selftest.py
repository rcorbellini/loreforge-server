"""Auto-teste da Fase 0 — roda sem servidor, sem dependências.

Valida: frontmatter parse/dump (round-trip), World Validator (aceita válido,
rejeita inválido), e as leituras do Motor sobre o mundo-semente.

Uso:  python3 server/selftest.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
# Fixture de mundo próprio e imutável (server/tests/world), desacoplado do world/ jogável:
# jogar (mover personagens, criar memórias) não quebra mais os testes.
os.environ["LOREFORGE_WORLD"] = str(SERVER_DIR / "tests" / "world")
sys.path.insert(0, str(SERVER_DIR))

import frontmatter
import validator
import motor

FAILS = []


def check(name: str, cond: bool, detail: str = "") -> None:
    status = "ok  " if cond else "FALHA"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


# --- frontmatter: round-trip de um character completo ---------------------- #
CHAR = motor.WORLD_DIR / "taverna-do-gancho" / "torvin-ferreiro" / "character.md"
fm, body = frontmatter.split(CHAR.read_text(encoding="utf-8"))

check("parse: type=character", fm.get("type") == "character")
check("parse: id", fm.get("id") == "torvin-ferreiro")
check("parse: attributes.STR=16 (int)", fm.get("attributes", {}).get("STR") == 16)
check("parse: skills.ferraria=5", fm.get("skills", {}).get("ferraria") == 5)
check("parse: status.conditions == []", fm.get("status", {}).get("conditions") == [])
check("parse: status.action string", isinstance(fm.get("status", {}).get("action"), str))
check("parse: body não vazio", len(body.strip()) > 0)

# round-trip: dump -> split de volta preserva os valores estruturais
roundtrip_text = frontmatter.join(fm, body)
fm2, body2 = frontmatter.split(roundtrip_text)
check("round-trip: attributes iguais", fm2.get("attributes") == fm.get("attributes"))
check("round-trip: skills iguais", fm2.get("skills") == fm.get("skills"))
check("round-trip: status iguais", fm2.get("status") == fm.get("status"))
check("round-trip: body preservado", body2.strip() == body.strip())

# --- inline list e flow map ------------------------------------------------ #
sample = "a:\n  b: [1, 2, 3]\n  c: {x: 1, y: dois}\n  d: null\n  e: true\n"
parsed = frontmatter.parse(sample)
check("flow: lista inline", parsed["a"]["b"] == [1, 2, 3])
check("flow: mapa inline", parsed["a"]["c"] == {"x": 1, "y": "dois"})
check("flow: null", parsed["a"]["d"] is None)
check("flow: bool", parsed["a"]["e"] is True)

# --- sequência em bloco de mapas (route prerequisites) --------------------- #
seq = (
    "prerequisites:\n"
    "  - id: p1\n"
    "    type: none\n"
    "    active: true\n"
    "  - id: p2\n"
    "    type: item\n"
    "    required: chave\n"
    "    active: false\n"
)
pseq = frontmatter.parse(seq)["prerequisites"]
check("seq: 2 prerequisites", isinstance(pseq, list) and len(pseq) == 2)
check("seq: p1.type=none", pseq[0].get("type") == "none")
check("seq: p2.required=chave", pseq[1].get("required") == "chave")
check("seq: p2.active=false", pseq[1].get("active") is False)

# --- validator ------------------------------------------------------------- #
check("validator: character válido", validator.validate(fm) == [])

bad_char = {"type": "character", "id": "x", "name": "X",
            "controlled_by": "p", "skills": {}, "status": {}}  # sem attributes
check("validator: rejeita sem attributes", len(validator.validate(bad_char)) > 0)

bad_mem = {"type": "memory", "id": "m", "timestamp_start": "t",
           "timestamp_end": "t", "intensity": "enorme", "state": "active"}
check("validator: rejeita intensity inválida", len(validator.validate(bad_mem)) > 0)

check("validator: rejeita tipo fora do MVP",
      len(validator.validate({"type": "island", "id": "i", "name": "I"})) > 0)

# --- motor: leituras ------------------------------------------------------- #
ctx = motor.get_context("torvin-ferreiro")
# checa pelo id (estável), não pelo name (conteúdo editável do mundo)
check("motor: location = taverna-do-gancho",
      ctx["location"]["id"] == "taverna-do-gancho")
present_ids = {c["id"] for c in ctx["characters_present"]}
check("motor: torvin e elga presentes",
      {"torvin-ferreiro", "elga-taverneira"} <= present_ids)
self_state = next(c for c in ctx["characters_present"] if c["id"] == "torvin-ferreiro")
check("motor: self marcado", self_state["state"] == "self")

inv = motor.get_inventory("torvin-ferreiro")
check("motor: inventário raiz = personagem", inv["kind"] == "character")
bag = inv["children"][0] if inv["children"] else {}
check("motor: bolsa no inventário", bag.get("id") == "bolsa-de-couro")
check("motor: frasco dentro da bolsa",
      bool(bag.get("children")) and bag["children"][0]["id"] == "frasco-de-oleo")

detail = motor.get_entity_detail("frasco-de-oleo")
check("motor: detalhe do frasco", detail["name"] == "Frasco de Óleo")
check("motor: detalhe sem campos de sistema",
      "id" not in detail and "type" not in detail.get("description", ""))

chars = motor.list_characters()
check("motor: list_characters retorna 2", len(chars) == 2)

# --- docs/tools.md acompanha o código (skill loreforge-tools) ---------------- #
# A referência de tools é escrita à mão (o que uma tool VALIDA não se extrai do
# manifest), mas a lista não pode divergir. Isto pega o esquecimento comum: tool
# nova ou regra de recusa nova sem entrada no documento.
# Frontmatter não pode perder dado por causa de uma quebra de linha (bug real: um
# narrative_hint multi-linha foi parar em status.action, cortou a ficha ao meio e
# levou junto `mood` e `conditions` — sem o validador acusar nada).
_fm_teste = {"type": "character", "id": "x", "name": "X", "controlled_by": "a",
             "attributes": {}, "skills": {},
             "status": {"action": "linha um\nlinha dois: com dois pontos",
                        "mood": "fechado", "conditions": []}}
_txt_fm = frontmatter.join(_fm_teste, "corpo")
_volta = frontmatter.parse(_txt_fm)
check("frontmatter: valor multi-linha não corrompe o documento",
      _volta["status"].get("mood") == "fechado"
      and _volta["status"].get("conditions") == []
      and "\n" in _volta["status"]["action"],
      str(_volta.get("status")))
check("frontmatter: nenhuma linha do bloco vira chave solta",
      all(not (l.endswith(":") and len(l) > 60)
          for l in _txt_fm.split("---")[1].splitlines()))

import arbiter  # noqa: E402
import tools_doc  # noqa: E402
_doc = (Path(__file__).resolve().parent.parent / "docs" / "tools.md")
_gen = (Path(__file__).resolve().parent.parent / "docs" / "tools.generated.md")
_specs = sorted(motor.registro.specs())
_regras = sorted(motor._WHY_BY_REGRA)
_reguas = sorted(n for n in dir(arbiter) if n.startswith("REGUA_"))
if not _doc.exists():
    check("docs/tools.md existe", False, "arquivo ausente")
else:
    _texto = _doc.read_text(encoding="utf-8")
    # A fonte da verdade das tools/recusas agora é o REGISTRO de declarações
    # (spec 038: os nomes saíram do arbiter.py para os `@tool_spec`). A doc
    # HAND-WRITTEN (rationale) não pode divergir dessa lista.
    _faltando = [t for t in _specs if f"`{t}`" not in _texto]
    check("docs/tools.md cobre todas as tools declaradas",
          not _faltando, f"sem entrada: {', '.join(_faltando)}")
    _sem_doc = [r for r in _regras if f"`{r}`" not in _texto]
    check("docs/tools.md cobre todas as regras de recusa",
          not _sem_doc, f"sem entrada: {', '.join(_sem_doc)}")
# spec 038 (US3): a versão GERADA (companion) está EM SYNC com o código?
check("docs/tools.generated.md em sync com as declarações (rode server/tools_doc.py)",
      _gen.exists() and _gen.read_text(encoding="utf-8") == tools_doc.gerar())
# SC-006: a doc gerada COBRE a mesma superfície — tools + recusas + réguas
_g = tools_doc.gerar()
check("SC-006: doc gerada cobre todas as tools/recusas/réguas",
      all(f"`{t}`" in _g for t in _specs)
      and all(f"`{r}`" in _g for r in _regras)
      and all(f"`{rn}`" in _g for rn in _reguas),
      "cobertura incompleta na doc gerada")

# spec 043: o PORTAL foi aposentado. Ele hospedava uma segunda cópia do texto das
# capacidades (`portal/rules/rules.json`) e um `sync.py` inteiro só para detectar
# quando ela divergia da `@tool_spec` — duas fontes para o mesmo fato. Com a
# `description` da declaração virando o texto player-facing (a que de fato desce à
# Mente), a cópia perdeu razão de existir e o drift virou impossível por construção.
#
# A garantia que o portal dava NÃO se perdeu: a checagem anti-vazamento migrou para
# `selftest_phase44.py`, e agora incide sobre a FONTE, não sobre a cópia.

# --- resultado ------------------------------------------------------------- #
print()
if FAILS:
    print(f"{len(FAILS)} FALHA(S): {', '.join(FAILS)}")
    sys.exit(1)
print("todos os checks passaram.")
