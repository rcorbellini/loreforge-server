"""SONDAGEM R4 (spec 070) — pedir DOIS CAMPOS A MAIS ao Árbitro degrada as notas antigas?

O PORTÃO. A spec 070 precisa que toda tool que cria coisa com prazo obtenha do Árbitro,
na MESMA chamada em que já pede as descrições do resultado, mais dois textos:

    "urgencia":          o que está em jogo enquanto o prazo corre
    "descricao_vencida": como a coisa fica depois que o prazo passa

É isso que torna a avaliação preguiçosa viável: com os dois carimbados na criação, vencer
é trocar uma string, e uma cena com N vencidos custa N trocas em vez de N chamadas de
Árbitro. Mas o custo se desloca para a criação, e o achado de 2026-09-05 diz que o risco
é concreto:

    numa MESMA resposta, o primeiro eixo é julgado bem e o SEGUNDO É ARRASTADO
    (medido em cinco variantes, `docs/backlog.md`)

O contrato da forja já pede CINCO notas e TRÊS textos. Passar a nove campos é exatamente
o caso que aquele achado descreve.

A PERGUNTA NÃO É se `urgencia` sai boa. É se `forjabilidade`, `qualidade_material`,
`fogo_de_forja`, `ferramental` e `duracao` PIORAM. Por isso a sondagem compara as notas
ANTIGAS entre as duas variantes, na mesma cena, com o mesmo modelo.

Uso:  python3 tests/exploracao/sondagem_contrato_com_prazo.py [N]
      OLLAMA=http://localhost:11434 MODELO=llama3.1:8b python3 ...
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from motor import juizo  # noqa: E402
from motor.forja.declaracao import REGUA_FORJAR_ARMA  # noqa: E402

OLLAMA = os.environ.get("OLLAMA", "http://localhost:11434")
MODELO = os.environ.get("MODELO", "llama3.1:8b")
N = int(sys.argv[1]) if len(sys.argv) > 1 else 8

# As notas que JÁ existem — é a degradação delas que se mede.
NOTAS = {"forjabilidade": 0, "qualidade_material": 0, "fogo_de_forja": 0,
         "ferramental": 0, "duracao": 5}
TEXTOS = {"nome": "", "descricao_alta": "", "descricao_baixa": ""}

# O acréscimo que a spec 070 propõe (FR-018), na redação de contracts/prazo.md.
_ACRESCIMO_PROMPT = """

Esta peça tem PRAZO: ela se degrada se o trabalho não for concluído a tempo. Escreva
mais dois textos, ambos sobre o OBJETO e nunca sobre quem trabalha nele:
- `urgencia`: o que está em jogo enquanto o prazo corre, numa frase curta e in-world.
- `descricao_vencida`: como a peça fica depois que o prazo passa — factual, e ela ainda
  É a peça, nunca sumida."""

_ACRESCIMO_CHAVES = ', "urgencia": "<uma frase>", "descricao_vencida": "<texto factual>"'

# Cenas reais o bastante para a régua ter o que julgar.
CENAS = [
    {"materiais": ["Lingote de Ferro", "Cabo de Carvalho"],
     "fonte_calor": "Forja de Ferro acesa", "tipo": "arma"},
    {"materiais": ["Sucata de Bronze", "Tira de Couro Velho"],
     "fonte_calor": "Lareira do Canto", "tipo": "arma"},
    {"materiais": ["Barra de Aço Temperado", "Rebites de Latão", "Cabo de Freixo"],
     "fonte_calor": "Forja de Ferro acesa", "tipo": "arma"},
]


def _chamar(system: str, user: str) -> str:
    corpo = json.dumps({
        "model": MODELO, "stream": False,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
    }).encode()
    req = urllib.request.Request(f"{OLLAMA}/api/chat", data=corpo,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read()).get("message", {}).get("content", "")


def _rodar(nome: str, regua: str, campos: dict, textos: dict) -> dict:
    linhas, parses = [], 0
    for cena in CENAS:
        for _ in range(N):
            bruto = _chamar(regua, json.dumps(cena, ensure_ascii=False))
            julgado = juizo.julgamento(bruto, campos, texto_campos=textos)
            # `julgamento` cai no default quando o parse falha; um JSON legível é
            # detectado pela presença literal das chaves no bruto.
            if all(f'"{k}"' in bruto for k in campos):
                parses += 1
            linhas.append(julgado)
    total = len(linhas)
    saida = {"parse_ok": parses, "total": total}
    for k in NOTAS:
        vals = [l.get(k, 0) for l in linhas]
        saida[k] = (statistics.mean(vals), statistics.pstdev(vals))
    for k in textos:
        saida[f"texto_{k}"] = sum(1 for l in linhas if (l.get(k) or "").strip())
    print(f"\n── {nome}")
    print(f"   parse do JSON: {parses}/{total}")
    for k in NOTAS:
        m, d = saida[k]
        print(f"   {k:22} média {m:5.2f}  desvio {d:4.2f}")
    for k in textos:
        print(f"   texto `{k}` preenchido: {saida[f'texto_{k}']}/{total}")
    return saida


def main() -> int:
    print(f"modelo: {MODELO} · {len(CENAS)} cenas × {N} repetições = "
          f"{len(CENAS) * N} chamadas por variante")

    a = _rodar("A — contrato de HOJE (5 notas + 3 textos)", REGUA_FORJAR_ARMA,
               dict(NOTAS), dict(TEXTOS))

    regua_b = REGUA_FORJAR_ARMA.replace(
        '"descricao_baixa": "<texto factual da MESMA peça, comprometida — ainda É a peça, nunca sumida>"}',
        '"descricao_baixa": "<texto factual da MESMA peça, comprometida — ainda É a peça, nunca sumida>"'
        + _ACRESCIMO_CHAVES + "}")
    if regua_b == REGUA_FORJAR_ARMA:
        print("\nAVISO: não consegui injetar as chaves novas — a régua mudou de forma.")
        return 2
    regua_b += _ACRESCIMO_PROMPT
    textos_b = dict(TEXTOS, urgencia="", descricao_vencida="")
    b = _rodar("B — com `urgencia` e `descricao_vencida` (5 notas + 5 textos)",
               regua_b, dict(NOTAS), textos_b)

    print("\n=== O QUE DECIDE: as notas ANTIGAS pioraram? ===")
    pior = []
    for k in NOTAS:
        ma, _ = a[k]
        mb, _ = b[k]
        delta = mb - ma
        marca = ""
        if abs(delta) >= 1.0:
            marca = "  <-- MUDANÇA GRANDE"
            pior.append(k)
        print(f"   {k:22} A {ma:5.2f}  ->  B {mb:5.2f}   ({delta:+.2f}){marca}")
    print(f"   parse do JSON        A {a['parse_ok']}/{a['total']}  ->  "
          f"B {b['parse_ok']}/{b['total']}")
    print(f"   `urgencia` preenchida em B: {b.get('texto_urgencia', 0)}/{b['total']}")
    print(f"   `descricao_vencida` em B:   {b.get('texto_descricao_vencida', 0)}/{b['total']}")

    print()
    if pior:
        print("VEREDITO: as notas antigas MUDARAM em " + ", ".join(pior) + ".")
        print("Aplicar a saída prevista no plano: pedir os dois textos SÓ quando a coisa")
        print("criada tem prazo, e remedir. Ver research.md R4.")
        return 1
    print("VEREDITO: nenhuma nota antiga mudou mais de 1 ponto de média. O acréscimo")
    print("cabe na mesma chamada — mas registre o número em research.md, não a conclusão.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
