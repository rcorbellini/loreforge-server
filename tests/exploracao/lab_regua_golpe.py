"""LAB da régua-mãe do golpe (spec 069) — variantes medidas contra o modelo real.

Por que existe: a primeira composição (vantagem + revide, nessa ordem, coladas)
falhou nas DUAS pontas, medido com llama3.1:8b:
  - revide SEMPRE 0, inclusive para guarda alerta e fera em sua toca;
  - vantagem INFLADA: média 5.20 (régua isolada) -> 7.67 (régua-mãe), dist. {3..8}
    virando {7,8}.

Hipótese: a régua da vantagem é escrita da ótica de QUEM ATACA ("o que a cena dá ou
tira do golpe"). Colada a ela, a régua do revide é lida na mesma moldura, e o modelo
julga os dois eixos a favor do agressor — o que explica a inflação E o zero.

`[[medir-prompt-do-arbitro-antes-de-aplicar]]`: duas ou mais propostas, medidas.

Uso:  python3 tests/exploracao/lab_regua_golpe.py [rodadas]
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
from motor.combate.declaracao import REGUA_VANTAGEM, REGUA_REVIDE  # noqa: E402

MODELO = os.environ.get("LOREFORGE_MODELO", "llama3.1:8b")
RODADAS = int(sys.argv[1]) if len(sys.argv) > 1 else 3

PEDIDO = ('Responda APENAS um objeto JSON, sem texto antes ou depois, com exatamente '
          'estas duas chaves e nada mais:\n'
          '{"vantagem": <inteiro 0-10>, "revide": <inteiro 0-10>}')

# --- V0: a composição atual (vantagem, depois revide) ----------------------- #
V0 = f"""\
Você vai julgar UM golpe, em DOIS eixos independentes. Leia a cena uma vez e responda
os dois.

{REGUA_VANTAGEM}

{REGUA_REVIDE}

{PEDIDO}"""

# --- V1: inverte a ordem e MARCA de quem é cada eixo ------------------------ #
V1 = f"""\
Você vai julgar UMA cena de golpe em DOIS eixos SEPARADOS. Eles olham para lados
OPOSTOS: um é do corpo de quem APANHA, o outro é da mão de quem GOLPEIA. Julgue cada
um por si, e NÃO deixe a nota de um puxar a do outro.

########  EIXO 1 — DE QUEM APANHA (olhe para o ALVO, não para quem ataca)  ########

{REGUA_REVIDE}

########  EIXO 2 — DE QUEM GOLPEIA (olhe para a mão e a cena)  ########

{REGUA_VANTAGEM}

{PEDIDO}"""

# --- V2: como a V1, mais uma PERGUNTA explícita por eixo -------------------- #
V2 = f"""\
Você vai julgar UMA cena de golpe em DOIS eixos SEPARADOS. Eles olham para lados
OPOSTOS: um é do corpo de quem APANHA, o outro é da mão de quem GOLPEIA. Julgue cada
um por si, e NÃO deixe a nota de um puxar a do outro.

########  EIXO 1 — "revide": O ALVO DEVOLVE O GOLPE?  ########
A pergunta é sobre O ALVO, e só sobre ele: o corpo dele está desperto, livre e
disposto a responder AGORA? Um alvo alerta, em guarda, ou cuja natureza é devolver,
tem nota ALTA aqui — mesmo que o golpe contra ele seja fácil.

{REGUA_REVIDE}

########  EIXO 2 — "vantagem": O GOLPE ESTÁ FÁCIL OU DIFÍCIL?  ########
A pergunta é sobre O GOLPE. Alvo alerta e de frente TIRA vantagem (nota baixa); alvo
desprevenido ou de costas DÁ vantagem (nota alta). Um alvo perigoso não torna o golpe
mais fácil.

{REGUA_VANTAGEM}

{PEDIDO}"""

# --- V3: o revide da V2 (5/5) com a vantagem CRUA da V1 (menor deriva) ------ #
# A V2 acertou o revide em 5/5 mas inflou a vantagem (+1.27); a V1 preservou a
# vantagem (+0.33) e errou o revide. A diferença entre elas é o texto extra POR EIXO.
# Hipótese: a pergunta acrescentada ao eixo da VANTAGEM é que empurra aos extremos —
# então mantém-se só a do REVIDE, que é a que faltava.
V3 = f"""\
Você vai julgar UMA cena de golpe em DOIS eixos SEPARADOS. Eles olham para lados
OPOSTOS: um é do corpo de quem APANHA, o outro é da mão de quem GOLPEIA. Julgue cada
um por si, e NÃO deixe a nota de um puxar a do outro.

########  EIXO 1 — "revide": O ALVO DEVOLVE O GOLPE?  ########
A pergunta é sobre O ALVO, e só sobre ele: o corpo dele está desperto, livre e
disposto a responder AGORA? Um alvo alerta, em guarda, ou cuja natureza é devolver,
tem nota ALTA aqui — mesmo que o golpe contra ele seja fácil.

{REGUA_REVIDE}

########  EIXO 2 — "vantagem": O QUE A CENA DÁ OU TIRA DO GOLPE  ########

{REGUA_VANTAGEM}

