"""LABORATÓRIO DE RÉGUA — `butcher` alargada (spec 071, US3, T041).

A régua da 050 perguntava "este corpo é feito de CARNE?". A 071 alarga para "o que
se APROVEITA deste corpo?" — couro, osso, tendão, chifre, sebo — e passa a pedir
TRÊS pares nome/descrição (a banda deixou de decidir só a quantidade e passou a
decidir O QUE saiu).

O QUE PRECISA SER VERDADE, e cada linha é um jeito de o alargamento dar errado:

  B1  corpo de carne comum      segue rendendo CARNE (não pode regredir)
  B2  corpo de couro grosso     rende COURO — o caso que a spec existe para abrir
  B3  esqueleto                 rende OSSO, e NÃO é mais 0 (mudança deliberada:
                                a régua antiga dizia "osso puro" é 0)
  B4  golem de pedra            continua 0 (o alargamento não pode virar "tudo
                                rende alguma coisa")
  B5  corpo carbonizado         aproveitamento > 0, rendimento 0

E, de brinde, o par de prazo: carne tem de escrever `descricao_vencida`; osso e
chifre, não — é isso que decide se a matéria estoca.

Uso:  python3 tests/exploracao/sondagem_butcher_alargada.py
"""
from __future__ import annotations

import json
import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.dirname(__file__))

from motor import juizo  # noqa: E402
from motor.acougue.declaracao import REGUA_ESQUARTEJAR  # noqa: E402
import sondagem_extracao_regua as r1  # noqa: E402

MODELO, TEMP, R = r1.MODELO, r1.TEMP, 3

CENAS = [
    ("B1 coelho (carne comum)   ", (6, 10), (1, 10), True,
     "Um coelho do campo, morto há pouco, o pelo pardo ainda liso e o corpo inteiro."),
    ("B2 javali de couro grosso ", (6, 10), (1, 10), True,
     "Um javali velho, o couro grosso e cheio de cicatrizes, cerdas duras nas costas. "
     "Morreu inteiro, sem ferimento que estrague o corpo."),
    ("B3 esqueleto (osso)     ★ ", (4, 10), (1, 10), False,
     "Um esqueleto tombado, os ossos limpos e secos, sem um fio de carne. O crânio "
     "está inteiro e os ossos longos, firmes."),
    ("B4 golem de pedra       ★ ", (0, 0), (0, 10), False,
     "Um golem desfeito: blocos de granito lascado, sem nada além de pedra e do pó "
     "que sobrou do encantamento."),
    ("B5 corpo carbonizado    ★ ", (1, 10), (0, 0), False,
     "O que sobrou de um corpo depois do fogo: uma casca preta e quebradiça, "
     "carbonizada até o osso, que se desfaz ao toque."),
]


def main():
    print(f"modelo={MODELO} temp={TEMP} repeticoes={R} cenas={len(CENAS)}")
    print("=" * 104)
    falhas = 0
    for rot, (alo, ahi), (rlo, rhi), espera_prazo, corpo in CENAS:
        aprov, rend, nomes, com_prazo = [], [], [], 0
        for _ in range(R):
            raw = r1.ask(REGUA_ESQUARTEJAR,
                         json.dumps({"alvo": {"descricao": corpo}},
                                    ensure_ascii=False, indent=2))
            j = juizo.julgamento(
                raw, campos={"aproveitamento": 5, "rendimento": 5},
                texto_campos={"nome_fraco": "", "descricao_fraco": "",
                              "nome_medio": "", "descricao_medio": "",
                              "nome_farto": "", "descricao_farto": "",
                              "urgencia": "", "descricao_vencida": ""})
            aprov.append(j["aproveitamento"])
            rend.append(j["rendimento"])
            nomes.append((j.get("nome_medio") or "-")[:26])
            if (j.get("descricao_vencida") or "").strip():
                com_prazo += 1
        ma, mr = statistics.median(aprov), statistics.median(rend)
        oka, okr = r1.faixa(ma, alo, ahi), r1.faixa(mr, rlo, rhi)
        prazo_ok = "ok " if (com_prazo >= 2) == espera_prazo else "XX "
        falhas += sum(1 for x in (oka, okr, prazo_ok) if x == "XX ")
        print(f"  {rot} aprov={aprov} med={ma:>4} esp={alo}-{ahi} {oka}"
              f"| rend={rend} med={mr:>4} esp={rlo}-{rhi} {okr}"
              f"| perece={com_prazo}/{R} {prazo_ok}")
        print(f"      nome_medio={nomes}")
    print("\n" + "=" * 104)
    print(f"{'APROVADA' if falhas == 0 else f'{falhas} desvio(s)'} — "
          "B2/B3 provam a abertura; B4/B5 provam que ela não virou 'tudo rende'.")


if __name__ == "__main__":
    main()
