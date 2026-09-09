"""LABORATÓRIO DE RÉGUA — extração, RODADA 2.

A rodada 1 (`sondagem_extracao_regua.py`) não produziu veredito: mediu uma régua
mal escrita minha, e com um arnês que perdia informação. O que ela ACHOU, e que
esta rodada existe para confirmar ou derrubar:

  A1  A nota de admissão só usa o fundo da escala em caso NOMEADO. "Mão vazia
      contra pedra é 0" estava escrito -> 0 nas duas variantes, 6/6. Ferramenta
      IMPRÓPRIA não estava escrita -> travada em 3 (VA) / 5 (VB), 6/6.
  A2  Dividir a admissão em duas notas conserta o PISO DO ALVO (convés 3 -> 0)
      e NÃO conserta a cegueira de ferramenta.
  A3  A quarta nota custou caro numa chave que nem estava em teste: a
      `renovacao` da amora caiu de [8,8,8] (VA, estável) para [3,3,5] (VB), e as
      triplas reprodutíveis caíram de 6/6 para 4/6.

AS DUAS VARIANTES, e a previsão falsificável:

  VD  = VA + os dois casos NOMEADOS (extremo do alvo, portado literalmente da
        `forage` de produção; ferramenta imprópria, no molde da lição da régua
        de fogo da spec 052). 13 chaves, 3 notas.
  VE  = VB + os MESMOS dois casos nomeados. 14 chaves, 4 notas.

  PREVISÃO: VD dá C6=0 e C2<=1 MANTENDO renovacao=8 na amora e triplas
  estáveis. Se der, a nota única vence e a divisão da VB era um remédio caro
  para um problema de redação. Se VD não zerar o convés, a divisão é mesmo
  necessária e o cross-talk é o preço.

CONSERTOS DE ARNÊS (a rodada 1 não os tinha, e por isso perdeu atribuição):
  1. as DUAS notas das variantes de dois eixos são registradas separadas, não
     só o `min` que a tool usaria como gate;
  2. toda resposta CRUA vai para um .jsonl, para análise posterior sem re-rodar;
  3. reprodutibilidade (triplas idênticas) e derrapagem de `renovacao` são
     CONTADAS, não olhadas de relance na mediana.

Uso:  python3 tests/exploracao/sondagem_extracao_regua2.py
      (exige só o Ollama de pé)
"""
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.dirname(__file__))

from motor import juizo  # noqa: E402  — o parse REAL
import sondagem_extracao_regua as r1  # noqa: E402  — blocos que já funcionam

MODELO, TEMP, R = r1.MODELO, r1.TEMP, 3
CRU = os.path.join(os.path.dirname(__file__), "sondagem_extracao_regua2.jsonl")

# --------------------------------------------------------------------------- #
# Cenas: as seis da rodada 1 + a que desfaz a confusão da C1.
#
# A C1 misturou DUAS penalidades numa descrição só — o metal "preso fundo" E a
# picareta de bico "arredondado de tanto bater". Sem separar, não dá pra saber
# se o 3 da rodada 1 foi a régua cega ou uma leitura correta de duas coisas
# ruins. C7 é a mesma matéria com as duas penalidades REMOVIDAS.
# --------------------------------------------------------------------------- #
VEIO_SOLTO = ("Parede de rocha lascada onde uma veia de estanho aflora larga e solta, "
              "o metal já destacado da pedra em placas que se soltam ao toque.")
PICARETA_BOA = ("Picareta de mineiro recém-afiada, o bico de aço em ponta viva e o cabo "
                "de freixo firme na mão.")

CENAS = list(r1.CENAS) + [
    ("C7 veio SOLTO + picareta AFIADA ", VEIO_SOLTO, PICARETA_BOA, (9, 10), (0, 2)),
]

# --------------------------------------------------------------------------- #
# Os dois casos NOMEADOS — a hipótese A1 virada em texto.
# --------------------------------------------------------------------------- #
NOMEADOS = """\
NÃO HESITE NO EXTREMO. Um alvo CLARAMENTE sem mineral nenhum — convés de tábuas,
moita de mato, salão de madeira, água — é 0, não 2 ou 3, mesmo com a ferramenta
mais própria na mão.

Uma ferramenta que não foi feita para arrancar pedra — uma colher, uma faca de
cozinha, um remo, um pano — é 0 ou 1, mesmo diante do alvo mais rico. Julgue
SOMENTE a ferramenta que está na mão: outras coisas que existam na cena não
contam para esta nota."""

