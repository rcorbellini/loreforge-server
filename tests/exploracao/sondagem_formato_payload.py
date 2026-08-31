"""O FORMATO DO PEDIDO — dá pra gastar menos token com resultado igual ou melhor?

Duas perguntas do mantenedor, medidas antes de mexer em qualquer coisa que vá à
LLM (é a regra do projeto: nada de régua nova sem medição com o modelo real).

  PARTE 1 — o que o Ollama COBRA por cada pedaço do bloco `tools`. O bloco não é
  enviado como JSON cru: o runtime o RENDERIZA no template do modelo. Então a
  pergunta "compactar o JSON economiza?" não se responde contando caracteres do
  nosso lado — só medindo `prompt_eval_count` com cada variante.

  PARTE 2 — o formato do CONTEXTO, que é 100% nosso. Cinco maneiras de dizer a
  MESMA coisa, medidas em token E em acerto (tool certa + alvo certo).

RESULTADO (2026-08-31, llama3.1:8b, face real do Torvin, 39 tools).

PARTE 1 — o bloco `tools`, cobrado pelo Ollama (`prompt_eval_count`):

    tudo (hoje)                       16.739      —
    sem description de parametro      15.163    -9%
    descricoes de tool CURTAS         12.831   -23%
    descricoes de tool VAZIAS         11.680   -30%
    sem enum de id                    10.944   -35%
    sem enum + descricoes curtas       7.036   -58%
    so o osso (nome e mais nada)       4.309   -74%

DOIS ACHADOS QUE MUDAM COMO SE PENSA NISSO:

  - O COBRADO E ~25% MAIOR QUE A NOSSA CONTA. Estimativa por caracteres/4 dava
    13.332; o Ollama cobra 16.739. Toda estimativa anterior (inclusive o
    "13.300 tokens de face" do item 60) estava por baixo.

  - "COMPACTAR O JSON" NAO E ALAVANCA. O `tools` viaja como OBJETO no corpo da
    requisicao — quem serializa e o Ollama, no template do modelo. A indentacao
    do nosso `json.dumps` nunca chega la: o mesmo objeto custa 16.739 indentado
    ou compacto. As alavancas sao de CONTEUDO (enum, descricao), nao de forma.

PARTE 2 — o formato do CONTEXTO (esse sim e nosso, e a compactacao chega):

    formato                    nossos   cobrado   tool ok   alvo ok
    JSON indentado (hoje)       1.191    18.306     19/20     19/20
    JSON compacto                 939    17.983     19/20     19/20
    linhas `chave: valor`         805    17.851     16/20     15/20
    tabular (cabecalho 1x)        816    17.847     19/20     19/20
    PROSA CORRIDA                 801    17.818     20/20     20/20

  A prosa e a MAIS BARATA e a MAIS CERTEIRA ao mesmo tempo. E o resultado nao e
  "menos estrutura e melhor": as `linhas chave: valor` sao quase tao baratas e
  sao as PIORES (15/20) — a forma especifica importa, nao a quantidade de
  pontuacao.

  Mas a economia aqui e pequena em absoluto: o contexto e ~1,2k de um pedido de
  18,3k. Trocar JSON por prosa poupa ~490 tokens (-2,7% do pedido). O dinheiro
  esta no bloco de tools, nao no contexto.

O QUE ESTA SONDAGEM **NAO** MEDIU, e e onde mora o risco:
  - encurtar descricao foi medido em TOKEN, nunca em ESCOLHA. O item 54 mediu
    justamente isso e achou o contrario do intuitivo: trocar a description de
    `kindle_fire` mudou o acerto de `cook` de 1/5 para 5/5 numa cena que nem era
    dela. Cortar as 39 descricoes na primeira frase NAO e economia gratis — cada
    uma precisa passar pelo processo de `docs/validacao-de-descriptions.md`.
  - os 4 casos daqui tem alvo facil e tool obvia. Nao medem falso negativo em
    cena dificil, que e o que a description de fato compra.

Uso:  python3 tests/exploracao/sondagem_formato_payload.py
      (exige o Ollama de pé; lê o mundo real pelo Motor, sem servidor)
"""
import json, os, sys, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("LOREFORGE_LOG", "0")
import motor, face, mcp_core   # noqa: E402

_M = (Path(__file__).resolve().parents[3] / "loreforge-connector" / "mente.js").read_text(encoding="utf-8")
_i = _M.index("const ESCOLHER_SYSTEM = `") + 25
SYS = _M[_i:_M.index("`;", _i)]

MODELO, R = "llama3.1:8b", 5
ctx = motor.get_context("torvin-ferreiro")
s, l = ctx["self"], ctx["location"]
caps = face.build(ctx)

ENTRIES = ([(c["id"], c.get("name") or "") for c in ctx["characters_present"]]
         + [(i["id"], i.get("name") or "") for i in ctx["items_present"]]
         + [(i["id"], i.get("name") or "") for i in s["inventory"]]
         + [(o["id"], o.get("name") or "") for o in ctx["objects_present"]]
         + [(r["id"], r.get("name") or "") for r in ctx["routes"]])


