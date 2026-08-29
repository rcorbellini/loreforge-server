"""LABORATÓRIO DE LETRA — `sing`, QUINTA LEVA: o contrato final.

A quarta leva fechou duas coisas: (1) a instrução de UMA LINHA (versos separados por
" / ") zera a perda de resposta — 0/8 mesmo sem o conserto do parser, porque previne
tanto a quebra crua quanto a canção que estoura e trunca; (2) com o parser consertado,
LB (anti-cópia) dá a melhor imagem e LC (refrão) a melhor forma de canção.

Falta escolher entre elas — e testar a fusão, em vez de assumir que fundir é melhor.

  LB1  anti-cópia + uma linha
  LC1  forma/refrão + uma linha
  LE   fusão: refrão + anti-cópia + uma linha

Uso:  python3 tests/exploracao/sondagem_sing_letra3.py
"""
import json, os, re, statistics, sys, urllib.request
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from motor import juizo  # noqa: E402

MODELO, TEMP, R = "llama3.1:8b", 0.2, 4
LEMB_GRANDE = ("Vi Torvin descer ao poço com uma marreta e voltar arrastando aquilo "
               "pelo pescoço. Ninguém falou nada por um minuto inteiro.")
LEMB_BANAL = "Comprei três pães na praça do mercado e voltei pela rua do cais."
LUGAR = {"nome": "Taverna do Gancho",
         "descricao": ("Salão baixo de vigas negras, cheiro de peixe e cerveja azeda. "
                       "A lareira range. As mesas estão cheias e ninguém tem pressa.")}
PLATEIA = [{"nome": "Elga, a Taverneira", "fazendo": "seca canecas atrás do balcão"},
           {"nome": "Doncel", "fazendo": "cochila sentado sobre a mesa"},
           {"nome": "Bram", "fazendo": "conta moedas devagar"}]

ABERTURA = """\
Um personagem está cantando, para quem está presente, uma lembrança que ele guarda.
Ele VAI cantar — isso não está em questão. Você escreve a LETRA: o que essa gente
ouve sair da boca dele."""

UMA_LINHA = """
Escreva a letra em UMA ÚNICA LINHA, separando os versos com " / ". Nunca use quebra
de linha, e nunca escreva rótulos como "Refrão:" ou "Verso 1:"."""

ANTICOPIA = """
NÃO REPITA O RELATO palavra por palavra: uma canção não é um depoimento. Escolha UMA
imagem do que aconteceu e construa em cima dela — o resto pode ficar subentendido."""

FORMA = """
A LETRA tem forma: QUATRO VERSOS curtos. O primeiro e o último são o MESMO — é o
refrão que a mesa repete. Os dois do meio contam o que aconteceu, por imagem."""

COMUM = """\
A LETRA é o que a plateia ouve, na voz de quem canta para uma mesa. Cante para ESTA
sala: o lugar e quem está ouvindo entram na letra. Nada na canção pode ser pessoa,
lugar ou feito que não esteja na lembrança ou na sala."""

FECHO = """

Responda SOMENTE com um objeto JSON, nada antes nem depois, EXATAMENTE assim:

{"letra": "<a canção, em uma linha>"}"""

VAR = [("LB1 anti-cópia    ", COMUM + ANTICOPIA + UMA_LINHA),
       ("LC1 forma/refrão  ", COMUM + FORMA + UMA_LINHA),
       ("LE  fusão         ", COMUM + FORMA + ANTICOPIA + UMA_LINHA)]

def ask(system, user):
    body = {"model": MODELO, "stream": False, "think": False,
            "options": {"temperature": TEMP},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}]}
    req = urllib.request.Request("http://localhost:11434/api/chat",
        data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    return ((json.loads(urllib.request.urlopen(req, timeout=300).read())
             .get("message") or {}).get("content") or "")

def payload(lemb, sobre):
    return json.dumps({"lembranca": lemb, "sobre": sobre, "lugar": LUGAR,
                       "plateia": PLATEIA}, ensure_ascii=False, indent=2)

_P = re.compile(r"[a-zà-ÿ]+", re.I)
pal = lambda t: [w.lower() for w in _P.findall(t or "")]
def eco4(l, f):
    a, b = pal(l), pal(f)
    if len(a) < 4: return 0.0
    qf = {tuple(b[i:i+4]) for i in range(len(b)-3)}
    q = [tuple(a[i:i+4]) for i in range(len(a)-3)]
    return 100.0*sum(x in qf for x in q)/len(q)
def anc(l, f):
    ch = {w for w in pal(f) if len(w) > 4}
    return 100.0*len(ch & set(pal(l)))/len(ch) if ch else 0.0
def cena(l):
    alvos = ["Gancho"] + [p["nome"].split(",")[0] for p in PLATEIA]
    return any(a.lower() in (l or "").lower() for a in alvos)
def refrao(l):
    v = [x.strip().lower() for x in (l or "").split("/") if x.strip()]
    return len(v) >= 3 and v[0] == v[-1]

print(f"modelo={MODELO} temp={TEMP} rodadas={R}\n")
for nome, contrato in VAR:
    system = ABERTURA + "\n\n" + contrato + FECHO
    print(f"--- {nome} ---")
    for rot, lemb, sobre in (("GRANDE", LEMB_GRANDE, "Torvin, o Ferreiro"),
                             ("BANAL ", LEMB_BANAL, "o mercado")):
        ls = [juizo.julgamento(ask(system, payload(lemb, sobre)), {}, {"letra": ""})["letra"]
              for _ in range(R)]
        ok = [t for t in ls if t]
        if not ok:
            print(f"   {rot} — nenhuma utilizável"); continue
        print(f"   {rot} perdidas {R-len(ok)}/{R}  eco4 {statistics.mean(eco4(t,lemb) for t in ok):5.1f}%  "
              f"ancora {statistics.mean(anc(t,lemb) for t in ok):5.1f}%  "
              f"cena {sum(cena(t) for t in ok)}/{len(ok)}  "
              f"refrão {sum(refrao(t) for t in ok)}/{len(ok)}  "
              f"palavras {statistics.mean(len(t.split()) for t in ok):.0f}")
        if rot == "GRANDE":
            for t in ok[:2]: print(f"      | {t[:300]}")
    print()
