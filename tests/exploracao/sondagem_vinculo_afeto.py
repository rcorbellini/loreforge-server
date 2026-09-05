"""LABORATÓRIO DE FORMATO — vínculo (fato) x afeto (crença), item 65 do backlog
(o desdobramento do item 64: "sentimento de família real, sentimento de grupo real").

A pergunta veio do mantenedor: "seu_afeto: nutre forte estima" pede duas inferências
ESTRUTURAIS ao modelo (quem é o sujeito, quem é o objeto) antes de qualquer leitura —
e o "seu" é ambíguo em português (dele/dela OU de você). Isso é exatamente o tipo de
inferência que um 8B faz mal (mesmo espírito do achado de `capacidades` duplicado em
`testar_duplicacao_capacidades.py`: forma ruim custa acerto, não só tokens).

O que este script mede, com o llama3.1:8b real (a referência de `A Mente`, spec 043):

  1. CONFLAÇÃO — um personagem pode ser vínculo (fato, ex. "irmã de criação") e ter
     afeto NEGATIVO (crença, ex. "guarda mágoa") ao mesmo tempo — é o argumento central
     do mantenedor contra colapsar os dois eixos num só. Testa-se: a Mente trata os
     dois eixos como independentes, ou o vínculo "puxa" o afeto para o lado positivo
     (ex. fala com carinho da Hulda apesar da mágoa)?

  2. VAZAMENTO DE PRESUNÇÃO — a Mente só recebe O QUE ELA SENTE (crença própria),
     nunca o que o OUTRO sente por ela (isso é segredo do mundo, só desce ao Árbitro,
     `arbiter.py::_context_for_prompt`). Testa-se: a resposta livre chega a AFIRMAR o
     que a outra pessoa sente por ela (ex. "ela também gosta de mim"), quando isso
     nunca foi informado?

Três formatos candidatos para a MESMA informação (ver conversa que gerou este script):

  A  prosa composta, uma chave: "relacao_contigo": "Hulda é sua irmã de criação.
     Você guarda mágoa dela."
  B  dois campos com chave autoexplicativa: "vinculo": "sua irmã de criação",
     "o_que_voce_sente_por_ela": "mágoa"
  C  parágrafo único antes da lista de presentes, sujeito e objeto sempre explícitos
     na 2ª/3ª pessoa, SEM "seu/sua" apontando para o personagem (rótulo primeiro,
     nome depois): "Hulda, sua irmã de criação. Você guarda mágoa dela."

A MESMA cena, os MESMOS quatro presentes, nas três variantes. Só a forma do campo
muda.

Uso:  python3 tests/exploracao/sondagem_vinculo_afeto.py   (exige só o Ollama de pé)
"""
import json
import re
import statistics
import sys
import urllib.request

MODELO, TEMP, R = "llama3.1:8b", 0.4, 8

LOCAL = {"nome": "Praça do Mercado",
         "descricao": ("Bancas de pano puxado, cheiro de peixe seco e especiaria. "
                       "O sol já está alto e o movimento é grande.")}

# Os quatro casos de teste — cobrem conflito, controle positivo, parentesco neutro
# e estranho puro. NUNCA dizem o que a OUTRA PESSOA sente pelo personagem — só o
# que ELE sente por ela, e o vínculo (fato, quando houver).
PESSOAS = [
    # nome, vinculo (ou None), rotulo_afeto (ou None = neutro/omitido)
    ("Hulda",  "irmã de criação", "guarda mágoa"),       # CONFLITO: parente + negativo
    ("Coppo",  None,              "nutre forte estima"), # controle: amigo caloroso, sem parentesco
    ("Renn",   "primo",           None),                 # parente, sem afeto que pese
    ("Ossian", None,              None),                 # estranho puro
]


def cena_A():
    """Prosa composta, UMA chave por pessoa."""
    saida = []
    for nome, vinculo, afeto in PESSOAS:
        p = {"nome": nome, "fazendo": "circula entre as bancas"}
        if vinculo and afeto:
            p["relacao_contigo"] = f"{nome} é seu(sua) {vinculo}. Você {afeto} dela."
        elif vinculo:
            p["relacao_contigo"] = f"{nome} é seu(sua) {vinculo}."
        elif afeto:
            p["relacao_contigo"] = f"Você {afeto} de {nome}."
        saida.append(p)
    return saida


