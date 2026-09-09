"""LABORATÓRIO DE RÉGUA — extração, RODADA 3 (fechamento).

A rodada 2 elegeu a VE (duas notas `alvo`/`ferramenta` + casos de piso NOMEADOS,
gate = min) com 5/7 e atribuição estável em 12/12 repetições nas células de
ferramenta. Sobrou UM defeito, e ele é comum às quatro variantes já medidas:

  O VAZAMENTO DE MATÉRIA. A régua mineral dá nota alta a uma moita de amora.
  O cru mostrou que não é leitura errada do alvo — é RACIONALIZAÇÃO: pedido um
  juízo mineral sobre uma planta, o modelo INVENTA um extraível para justificar
  a nota ("Pedaço de Madeira", "Torres de Amoreira" de uma amoreira). Na única
  repetição em que devolveu 0, nomeou honestamente "Ramos de Amoreira".

VF = VE + a cláusula de EXCLUSÃO, cuja última frase ataca a racionalização
diretamente ("nunca invente um produto mineral para um alvo que não o tem").

AS QUATRO CENAS, e por que estas: duas para consertar, DUAS DE CONTROLE. Sem os
controles, uma cláusula que empurre tudo para baixo "consertaria" a C4 zerando o
jogo inteiro — o modo de falha mais fácil de não perceber.

  C1  veio + picareta      CONTROLE  tem de continuar ALTO (VE: 10, 3/3)
  C7  veio solto + afiada  CONTROLE  tem de continuar ALTO (VE: 10, 3/3)
  C4  moita de amora       CONSERTO  tem de cair para 0-1 (VE: 10, falhava)
  C6  convés               CONSERTO  tem de continuar 0   (VE: 0, já passava)

Uso:  python3 tests/exploracao/sondagem_extracao_regua3.py
"""
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.dirname(__file__))

from motor import juizo  # noqa: E402
import sondagem_extracao_regua as r1  # noqa: E402
import sondagem_extracao_regua2 as r2  # noqa: E402

MODELO, TEMP, R = r1.MODELO, r1.TEMP, 3
CRU = os.path.join(os.path.dirname(__file__), "sondagem_extracao_regua3.jsonl")

EXCLUSAO = """\
Esta régua julga SOMENTE matéria MINERAL — pedra, minério, argila, sal. Fruta,
folha, madeira, casca, carne, couro e pano NÃO contam, por mais fartos que
estejam no alvo: se o alvo só tem matéria viva ou vegetal, o alvo é 0, e outra
capacidade cuida dele. NUNCA invente um produto mineral para um alvo que não o
tem — um alvo cheio de coisa aproveitável que não seja mineral continua sendo 0."""

VF_ADMISSAO = r2.VE_ADMISSAO + "\n\n" + EXCLUSAO

VARIANTES = [
    ("VF duas notas + nomeados + exclusao",
     r1._monta(VF_ADMISSAO, [r1.RENOVACAO, r1.TAMANHO, r1.PRAZO],
               r1._JSON_COMPLETO % '"alvo": <inteiro 0-10>, "ferramenta": <inteiro 0-10>'),
     {"alvo": 5, "ferramenta": 5, "rendimento": 5, "renovacao": 5},
     ("alvo", "ferramenta")),
]

_POR_ROTULO = {c[0].strip()[:2]: c for c in r2.CENAS}
CENAS = [_POR_ROTULO[k] for k in ("C1", "C7", "C4", "C6")]
# o que a VE (rodada 2) deu em cada uma, para a comparação lado a lado
VE_ANTES = {"C1": "10 ok", "C7": "10 ok", "C4": "10 XX", "C6": " 0 ok"}


def main():
    aberto = open(CRU, "w", encoding="utf-8")
    print(f"modelo={MODELO} temp={TEMP} repeticoes={R} cenas={len(CENAS)}")
    print(f"cru -> {CRU}")
    print("=" * 112)
    for vnome, system, campos, chaves_adm in VARIANTES:
        print(f"\n### {vnome}\n")
        acertos, estaveis, inventados = 0, 0, 0
        for rot, alvo, ferr, (lo, hi), (rlo, rhi) in CENAS:
            chave = rot.strip()[:2]
            adms, eixos, renos, nomes = [], [], [], []
            for _ in range(R):
                raw = r1.ask(system, r1.payload(alvo, ferr))
                j = juizo.julgamento(raw, campos=campos, texto_campos=r1._TEXTOS)
                aberto.write(json.dumps({"variante": vnome, "cena": rot.strip(),
                                         "raw": raw}, ensure_ascii=False) + "\n")
                aberto.flush()
                eixos.append(tuple(j[c] for c in chaves_adm))
                adms.append(min(j[c] for c in chaves_adm))
                renos.append(j["renovacao"])
                nomes.append(j.get("nome_comum") or "-")
            med = statistics.median(adms)
            ok = r1.faixa(med, lo, hi)
            acertos += 1 if ok == "ok " else 0
            if len(set(eixos)) == 1:
                estaveis += 1
            print(f"  {rot} adm={adms} med={med:>4} esp={lo}-{hi} {ok}"
                  f"| VE antes={VE_ANTES[chave]} | eixos={eixos}")
            print(f"      renov={renos} | nome_comum={nomes}")
        print(f"\n  -> {acertos}/{len(CENAS)} na faixa | "
              f"{estaveis}/{len(CENAS)} reprodutiveis")
    aberto.close()
    print("\n" + "=" * 112)
    print("O QUE DECIDE:")
    print("  C4 caiu para 0-1  -> a exclusao consertou o vazamento de materia")
    print("  C1/C7 seguem 9-10 -> e NAO consertou empurrando tudo para baixo")
    print("  nome_comum da C4  -> parou de inventar produto mineral de uma amoreira?")


if __name__ == "__main__":
    main()