{PEDIDO}"""

VARIANTES = [("V1 invertida + marcada ", V1),
             ("V2 V1 + pergunta/eixo  ", V2),
             ("V3 revide-V2 + vant-V1 ", V3)]

# (rótulo, prosa do alvo, cena, ação, revide esperado, vantagem esperada)
CASOS = [
    ("bêbado caído", "Doncel passa os dias na taverna e as noites debaixo da mesa.",
     "O salão quente e cheio. Doncel está caído sobre a mesa, murmurando.",
     "avanço e desço o punho nele", "baixo", "alta"),
    ("de costas, contando moedas",
     "Sorin leva cartas de um porto a outro. Cauteloso, mas hoje conta moedas.",
     "O cais vazio ao anoitecer. Sorin está agachado de costas para a rua.",
     "chego por trás, sem ruído, e golpeio", "baixo", "alta"),
    ("guarda alerta de frente",
     "Draven vigia a porta há doze anos. A mão não sai do cabo.",
     "A porta da torre, ao meio-dia. Draven está de pé, de frente para quem chega, "
     "a mão no cabo da espada.",
     "avanço para cima dele de frente", "alto", "baixa"),
    ("fera em sua toca",
     "O Rastejante não caça por fome: caça porque o que se move na galeria dele não "
     "devia estar ali. Nada nele entende recuo — quem entra já entrou. As patas "
     "dianteiras terminam em garras de osso escuro.",
     "A galeria funda da mina. O Rastejante está imóvel contra a parede, e virou a "
     "cabeça quando entrei.",
     "ergo a picareta e desço nele", "alto", "baixa"),
    ("curandeira ALERTA e pacífica",     # O CASO DECISIVO
     "Moura remenda quem chega ferido. Decidiu uma coisa e não voltou atrás — não "
     "devolve, nem golpe nem palavra. Diz que quem revida vira o que bateu nele. Ela "
     "vê tudo o que acontece na boca da mina, e não reage a nada.",
     "A boca da mina, de dia. Moura está de joelhos sobre um pano, de frente para a "
     "entrada, e olhou para mim assim que cheguei.",
     "avanço e a golpeio de frente", "baixo", "baixa"),
]


def ask(system, user):
    body = {"model": MODELO, "stream": False, "options": {"temperature": 0.2},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}]}
    req = urllib.request.Request("http://localhost:11434/api/chat",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        r = json.loads(urllib.request.urlopen(req, timeout=300).read())
        return (r.get("message") or {}).get("content") or ""
    except Exception:
        return ""


def payload(prosa, cena, acao):
    return json.dumps({"alvo": prosa, "arma": "desarmado", "cena": cena,
                       "prosa": acao}, ensure_ascii=False, indent=2)


def faixa(n, eixo):
    if eixo == "revide":
        return "alto" if n >= 4 else "baixo"
    return "alta" if n >= 6 else "baixa" if n <= 4 else "meio"


print("=" * 80)
print(f"LAB da régua-mãe — modelo {MODELO}, {RODADAS} rodada(s) por caso")
print("=" * 80)

# baseline: a régua da vantagem SOZINHA, como era antes da spec 069
base = []
for _r, prosa, cena, acao, _e, _v in CASOS:
    for _ in range(RODADAS):
        n = motor.juizo.nota(ask(REGUA_VANTAGEM + motor.juizo.NOTA_0_10,
                                 payload(prosa, cena, acao)), default=-1)
        if n >= 0:
            base.append(n)
print(f"\nBASELINE vantagem isolada: n={len(base)} média={statistics.mean(base):.2f} "
      f"dist={dict(sorted(Counter(base).items()))}")

placar = []
for nome, regua in VARIANTES:
    print(f"\n{'─' * 80}\n{nome}\n{'─' * 80}")
    ok_rev = ok_van = mudo = 0
    vants = []
    for rotulo, prosa, cena, acao, esp_rev, esp_van in CASOS:
        revs, vs = [], []
        for _ in range(RODADAS):
            j = motor.juizo.julgamento(ask(regua, payload(prosa, cena, acao)),
                                       {"vantagem": -1, "revide": -1})
            if j["revide"] < 0 or j["vantagem"] < 0:
                mudo += 1
                continue
            revs.append(j["revide"])
            vs.append(j["vantagem"])
        if not revs:
            print(f"  {rotulo:30} SEM LEITURA")
            continue
        mr, mv = statistics.median(revs), statistics.median(vs)
        vants += vs
        r_ok = faixa(mr, "revide") == esp_rev
        v_ok = faixa(mv, "vantagem") in (esp_van, "meio")
        ok_rev += r_ok
        ok_van += v_ok
        print(f"  [{'ok ' if r_ok else 'ERR'}|{'ok ' if v_ok else 'ERR'}] "
              f"{rotulo:30} revide={revs} (esp {esp_rev:5}) "
              f"vant={vs} (esp {esp_van})")
    delta = (statistics.mean(vants) - statistics.mean(base)) if vants and base else 0
    print(f"\n  revide certo: {ok_rev}/{len(CASOS)} | vantagem certa: "
          f"{ok_van}/{len(CASOS)} | mudo: {mudo} | Δ média vantagem: {delta:+.2f}")
    placar.append((nome, ok_rev, ok_van, abs(delta), mudo))

print("\n" + "=" * 80)
print("PLACAR (revide certo, vantagem certa, |Δ| da vantagem, mudo)")
for nome, r, v, d, m in sorted(placar, key=lambda x: (-x[1] - x[2], x[3])):
    print(f"  {nome}  revide {r}/{len(CASOS)}  vant {v}/{len(CASOS)}  "
          f"Δ={d:.2f}  mudo={m}")
print("=" * 80)