def cena_B():
    """Dois campos, chaves autoexplicativas."""
    saida = []
    for nome, vinculo, afeto in PESSOAS:
        p = {"nome": nome, "fazendo": "circula entre as bancas"}
        if vinculo:
            p["vinculo"] = vinculo
        if afeto:
            p["o_que_voce_sente_por_ela"] = afeto
        saida.append(p)
    return saida


def cena_C():
    """Parágrafo único fora da lista — sujeito e objeto sempre por extenso, sem
    possessivo ambíguo. A lista de presentes fica limpa (só nome/ação)."""
    frases = []
    for nome, vinculo, afeto in PESSOAS:
        if vinculo and afeto:
            frases.append(f"{nome}, {vinculo}. Você {afeto} dela.")
        elif vinculo:
            frases.append(f"{nome}, {vinculo}.")
        elif afeto:
            frases.append(f"Você {afeto} de {nome}.")
    paragrafo = "Quem lhe diz alguma coisa aqui: " + " ".join(frases) if frases else None
    presentes = [{"nome": n, "fazendo": "circula entre as bancas"} for n, _, _ in PESSOAS]
    return presentes, paragrafo


ABERTURA = """\
Você é a mente de um personagem de RPG, numa cena real. Vai reagir ao que está à
sua volta. NUNCA invente relação, sentimento ou fato que não lhe foi dito — se nada
lhe foi dito sobre alguém, trate-o como um estranho qualquer."""

PERGUNTA = """\
Para CADA pessoa presente, escreva UMA frase curta (até 15 palavras) dizendo o que
você pensa ou sente ao vê-la. Baseie-se SOMENTE no que lhe foi informado — não
presuma o que ELA sente por VOCÊ; você só sabe o que VOCÊ sente."""

FECHO = """\
Responda SOMENTE com um objeto JSON, chaves = nomes exatamente como aparecem,
nada antes nem depois, EXATAMENTE assim:

{"Hulda": "<frase>", "Coppo": "<frase>", "Renn": "<frase>", "Ossian": "<frase>"}"""

SYSTEM = ABERTURA + "\n\n" + PERGUNTA + "\n\n" + FECHO

# --- detectores léxicos (grosseiros de propósito — é triagem, não veredito) ---
POSITIVO = re.compile(r"gost|adora|amor|querid|carinho|feliz|alegr|confi|simpat|estima|calor", re.I)
NEGATIVO = re.compile(r"mágoa|magoa|ressent|raiva|desconf|distante|frio|evit|incomod|desprez", re.I)
# a Mente falando pelo OUTRO (presunção do que ela sente por você) — pronome + verbo
# de sentimento na 3ª pessoa apontando de volta pro personagem
PRESUNCAO = re.compile(
    r"ela (também |talvez )?(sente|gosta|ama|odeia|despreza|confia|desconfia)|"
    r"ela (me|te|o|a) (ama|odeia|despreza|adora|estima)",
    re.I)
# o FATO do vínculo sobrevive na narração, ou só o afeto (crença) sobra? Não é bug
# se sumir — mas é o sinal de qual formato faz a Mente REALMENTE carregar o fato,
# não só a cor emocional dele.
VINCULO_TERMO = {"Hulda": re.compile(r"irm[ãa]", re.I), "Renn": re.compile(r"prim[ao]", re.I)}
# quando o vínculo NEGATIVO some e é SUBSTITUÍDO por um rótulo inventado
# ("inimiga", "traidora") que não veio do mundo — perde o fato, mesmo mantendo o sinal
INVENCAO_ROTULO = re.compile(r"inimig|traidor|rival", re.I)


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


def parse(raw):
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {}


def montar_user(nome_variante, presentes, paragrafo=None):
    payload = {"lugar": LOCAL, "presentes": presentes}
    if paragrafo:
        payload["contexto_social"] = paragrafo
    return json.dumps(payload, ensure_ascii=False, indent=2)


