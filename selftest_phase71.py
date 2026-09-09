"""Fase 71 — JUÍZO AUSENTE É FALHA (spec 071, US1).

O defeito que este arquivo protege: uma resposta do Árbitro sem juízo legível —
recusa do modelo ou desistência — caía nos defaults da capacidade (tipicamente 5).
Como TODO gate do projeto é `nota == 0`, isso virava "prossiga com nota média": a
ação acontecia sem ninguém ter julgado, e o jogador lia um efeito que o mundo nunca
decidiu. Medido em campo: 8 em 108 chamadas (~7%).

O que cada check protege:

1. **Ausência levanta.** Os três caminhos de `julgamento()` (sem objeto, objeto
   ilegível, objeto que não é mapa) e o de `nota()` (sem número).
2. **PARCIAL não regride.** JSON legível com chave faltando continua caindo no
   default por campo. É a fronteira que impede a correção de virar outra feature —
   e o único check aqui que falha se alguém "melhorar" a regra depois.
3. **A recusa não vaza vocabulário de máquina.** Nem nome de ferramenta, nem
   "erro/modelo/sistema/juízo" na frase que o jogador lê (Princípio IX).
4. **A frase não cai no fallback com sujeito.** `juizo_ausente` tem de estar entre
   as regras SEM SUJEITO, senão vira "'<nome da tool>' não foi movido — ...".
5. **Nenhuma capacidade captura a exceção.** Capturar é reintroduzir o defeito: a
   exceção tem de subir até o despacho único.
6. **As 19 chamadas de juízo seguem sob o despacho único.** Se alguém acrescentar
   uma chamada de juízo FORA de `motor/*/declaracao.py`, ela escapa do tratamento —
   e este check é o que avisa.

Uso:  python3 selftest_phase71.py
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from motor import io, juizo  # noqa: E402

RAIZ = Path(os.path.dirname(os.path.abspath(__file__)))
falhas: list[str] = []


def check(nome: str, cond: bool, detalhe: str = "") -> None:
    if cond:
        print(f"[ok  ] {nome}")
    else:
        print(f"[FALHA] {nome}" + (f" — {detalhe}" if detalhe else ""))
        falhas.append(nome)


def _levanta(fn) -> bool:
    try:
        fn()
        return False
    except juizo.NaoJulgado:
        return True


# --------------------------------------------------------------------------- #
# 1. AUSÊNCIA levanta — nos quatro caminhos
# --------------------------------------------------------------------------- #
# As respostas são REAIS: capturadas do llama3.1:8b durante a medição da 071.
sys.path.insert(0, str(RAIZ / "tests" / "exploracao"))
from juizo_mudo import RECUSAS, SEM_JUIZO  # noqa: E402

for i, r in enumerate(RECUSAS):
    check(f"julgamento levanta na recusa real #{i + 1}",
          _levanta(lambda r=r: juizo.julgamento(r, campos={"nota": 5})))

check("julgamento levanta com resposta vazia",
      _levanta(lambda: juizo.julgamento("", campos={"nota": 5})))
check("julgamento levanta com JSON truncado",
      _levanta(lambda: juizo.julgamento('{"nota": 7', campos={"nota": 5})))
check("julgamento levanta com JSON ilegível",
      _levanta(lambda: juizo.julgamento('{"nota": }', campos={"nota": 5})))
check("julgamento levanta quando o juízo não é um mapa",
      _levanta(lambda: juizo.julgamento('[1, 2, 3]', campos={"nota": 5})))

for i, r in enumerate(RECUSAS):
    check(f"nota levanta na recusa real #{i + 1}", _levanta(lambda r=r: juizo.nota(r, 5)))
check("nota levanta com resposta vazia", _levanta(lambda: juizo.nota("", 5)))

# R9 medido: nenhuma das respostas sem juízo contém algarismo — é o que faz a regra
# simples de `nota()` cobrir as oito. Se uma futura passar a conter, este check cai
# e o endurecimento deixa de ser especulativo.
check("nenhuma resposta sem juízo contém algarismo (premissa de R9)",
      all(re.search(r"\d", r) is None for r in SEM_JUIZO))

# --------------------------------------------------------------------------- #
# 2. PARCIAL não regride — a fronteira (FR-006)
# --------------------------------------------------------------------------- #
parcial = juizo.julgamento('{"a": 7}', campos={"a": 5, "b": 3})
check("parcial: chave presente é lida", parcial["a"] == 7, str(parcial))
check("parcial: chave ausente cai no default da capacidade", parcial["b"] == 3, str(parcial))

texto = juizo.julgamento('{"a": 7}', campos={"a": 5}, texto_campos={"t": "padrao"})
check("parcial: texto ausente cai no default", texto["t"] == "padrao", str(texto))

check("parcial: tipo errado cai no default",
      juizo.julgamento('{"a": "muito"}', campos={"a": 4})["a"] == 4)
check("parcial: booleano NÃO é lido como nota",
      juizo.julgamento('{"a": true}', campos={"a": 4})["a"] == 4)
check("nota torta (inteiro absurdo) NÃO levanta — houve juízo",
      juizo.nota("9" * 400, 5) == 10)

# --------------------------------------------------------------------------- #
# 3 e 4. A recusa chega ao jogador sem vocabulário de máquina
# --------------------------------------------------------------------------- #
why = io._WHY_BY_REGRA.get("juizo_ausente", "")
check("existe prosa de recusa para juizo_ausente", bool(why))
check("a prosa não cita mecânica",
      not any(p in why.lower() for p in
              ("erro", "modelo", "sistema", "servidor", "juízo", "juizo", "json")),
      why)

app_src = (RAIZ / "app.py").read_text(encoding="utf-8")
sem_sujeito = re.search(r"_REGRAS_SEM_SUJEITO = \{([^}]*)\}", app_src)
check("juizo_ausente está entre as regras SEM SUJEITO",
      bool(sem_sujeito) and "juizo_ausente" in sem_sujeito.group(1),
      "senão a frase vira \"'<tool>' não foi movido\" e vaza o nome da capacidade")

arb_src = (RAIZ / "arbiter.py").read_text(encoding="utf-8")
check("a rejeição de juizo_ausente NÃO carrega o nome da capacidade",
      '_deny("", None, {"regra": "juizo_ausente"' in arb_src,
      "nome de ferramenta nunca desce ao client (Princípio IX)")

# --------------------------------------------------------------------------- #
# 5. Ninguém captura a exceção pelo caminho
# --------------------------------------------------------------------------- #
capturas = []
for p in sorted((RAIZ / "motor").rglob("*.py")):
    t = p.read_text(encoding="utf-8")
    if re.search(r"except\s+[\w.]*NaoJulgado", t):
        capturas.append(str(p.relative_to(RAIZ)))
check("nenhuma capacidade captura NaoJulgado", not capturas, ", ".join(capturas))

check("o despacho único captura NaoJulgado",
      re.search(r"except\s+motor\.juizo\.NaoJulgado", arb_src) is not None)

# --------------------------------------------------------------------------- #
# 6. Toda chamada de juízo segue sob o despacho único
# --------------------------------------------------------------------------- #
fora, dentro = [], 0
for p in sorted((RAIZ / "motor").rglob("*.py")):
    if p.name == "juizo.py":
        continue
    for n, linha in enumerate(p.read_text(encoding="utf-8").split("\n"), 1):
        if re.search(r"juizo\.(julgamento|nota)\(", linha):
            dentro += 1
            if p.name != "declaracao.py":
                fora.append(f"{p.relative_to(RAIZ)}:{n}")
check("toda chamada de juízo vive em declaracao.py (logo, sob _execute)",
      not fora, ", ".join(fora))
check("o inventário de chamadas de juízo bate com o baseline da spec (19)",
      dentro == 19, f"achei {dentro}")

print()
if falhas:
    print(f"{len(falhas)} FALHA(S): " + "; ".join(falhas))
    sys.exit(1)
print("fase 71: todos os checks passaram.")
