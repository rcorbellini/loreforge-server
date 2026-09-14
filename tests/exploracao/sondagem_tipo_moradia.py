"""SONDAGEM — o `tipo` do que se cria: quando é MORADIA, tem de ser `location`.

O DEFEITO, achado ao medir "dá para erguer uma casa?" (spec 071, R14): um abrigo de
uma noite saiu classificado como **`object`** 3/3. Object é coisa fixa no lugar, e
**não se entra num object** — um abrigo que não se pode habitar não é abrigo. A casa
de pedra saiu `location` 3/3, então a régua acerta o caso grande e erra o pequeno.

A HIPÓTESE, e ela tem precedente medido nesta mesma spec: a régua do `craft` traz
desempate para **item × object** ("dá pra carregar? Então é item") e **nenhum para
object × location**. É o caso NÃO NOMEADO — e a rodada 2 da régua de extração já
mostrou que caso nomeado acerta 12/12 enquanto princípio geral trava 9/9.

  VA  régua ATUAL (controle)
  VB  régua + o desempate object x location NOMEADO ("dá para entrar? é location")

CENÁRIOS. Cinco que TÊM de ser `location` (do abrigo mais frágil à casa de pedra —
inclusive a cabana de folha de bananeira, que o mantenedor quer que seja possível) e
quatro de CONTROLE que têm de continuar `object`/`item`. Sem os controles, uma régua
que empurrasse tudo para `location` pareceria conserto.

Uso:  python3 tests/exploracao/sondagem_tipo_moradia.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.dirname(__file__))

from motor import juizo  # noqa: E402
from motor.craft.declaracao import REGUA_CRAFT  # noqa: E402
import sondagem_extracao_regua as r1  # noqa: E402

R = 3

# O desempate que falta. Molde do que já existe para item x object, e da lição da
# rodada 2: nomear o caso, não confiar no princípio geral.
DESEMPATE = """\
Na dúvida entre "object" e "location", a pergunta é UMA: dá para uma pessoa ENTRAR
e ficar lá dentro? Então é "location", por mais tosco, pequeno ou frágil que seja —
um abrigo de folhas, uma toca cavada, uma tenda de peles e uma casa de pedra são
todos "location". "object" é o que fica no lugar mas ninguém habita: um banco, uma
cerca, um baú, uma fogueira."""

VA = REGUA_CRAFT
VB = REGUA_CRAFT.replace(
    'Na dúvida entre item e object: dá pra carregar?\nEntão é item.',
    'Na dúvida entre item e object: dá pra carregar?\nEntão é item.\n\n' + DESEMPATE)
assert VB != VA, "o desempate não foi inserido — o texto âncora mudou"

LUGAR = {"nome": "Clareira da Trilha Fria",
         "descricao": "Uma clareira rasa entre pedras, chão de cascalho seco, um "
                      "círculo de pedras que alguém arrumou há muito tempo."}


def m(nome, desc, n=1):
    return [{"nome": nome, "descricao": desc}] * n


CENAS = [
    # (rótulo, tipo esperado, narração, materiais)
    ("M1 cabana de folha    ", "location",
     "tranço as folhas de bananeira sobre uma armação de galhos e faço uma cabana "
     "para passar a noite",
     m("Folha de Bananeira", "Folha larga e comprida, ainda verde.", 8)
     + m("Galho Fino", "Galho fino e flexível.", 4)),
    ("M2 abrigo de uma noite", "location",
     "amarro os galhos e a fibra num abrigo encostado nas pedras, só para "
     "atravessar a noite",
     m("Galho Grosso", "Galho grosso de carvalho.", 3)
     + m("Feixe de Fibra", "Fibra vegetal torcida.", 2)),
    ("M3 tenda de peles    ", "location",
     "estico as peles sobre as varas e armo uma tenda",
     m("Pele Curtida", "Pele de javali curtida, grande.", 4)
     + m("Vara de Freixo", "Vara reta e firme.", 4)),
    ("M4 cabana de troncos ", "location",
     "ergo uma cabana de troncos, encaixando as toras e amarrando as juntas",
     m("Tora de Carvalho", "Tora pesada, miolo firme.", 6)
     + m("Feixe de Fibra", "Fibra vegetal torcida.", 3)),
    ("M5 casa de pedra     ", "location",
     "levanto uma casa: paredes de laje assentada e telhado de toras",
     m("Laje de Pedra", "Laje bruta, plana de um lado.", 8)
     + m("Tora de Carvalho", "Tora pesada.", 6)),
    # --- CONTROLES: não podem virar location -------------------------------- #
    ("C1 banco de tora   ctl", "object",
     "racho a tora ao meio e faço um banco para sentar junto do fogo",
     m("Tora de Carvalho", "Tora pesada.", 1)),
    ("C2 cerca de estacas ctl", "object",
     "finco as estacas em fila e amarro, fazendo uma cerca",
     m("Estaca", "Estaca de madeira apontada.", 10)),
    ("C3 baú de tábuas   ctl", "object",
     "prego as tábuas e monto um baú para guardar coisas",
     m("Tábua", "Tábua de carvalho serrada.", 6)),
    ("C4 corda de fibra  ctl", "item",
     "torço a fibra até virar uma corda",
     m("Feixe de Fibra", "Fibra vegetal torcida.", 3)),
]


def roda(nome_var, regua):
    print(f"\n### {nome_var}\n")
    acertos = 0
    for rot, esperado, narracao, materiais in CENAS:
        tipos, viabs = [], []
        for _ in range(R):
            raw = r1.ask(regua, json.dumps({
                "narracao": narracao, "materiais": materiais,
                "lugar": LUGAR, "objetos_presentes": []},
                ensure_ascii=False, indent=2))
            j = juizo.julgamento(raw, campos={"viabilidade": 5, "duracao": 5},
                                 texto_campos={"tipo": "item", "tamanho": "P",
                                               "nome": "", "descricao_alta": "",
                                               "descricao_baixa": "", "urgencia": "",
                                               "descricao_vencida": ""})
            tipos.append(j.get("tipo")); viabs.append(j["viabilidade"])
        c = Counter(tipos)
        moda, n = c.most_common(1)[0]
        ok = "ok " if moda == esperado else "XX "
        acertos += 1 if ok == "ok " else 0
        print(f"  {rot} esp={esperado:<8} tipos={tipos} {ok}| viab={viabs}")
    print(f"\n  -> {acertos}/{len(CENAS)} classificados certo")
    return acertos


def main():
    print(f"modelo={r1.MODELO} temp={r1.TEMP} repeticoes={R} cenas={len(CENAS)}")
    print("=" * 100)
    a = roda("VA regua ATUAL (controle)", VA)
    b = roda("VB + desempate object x location NOMEADO", VB)
    print("\n" + "=" * 100)
    print(f"VA {a}/{len(CENAS)}   VB {b}/{len(CENAS)}")
    print("Se VB não fechar, a classificação não é controlável por régua e a")
    print("conversa passa a ser SEPARAR AS TOOLS (uma para erguer moradia).")


if __name__ == "__main__":
    main()
