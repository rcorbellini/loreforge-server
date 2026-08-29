"""LABORATÓRIO DE RÉGUA — `sing`, SEGUNDA LEVA (spec 058).

A primeira leva (`sondagem_sing_regua.py`) achou que as duas habilidades que a régua
precisa ter moram em variantes DIFERENTES:

  · a escada de 11 degraus NUNCA fecha o portão (episódio banal → 5,5,5) mas lê a
    cena (taverna em chamas → 3,3,3);
  · a de dois âncoras fecha o portão perfeito (banal → 0,0,0) mas IGNORA a cena
    (taverna em chamas → 10,10,5);
  · a de duas notas colapsou (8 em tudo) — mas a primeira leva só imprimiu a MÉDIA,
    então não se sabe se as duas notas colapsaram ou só a média escondeu.

Esta leva resolve os três pontos abertos:

  E4  JC com as DUAS notas impressas — colapso real ou artefato da média?
  E5  JF (híbrido: dois âncoras + ordem explícita de checar a cena ANTES) × JB
  E6  DUMP de letras — a heurística de "inventou nome próprio" é confiável?

Uso:  python3 tests/exploracao/sondagem_sing_regua2.py   (exige só o Ollama de pé)
"""
import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from motor import juizo  # noqa: E402

MODELO, TEMP, R = "llama3.1:8b", 0.2, 3

LEMB_GRANDE = ("Vi Torvin descer ao poço com uma marreta e voltar arrastando aquilo "
               "pelo pescoço. Ninguém falou nada por um minuto inteiro.")
LEMB_BANAL = "Comprei três pães na praça do mercado e voltei pela rua do cais."
LEMB_MEDIA = ("Elga me deixou dormir no salão na noite da tempestade, sem cobrar "
              "nada, e ainda esquentou um caldo.")
OCIOSA = {"nome": "Taverna do Gancho",
          "descricao": ("Salão baixo de vigas negras, cheiro de peixe e cerveja azeda. "
                        "A lareira range. As mesas estão cheias e ninguém tem pressa.")}
PANICO = {"nome": "Taverna do Gancho",
          "descricao": ("O telhado dos fundos pegou fogo e a fumaça já toma o salão. "
                        "Gente empurra gente na direção da porta, alguém grita por água.")}
P_CHEIA = [{"nome": "Elga, a Taverneira", "fazendo": "seca canecas atrás do balcão",
            "humor": "cansada"},
           {"nome": "Doncel", "fazendo": "cochila sentado sobre a mesa",
            "humor": "bêbado"},
           {"nome": "Ossian", "fazendo": "olha a porta a cada ruído", "humor": "arisco"},
           {"nome": "Bram", "fazendo": "conta moedas devagar", "humor": "tranquilo"}]
P_FUGINDO = [{"nome": "Elga, a Taverneira", "fazendo": "arrasta um barril para fora",
              "humor": "em pânico"},
             {"nome": "Ossian", "fazendo": "corre para a porta", "humor": "apavorado"}]
P_UM = [{"nome": "Bram", "fazendo": "discute uma dívida com o taverneiro, de costas",
         "humor": "irritado"}]

CENAS = [
    ("S1 feito grande + mesa ociosa   ", LEMB_GRANDE, "Torvin, o Ferreiro", OCIOSA,
     P_CHEIA, (7, 10)),
    ("S2 feito BANAL + mesa ociosa    ", LEMB_BANAL, "o mercado", OCIOSA,
     P_CHEIA, (0, 2)),
    ("S3 feito grande + taverna em fogo", LEMB_GRANDE, "Torvin, o Ferreiro", PANICO,
     P_FUGINDO, (0, 3)),
    ("S4 feito médio + mesa ociosa    ", LEMB_MEDIA, "Elga, a Taverneira", OCIOSA,
     P_CHEIA, (4, 7)),
    ("S5 feito grande + um só, ocupado", LEMB_GRANDE, "Torvin, o Ferreiro", OCIOSA,
     P_UM, (3, 6)),
]

ABERTURA = """\
Você vai julgar UMA tentativa de cantar uma lembrança para quem está presente.
Leia a lembrança e a cena REAIS fornecidas com cuidado — nunca invente detalhes
que não estejam nelas."""

LETRA = """\
A LETRA é o que a plateia ouve, na voz de quem canta para uma mesa. Duas a quatro
frases. Use o LUGAR e QUEM está ouvindo. NÃO invente pessoas, lugares ou feitos
que não estejam na lembrança."""

DUAS_NOTAS = """\
Régua do EPISÓDIO (o quanto o que ele lembra comporta virar canção, ignorando
quem está ouvindo):
  0  nada de memorável — uma compra, um caminho andado
  5  um feito de verdade, sem nada de extraordinário
  10 um feito que se canta sozinho

Régua da PLATEIA (o quanto ESTA cena e ESTA gente comportam ouvir uma canção
agora, ignorando o que vai ser cantado):
  0  ninguém pode ouvir — correria, briga, incêndio, todos dormindo
  5  uma mesa comum, meio atenta
  10 gente ociosa e disposta, uma sala feita para isso
As notas são segredo do mundo."""

