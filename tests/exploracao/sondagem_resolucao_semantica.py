"""RESOLVER O ALVO POR SEMÂNTICA — o id sai do contexto e a Mente aponta por descrição.

A IDEIA (mantenedor, 2026-08-31): *"os ids vão pro front mas não pra LLM, a LLM
chama com base descritiva, o conector pluga nesse rag e descobre o ID, e então
envia pra Tool resolvido."*

É mais forte do que tirar só o enum: se a resolução muda de lado, o id some do
CONTEXTO também — e o contexto carrega id+nome de tudo que está na cena.

A PERGUNTA QUE DECIDE, e é uma só: **existe um limiar que separa o que existe do
que não existe?** Um top-1 sem limiar sempre devolve alguma coisa — e devolver "o
fogão" para quem pediu "o destilador" é exatamente a SUBSTITUIÇÃO SILENCIOSA que
a sondagem do enum mediu como o pior caso (5/5). O limiar não é detalhe de
afinação: é o desenho inteiro.

Mede duas coisas:
  ACERTO   — a referência descritiva que TEM alvo resolve no alvo certo?
  REJEIÇÃO — a referência que NÃO tem alvo fica abaixo do limiar?

Uso:  python3 tests/exploracao/sondagem_resolucao_semantica.py
"""
import json, os, sys, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("LOREFORGE_LOG", "0")
import motor   # noqa: E402

EMB = "nomic-embed-text"


def embed(textos):
    req = urllib.request.Request("http://localhost:11434/api/embed",
        data=json.dumps({"model": EMB, "input": textos}).encode(),
        headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=300).read())["embeddings"]


def cos(a, b):
    d = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return d / (na * nb) if na and nb else 0.0


def cena(quem):
    """Os candidatos reais: (id, texto que o representa)."""
    ctx = motor.get_context(quem)
    out = []
    for c in ctx["characters_present"]:
        if c.get("state") == "self":
            continue
        out.append((c["id"], c.get("name") or c["id"]))
        for it in (c.get("carrying") or []):
            out.append((it["id"], it.get("name") or it["id"]))
    for i in ctx["items_present"]:
        out.append((i["id"], i.get("name") or i["id"]))
    for i in ctx["self"]["inventory"]:
        out.append((i["id"], i.get("name") or i["id"]))
    for o in ctx["objects_present"]:
        out.append((o["id"], o.get("name") or o["id"]))
    for r in ctx["routes"]:
        out.append((r["id"], r.get("name") or r["id"]))
    vistos, uniq = set(), []
    for i, t in out:
        if i not in vistos:
            vistos.add(i); uniq.append((i, t))
    return ctx, uniq


CENAS = {
    "torvin-ferreiro": (
        # (referência descritiva, id esperado ou None se NÃO existe na cena)
        [("o frasco de óleo", "frasco-de-oleo"),
         ("Frasco de Óleo", "frasco-de-oleo"),
         ("aquele frasco de azeite no chão", "frasco-de-oleo"),
         ("o cantil de água", "cantil-de-agua-fresca"),
         ("o cantil", "cantil-de-agua-fresca"),
         ("o mascate", "obadiah-mascate"),
         ("Obadiah", "obadiah-mascate"),
         ("a aguadeira", "odila-aguadeira"),
         ("a mulher que vende água", "odila-aguadeira"),
         ("minha bolsa de couro", "bolsa-de-couro"),
         # AUSENTES — nada disso está na cena do Torvin
         ("o pingente de estanho", "pingente-de-estanho"),  # está no Obadiah, presente
         # AUSENTES — nada disso está na cena do Torvin
         ("o destilador", None),
         ("a espada élfica", None),
         ("o cavalo preto", None),
         ("o barril de cerveja", None),
         ("a chave do quarto", None)]),
}

for quem, casos in CENAS.items():
    ctx, cands = cena(quem)
    print(f"### {quem} @ {ctx['location']['name']} — {len(cands)} candidatos na cena\n")
    vet_c = embed([t for _, t in cands])
    vet_r = embed([r for r, _ in casos])

    print(f"{'referência':34} {'top-1 resolvido':26} {'sim':>6}  {'2o':>6}  {'margem':>7}")
    print("-" * 90)
    presentes, ausentes = [], []
    for (ref, esperado), v in zip(casos, vet_r):
        pontos = sorted((( cos(v, vc), cid) for vc, (cid, _) in zip(vet_c, cands)),
                        reverse=True)
        s1, id1 = pontos[0]
        s2 = pontos[1][0]
        marca = "" if esperado is None else ("  ok" if id1 == esperado else "  ERRO")
        print(f"{ref:34} {id1:26} {s1:>6.3f}  {s2:>6.3f}  {s1-s2:>7.3f}{marca}")
        (presentes if esperado else ausentes).append((s1, id1 == esperado))

    print()
    if presentes:
        print(f"  PRESENTES ({len(presentes)}): similaridade do top-1 "
              f"min {min(s for s,_ in presentes):.3f} · "
              f"max {max(s for s,_ in presentes):.3f} · "
              f"acerto {sum(1 for _,ok in presentes if ok)}/{len(presentes)}")
    if ausentes:
        print(f"  AUSENTES  ({len(ausentes)}): similaridade do top-1 "
              f"min {min(s for s,_ in ausentes):.3f} · "
              f"max {max(s for s,_ in ausentes):.3f}")
    if presentes and ausentes:
        # o discriminador é a MARGEM (top-1 menos top-2), não a similaridade
        # absoluta: se a coisa existe, UM candidato se destaca; se não existe,
        # tudo empata em mediocre. É a versão contínua da regra que o
        # `_match_scene_ref` já usa ("só resolve se casar com EXATAMENTE um").
        piso = min(s for s, _ in presentes)
        teto = max(s for s, _ in ausentes)
        print(f"\n  PISO dos presentes  {piso:.3f}")
        print(f"  TETO dos ausentes   {teto:.3f}")
        if piso > teto:
            print(f"  >>> SEPARA. Existe limiar (entre {teto:.3f} e {piso:.3f}) "
                  f"que aceita todo presente e recusa todo ausente.")
        else:
            print(f"  >>> NÃO SEPARA — sobreposição de {piso-teto:+.3f}. "
                  f"Um limiar único ou perde alvo real ou aceita fantasma.")
