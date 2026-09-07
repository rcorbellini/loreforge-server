"""Sondagem da RÉGUA DO REVIDE (spec 069) contra o modelo REAL.

Três medições que nenhuma fase verde prova (quickstart, passo 5):

  5a — a régua acerta? O caso decisivo é o CURANDEIRO ALERTA E PACÍFICO: se ele
       revidar, a régua está lendo só a cena e ignorando a prosa, e o corte entre
       PRONTIDÃO e DISPOSIÇÃO não funcionou.
  5b — a VANTAGEM regrediu? Ela passou a dividir prompt e resposta com outra régua.
       Compara a distribuição das notas de vantagem entre a régua-mãe (duas notas) e
       a régua isolada de antes (uma nota).
  5c — o parse aguenta? Quantas respostas saem no formato pedido.

Uso:  python3 tests/exploracao/sondagem_revide.py [rodadas]
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import urllib.request
from collections import Counter
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SERVER_DIR))
os.environ.setdefault("LOREFORGE_LOG", "0")

import motor  # noqa: E402
from motor.combate import declaracao as D  # noqa: E402

MODELO = os.environ.get("LOREFORGE_MODELO", "llama3.1:8b")
RODADAS = int(sys.argv[1]) if len(sys.argv) > 1 else 5


def ask(system: str, user: str) -> str:
    body = {"model": MODELO, "stream": False, "options": {"temperature": 0.2},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}]}
    req = urllib.request.Request("http://localhost:11434/api/chat",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        r = json.loads(urllib.request.urlopen(req, timeout=300).read())
        return (r.get("message") or {}).get("content") or ""
    except Exception as exc:                       # rede/modelo fora: some do placar
        return f"__ERRO__ {exc}"


# Os CASOS. Cada um é (rótulo, prosa do alvo, cena, prosa da ação, revide esperado).
# "alto" = deve revidar; "baixo" = não deve.
CASOS = [
    ("bêbado cambaleante",
     "Doncel passa os dias na taverna e as noites debaixo da mesa. Hoje não ficou de "
     "pé sozinho uma vez.",
     "O salão da taverna, quente e cheio. Doncel está caído sobre a mesa, murmurando.",
     "avanço e desço o punho nele", "baixo"),
    ("pego de costas, sem perceber",
     "Sorin leva cartas de um porto a outro. Cauteloso, mas hoje conta moedas.",
     "O cais vazio ao anoitecer. Sorin está agachado de costas para a rua, contando "
     "moedas à luz de uma lamparina.",
     "chego por trás, sem fazer ruído, e golpeio", "baixo"),
    ("guarda de ronda, alerta",
     "Draven vigia a porta há doze anos. Não deixa passar quem não conhece, e a mão "
     "não sai do cabo.",
     "A porta da torre, ao meio-dia. Draven está de pé, de frente para quem chega, a "
     "mão no cabo da espada.",
     "avanço para cima dele de frente", "alto"),
    ("fera em sua toca",
     "O Rastejante não é bicho de superfície. Não caça por fome: caça porque o que se "
     "move na galeria dele não devia estar ali. Nada nele negocia, e nada nele "
     "entende recuo — quem entra já entrou. As patas dianteiras terminam em garras de "
     "osso escuro.",
     "A galeria funda da mina, escura. O Rastejante está imóvel contra a parede fria.",
     "ergo a picareta e desço nele", "alto"),
    # O CASO DECISIVO: alerta (prontidão alta) e pacífica (disposição zero).
    ("curandeira ALERTA e pacífica",
     "Moura remenda quem chega ferido. Já viu homem morrer segurando a mão dela, e "
     "desde então decidiu uma coisa e não voltou atrás — não devolve. Nem golpe, nem "
     "palavra. Diz que quem revida vira o que bateu nele. Ela vê tudo o que acontece "
     "na boca da mina, e não reage a nada.",
     "A boca da mina, de dia. Moura está de joelhos sobre um pano, de frente para a "
     "entrada, e olhou para mim assim que cheguei.",
     "avanço e a golpeio de frente", "baixo"),
]


def payload(prosa_alvo, cena, prosa_acao):
    return json.dumps({"alvo": prosa_alvo, "arma": "desarmado",
                       "cena": cena, "prosa": prosa_acao},
                      ensure_ascii=False, indent=2)


print("=" * 78)
print(f"SONDAGEM DO REVIDE — modelo {MODELO}, {RODADAS} rodada(s) por caso")
print("=" * 78)

acertos = falhas_parse = 0
vant_mae, vant_isolada = [], []

print("\n--- 5a: a régua separa PRONTIDÃO de DISPOSIÇÃO? -------------------------")
for rotulo, prosa, cena, acao, esperado in CASOS:
    notas, brutos = [], []
    for _ in range(RODADAS):
        bruto = ask(D.REGUA_GOLPE, payload(prosa, cena, acao))
        brutos.append(bruto)
        j = motor.juizo.julgamento(bruto, {"vantagem": -1, "revide": -1})
        if j["revide"] < 0:
            falhas_parse += 1
            continue
        notas.append(j["revide"])
        if j["vantagem"] >= 0:
            vant_mae.append(j["vantagem"])
    if not notas:
        print(f"  {rotulo:32} SEM LEITURA (parse falhou em todas)")
        continue
    mediana = statistics.median(notas)
    veredito = "alto" if mediana >= 4 else "baixo"
    ok = veredito == esperado
    acertos += ok
    marca = "ok  " if ok else "FALHA"
    print(f"  [{marca}] {rotulo:32} notas={notas} mediana={mediana} "
          f"⇒ {veredito} (esperado {esperado})")

print(f"\n  {acertos}/{len(CASOS)} casos leram como esperado")
print(f"  falhas de parse: {falhas_parse} de {len(CASOS) * RODADAS}")

print("\n--- 5b: a VANTAGEM regrediu ao dividir a chamada? ----------------------")
for rotulo, prosa, cena, acao, _e in CASOS:
    for _ in range(RODADAS):
        bruto = ask(D.REGUA_VANTAGEM + motor.juizo.NOTA_0_10,
                    payload(prosa, cena, acao))
        n = motor.juizo.nota(bruto, default=-1)
        if n >= 0:
            vant_isolada.append(n)

if vant_mae and vant_isolada:
    print(f"  régua ISOLADA (como era):  n={len(vant_isolada):3} "
          f"média={statistics.mean(vant_isolada):.2f} "
          f"mediana={statistics.median(vant_isolada)} "
          f"dist={dict(sorted(Counter(vant_isolada).items()))}")
    print(f"  régua-MÃE  (duas notas):   n={len(vant_mae):3} "
          f"média={statistics.mean(vant_mae):.2f} "
          f"mediana={statistics.median(vant_mae)} "
          f"dist={dict(sorted(Counter(vant_mae).items()))}")
    delta = statistics.mean(vant_mae) - statistics.mean(vant_isolada)
    print(f"\n  DELTA da média: {delta:+.2f} — "
          + ("dentro do ruído (< 1.0), sem regressão aparente" if abs(delta) < 1.0
             else "ATENÇÃO: a régua nova pode estar ancorando a antiga"))
else:
    print("  sem leituras suficientes para comparar")
print("=" * 78)
