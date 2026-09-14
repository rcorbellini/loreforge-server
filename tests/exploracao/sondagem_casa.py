"""SONDAGEM — "dá para erguer uma casa?" (pergunta que originou a spec 071).

Mede o que só o modelo real responde: o que o Árbitro JULGA quando alguém tenta
erguer um abrigo com o material que as capacidades de extração agora produzem.

Usa a régua REAL de `craft` (`motor.craft.declaracao.REGUA_CRAFT`), não uma cópia.

O que importa em cada resposta:
  viabilidade  0 recusa; > 0 a coisa nasce
  tipo         "location" é o que faz nascer um LUGAR onde se entra
  duracao      vira segundos por `duracao_segundos_craft` — e é AQUI que a
               pergunta deixa de ser sobre material e passa a ser sobre TEMPO

Quatro ambições, do abrigo de uma noite à casa de pedra, com o mesmo material
plausível de quem extraiu na mina e no bosque.

Uso:  python3 tests/exploracao/sondagem_casa.py
"""
from __future__ import annotations

import json
import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.dirname(__file__))

from motor import juizo  # noqa: E402
from motor.craft.declaracao import REGUA_CRAFT  # noqa: E402
from motor.craft.primitivas import duracao_segundos_craft, LIMIAR_SINCRONO_S  # noqa: E402
import sondagem_extracao_regua as r1  # noqa: E402

R = 3

LUGAR = {"nome": "Clareira da Trilha Fria",
         "descricao": "Uma clareira rasa entre pedras, chão de cascalho seco, um "
                      "círculo de pedras antigo que ninguém desfez. O vento desce "
                      "da encosta e não encontra nada que o segure."}

TORAS = [{"nome": "Tora de Carvalho", "descricao": "Uma tora de carvalho, casca "
          "escura e miolo firme, pesada demais para carregar num braço só."}] * 6
PEDRAS = [{"nome": "Laje de Pedra", "descricao": "Uma laje de pedra bruta, lascada "
           "na mina, plana de um lado."}] * 8
FIBRA = [{"nome": "Feixe de Fibra", "descricao": "Um feixe de fibra vegetal torcida, "
          "boa para amarrar."}] * 3

AMBICOES = [
    ("A1 abrigo de uma noite  ",
     "amarro os galhos e a fibra num abrigo encostado nas pedras, só para "
     "atravessar a noite", TORAS[:2] + FIBRA),
    ("A2 cabana de troncos    ",
     "ergo uma cabana de troncos, encaixando as toras e amarrando as juntas com "
     "a fibra", TORAS + FIBRA),
    ("A3 casa de pedra e mad. ",
     "levanto uma casa: paredes de laje de pedra assentada e telhado de toras "
     "encaixadas", TORAS + PEDRAS + FIBRA),
    ("A4 casa SEM material    ",
     "levanto uma casa de pedra e madeira aqui", []),
]


def main():
    print(f"modelo={r1.MODELO} temp={r1.TEMP} repeticoes={R}")
    print(f"limiar sincrono={LIMIAR_SINCRONO_S}s  (abaixo disso conclui no ato)")
    print("=" * 104)
    for rot, narracao, materiais in AMBICOES:
        vias, durs, tipos, nomes = [], [], [], []
        for _ in range(R):
            raw = r1.ask(REGUA_CRAFT, json.dumps({
                "narracao": narracao,
                "materiais": materiais,
                "lugar": LUGAR,
                "objetos_presentes": [],
            }, ensure_ascii=False, indent=2))
            j = juizo.julgamento(raw, campos={"viabilidade": 5, "duracao": 5},
                                 texto_campos={"tipo": "item", "tamanho": "P",
                                               "nome": "", "descricao_alta": "",
                                               "descricao_baixa": "", "urgencia": "",
                                               "descricao_vencida": ""})
            vias.append(j["viabilidade"]); durs.append(j["duracao"])
            tipos.append(j.get("tipo")); nomes.append((j.get("nome") or "-")[:24])
        mv, md = statistics.median(vias), statistics.median(durs)
        seg = duracao_segundos_craft(int(md))
        horas = seg / 3600
        modo = "NO ATO" if seg < LIMIAR_SINCRONO_S else f"{horas:.1f} h de ESFORÇO"
        print(f"  {rot} viab={vias} med={mv:>4} | dur={durs} med={md:>4} -> {modo}")
        print(f"      tipo={tipos} nome={nomes}")
    print("\n" + "=" * 104)
    print("A pergunta material responde-se no enum; a temporal, nesta coluna de ESFORÇO.")


if __name__ == "__main__":
    main()
