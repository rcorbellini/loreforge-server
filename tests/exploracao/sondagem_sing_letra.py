"""LABORATÓRIO DE LETRA — `sing` (spec 058), TERCEIRA LEVA.

Depois que a régua de cena caiu (decisão do mantenedor: cantar não tem pré-requisito
— ele abre a boca e canta), a ÚNICA coisa que a LLM ainda produz nesta tool é a
LETRA. Então é ela que precisa ser medida com cuidado.

O que a segunda leva achou: a letra não inventa — ela COPIA. "Torvin desceu ao poço
com uma marreta, arrastou algo pelo pescoço, ninguém falou nada por um minuto inteiro
na Taverna do Gancho" é a lembrança quase palavra por palavra, com o nome do lugar
colado no fim. O contrato conseguiu fazê-la usar a sala (1/10 → 6/10) e não conseguiu
fazê-la TRANSFORMAR.

  E7  quatro contratos de letra — LA (o atual) × LB (anti-cópia) × LC (forma fixa)
      × LD (persona/voz). Mede eco, âncora, uso da cena, invenção e tamanho.
  E8  o REGISTRO pela intensidade — dizer à LLM em que chave cantar ("marcou fundo"
      × "lembrança miúda") muda a letra, ou é peso morto como foi o rótulo de afeto?

MÉTRICAS (nenhuma decide sozinha — as letras são impressas para o humano julgar):
  eco4    % dos 4-gramas da letra que aparecem LITERAIS na lembrança. Alto = cópia.
  ancora  % das palavras-chave da lembrança presentes na letra. Zero = soltou a âncora.
  cena    citou o lugar ou alguém da plateia.
  novos   nome próprio fora da fonte — IGNORANDO início de frase (a heurística da
          leva anterior contava "Ninguém" como invenção: 4/10 era ruído).

Uso:  python3 tests/exploracao/sondagem_sing_letra.py   (exige só o Ollama de pé)
"""
import json
import os
import re
import statistics
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from motor import juizo  # noqa: E402

MODELO, TEMP, R = "llama3.1:8b", 0.2, 4

LEMB_GRANDE = ("Vi Torvin descer ao poço com uma marreta e voltar arrastando aquilo "
               "pelo pescoço. Ninguém falou nada por um minuto inteiro.")
LEMB_BANAL = "Comprei três pães na praça do mercado e voltei pela rua do cais."
LUGAR = {"nome": "Taverna do Gancho",
         "descricao": ("Salão baixo de vigas negras, cheiro de peixe e cerveja azeda. "
                       "A lareira range. As mesas estão cheias e ninguém tem pressa.")}
PLATEIA = [{"nome": "Elga, a Taverneira", "fazendo": "seca canecas atrás do balcão",
            "humor": "cansada"},
           {"nome": "Doncel", "fazendo": "cochila sentado sobre a mesa",
            "humor": "bêbado"},
           {"nome": "Bram", "fazendo": "conta moedas devagar", "humor": "tranquilo"}]
INSTRUMENTO = {"nome": "Alaúde Remendado",
               "descricao": ("Um alaúde velho, o corpo de madeira rachado e colado "
                             "mais de uma vez. Uma das cordas é visivelmente mais "
                             "nova que as outras.")}

ABERTURA = """\
Um personagem está cantando, para quem está presente, uma lembrança que ele guarda.
Ele VAI cantar — isso não está em questão. Você escreve a LETRA: o que essa gente
ouve sair da boca dele."""

# ---- os quatro contratos ---------------------------------------------------- #
LA = """\
A LETRA é o que a plateia ouve, na voz de quem canta para uma mesa. Duas a quatro
frases. Use o LUGAR e QUEM está ouvindo. NÃO invente pessoas, lugares ou feitos que
não estejam na lembrança."""

LB = LA + """
NÃO REPITA O RELATO palavra por palavra: uma canção não é um depoimento. Escolha UMA
imagem do que aconteceu e construa em cima dela — o resto do episódio pode ficar
subentendido. Se a sua letra puder ser confundida com a lembrança original, refaça."""

