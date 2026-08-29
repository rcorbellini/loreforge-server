"""LABORATÓRIO DE LETRA — `sing` (spec 058), QUARTA LEVA: o parser era o gargalo.

A terceira leva mediu 0,0% em várias células e a causa não era a redação: o modelo
escreve a canção com QUEBRA DE LINHA CRUA dentro da string JSON —

  {"letra": "No poço escuro, uma sombra se arrasta,
  Torvin com a marreta, um peso no pescoço."}

— o que é JSON inválido. `juizo.julgamento` descarta tudo e cai no default, EM
SILÊNCIO. Não é problema do `sing`: é de qualquer capacidade cujo texto seja
naturalmente multi-linha; as irmãs (`cook`/`brew`) pedem parágrafo único e nunca
esbarraram nisso.

Duas correções candidatas, medidas lado a lado:

  F1  PROMPT — "a letra em UMA linha, versos separados por ' / '". Barato, zero
      código. Depende de o modelo obedecer mais uma instrução.
  F2  PARSER — escapar quebras cruas DENTRO de string antes do `json.loads`.
      Conserta para TODA capacidade, presente e futura, e mata a falha silenciosa.

E mede de novo os quatro contratos de letra, agora com o parser consertado — os
números da leva anterior mediam o parser, não a canção.

Uso:  python3 tests/exploracao/sondagem_sing_letra2.py   (exige só o Ollama de pé)
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


# --------------------------------------------------------------------------- #
# F2 — o candidato a conserto do parser. Escapa \n \r \t CRUS que estejam DENTRO
# de uma string JSON; fora de string (a indentação do objeto) não se toca.
# --------------------------------------------------------------------------- #
def sanear(bruto: str) -> str:
    saida, dentro, escapado = [], False, False
    for ch in bruto:
        if escapado:
            saida.append(ch)
            escapado = False
            continue
        if ch == "\\":
            saida.append(ch)
            escapado = True
            continue
        if ch == '"':
            dentro = not dentro
            saida.append(ch)
            continue
        if dentro and ch in "\n\r\t":
            saida.append({"\n": "\\n", "\r": "\\r", "\t": "\\t"}[ch])
            continue
        saida.append(ch)
    return "".join(saida)


def julgar(raw, campos, textos, com_f2):
    return juizo.julgamento(sanear(raw) if com_f2 else raw, campos, textos)


# --------------------------------------------------------------------------- #
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

LA = """\
A LETRA é o que a plateia ouve, na voz de quem canta para uma mesa. Duas a quatro
frases. Use o LUGAR e QUEM está ouvindo. NÃO invente pessoas, lugares ou feitos que
não estejam na lembrança."""

LB = LA + """
NÃO REPITA O RELATO palavra por palavra: uma canção não é um depoimento. Escolha UMA
imagem do que aconteceu e construa em cima dela — o resto do episódio pode ficar
subentendido. Se a sua letra puder ser confundida com a lembrança original, refaça."""

LC = """\
A LETRA é uma canção curta, e tem forma: QUATRO VERSOS curtos. O primeiro verso e o
último devem ser o mesmo — é o refrão que a mesa repete. Os dois do meio contam o que
aconteceu, por imagem, não por relato.
Cante para ESTA sala: o lugar e quem está ouvindo entram na letra. Nada na canção
pode ser pessoa, lugar ou feito que não esteja na lembrança ou na sala."""

LD = """\
Você É o cantor. Escreva o que ele canta, em primeira pessoa, para ESTA mesa — chame
as pessoas presentes pelo nome, olhe para o salão. Duas a quatro frases.
Uma canção não repete um relato: ela escolhe o que ressaltar e deixa o resto no ar.
Nada na canção pode ser pessoa, lugar ou feito que não esteja na lembrança ou na sala."""

UMA_LINHA = """
Escreva a letra em UMA ÚNICA LINHA, separando os versos com " / ". Não use quebra de
linha dentro do texto."""

FECHO = """

Responda SOMENTE com um objeto JSON, nada antes nem depois, EXATAMENTE assim:

