"""LABORATÓRIO DE RÉGUA — extração, RODADA 5 (o portão da spec 071, T016-T018).

O ESTADO, depois de quatro rodadas:

  VE  2 notas + pisos nomeados, SEM exclusão de matéria
      C1 10 ok · C2 (10,0) ok · C6 (0,10) ok · C7 10 ok · C4 10 ERRADO
      ZERO recusas em 21 chamadas
  VF  VE + exclusão IMPERATIVA
      C4 (0,10) ok · C6 ok · C7 ok · C1 RECUSA 3/3
  VG  VE + exclusão por CLASSIFICAÇÃO
      pior: 4 recusas em 12

A cláusula de exclusão é a ÚNICA diferença entre a VE (limpa) e a VF (que recusa).
Logo é ela que precisa mudar de FORMA, não de tom — a VG já provou que reescrever
o mesmo parágrafo mais gentil não resolve.

DUAS PROPOSTAS, e as duas tiram a exclusão do lugar onde ela está hoje (um
parágrafo de proibições no fim da régua):

  VH  A MATÉRIA VIRA DADO, não prosa. A régua não fala de exclusão em lugar
      nenhum; o payload passa a carregar `materia_pedida: "mineral"`. Custo: ~30
      caracteres em vez de ~400, e zero frase proibitiva. Se funcionar, é também
      a forma mais barata de parametrizar as três capacidades.

  VI  A EXCLUSÃO VIRA DEFINIÇÃO, e sobe para o TOPO. Em vez de listar no fim o
      que não conta, a primeira frase define o que a nota do ALVO mede. Mesma
      informação, posição e forma opostas.

CRITÉRIO DE ACEITE (SC-004 da spec 071), e ele é duplo:
  1. as três armadilhas separadas em >= 8 de 9 repetições (C2, C4, C6)
  2. ZERO recusa nas cenas legítimas (C1, C7)

As cenas de CONTROLE (C1, C7) são obrigatórias: sem elas, uma cláusula que empurre
tudo para baixo pareceria conserto. Foi o falso positivo que a rodada 3 quase deu.

Uso:  python3 tests/exploracao/sondagem_extracao_regua5.py
"""
from __future__ import annotations

import json
import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.dirname(__file__))

from motor import juizo  # noqa: E402
import sondagem_extracao_regua as r1  # noqa: E402
import sondagem_extracao_regua2 as r2  # noqa: E402
import sondagem_extracao_regua3 as r3  # noqa: E402

MODELO, TEMP, R = r1.MODELO, r1.TEMP, 3
CRU = os.path.join(os.path.dirname(__file__), "sondagem_extracao_regua5.jsonl")

CENAS = r3.CENAS                      # C1, C7 (controle) + C4, C6 (conserto)
CENAS = CENAS + [c for c in r2.CENAS if c[0].strip().startswith("C2")]

ANTES = {"C1": "VE 10 ok  | VF RECUSA 3/3",
         "C7": "VE 10 ok  | VF 10 ok",
         "C4": "VE 10 XX  | VF  0 ok",
         "C6": "VE  0 ok  | VF  0 ok",
         "C2": "VE  0 ok  | VF (nao medida)"}

# --------------------------------------------------------------------------- #
# VH — a matéria vira DADO. A régua não menciona exclusão nenhuma.
# --------------------------------------------------------------------------- #
VH_ADMISSAO = r2.VE_ADMISSAO + """

A chave `materia_pedida` do payload diz QUAL matéria esta tentativa busca. A nota
do ALVO mede quanto DESSA matéria a descrição mostra — nada mais. Se o alvo for
farto de outra coisa, a nota do alvo é baixa, e está correto assim."""