def chamar(msgs, tools):
    body = {"model": MODELO, "stream": False, "options": {"temperature": 0.4},
            "messages": msgs, "tools": tools}
    req = urllib.request.Request("http://localhost:11434/api/chat",
        data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=600).read())
    return (r.get("message") or {}), r.get("prompt_eval_count", 0)


# ---------------------------------------------------------------- PARTE 1 --- #
def tools_de(*, enums=True, desc="cheia", prop_desc=True, indent=None):
    out = []
    for c in caps:
        d = c.get("descricao") or ""
        if desc == "curta":
            d = d.split(".")[0].strip() + "." if "." in d else d
        elif desc == "nenhuma":
            d = ""
        esq = json.loads(json.dumps(mcp_core.input_schema(c)))
        for k, v in (esq.get("properties") or {}).items():
            if isinstance(v, dict):
                if not enums:
                    v.pop("enum", None)
                if not prop_desc:
                    v.pop("description", None)
        out.append({"type": "function",
                    "function": {"name": c["nome"], "description": d, "parameters": esq}})
    return out


BASE_USER = ("O que ele faz?\n\nINSTRUÇÃO: Pegue o frasco de óleo do chão.\n\n"
             + json.dumps({"contexto": {"local": l.get("name")}}, ensure_ascii=False))

print("=" * 78)
print("PARTE 1 — o que o Ollama COBRA por cada pedaço do bloco `tools`")
print("=" * 78)
print(f"{'variante':44} {'nosso JSON':>11} {'cobrado':>9} {'vs base':>9}")
print("-" * 78)
VAR1 = [
    ("tudo (hoje)",                     dict()),
    ("descrições de tool CURTAS",       dict(desc="curta")),
    ("descrições de tool VAZIAS",       dict(desc="nenhuma")),
    ("sem enum de id",                  dict(enums=False)),
    ("sem description de parâmetro",    dict(prop_desc=False)),
    ("sem enum + descrições curtas",    dict(enums=False, desc="curta")),
    ("só o osso (nada além do nome)",   dict(enums=False, desc="nenhuma", prop_desc=False)),
]
base_cobrado = None
for nome, kw in VAR1:
    t = tools_de(**kw)
    nosso = len(json.dumps(t, ensure_ascii=False)) // 4
    _, cobrado = chamar([{"role": "system", "content": SYS},
                         {"role": "user", "content": BASE_USER}], t)
    if base_cobrado is None:
        base_cobrado = cobrado
    print(f"{nome:44} {nosso:>11} {cobrado:>9} {cobrado-base_cobrado:>+9}")

# um controle: o MESMO conteúdo, serializado com indentação (nosso JSON incha,
# o cobrado muda?) — responde "compactar o nosso JSON adianta?"
t = tools_de()
_, c_normal = chamar([{"role": "system", "content": SYS}, {"role": "user", "content": BASE_USER}], t)
print(f"\n  controle: o `tools` é objeto Python, não string — a indentação do NOSSO")
print(f"  json.dumps não chega ao modelo. Cobrado com o mesmo objeto: {c_normal}")

# ---------------------------------------------------------------- PARTE 2 --- #
PRES = [c for c in ctx["characters_present"] if c.get("state") != "self"]
DADOS = dict(
    personalidade=s.get("body") or "",
    local=l.get("name"), descricao=l.get("narrative") or "",
    presentes=[(c["id"], c.get("name") or "", c.get("action") or "") for c in PRES],
    itens=[(i["id"], i.get("name") or "") for i in ctx["items_present"]],
    objetos=[(o["id"], o.get("name") or "") for o in ctx["objects_present"]],
    inventario=[(i["id"], i.get("name") or "") for i in s["inventory"]],
    rotas=[(r["id"], r.get("name") or "", r.get("destination_name") or "") for r in ctx["routes"]],
    memorias=[(m.get("summary") or m.get("content") or "") for m in (ctx.get("memories") or [])][:20],
)


def f_json_indent(d):
    return json.dumps({
        "personalidade": d["personalidade"],
        "contexto": {"local": d["local"], "descricao": d["descricao"],
            "presentes": [{"id": a, "nome": b, "fazendo": c} for a, b, c in d["presentes"]],
            "objetos_presentes": [{"id": a, "nome": b} for a, b in d["objetos"]],
            "itens_presentes": [{"id": a, "nome": b} for a, b in d["itens"]],
            "inventario": [{"id": a, "nome": b} for a, b in d["inventario"]]},
        "memorias": d["memorias"],
        "rotas_disponiveis": [{"id": a, "nome": b, "para": c} for a, b, c in d["rotas"]],
    }, ensure_ascii=False, indent=2)


def f_json_compacto(d):
    return json.dumps(json.loads(f_json_indent(d)), ensure_ascii=False, separators=(",", ":"))


