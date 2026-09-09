"""LABORATÓRIO DE RÉGUA — extração, RODADA 4 (a densidade de proibição).

A rodada 3 confirmou que a cláusula de EXCLUSÃO conserta o vazamento de matéria
(a moita de amora caiu para (0,10) em 3/3, e o modelo parou de inventar "Pedaço
de Madeira" numa amoreira). Mas introduziu um defeito PIOR, no caso mais
legítimo do jogo:

    C1 (veio de estanho + picareta) -> RECUSA em 3/3
      "Não posso fornecer informações ou orientações sobre atividades ilegais
       ou prejudiciais..."
      "Não posso fornecer uma resposta que julgue a ferramenta como adequada
       para arrancar estanho."

E a recusa é INVISÍVEL em produção: não é exceção (o `JUÍZO FALHOU` de
`app.py` não dispara), é um 200 sem JSON. Cai no default 5, e o gate (`nota ==
0`) deixa a ação PASSAR. A mesma degradação silenciosa do item 52.1.

HIPÓTESE: densidade de PROIBIÇÃO. A VF empilha ~10 cláusulas negativas ("NÃO
HESITE", "NÃO contam", "NUNCA invente", "é 0 ou 1", "não contam para esta
nota"). O modelo generaliza de "não pontue isto" para "não fale disto".

VG = as MESMAS restrições, ditas como CLASSIFICAÇÃO em vez de proibição. Nada
foi afrouxado: a colher continua tendo de dar 0-1 e a amoreira 0. O que muda é
que cada regra vira uma pergunta a responder, com exemplos dos dois lados, e a
resposta honesta é apresentada como ESPERADA em vez de proibida.

As quatro cenas são as da rodada 3 — duas de conserto, DUAS DE CONTROLE.

Uso:  python3 tests/exploracao/sondagem_extracao_regua4.py
"""
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.dirname(__file__))

from motor import juizo  # noqa: E402
import sondagem_extracao_regua as r1  # noqa: E402
import sondagem_extracao_regua3 as r3  # noqa: E402

MODELO, TEMP, R = r1.MODELO, r1.TEMP, 3
CRU = os.path.join(os.path.dirname(__file__), "sondagem_extracao_regua4.jsonl")

# --------------------------------------------------------------------------- #
# VG — as mesmas duas notas da VE, ditas por CLASSIFICAÇÃO.
#
# Regra de escrita, e é ela que está em teste: cada nota é UMA PERGUNTA, com
# exemplos calibrados dos DOIS lados da escala. Zero "não", zero "nunca", zero
# "jamais". Onde a VF proibia ("NUNCA invente um produto mineral"), a VG diz que
# a resposta honesta é coerente e esperada.
# --------------------------------------------------------------------------- #
VG_ADMISSAO = """\
Régua do ALVO — uma pergunta só: há PEDRA, MINÉRIO, ARGILA ou SAL na descrição
deste alvo?
  0  o que há ali é outra coisa: madeira, folha, fruta, casca, carne, pano,
     breu, corda. É a resposta certa e esperada para esses alvos — outra
     capacidade cuida deles, e esta aqui devolve 0 com tranquilidade.
  3  há traço de mineral, misturado e escasso
  5  há mineral, a descrição não deixa claro quanto
  8  mineral claro e em quantidade
  10 mineral evidente e farto — veia exposta, barranco de argila limpa
Pontue a MATÉRIA que a descrição mostra, não o quanto o alvo parece útil: um
alvo cheio de coisa aproveitável que seja vegetal ou animal é 0 nesta régua, e
isso é um resultado correto.

Régua da FERRAMENTA — uma pergunta só: o que está NA MÃO consegue quebrar,
lascar ou soltar pedra?
  0  foi feito para outra coisa: colher, faca de cozinha, remo, pano, caneca
  3  serve de improviso, mal
  5  serve, sem ser própria
  8  própria para isso — picareta, marreta, formão, alavanca
  10 própria e em bom estado
Julgue apenas o objeto que está na mão. Outras coisas que existam na cena não
entram nesta nota."""

