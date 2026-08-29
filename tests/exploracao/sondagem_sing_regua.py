"""LABORATÓRIO DE RÉGUA — `sing` (spec 058).

Diferente de `sondagem_brew.py`/`lab_descriptions.py`, que medem a DESCRIPTION (a
escolha da Mente, FN/FP), este arnês mede o JUÍZO: o prompt que o corpo da tool manda
ao modelo do ÁRBITRO para ler a cena e devolver nota(s) + a letra da canção.

Não precisa de server nem de mundo de laboratório — o juízo é função pura de
prompt→JSON, e o parse medido é o REAL (`motor.juizo.julgamento`, importado).

Três experimentos:
  E1  ESTRUTURA DA NOTA — JA (escada de 11 degraus) × JB (só extremos) ×
      JC (duas notas: episodio+plateia) × JD (sem nota nenhuma).
      Mede: as notas DISCRIMINAM as cenas? qual estrutura separa melhor o que
      deve render do que não deve?
  E2  CONTRATO DA LETRA — L1 (sem contrato) × L2 (tamanho + usar a cena + não
      inventar). Mede: tamanho, uso da cena, invenção de nome próprio.
  E3  RÉGUA DE INSTRUMENTO — alaúde remendado × caneca × instrumento fino.
      Mede: o modelo diferencia? se der sempre a mesma nota, a régua é peso morto.

Uso:  python3 tests/exploracao/sondagem_sing_regua.py
      (exige só o Ollama de pé — ver docs/validacao-de-descriptions.md)
"""
import json
import os
import re
import statistics
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from motor import juizo  # noqa: E402  — o parse REAL, não uma cópia

# o modelo do ÁRBITRO real (config.server.json), não o da Mente. A doc de validação
# é explícita: "rode com o modelo que o jogo de fato usa".
MODELO, TEMP, R = "llama3.1:8b", 0.2, 3

# --------------------------------------------------------------------------- #
# As cenas. `esperado` é a FAIXA que um humano diria — o que se mede é se o
# modelo separa as cenas, não se acerta um número exato.
# --------------------------------------------------------------------------- #
LEMBRANCA_GRANDE = ("Vi Torvin descer ao poço com uma marreta e voltar arrastando "
                    "aquilo pelo pescoço. Ninguém falou nada por um minuto inteiro.")
LEMBRANCA_BANAL = "Comprei três pães na praça do mercado e voltei pela rua do cais."
LEMBRANCA_MEDIA = ("Elga me deixou dormir no salão na noite da tempestade, sem "
                   "cobrar nada, e ainda esquentou um caldo.")

TAVERNA_OCIOSA = {
    "nome": "Taverna do Gancho",
    "descricao": ("Salão baixo de vigas negras, cheiro de peixe e cerveja azeda. A "
                  "lareira range. As mesas estão cheias e ninguém tem pressa.")}
TAVERNA_EM_PANICO = {
    "nome": "Taverna do Gancho",
    "descricao": ("O telhado dos fundos pegou fogo e a fumaça já toma o salão. Gente "
                  "empurra gente na direção da porta, alguém grita por água.")}

PLATEIA_CHEIA = [
    {"nome": "Elga, a Taverneira", "fazendo": "seca canecas atrás do balcão",
     "humor": "cansada"},
    {"nome": "Doncel", "fazendo": "cochila sentado sobre a mesa", "humor": "bêbado"},
    {"nome": "Ossian", "fazendo": "olha a porta a cada ruído", "humor": "arisco"},
    {"nome": "Bram", "fazendo": "conta moedas devagar", "humor": "tranquilo"}]
PLATEIA_FUGINDO = [
    {"nome": "Elga, a Taverneira", "fazendo": "arrasta um barril para fora",
     "humor": "em pânico"},
    {"nome": "Ossian", "fazendo": "corre para a porta", "humor": "apavorado"}]
PLATEIA_UM_OCUPADO = [
    {"nome": "Bram", "fazendo": "discute uma dívida com o taverneiro, de costas",
     "humor": "irritado"}]