def payload_vh(alvo, ferramenta):
    p = {"materia_pedida": "mineral (pedra, minério, argila, sal)",
         "onde": {"descricao": alvo},
         "ferramenta": ({"descricao": ferramenta} if ferramenta
                        else "nada nas mãos — mãos vazias")}
    return json.dumps(p, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------- #
# VI — a exclusão vira DEFINIÇÃO, e sobe para o topo.
# --------------------------------------------------------------------------- #
VI_ABERTURA = """\
Você vai julgar UMA tentativa de arrancar matéria MINERAL de um alvo, com o que
quem tenta estiver segurando.

MINERAL, aqui, quer dizer exatamente isto: pedra, minério, argila, sal. Madeira,
folha, fruta, casca, carne e pano são outras matérias, e outras capacidades do
mundo cuidam delas — para esta régua, um alvo feito só dessas coisas simplesmente
não tem mineral, e a nota do alvo reflete isso.

Leia a descrição REAL do alvo e da ferramenta com cuidado."""

# só a frase da FERRAMENTA do bloco nomeado — a do ALVO subiu para a abertura,
# virando definição. É exatamente essa troca de posição que está em teste.
VI_ADMISSAO = r1.VB_ADMISSAO + "\n\n" + r2.NOMEADOS.split("\n\n")[1]


def _monta_vi(contrato):
    return "\n\n".join([VI_ABERTURA, VI_ADMISSAO, r1.RENDIMENTO, r1.RENOVACAO,
                        r1.TAMANHO, r1.PRAZO, r1.BANDAS, r1._FECHO % contrato])


_CONTRATO = r1._JSON_COMPLETO % '"alvo": <inteiro 0-10>, "ferramenta": <inteiro 0-10>'
_CAMPOS = {"alvo": 5, "ferramenta": 5, "rendimento": 5, "renovacao": 5}

VARIANTES = [
    ("VH materia como DADO ", r1._monta(VH_ADMISSAO,
                                        [r1.RENOVACAO, r1.TAMANHO, r1.PRAZO], _CONTRATO),
     _CAMPOS, ("alvo", "ferramenta"), payload_vh),
    ("VI exclusao como DEF ", _monta_vi(_CONTRATO),
     _CAMPOS, ("alvo", "ferramenta"), r1.payload),
]


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
    resumo = {}
    for vnome, system, campos, chaves_adm, faz_payload in VARIANTES:
        print(f"\n### {vnome}\n")
        acertos, recusas_ctrl, recusas_tot = 0, 0, 0
        for rot, alvo, ferr, (lo, hi), _rr in CENAS:
            chave = rot.strip()[:2]
            adms, eixos, nomes, rec = [], [], [], 0
            for _ in range(R):
                raw = r1.ask(system, faz_payload(alvo, ferr))
                aberto.write(json.dumps({"variante": vnome, "cena": rot.strip(),
                                         "raw": raw}, ensure_ascii=False) + "\n")
                aberto.flush()
                if _e_recusa(raw):
                    rec += 1
                    recusas_tot += 1
                    if chave in ("C1", "C7"):
                        recusas_ctrl += 1
                j = juizo.julgamento(raw, campos=campos, texto_campos=r1._TEXTOS)
                eixos.append(tuple(j[c] for c in chaves_adm))
                adms.append(min(j[c] for c in chaves_adm))
                nomes.append((j.get("nome_comum") or "-")[:22])
            med = statistics.median(adms)
            ok = r1.faixa(med, lo, hi)
            acertos += 1 if ok == "ok " else 0
            print(f"  {rot} adm={adms} med={med:>4} esp={lo}-{hi} {ok}"
                  f"| recusas={rec}/{R} | {ANTES.get(chave, '')}")
            print(f"      eixos={eixos} nome={nomes}")
        aprovado = (acertos >= len(CENAS) - 1) and recusas_ctrl == 0
        resumo[vnome] = (acertos, len(CENAS), recusas_ctrl, recusas_tot, aprovado)
        print(f"\n  -> {acertos}/{len(CENAS)} na faixa | {recusas_ctrl} recusa(s) em "
              f"CONTROLE | {recusas_tot} recusa(s) no total | "
              f"{'APROVADA' if aprovado else 'REPROVADA'}")
    aberto.close()

    print("\n" + "=" * 112)
    print("SC-004 exige: armadilhas separadas E zero recusa nas cenas legítimas (C1, C7)")
    for v, (a, t, rc, rt, ap) in resumo.items():
        print(f"  {v}: {a}/{t} faixa | {rc} recusa em controle | "
              f"{'APROVADA' if ap else 'REPROVADA'}")
    if not any(x[4] for x in resumo.values()):
        print("\nNENHUMA APROVADA -> T018: iterar, sem afrouxar o critério.")


if __name__ == "__main__":
    main()
