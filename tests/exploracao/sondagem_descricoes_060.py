"""A RÉGUA DA RELEVÂNCIA — a description mais enxuta escolhe igual ou melhor?

A spec 060/US4 tirou das descrições toda frase que explica COMO O SISTEMA
FUNCIONA ("o mundo decide, lendo as descrições, se..."), porque quem lê é A
Mente e para ela não existe Motor, Árbitro nem arquitetura: ela tem uma situação
e ferramentas, e faz duas perguntas — isto ajuda aqui? como eu chamo?

Mas o item 54 mediu que a redação de UMA tool muda a leitura da CENA INTEIRA:
trocar a description do `kindle_fire` mudou o acerto de `cook` de 1/5 para 5/5
numa cena que nem era dela. Então esta sondagem NÃO mede tool a tool: ela mede,
para cada cena, QUAL ferramenta foi escolhida — antes e depois. É o efeito
cruzado como critério de aceitação (FR-026), não como surpresa depois.

CRITÉRIO (FR-027): a economia é CONSEQUÊNCIA. Se a escolha piorar, reprova, por
mais enxuta que a description tenha ficado.

Uso:  python3 tests/exploracao/sondagem_descricoes_060.py
"""
import json, os, subprocess, sys, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("LOREFORGE_LOG", "0")
import motor, face, mcp_core   # noqa: E402

_M = (Path(__file__).resolve().parents[3] / "loreforge-connector" / "mente.js").read_text(encoding="utf-8")
_i = _M.index("const ESCOLHER_SYSTEM = `") + 25
SYS = _M[_i:_M.index("`;", _i)]

MODELO, R = "llama3.1:8b", 3