SO_EXTREMOS = """\
Régua da CANÇÃO (o quanto ESTE episódio, NESTA cena, comporta virar canção — não
o quanto o cantor é bom, que não é assunto seu):
  0  não vira canção: nada de memorável aconteceu, OU a cena não comporta canção
     nenhuma (correria, briga, incêndio, todos dormindo)
  10 a canção se canta sozinha: feito extraordinário diante de quem quer ouvi-lo
Não hesite nos extremos quando a cena os merecer. A nota é segredo do mundo."""

HIBRIDO = """\
Régua da CANÇÃO (o quanto ESTE episódio, NESTA cena, comporta virar canção — não
o quanto o cantor é bom, que não é assunto seu).

Faça as DUAS perguntas nesta ordem, e a nota é a MENOR das duas respostas:
  1. A CENA permite que alguém pare e ouça agora? Se há correria, incêndio, briga,
     ou quem está ali não pode parar, a resposta é 0 ou 1 — por melhor que seja o
     feito. Uma sala ociosa e sem pressa é 8 a 10.
  2. O EPISÓDIO merece uma canção? Uma compra, um caminho andado, uma tarefa
     comum é 0 — não hesite no zero, a maior parte do que se lembra não vira
     canção. Um feito de verdade é 5. Um feito extraordinário é 10.
A nota é segredo do mundo."""

FECHO_1 = """\
Responda SOMENTE com um objeto JSON, nada antes nem depois, EXATAMENTE assim:

{"cancao": <inteiro 0-10>, "letra": "<a canção>"}"""

FECHO_2 = """\
Responda SOMENTE com um objeto JSON, nada antes nem depois, EXATAMENTE assim:

{"episodio": <inteiro 0-10>, "plateia": <inteiro 0-10>, "letra": "<a canção>"}"""


def payload(lemb, sobre, lugar, plat):
    return json.dumps({"lembranca": lemb, "sobre": sobre, "lugar": lugar,
                       "plateia": plat,
                       "prosa": "Renn puxa o banco para perto da lareira."},
                      ensure_ascii=False, indent=2)


def ask(system, user):
    body = {"model": MODELO, "stream": False, "think": False,
            "options": {"temperature": TEMP},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}]}
    req = urllib.request.Request("http://localhost:11434/api/chat",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return ((json.loads(urllib.request.urlopen(req, timeout=300).read())
             .get("message") or {}).get("content") or "")


print(f"modelo={MODELO} temp={TEMP} rodadas={R}\n")
print("=" * 78)
print("E4 — JC com as DUAS notas separadas (colapso real ou artefato da média?)")
print("=" * 78)
SYS_JC = ABERTURA + "\n\n" + DUAS_NOTAS + "\n\n" + LETRA + "\n\n" + FECHO_2
for rot, lemb, sobre, lugar, plat, _ in CENAS:
    pares = []
    for _ in range(R):
        j = juizo.julgamento(ask(SYS_JC, payload(lemb, sobre, lugar, plat)),
                             {"episodio": 5, "plateia": 5}, {"letra": ""})
        pares.append((j["episodio"], j["plateia"]))
    print(f"   {rot} → episodio/plateia {pares}")

print("\n" + "=" * 78)
print("E5 — JF híbrido (dois âncoras + ordem de checar a cena ANTES) × JB")
print("=" * 78)
for nome_v, regua in (("JB só extremos", SO_EXTREMOS), ("JF híbrido    ", HIBRIDO)):
    system = ABERTURA + "\n\n" + regua + "\n\n" + LETRA + "\n\n" + FECHO_1
    acertos = 0
    print(f"\n--- {nome_v} ---")
    for rot, lemb, sobre, lugar, plat, (lo, hi) in CENAS:
        vals = []
        for _ in range(R):
            j = juizo.julgamento(ask(system, payload(lemb, sobre, lugar, plat)),
                                 {"cancao": 5}, {"letra": ""})
            vals.append(j["cancao"])
            if lo <= j["cancao"] <= hi:
                acertos += 1
        print(f"   {rot} → {vals}  (esperado {lo}-{hi})")
    print(f"   ACERTOS na faixa: {acertos}/{len(CENAS)*R}")

print("\n" + "=" * 78)
print("E6 — DUMP DE LETRAS (a heurística de 'inventou nome' é confiável?)")
print("=" * 78)
SYS_L = ABERTURA + "\n\n" + SO_EXTREMOS + "\n\n" + LETRA + "\n\n" + FECHO_1
_N = re.compile(r"\b[A-ZÁÉÍÓÚÂÊÔÃÕ][a-záéíóúâêôãõç]{2,}\b")
for rot, lemb, sobre, lugar, plat, _ in CENAS[:2]:
    base = set()
    for t in (lemb, lugar["descricao"], lugar["nome"], sobre):
        base |= {n.lower() for n in _N.findall(t)}
    base |= {n.lower() for p in plat for n in _N.findall(p["nome"])}
    print(f"\n--- {rot} (fonte: {sorted(base)}) ---")
    for _ in range(R):
        j = juizo.julgamento(ask(SYS_L, payload(lemb, sobre, lugar, plat)),
                             {"cancao": 5}, {"letra": ""})
        novos = {n.lower() for n in _N.findall(j["letra"])} - base - {"renn"}
        print(f"   [{len(j['letra'].split()):>2}p] {j['letra'][:240]}")
        print(f"        novos={sorted(novos) if novos else '—'}")
print("\nFIM.")