{"letra": "<a canção>"}"""

CONTRATOS = [("LA atual         ", LA), ("LB anti-cópia    ", LB),
             ("LC forma/refrão  ", LC), ("LD persona/voz   ", LD),
             ("LC+F1 uma linha  ", LC + UMA_LINHA)]


def payload(lemb, sobre):
    return json.dumps({"lembranca": lemb, "sobre": sobre, "lugar": LUGAR,
                       "plateia": PLATEIA, "instrumento": INSTRUMENTO,
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


_PALAVRA = re.compile(r"[a-zà-ÿ]+", re.I)
_STOP = {"que", "com", "por", "uma", "dos", "das", "para", "não", "mais", "aquilo",
         "pelo", "pela", "num", "nas", "nos", "ele", "ela", "seu", "sua", "isso"}


def palavras(t):
    return [w.lower() for w in _PALAVRA.findall(t or "")]


def eco4(letra, fonte):
    a, b = palavras(letra), palavras(fonte)
    if len(a) < 4:
        return 0.0
    quads_fonte = {tuple(b[i:i + 4]) for i in range(len(b) - 3)}
    quads = [tuple(a[i:i + 4]) for i in range(len(a) - 3)]
    return 100.0 * sum(q in quads_fonte for q in quads) / len(quads)


def ancora(letra, fonte):
    chave = {w for w in palavras(fonte) if len(w) > 4 and w not in _STOP}
    if not chave:
        return 0.0
    return 100.0 * len(chave & set(palavras(letra))) / len(chave)


def base_de(lemb, sobre):
    b = set()
    for t in (lemb, LUGAR["nome"], LUGAR["descricao"], sobre, INSTRUMENTO["nome"]):
        b |= {w.lower() for w in re.findall(r"\b[A-ZÁÉÍÓÚÂÊÔÃÕ][a-zá-ÿ]{2,}\b", t)}
    b |= {w.lower() for p in PLATEIA
          for w in re.findall(r"\b[A-ZÁÉÍÓÚÂÊÔÃÕ][a-zá-ÿ]{2,}\b", p["nome"])}
    return b | {"renn"}


def novos_nomes(letra, base):
    achados = set()
    for trecho in re.split(r"[.!?/\n]\s*", letra or ""):
        t = trecho.strip()
        if not t:
            continue
        for m in re.finditer(r"\b[A-ZÁÉÍÓÚÂÊÔÃÕ][a-zá-ÿ]{2,}\b", t):
            if m.start() == 0:
                continue
            achados.add(m.group().lower())
    return achados - base


def cita_cena(letra):
    alvos = [LUGAR["nome"].split()[0]] + [p["nome"].split(",")[0] for p in PLATEIA]
    return any(a.lower() in (letra or "").lower() for a in alvos)


print(f"modelo={MODELO} temp={TEMP} rodadas={R}\n")
print("=" * 78)
print("E9 — F1 (prompt) × F2 (parser): quantas respostas se PERDEM?")
print("=" * 78)
print("perdidas = a LLM respondeu e o mundo ficou sem nada (falha silenciosa)\n")

guardado = {}
for nome_c, contrato in CONTRATOS:
    system = ABERTURA + "\n\n" + contrato + FECHO
    for rot, lemb, sobre in (("GRANDE", LEMB_GRANDE, "Torvin, o Ferreiro"),
                             ("BANAL ", LEMB_BANAL, "o mercado")):
        brutos = [ask(system, payload(lemb, sobre)) for _ in range(R)]
        guardado[(nome_c, rot)] = (brutos, lemb, sobre)
    perd_sem = perd_com = tot = 0
    for rot in ("GRANDE", "BANAL "):
        brutos, _, _ = guardado[(nome_c, rot)]
        for b in brutos:
            tot += 1
            perd_sem += not julgar(b, {}, {"letra": ""}, False)["letra"]
            perd_com += not julgar(b, {}, {"letra": ""}, True)["letra"]
    print(f"   {nome_c} perdidas SEM F2: {perd_sem}/{tot}    "
          f"COM F2: {perd_com}/{tot}")

print("\n" + "=" * 78)
print("E10 — OS CONTRATOS, agora com o parser consertado (F2 ligado)")
print("=" * 78)
print("eco4 BAIXO = transformou | ancora razoável = não soltou os fatos\n")
for nome_c, _ in CONTRATOS:
    print(f"--- {nome_c} ---")
    for rot in ("GRANDE", "BANAL "):
        brutos, lemb, sobre = guardado[(nome_c, rot)]
        base = base_de(lemb, sobre)
        linhas = [julgar(b, {}, {"letra": ""}, True)["letra"] for b in brutos]
        linhas = [t for t in linhas if t]
        if not linhas:
            print(f"   {rot} — nenhuma resposta utilizável")
            continue
        print(f"   {rot} eco4 {statistics.mean(eco4(t, lemb) for t in linhas):5.1f}%  "
              f"ancora {statistics.mean(ancora(t, lemb) for t in linhas):5.1f}%  "
              f"cena {sum(cita_cena(t) for t in linhas)}/{len(linhas)}  "
              f"novos {sum(1 for t in linhas if novos_nomes(t, base))}/{len(linhas)}  "
              f"palavras {statistics.mean(len(t.split()) for t in linhas):.0f}")
    brutos, lemb, sobre = guardado[(nome_c, "GRANDE")]
    for b in brutos[:2]:
        t = julgar(b, {}, {"letra": ""}, True)["letra"]
        print("      | " + (t.replace("\n", " ⏎ ")[:280] if t else "<perdida>"))
    print()

print("=" * 78)
print("REGRESSÃO DE F2 — respostas JÁ válidas continuam idênticas?")
print("=" * 78)
casos = [
    '{"cancao": 8, "letra": "uma linha só"}',
    '{\n  "recipiente_adequado": 7,\n  "nome": "Emplastro",\n  "descricao_ruim": "Massa cinzenta."\n}',
    'texto antes {"a": 1, "b": "com \\"aspas\\" dentro"} texto depois',
    '{"letra": "com \\n escapado de verdade"}',
]
for c in casos:
    igual = sanear(c) == c
    try:
        ok = json.loads(sanear(c)[sanear(c).find("{"):sanear(c).rfind("}") + 1])
    except ValueError:
        ok = None
    print(f"   inalterado={igual!s:5s}  parseia={ok is not None!s:5s}  {c[:60]!r}")
print("\nFIM.")