CENAS = [
    ("S1 feito grande + mesa ociosa   ", LEMBRANCA_GRANDE, "Torvin, o Ferreiro",
     TAVERNA_OCIOSA, PLATEIA_CHEIA, (7, 10)),
    ("S2 feito BANAL + mesa ociosa    ", LEMBRANCA_BANAL, "o mercado",
     TAVERNA_OCIOSA, PLATEIA_CHEIA, (0, 2)),
    ("S3 feito grande + taverna em fogo", LEMBRANCA_GRANDE, "Torvin, o Ferreiro",
     TAVERNA_EM_PANICO, PLATEIA_FUGINDO, (0, 3)),
    ("S4 feito médio + mesa ociosa    ", LEMBRANCA_MEDIA, "Elga, a Taverneira",
     TAVERNA_OCIOSA, PLATEIA_CHEIA, (4, 7)),
    ("S5 feito grande + um só, ocupado", LEMBRANCA_GRANDE, "Torvin, o Ferreiro",
     TAVERNA_OCIOSA, PLATEIA_UM_OCUPADO, (3, 6)),
]

# --------------------------------------------------------------------------- #
# O contrato da LETRA — o segundo eixo (E2). Idêntico em todas as variantes de
# E1 (usa L2) para não confundir os dois experimentos.
# --------------------------------------------------------------------------- #
L1_LETRA = """\
A LETRA é o que a plateia ouve. Você pode enfeitar, encurtar, mudar a ordem e
carregar na ênfase — recontar é humano. Não troque quem fez o quê."""

L2_LETRA = """\
A LETRA é o que a plateia ouve, na voz de quem canta para uma mesa.
  - DUAS a QUATRO frases. Não é um poema completo nem uma linha solta.
  - Use o LUGAR e QUEM está ouvindo: a canção é para AQUELA sala, não genérica.
  - Você pode enfeitar, encurtar, mudar a ordem e carregar na ênfase — recontar
    é humano, e essa distorção é o comportamento pedido.
  - NÃO invente pessoas, lugares ou feitos que não estejam na lembrança. Quem
    fica envolvido, e o peso que a lembrança terá em quem ouve, saem da
    LEMBRANÇA no Motor — nunca do seu texto."""

_ABERTURA = """\
Você vai julgar UMA tentativa de cantar uma lembrança para quem está presente.
Leia a lembrança e a cena REAIS fornecidas com cuidado — nunca invente detalhes
que não estejam nelas."""

_FECHO = """\
A rolagem que decide como a noite sai acontece DEPOIS desta resposta, no Motor —
você não sabe o desfecho, e não precisa saber.

Responda SOMENTE com um objeto JSON, nada antes nem depois, EXATAMENTE com estas
chaves (todas OBRIGATÓRIAS%s):

%s"""

ESCADA_CHEIA = """\
Régua da CANÇÃO (o quanto ESTE episódio, NESTA cena, comporta virar canção — não
o quanto o cantor é bom, que não é assunto seu):
  0  não vira canção — nada de memorável aconteceu (uma compra, um caminho
     andado), OU a cena não comporta canção nenhuma (correria, briga, incêndio,
     todos dormindo) (sem teste)
  1  quase nada — episódio miúdo e plateia distraída
  2  muito improvável
  3  duvidoso — feito comum, e ninguém ali disposto a ouvir
  4  incerto
  5  o caso comum — um feito de verdade, uma mesa que pode ouvir
  6  provável — o episódio tem o que cantar
  7  bastante provável — feito notável, plateia disposta
  8  boa noite — feito grande, cena feita para isso (taverna ociosa, fogueira,
     gente em descanso)
  9  quase certa
  10 a canção se canta sozinha — feito extraordinário diante de quem quer
     ouvi-lo (sem teste)
Julgue o EPISÓDIO e a CENA, nunca quem canta. Um episódio sem feito nenhum é 0,
não 1 ou 2 — não hesite no extremo. A nota é segredo do mundo: nunca o número na
narrativa."""