LC = """\
A LETRA é uma canção curta, e tem forma: QUATRO VERSOS curtos, um por linha. O
primeiro verso e o último devem ser o mesmo — é o refrão que a mesa repete. Os dois
do meio contam o que aconteceu, por imagem, não por relato.
Cante para ESTA sala: o lugar e quem está ouvindo entram na letra. Nada na canção
pode ser pessoa, lugar ou feito que não esteja na lembrança ou na sala."""

LD = """\
Você É o cantor. Escreva o que ele canta, em primeira pessoa, para ESTA mesa — chame
as pessoas presentes pelo nome, olhe para o salão. Duas a quatro frases.
Uma canção não repete um relato: ela escolhe o que ressaltar e deixa o resto no ar.
Nada na canção pode ser pessoa, lugar ou feito que não esteja na lembrança ou na sala."""

CONTRATOS = [("LA atual        ", LA), ("LB anti-cópia   ", LB),
             ("LC forma fixa   ", LC), ("LD persona/voz  ", LD)]

FECHO = """

Responda SOMENTE com um objeto JSON, nada antes nem depois, EXATAMENTE assim:

{"letra": "<a canção>"}"""

REGISTRO_FORTE = """
Esta lembrança MARCOU FUNDO quem a viveu — é matéria de canção grande. Cante à
altura dela."""
REGISTRO_FRACO = """
Esta lembrança é MIÚDA — um dia comum, que quase ninguém guardaria. Não force
grandeza que ela não tem; cante o que ela é."""


def payload(lemb, sobre, com_instrumento=True):
    p = {"lembranca": lemb, "sobre": sobre, "lugar": LUGAR, "plateia": PLATEIA,
         "prosa": "Renn puxa o banco para perto da lareira."}
    if com_instrumento:
        p["instrumento"] = INSTRUMENTO
    return json.dumps(p, ensure_ascii=False, indent=2)


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


# ---- métricas --------------------------------------------------------------- #
_PALAVRA = re.compile(r"[a-zà-ÿ]+", re.I)
_STOP = {"que", "com", "por", "uma", "dos", "das", "para", "não", "mais", "aquilo",
         "pelo", "pela", "num", "nas", "nos", "ele", "ela", "seu", "sua", "isso"}


def palavras(t):
    return [w.lower() for w in _PALAVRA.findall(t or "")]


def eco4(letra, fonte):
    """% dos 4-gramas da letra que aparecem literais na lembrança. Alto = cópia."""
    a, b = palavras(letra), palavras(fonte)
    if len(a) < 4:
        return 0.0
    quads_fonte = {tuple(b[i:i + 4]) for i in range(len(b) - 3)}
    quads = [tuple(a[i:i + 4]) for i in range(len(a) - 3)]
    return 100.0 * sum(q in quads_fonte for q in quads) / len(quads)


def ancora(letra, fonte):
    """% das palavras-chave da lembrança presentes na letra. 0 = soltou a âncora."""
    chave = {w for w in palavras(fonte) if len(w) > 4 and w not in _STOP}
    if not chave:
        return 0.0
    tem = set(palavras(letra))
    return 100.0 * len(chave & tem) / len(chave)


_MAIUSCULA = re.compile(r"(?<![.!?\n]\s)(?<!^)\b[A-ZÁÉÍÓÚÂÊÔÃÕ][a-zá-ÿ]{2,}\b")


def novos_nomes(letra, base):
    """Nome próprio fora da fonte, IGNORANDO início de frase (conserto da heurística
    da leva anterior, que contava 'Ninguém' como invenção)."""
    achados = set()
    for trecho in re.split(r"[.!?\n]\s*", letra or ""):
        t = trecho.strip()
        if not t:
            continue
        for m in re.finditer(r"\b[A-ZÁÉÍÓÚÂÊÔÃÕ][a-zá-ÿ]{2,}\b", t):
            if m.start() == 0:
                continue                      # início de frase: não é nome próprio
            achados.add(m.group().lower())
    return achados - base