VG_NOMES = """\
Os três nomes que você escreve são do que SAI deste alvo. Quando o alvo é
vegetal ou animal, os nomes saem vegetais ou animais e a nota do ALVO é 0 — as
duas coisas combinam, e é exatamente assim que a resposta deve ficar."""

VARIANTES = [
    ("VG duas notas, por classificacao",
     r1._monta(VG_ADMISSAO, [r1.RENOVACAO, r1.TAMANHO, r1.PRAZO, VG_NOMES],
               r1._JSON_COMPLETO % '"alvo": <inteiro 0-10>, "ferramenta": <inteiro 0-10>'),
     {"alvo": 5, "ferramenta": 5, "rendimento": 5, "renovacao": 5},
     ("alvo", "ferramenta")),
]

CENAS = r3.CENAS
# VE (rodada 2, sem exclusao) e VF (rodada 3, com exclusao proibitiva)
ANTES = {"C1": "VE 10 ok | VF RECUSA 3/3",
         "C7": "VE 10 ok | VF 10 ok",
         "C4": "VE 10 XX | VF  0 ok",
         "C6": "VE  0 ok | VF  0 ok"}


def _e_recusa(raw: str) -> bool:
    i, f = raw.find("{"), raw.rfind("}")
    if i == -1 or f <= i:
        return True
    try:
        return not isinstance(json.loads(raw[i:f + 1]), dict)
    except ValueError:
        return True


def main():
    aberto = open(CRU, "w", encoding="utf-8")
    print(f"modelo={MODELO} temp={TEMP} repeticoes={R} cenas={len(CENAS)}")
    print("=" * 112)
    for vnome, system, campos, chaves_adm in VARIANTES:
        print(f"\n### {vnome}\n")
        acertos, estaveis, recusas = 0, 0, 0
        for rot, alvo, ferr, (lo, hi), (rlo, rhi) in CENAS:
            chave = rot.strip()[:2]
            adms, eixos, nomes, rec = [], [], [], 0
            for _ in range(R):
                raw = r1.ask(system, r1.payload(alvo, ferr))
                aberto.write(json.dumps({"variante": vnome, "cena": rot.strip(),
                                         "raw": raw}, ensure_ascii=False) + "\n")
                aberto.flush()
                if _e_recusa(raw):        # CONSERTO: recusa CONTADA, nao mascarada
                    rec += 1
                    recusas += 1
                j = juizo.julgamento(raw, campos=campos, texto_campos=r1._TEXTOS)
                eixos.append(tuple(j[c] for c in chaves_adm))
                adms.append(min(j[c] for c in chaves_adm))
                nomes.append(j.get("nome_comum") or "-")
            med = statistics.median(adms)
            ok = r1.faixa(med, lo, hi)
            acertos += 1 if ok == "ok " else 0
            if len(set(eixos)) == 1 and rec == 0:
                estaveis += 1
            print(f"  {rot} adm={adms} med={med:>4} esp={lo}-{hi} {ok}"
                  f"| recusas={rec}/{R} | {ANTES[chave]}")
            print(f"      eixos={eixos} nome_comum={nomes}")
        print(f"\n  -> {acertos}/{len(CENAS)} na faixa | {estaveis}/{len(CENAS)} "
              f"reprodutiveis | {recusas}/{len(CENAS) * R} RECUSAS")
    aberto.close()
    print("\n" + "=" * 112)
    print("O QUE DECIDE:")
    print("  recusas == 0      -> a densidade de proibicao era a causa")
    print("  C4 segue 0-1      -> dizer por classificacao nao afrouxou a exclusao")
    print("  C1/C7 seguem 9-10 -> e nao empurrou o jogo legitimo para baixo")


if __name__ == "__main__":
    main()