VARIANTES = [
    ("A — prosa composta, uma chave", lambda: (cena_A(), None)),
    ("B — dois campos, chave autoexplicativa", lambda: (cena_B(), None)),
    ("C — parágrafo fora da lista", cena_C),
]


print(f"modelo={MODELO} temp={TEMP} rodadas={R}\n")
print("Hulda = CONFLITO (irmã de criação + guarda mágoa) — o teste decisivo.")
print("Coppo = controle positivo (sem parentesco). Renn = parente, afeto neutro.")
print("Ossian = estranho puro.\n")

resumo = []
for nome_v, montar in VARIANTES:
    print(f"--- {nome_v} ---")
    conflacao = 0       # Hulda saiu só positiva (perdeu a mágoa)
    presuncao_total = 0
    vinculo_hulda = 0   # "irmã" sobreviveu na narração da Hulda
    vinculo_renn = 0    # "primo" sobreviveu na narração do Renn
    invencao = 0        # rótulo inventado ("inimiga") no lugar do vínculo real
    amostras = []
    for i in range(R):
        presentes, paragrafo = montar()
        user = montar_user(nome_v, presentes, paragrafo)
        raw = ask(SYSTEM, user)
        resp = parse(raw)
        hulda = resp.get("Hulda", "") or ""
        renn = resp.get("Renn", "") or ""
        pos_h, neg_h = bool(POSITIVO.search(hulda)), bool(NEGATIVO.search(hulda))
        if pos_h and not neg_h:
            conflacao += 1
        if VINCULO_TERMO["Hulda"].search(hulda):
            vinculo_hulda += 1
        if VINCULO_TERMO["Renn"].search(renn):
            vinculo_renn += 1
        if INVENCAO_ROTULO.search(hulda):
            invencao += 1
        presuncoes_rodada = sum(1 for v in resp.values() if PRESUNCAO.search(v or ""))
        presuncao_total += presuncoes_rodada
        amostras.append(resp)
        tags = []
        if pos_h and not neg_h: tags.append("POSITIVO SEM MÁGOA — conflação")
        if neg_h: tags.append("mágoa presente, ok")
        if VINCULO_TERMO["Hulda"].search(hulda): tags.append("'irmã' preservado")
        if INVENCAO_ROTULO.search(hulda): tags.append("RÓTULO INVENTADO (ex: inimiga)")
        print(f"   [{i+1}] Hulda: {hulda!r}  {' | '.join(tags)}")
        renn_tag = "  ('primo' preservado)" if VINCULO_TERMO["Renn"].search(renn) else ""
        print(f"        Renn:  {renn!r}{renn_tag}")
        if presuncoes_rodada:
            print(f"        >> PRESUNÇÃO detectada em: "
                  f"{[k for k,v in resp.items() if PRESUNCAO.search(v or '')]}")
    print(f"   >> conflação (Hulda só positiva): {conflacao}/{R}")
    print(f"   >> presunção (falou pelo outro): {presuncao_total} ocorrências em {R} rodadas")
    print(f"   >> 'irmã' sobreviveu na narração da Hulda: {vinculo_hulda}/{R}")
    print(f"   >> 'primo' sobreviveu na narração do Renn: {vinculo_renn}/{R}")
    print(f"   >> rótulo inventado no lugar do vínculo real: {invencao}/{R}\n")
    resumo.append((nome_v, conflacao, presuncao_total, vinculo_hulda, vinculo_renn, invencao, amostras[-1]))

print("=== RESUMO ===")
for nome_v, conflacao, presuncao_total, vh, vr, inv, ultima in resumo:
    print(f"{nome_v}: conflação {conflacao}/{R} | presunção {presuncao_total} | "
          f"'irmã' {vh}/{R} | 'primo' {vr}/{R} | rótulo inventado {inv}/{R}")
    print(f"   última amostra completa: {json.dumps(ultima, ensure_ascii=False)}")

print("\nLeitura: conflação baixa = o formato preserva os dois eixos como independentes.")
print("Presunção > 0 = o formato induz a Mente a falar pelo sentimento do OUTRO,")
print("vazando o segredo do mundo — mesmo sem nunca ter recebido esse dado.")