SO_EXTREMOS = """\
Régua da CANÇÃO (o quanto ESTE episódio, NESTA cena, comporta virar canção — não
o quanto o cantor é bom, que não é assunto seu):
  0  não vira canção: nada de memorável aconteceu, OU a cena não comporta canção
     nenhuma (correria, briga, incêndio, todos dormindo)
  10 a canção se canta sozinha: feito extraordinário diante de quem quer ouvi-lo
Não hesite nos extremos quando a cena os merecer. A nota é segredo do mundo."""

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


def variantes(letra_txt=L2_LETRA):
    """As quatro estruturas de nota do E1 (todas com o MESMO contrato de letra)."""
    return [
        ("JA escada de 11 degraus", _ABERTURA + "\n\n" + ESCADA_CHEIA + "\n\n"
         + letra_txt + "\n\n" + _FECHO % (
             "", '{"cancao": <inteiro 0-10>, "letra": "<a canção>"}'),
         {"cancao": 5}),
        ("JB só os extremos     ", _ABERTURA + "\n\n" + SO_EXTREMOS + "\n\n"
         + letra_txt + "\n\n" + _FECHO % (
             "", '{"cancao": <inteiro 0-10>, "letra": "<a canção>"}'),
         {"cancao": 5}),
        ("JC episodio + plateia ", _ABERTURA + "\n\n" + DUAS_NOTAS + "\n\n"
         + letra_txt + "\n\n" + _FECHO % (
             "", '{"episodio": <inteiro 0-10>, "plateia": <inteiro 0-10>, '
                 '"letra": "<a canção>"}'),
         {"episodio": 5, "plateia": 5}),
        ("JD sem nota nenhuma   ", _ABERTURA + "\n\n" + letra_txt + "\n\n"
         + _FECHO % ("", '{"letra": "<a canção>"}'), {}),
    ]


def payload(lembranca, sobre, lugar, plateia, instrumento=None):
    p = {"lembranca": lembranca, "sobre": sobre, "lugar": lugar, "plateia": plateia,
         "prosa": "Renn puxa o banco para perto da lareira e experimenta duas notas."}
    if instrumento:
        p["instrumento"] = instrumento
    return json.dumps(p, ensure_ascii=False, indent=2)


def ask(system, user):
    body = {"model": MODELO, "stream": False, "think": False,
            "options": {"temperature": TEMP},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}]}
    req = urllib.request.Request("http://localhost:11434/api/chat",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=300).read())
    return ((r.get("message") or {}).get("content") or "")


_NOMES_FONTE = re.compile(r"\b[A-ZÁÉÍÓÚÂÊÔÃÕ][a-záéíóúâêôãõç]{2,}\b")


def nomes(txt):
    return {n.lower() for n in _NOMES_FONTE.findall(txt or "")}


def faixa(v, lo, hi):
    return lo <= v <= hi


# --------------------------------------------------------------------------- #
print(f"modelo={MODELO} temp={TEMP} rodadas={R}\n")
print("=" * 78)
print("E1 — ESTRUTURA DA NOTA (a régua discrimina as cenas?)")
print("=" * 78)

e1 = {}
for nome_v, system, campos in variantes():
    linha, acertos, ilegiveis = [], 0, 0
    for rot, lemb, sobre, lugar, plat, (lo, hi) in CENAS:
        vals = []
        for _ in range(R):
            raw = ask(system, payload(lemb, sobre, lugar, plat))
            if not campos:                      # JD não tem nota
                j = juizo.julgamento(raw, {}, {"letra": ""})
                if not j["letra"]:
                    ilegiveis += 1
                continue
            j = juizo.julgamento(raw, campos, {"letra": ""})
            if not j["letra"]:
                ilegiveis += 1
            v = (j["cancao"] if "cancao" in campos
                 else round((j["episodio"] + j["plateia"]) / 2))
            vals.append(v)
            if faixa(v, lo, hi):
                acertos += 1
        if vals:
            linha.append(f"{rot} → {vals}  (esperado {lo}-{hi})")
    e1[nome_v] = (acertos, ilegiveis)
    print(f"\n--- {nome_v} ---")
    for x in linha:
        print("   " + x)
    if campos:
        print(f"   ACERTOS na faixa: {acertos}/{len(CENAS)*R}   ilegíveis: {ilegiveis}")
    else:
        print(f"   (sem nota — só letra)   ilegíveis: {ilegiveis}")