VD_ADMISSAO = r1.VA_ADMISSAO + "\n\n" + NOMEADOS
VE_ADMISSAO = r1.VB_ADMISSAO + "\n\n" + NOMEADOS

VARIANTES = [
    ("VD nota unica + nomeados (13 chaves)",
     r1._monta(VD_ADMISSAO, [r1.RENOVACAO, r1.TAMANHO, r1.PRAZO],
               r1._JSON_COMPLETO % '"extraibilidade": <inteiro 0-10>'),
     {"extraibilidade": 5, "rendimento": 5, "renovacao": 5},
     ("extraibilidade",)),
    ("VE duas notas + nomeados (14 chaves)",
     r1._monta(VE_ADMISSAO, [r1.RENOVACAO, r1.TAMANHO, r1.PRAZO],
               r1._JSON_COMPLETO % '"alvo": <inteiro 0-10>, "ferramenta": <inteiro 0-10>'),
     {"alvo": 5, "ferramenta": 5, "rendimento": 5, "renovacao": 5},
     ("alvo", "ferramenta")),
]


def main():
    aberto = open(CRU, "w", encoding="utf-8")
    print(f"modelo={MODELO} temp={TEMP} repeticoes={R} "
          f"cenas={len(CENAS)} variantes={len(VARIANTES)}")
    print(f"cru -> {CRU}")
    print("=" * 108)
    resumo = {}
    for vnome, system, campos, chaves_adm in VARIANTES:
        print(f"\n### {vnome}\n")
        acertos, estaveis, deriva_renov, tempos = 0, 0, 0, []
        for rot, alvo, ferr, (lo, hi), (rlo, rhi) in CENAS:
            adms, eixos, renos, tams = [], [], [], []
            for _ in range(R):
                t0 = time.time()
                raw = r1.ask(system, r1.payload(alvo, ferr))
                tempos.append(time.time() - t0)
                j = juizo.julgamento(raw, campos=campos, texto_campos=r1._TEXTOS)
                aberto.write(json.dumps({"variante": vnome, "cena": rot.strip(),
                                         "raw": raw}, ensure_ascii=False) + "\n")
                aberto.flush()
                # CONSERTO 1: as duas notas separadas, além do `min` que seria o gate.
                eixos.append(tuple(j[c] for c in chaves_adm))
                adms.append(min(j[c] for c in chaves_adm))
                renos.append(j["renovacao"])
                tams.append(j.get("tamanho") or "-")
            med = statistics.median(adms)
            ok = r1.faixa(med, lo, hi)
            acertos += 1 if ok == "ok " else 0
            # CONSERTO 3: reprodutibilidade CONTADA.
            if len(set(eixos)) == 1:
                estaveis += 1
            rmed = statistics.median(renos)
            rok = r1.faixa(rmed, rlo, rhi)
            if len(set(renos)) > 1:
                deriva_renov += 1
            detalhe = "" if len(chaves_adm) == 1 else f" eixos={eixos}"
            print(f"  {rot} adm={adms} med={med:>4} esp={lo}-{hi} {ok}"
                  f"| renov={renos} med={rmed:>4} esp={rlo}-{rhi} {rok}"
                  f"| tam={tams}{detalhe}")
        resumo[vnome] = (acertos, len(CENAS), estaveis, deriva_renov,
                         round(statistics.mean(tempos), 1))
        print(f"  -> {acertos}/{len(CENAS)} na faixa | {estaveis}/{len(CENAS)} "
              f"cenas reprodutiveis | {deriva_renov} cenas com renovacao instavel "
              f"| {resumo[vnome][4]}s/chamada")
    aberto.close()

    print("\n" + "=" * 108)
    print("RESUMO  (rodada 1: VA 2/6 faixa, 6/6 reprodutivel | VB 3/6 faixa, 4/6 reprodutivel)")
    for v, (a, t, e, d, seg) in resumo.items():
        print(f"  {v}: {a}/{t} faixa | {e}/{t} reprodutivel | "
              f"{d} renovacao instavel | {seg}s/chamada")
    print("\nAS TRES CELULAS QUE DECIDEM:")
    print("  C2 (colher)  <=1 ? -> os casos nomeados consertaram a cegueira de ferramenta")
    print("  C6 (conves)  ==0 ? -> a nota unica alcanca o piso do alvo sem dividir")
    print("  C4 (renov=8) ok  ? -> a nota unica nao paga o cross-talk da quarta nota")


if __name__ == "__main__":
    main()