def f_linhas(d):
    """Uma linha por fato, `chave: valor` — sem chaves, colchetes nem aspas."""
    L = [f"local: {d['local']}", f"cena: {d['descricao']}", f"quem ele é: {d['personalidade']}"]
    L.append("presentes:")
    L += [f"  {a} ({b}) — {c}" for a, b, c in d["presentes"]]
    L.append("no chão:")
    L += [f"  {a} ({b})" for a, b in d["itens"]]
    L.append("objetos:")
    L += [f"  {a} ({b})" for a, b in d["objetos"]]
    L.append("ele carrega:")
    L += [f"  {a} ({b})" for a, b in d["inventario"]]
    L.append("saídas:")
    L += [f"  {a} ({b}) leva a {c}" for a, b, c in d["rotas"]]
    L.append("ele lembra:")
    L += [f"  {m}" for m in d["memorias"]]
    return "\n".join(L)


def f_tabular(d):
    """As LISTAS viram tabela: o cabeçalho aparece UMA vez, não por linha.
    É o desperdício central do JSON — repetir a chave em cada elemento."""
    L = [f"local: {d['local']}", f"cena: {d['descricao']}", f"quem ele é: {d['personalidade']}", ""]
    L.append("presentes | id | nome | fazendo")
    L += [f"| {a} | {b} | {c}" for a, b, c in d["presentes"]]
    L.append("no_chao | id | nome")
    L += [f"| {a} | {b}" for a, b in d["itens"]]
    L.append("objetos | id | nome")
    L += [f"| {a} | {b}" for a, b in d["objetos"]]
    L.append("carrega | id | nome")
    L += [f"| {a} | {b}" for a, b in d["inventario"]]
    L.append("saidas | id | nome | leva_a")
    L += [f"| {a} | {b} | {c}" for a, b, c in d["rotas"]]
    L.append("lembra")
    L += [f"| {m}" for m in d["memorias"]]
    return "\n".join(L)


def f_prosa(d):
    """Tudo em frase corrida, com os ids entre parênteses."""
    p = ", ".join(f"{b} ({a}), {c}" for a, b, c in d["presentes"])
    i = ", ".join(f"{b} ({a})" for a, b in d["itens"]) or "nada"
    o = ", ".join(f"{b} ({a})" for a, b in d["objetos"]) or "nada"
    inv = ", ".join(f"{b} ({a})" for a, b in d["inventario"]) or "nada"
    r = ", ".join(f"{b} ({a}), que leva a {c}" for a, b, c in d["rotas"]) or "nenhuma"
    return (f"Ele está em {d['local']}. {d['descricao']}\n"
            f"Quem ele é: {d['personalidade']}\n"
            f"Estão aqui: {p}.\nNo chão: {i}.\nObjetos: {o}.\nEle carrega: {inv}.\n"
            f"Saídas: {r}.\nEle lembra: " + " | ".join(d["memorias"]))


FORMATOS = [("JSON indentado (hoje)", f_json_indent), ("JSON compacto", f_json_compacto),
            ("linhas chave: valor", f_linhas), ("tabular (cabeçalho 1x)", f_tabular),
            ("prosa corrida", f_prosa)]

CASOS = [("Pegue o frasco de óleo do chão.", "take", "item", "frasco-de-oleo"),
         ("Entregue a moeda-cobre-038 ao Obadiah.", "give", "to", "obadiah-mascate"),
         ("Repare bem no cantil de água que está no chão.", "examine", "alvo", "cantil-de-agua-fresca"),
         ("Pergunte à Odila por onde se vai daqui.", "ask_directions", "quem", "odila-aguadeira")]

print("\n" + "=" * 78)
print("PARTE 2 — o formato do CONTEXTO (mesma informação, cinco maneiras)")
print("=" * 78)
tools = tools_de()
print(f"{'formato':26} {'nossos tokens':>14} {'cobrado':>8} {'tool ok':>8} {'alvo ok':>8}")
print("-" * 78)
for fnome, fn in FORMATOS:
    txt = fn(DADOS)
    tool_ok = alvo_ok = tot = 0
    cobrado = 0
    for instr, esperada, param, certo in CASOS:
        user = "O que ele faz?\n\nINSTRUÇÃO: " + instr + "\n\n" + txt
        for _ in range(R):
            m, tk = chamar([{"role": "system", "content": SYS},
                            {"role": "user", "content": user}], tools)
            cobrado += tk
            tot += 1
            c = next((x for x in (m.get("tool_calls") or [])
                      if x.get("function", {}).get("name") == esperada), None)
            if not c:
                continue
            tool_ok += 1
            v = (c["function"].get("arguments") or {}).get(param)
            v = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
            if v == certo or motor._match_scene_ref(v or "", ENTRIES) == certo:
                alvo_ok += 1
    print(f"{fnome:26} {len(txt)//4:>14} {cobrado//tot:>8} {tool_ok:>4}/{tot:<3} {alvo_ok:>4}/{tot:<3}")
