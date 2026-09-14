"""SONDAGEM da REGUA_COBRANCA (spec 073, US6) — contra o modelo real.

O que o dado forçado NÃO pega: que nota o Árbitro dá LENDO A PROSA. O
`selftest_phase73.py` prova a mecânica (os portões, as três faixas, a virada, o
segredo da nota) com `_roll_d20` fixo — mas a nota vem do modelo, e a régua é o único
lugar onde o desfecho pode sair torto sem nenhum teste reclamar.

SEM GABARITO MEU. Não há "a resposta certa" escrita aqui: o que se mede são
CONTRASTES que a própria cena decide, e que qualquer leitor humano concorda com a
direção. Escrever o gabarito de cabeça e pontuar o modelo contra ele já errou o sinal
duas vezes neste projeto (`[[medir-prompt-do-arbitro-antes-de-aplicar]]`).

Os contrastes:

  1. CUMPRIU > NÃO CUMPRIU — quem entregou tem de tirar mais que quem não entregou.
     Se este inverter, a régua está quebrada e nada mais importa.
  2. ELE VIU > ELE NÃO VIU — cumprir na frente dele vale mais que cumprir sozinho.
  3. AGORA > FAZ TEMPO — o mesmo cumprimento, recente, vale mais.
  4. COBRAR BEM > COBRAR CONSTRANGENDO — a mesma dívida, cobrada na frente de gente,
     tira nota (é o que a régua diz "puxa para baixo").

E a ANCORAGEM: a régua diz que o padrão é 4-5, não 7. Uma média muito acima disso
significa que o modelo paga quase sempre, e a tool vira enfeite — foi exatamente o
que a REGUA_NECESSIDADE precisou consertar ("O PADRÃO É 2-4, NÃO 5").

Uso:  python3 tests/exploracao/sondagem_cobranca.py [rodadas]
      LOREFORGE_MODELO=qwen3:8b python3 tests/exploracao/sondagem_cobranca.py 5
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import urllib.request
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SERVER_DIR))
os.environ.setdefault("LOREFORGE_LOG", "0")

from motor.comercio.declaracao import REGUA_COBRANCA  # noqa: E402

MODELO = os.environ.get("LOREFORGE_MODELO", "llama3.1:8b")
RODADAS = int(sys.argv[1]) if len(sys.argv) > 1 else 3

PEDIDO = ('Responda APENAS um objeto JSON, sem texto antes ou depois, com exatamente '
          'esta chave e nada mais:\n{"cumprimento": <inteiro 0-10>}')

SYSTEM = f"{REGUA_COBRANCA}\n\n{PEDIDO}"


def ask(user: str) -> str:
    # `think: False` viaja no CORPO — `/no_think` no prompt não funciona nesta versão
    # do Ollama, e pensando o `qwen3` devolve vazio (item 79). Para os modelos que
    # não pensam, o campo é ignorado.
    body = {"model": MODELO, "stream": False, "think": False,
            "options": {"temperature": 0.2},
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": user}]}
    req = urllib.request.Request("http://localhost:11434/api/chat",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        r = json.loads(urllib.request.urlopen(req, timeout=300).read())
        return (r.get("message") or {}).get("content") or ""
    except Exception as e:
        return f"__ERRO__ {e}"


def nota(texto: str):
    """A nota, ou None. Ausência é FALHA, nunca 'prossiga com 5'
    (`[[juizo-ausente-e-falha]]`)."""
    try:
        ini = texto.index("{")
        fim = texto.rindex("}") + 1
        v = json.loads(texto[ini:fim]).get("cumprimento")
        return int(v) if isinstance(v, (int, float)) else None
    except Exception:
        return None


def payload(de_quem: str, afeto: str, prosa: str,
            promessa: dict | None = None) -> str:
    """O MESMO payload que `_cobrar` monta — inclusive `o_que_ele_prometeu`, que é o
    FATO descendo como dado. A sondagem tem de medir o que o jogo manda, não uma
    versão simplificada: fixture à mão fica verde sobre a deriva de contrato
    (`[[fixture-de-teste-certifica-o-bug]]`)."""
    return json.dumps({"de_quem": de_quem,
                       "a_divida_dele_com_voce": promessa or {
                           "o_que": "tres moedas pelas barras de ferro",
                           "desde": "ontem"},
                       "afeto_por_voce": afeto, "prosa": prosa},
                      ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------- #
# Os casos, em PARES de contraste. A única diferença dentro de um par é a que
# está sendo medida — o resto do texto é idêntico de propósito.
# --------------------------------------------------------------------------- #
DEVEDOR = ("Torvin, o Ferreiro. Um homem grande, de mãos queimadas, que fala pouco "
           "e paga o que deve quando tem com quê.")

CASOS = [
    # (par, rótulo, payload)
    ("1. cumpriu x não cumpriu", "CUMPRIU",
     payload(DEVEDOR, "nutre estima",
             "Você trouxe as três barras de ferro que ele pediu, entregou na "
             "bancada dele ontem de manhã, e agora pede as moedas combinadas.")),
    ("1. cumpriu x não cumpriu", "NÃO CUMPRIU",
     payload(DEVEDOR, "nutre estima",
             "Você não chegou a trazer as barras de ferro que ele pediu — nem saiu "
             "atrás delas —, e agora pede as moedas combinadas.")),

    ("2. ele viu x não viu", "ELE VIU",
     payload(DEVEDOR, "indiferente",
             "Você deixou as três barras na bancada com ele olhando, os dois "
             "conferiram juntas, e agora pede as moedas combinadas.")),
    ("2. ele viu x não viu", "NÃO VIU",
     payload(DEVEDOR, "indiferente",
             "Você deixou as três barras na bancada enquanto ele estava fora, sem "
             "ninguém por perto, e agora pede as moedas combinadas.")),

    ("3. agora x faz tempo", "AGORA",
     payload(DEVEDOR, "indiferente",
             "Você entregou as três barras hoje de manhã, com ele presente, e "
             "agora pede as moedas combinadas.")),
    ("3. agora x faz tempo", "FAZ TEMPO",
     payload(DEVEDOR, "indiferente",
             "Você entregou as três barras há muitas semanas, com ele presente, e "
             "só agora pede as moedas combinadas.")),

    ("4. cobra bem x constrangendo", "COBRA BEM",
     payload(DEVEDOR, "indiferente",
             "Você entregou as três barras ontem, com ele presente. Agora o chama "
             "de lado, longe dos outros, e pede as moedas combinadas.")),
    ("4. cobra bem x constrangendo", "CONSTRANGENDO",
     payload(DEVEDOR, "indiferente",
             "Você entregou as três barras ontem, com ele presente. Agora, no meio "
             "do salão cheio, grita que ele é caloteiro e exige as moedas.")),
]

print("=" * 78)
print(f"SONDAGEM da REGUA_COBRANCA — modelo {MODELO}, {RODADAS} rodada(s) por caso")
print("=" * 78)

notas: dict[tuple, list] = {}
mudos = 0
for par, rotulo, corpo in CASOS:
    obtidas = []
    for _ in range(RODADAS):
        n = nota(ask(corpo))
        if n is None:
            mudos += 1
            continue
        obtidas.append(n)
    notas[(par, rotulo)] = obtidas
    media = f"{statistics.mean(obtidas):.2f}" if obtidas else "—"
    print(f"  {par:32} {rotulo:16} {media:>6}   {sorted(obtidas)}")

print("-" * 78)
print("CONTRASTES (o que a cena decide, não o que eu acho):")
invertidos = []
pares = []
for par, _rot, _c in CASOS:
    if par not in pares:
        pares.append(par)
for par in pares:
    lados = [(r, v) for (p, r), v in notas.items() if p == par]
    if len(lados) != 2 or not all(v for _r, v in lados):
        print(f"  {par:32} SEM DADO")
        continue
    (ra, va), (rb, vb) = lados
    ma, mb = statistics.mean(va), statistics.mean(vb)
    sinal = "OK " if ma > mb else "INVERTEU" if ma < mb else "EMPATOU"
    if ma <= mb:
        invertidos.append(par)
    print(f"  {par:32} {ra} {ma:.2f}  >  {rb} {mb:.2f}   [{sinal}]")

todas = [n for v in notas.values() for n in v]
print("-" * 78)
if todas:
    print(f"ANCORAGEM: média geral {statistics.mean(todas):.2f} "
          f"(a régua diz que o padrão é 4-5, não 7)")
    print(f"           distribuição {sorted(todas)}")
if mudos:
    print(f"JUÍZO AUSENTE em {mudos} chamada(s) — ausência é FALHA, nunca nota média")
if invertidos:
    print(f"CONTRASTE INVERTIDO em: {', '.join(invertidos)}")
    print("A régua precisa de outra redação ANTES de a tool ir a jogo.")
else:
    print("nenhum contraste invertido.")