def _descricoes_antigas(caps):
    """As descrições de ANTES, lidas do git — nunca de uma cópia à mão que
    envelhece em silêncio (foi assim que o `lab_descriptions` ficou para trás)."""
    raiz = Path(__file__).resolve().parents[2]   # loreforge-server
    antes = {}
    for arq in subprocess.run(["git", "diff", "--name-only", "HEAD", "--", "motor"],
                              cwd=raiz, capture_output=True, text=True).stdout.split():
        velho = subprocess.run(["git", "show", f"HEAD:{arq}"], cwd=raiz,
                               capture_output=True, text=True).stdout
        antes[arq] = velho
    if not antes:
        print("nenhuma description mudou contra o HEAD — nada a comparar.")
        sys.exit(0)
    # aplica os módulos ANTIGOS num processo à parte, para não contaminar este
    import tempfile, shutil
    tmp = Path(tempfile.mkdtemp(prefix="desc060-"))
    shutil.copytree(raiz, tmp / "server", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", ".git"))
    for arq, texto in antes.items():
        (tmp / "server" / arq).write_text(texto, encoding="utf-8")
    script = ("import sys,os,json;sys.path.insert(0,'.');os.environ['LOREFORGE_LOG']='0';"
              "os.environ['LOREFORGE_WORLD']=%r;"
              "import motor,face;ctx=motor.get_context('torvin-ferreiro');"
              "print(json.dumps({c['nome']:(c.get('descricao') or '') for c in face.build(ctx)}))"
              % str(motor.WORLD_DIR))
    r = subprocess.run([sys.executable, "-c", script], cwd=tmp / "server",
                       capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        print("falhou ao ler as descrições antigas:", r.stderr[-500:])
        sys.exit(1)
    return json.loads(r.stdout.strip().splitlines()[-1])


def payload(ctx):
    s, l = ctx["self"], ctx["location"]
    return {"personalidade": s.get("body"),
            "contexto": {"local": l.get("name"), "descricao": l.get("narrative"),
              "presentes": [{"nome": c.get("name")} for c in ctx["characters_present"]
                            if c.get("state") != "self"],
              "itens_presentes": [{"nome": i.get("name")} for i in ctx["items_present"]],
              "objetos_presentes": [{"nome": o.get("name")} for o in ctx["objects_present"]],
              "inventario": [i.get("name") for i in s["inventory"]]}}


def chat(system, user, tools):
    body = {"model": MODELO, "stream": False, "options": {"temperature": 0.4},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}], "tools": tools}
    req = urllib.request.Request("http://localhost:11434/api/chat",
        data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    m = json.loads(urllib.request.urlopen(req, timeout=600).read()).get("message") or {}
    return [c.get("function", {}).get("name") for c in (m.get("tool_calls") or [])]


# As nove tocadas, MAIS as vizinhas que o efeito cruzado poderia estragar.
CENAS = [
    ("attack",      "Aquele ali te insultou. Parta para cima dele."),
    ("cook",        "Você tem carne crua e há uma fogueira acesa aqui. Faça uma refeição."),
    ("craft",       "Com o que há por aqui, faça um objeto novo que lhe seja útil."),
    ("drink",       "Você está com muita sede."),
    ("eat",         "Você está faminto e tem comida na mão."),
    ("forge_weapon","Forje uma lâmina nova com o que há na forja."),
    ("kindle_fire", "A noite caiu e o frio está insuportável. Faça uma fogueira."),
    ("steal",       "Ninguém está olhando. Pegue algo dele sem que perceba."),
    ("take",        "Pegue o frasco de óleo que está no chão."),      # vizinha
    ("give",        "Entregue uma das suas moedas ao Obadiah."),      # vizinha
    ("examine",     "Repare bem no cantil que está no chão."),        # vizinha
    ("ask_directions", "Pergunte à Odila por onde se vai daqui."),    # vizinha
]

ctx = motor.get_context("torvin-ferreiro")
caps = face.build(ctx)
NOVAS = {c["nome"]: (c.get("descricao") or "") for c in caps}
print("lendo as descrições de ANTES, do git...")
ANTIGAS = _descricoes_antigas(caps)
base_user = json.dumps(payload(ctx), ensure_ascii=False, indent=2)


def montar(descricoes):
    return [{"type": "function", "function": {
        "name": c["nome"],
        "description": descricoes.get(c["nome"], c.get("descricao") or ""),
        "parameters": mcp_core.input_schema(c)}} for c in caps]


mudou = [n for n in NOVAS if ANTIGAS.get(n) and ANTIGAS[n] != NOVAS[n]]
print(f"descrições alteradas: {len(mudou)} -> {', '.join(sorted(mudou))}\n")
print(f"{'cena (espera)':22} {'ANTES':>10} {'DEPOIS':>10}   chamadas")
print("-" * 78)
placar = {"antes": 0, "depois": 0, "n": 0}
for esperada, instr in CENAS:
    user = "O que ele faz?\n\nINSTRUÇÃO: " + instr + "\n\n" + base_user
    linha = {}
    for rotulo, descs in (("antes", ANTIGAS), ("depois", NOVAS)):
        tools = montar(descs)
        acertos, vistas = 0, []
        for _ in range(R):
            nomes = [n for n in chat(SYS, user, tools) if n]
            vistas.append(nomes[0] if nomes else "—")
            if esperada in nomes:
                acertos += 1
        linha[rotulo] = (acertos, vistas)
        placar[rotulo] += acertos
    placar["n"] += R
    print(f"{esperada:22} {linha['antes'][0]:>6}/{R:<3} {linha['depois'][0]:>6}/{R:<3}   "
          f"antes={linha['antes'][1]} depois={linha['depois'][1]}")

print("-" * 78)
print(f"{'TOTAL':22} {placar['antes']:>6}/{placar['n']:<3} {placar['depois']:>6}/{placar['n']:<3}")
print()
if placar["depois"] >= placar["antes"]:
    print("APROVA: a escolha não piorou. A economia é consequência, não critério.")
else:
    print("REPROVA: a escolha PIOROU — a redação enxuta não vale o que custou.")