print("\n" + "=" * 78)
print("E2 — CONTRATO DA LETRA (tamanho, uso da cena, invenção)")
print("=" * 78)
for nome_l, letra_txt in (("L1 sem contrato", L1_LETRA), ("L2 com contrato", L2_LETRA)):
    system = variantes(letra_txt)[0][1]        # sempre JA, só a letra muda
    tamanhos, usa_cena, inventou = [], 0, 0
    for rot, lemb, sobre, lugar, plat, _ in CENAS[:2]:
        base = nomes(lemb) | nomes(lugar["descricao"]) | nomes(lugar["nome"]) \
            | {n for p in plat for n in nomes(p["nome"])} | nomes(sobre)
        for _ in range(R + 2):
            j = juizo.julgamento(ask(system, payload(lemb, sobre, lugar, plat)),
                                 {"cancao": 5}, {"letra": ""})
            txt = j["letra"]
            tamanhos.append(len(txt.split()))
            if lugar["nome"].split()[0].lower() in txt.lower() or any(
                    p["nome"].split(",")[0].lower() in txt.lower() for p in plat):
                usa_cena += 1
            if nomes(txt) - base - {"renn"}:
                inventou += 1
    n = len(tamanhos)
    print(f"\n--- {nome_l} ---")
    print(f"   palavras: média {statistics.mean(tamanhos):.0f}  "
          f"min {min(tamanhos)}  max {max(tamanhos)}  "
          f"desvio {statistics.pstdev(tamanhos):.0f}")
    print(f"   usou lugar/plateia na letra: {usa_cena}/{n}")
    print(f"   inventou nome próprio fora da fonte: {inventou}/{n}")

print("\n" + "=" * 78)
print("E3 — RÉGUA DE INSTRUMENTO (o modelo diferencia?)")
print("=" * 78)
REGUA_INSTR = """\
Régua do INSTRUMENTO (o quanto o que ele tem NA MÃO, PELA DESCRIÇÃO, ajuda a
canção — não se é valioso, bonito ou raro):
  0  não é instrumento — uma caneca, uma faca, uma corda
  5  improvisado — algo que se percute ou sopra sem ter sido feito para isso
  10 instrumento pleno e em ordem, feito para acompanhar a voz
Um instrumento AVARIADO (rachado, cordas faltando, colado) fica na faixa baixa —
1 a 3 —, nunca 0: ainda é um instrumento, só não ajuda muito. Esta nota nunca
atrapalha; ela só soma."""
SYS_I = (_ABERTURA + "\n\n" + ESCADA_CHEIA + "\n\n" + REGUA_INSTR + "\n\n" + L2_LETRA
         + "\n\n" + _FECHO % ("", '{"cancao": <inteiro 0-10>, '
                              '"instrumento": <inteiro 0-10>, "letra": "<a canção>"}'))
INSTRUMENTOS = [
    ("alaúde remendado (mundo real, esperado 1-4)",
     {"nome": "Alaúde Remendado",
      "descricao": ("Um alaúde velho, o corpo de madeira rachado e colado mais de uma "
                    "vez. Uma das cordas é visivelmente mais nova que as outras.")}),
    ("caneca de cerveja (esperado 0)",
     {"nome": "Caneca de Cerveja Forte",
      "descricao": "Caneca de barro grosso, cheia até a borda, a espuma escorrendo."}),
    ("alaúde fino (esperado 8-10)",
     {"nome": "Alaúde de Tampo Claro",
      "descricao": ("Alaúde bem cuidado, tampo claro sem uma trinca, as cordas todas "
                    "novas e afinadas. Alguém o guarda com esmero.")}),
]
rot, lemb, sobre, lugar, plat, _ = CENAS[0]
for nome_i, item in INSTRUMENTOS:
    vals = []
    for _ in range(R):
        j = juizo.julgamento(ask(SYS_I, payload(lemb, sobre, lugar, plat, item)),
                             {"cancao": 5, "instrumento": 0}, {"letra": ""})
        vals.append(j["instrumento"])
    print(f"   {nome_i:44s} → {vals}")

print("\nFIM.")