def base_de(lemb, sobre):
    b = set()
    for t in (lemb, LUGAR["nome"], LUGAR["descricao"], sobre, INSTRUMENTO["nome"]):
        b |= {w.lower() for w in re.findall(r"\b[A-ZÁÉÍÓÚÂÊÔÃÕ][a-zá-ÿ]{2,}\b", t)}
    b |= {w.lower() for p in PLATEIA
          for w in re.findall(r"\b[A-ZÁÉÍÓÚÂÊÔÃÕ][a-zá-ÿ]{2,}\b", p["nome"])}
    return b | {"renn"}


def cita_cena(letra):
    alvos = [LUGAR["nome"].split()[0]] + [p["nome"].split(",")[0] for p in PLATEIA]
    return any(a.lower() in (letra or "").lower() for a in alvos)


def roda(system, lemb, sobre, n=R):
    base, linhas = base_de(lemb, sobre), []
    for _ in range(n):
        j = juizo.julgamento(ask(system, payload(lemb, sobre)), {}, {"letra": ""})
        t = j["letra"]
        linhas.append({"t": t, "eco": eco4(t, lemb), "anc": ancora(t, lemb),
                       "cena": cita_cena(t), "novos": novos_nomes(t, base),
                       "p": len(t.split())})
    return linhas


def resumo(rot, linhas):
    print(f"   {rot} eco4 {statistics.mean(x['eco'] for x in linhas):5.1f}%  "
          f"ancora {statistics.mean(x['anc'] for x in linhas):5.1f}%  "
          f"cena {sum(x['cena'] for x in linhas)}/{len(linhas)}  "
          f"novos {sum(1 for x in linhas if x['novos'])}/{len(linhas)}  "
          f"palavras {statistics.mean(x['p'] for x in linhas):.0f}")


print(f"modelo={MODELO} temp={TEMP} rodadas={R}\n")
print("=" * 78)
print("E7 — QUATRO CONTRATOS DE LETRA")
print("=" * 78)
print("eco4 BAIXO = transformou (bom) | ancora ALTA demais junto com eco4 alto = cópia")
guardado = {}
for nome_c, contrato in CONTRATOS:
    system = ABERTURA + "\n\n" + contrato + FECHO
    print(f"\n--- {nome_c} ---")
    for rot, lemb, sobre in (("feito GRANDE", LEMB_GRANDE, "Torvin, o Ferreiro"),
                             ("feito BANAL ", LEMB_BANAL, "o mercado")):
        linhas = roda(system, lemb, sobre)
        guardado[(nome_c, rot)] = linhas
        resumo(rot, linhas)
    for x in guardado[(nome_c, "feito GRANDE")][:2]:
        print(f"      | {x['t'][:300]}")

print("\n" + "=" * 78)
print("E8 — O REGISTRO PELA INTENSIDADE muda a letra, ou é peso morto?")
print("=" * 78)
melhor = CONTRATOS[1][1]        # LB como base; trocar se E7 apontar outro
for nome_r, extra, lemb, sobre in (
        ("SEM registro  | feito GRANDE", "", LEMB_GRANDE, "Torvin, o Ferreiro"),
        ("COM registro+ | feito GRANDE", REGISTRO_FORTE, LEMB_GRANDE, "Torvin, o Ferreiro"),
        ("SEM registro  | feito BANAL ", "", LEMB_BANAL, "o mercado"),
        ("COM registro- | feito BANAL ", REGISTRO_FRACO, LEMB_BANAL, "o mercado")):
    system = ABERTURA + "\n\n" + melhor + extra + FECHO
    linhas = roda(system, lemb, sobre)
    resumo(nome_r, linhas)
    print(f"      | {linhas[0]['t'][:300]}")
print("\nFIM.")
