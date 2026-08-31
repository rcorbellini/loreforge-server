"""Move os RASTROS de pasta-por-registro para uma pasta de rastros por estrutura.

O QUE ESTAVA ERRADO. A spec 034 gravava cada marca de passagem em
`<lugar>/<rastro-id>/rastro.md`: uma PASTA por rastro, com um arquivo só dentro.
Pasta própria é o que distingue uma ENTIDADE (personagem, item, objeto, lugar,
rota) — coisas que ANINHAM outras. Rastro não aninha nada: é registro, irmão de
`memory` e `intention`, e os dois já moram soltos numa pasta única
(`memories/`, `intentions/`).

O ESTRAGO, medido no mundo real em 2026-08-30: 235 marcas viraram 235
diretórios dentro dos lugares — 67 na Praça do Mercado, 46 na Taverna do
Gancho, 26 no Boticário. Toda varredura de cena passava por eles, e no disco um
rastro era indistinguível de um item largado no chão.

DEPOIS:  <lugar>/rastros/<rastro-id>.md

SEGURO DE RODAR MAIS DE UMA VEZ: o que já está no formato novo é ignorado.
Nada é apagado — os arquivos são MOVIDOS, e a pasta vazia que sobra sai atrás.

Uso:
    python3 migra_rastros.py            # relatório, não escreve nada
    python3 migra_rastros.py --aplicar  # move de verdade
"""
from __future__ import annotations

import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SERVER_DIR))

import motor  # noqa: E402


def levantar() -> list[tuple[Path, Path]]:
    """(origem, destino) de cada rastro ainda no formato antigo."""
    mudancas = []
    for antigo in sorted(motor.WORLD_DIR.rglob("rastro.md")):
        pasta = antigo.parent
        fm, _ = motor.read_doc(antigo)
        if fm.get("type") != "rastro":
            continue
        rid = fm.get("id") or pasta.name
        # o lugar é o AVÔ do arquivo: <lugar>/<rastro-id>/rastro.md
        destino = pasta.parent / "rastros" / f"{rid}.md"
        mudancas.append((antigo, destino))
    return mudancas


def main() -> None:
    aplicar = "--aplicar" in sys.argv
    mudancas = levantar()
    if not mudancas:
        print("Nenhum rastro no formato antigo — nada a fazer.")
        return

    por_lugar: dict[str, int] = {}
    for antigo, _ in mudancas:
        lugar = str(antigo.parent.parent.relative_to(motor.WORLD_DIR))
        por_lugar[lugar] = por_lugar.get(lugar, 0) + 1

    print(f"{len(mudancas)} rastro(s) no formato antigo, em "
          f"{len(por_lugar)} estrutura(s):\n")
    for lugar, n in sorted(por_lugar.items(), key=lambda kv: -kv[1]):
        print(f"   {n:4}  {lugar}")

    if not aplicar:
        print("\n(relatório só — rode com --aplicar para mover)")
        return

    movidos = 0
    for antigo, destino in mudancas:
        if destino.exists():
            print(f"⚠ destino já existe, pulando: {destino}")
            continue
        destino.parent.mkdir(parents=True, exist_ok=True)
        antigo.rename(destino)
        # a pasta do rastro fica vazia: sai atrás. Só se estiver MESMO vazia —
        # se alguém pôs outra coisa ali, o aviso é melhor que a remoção.
        pasta = antigo.parent
        restante = list(pasta.iterdir())
        if not restante:
            pasta.rmdir()
        else:
            print(f"⚠ pasta não ficou vazia, mantida: {pasta} "
                  f"({[p.name for p in restante]})")
        movidos += 1

    print(f"\n{movidos} rastro(s) movido(s).")
    problemas = motor.validate_world()
    dups = motor.duplicate_ids()
    print(f"validação após a migração: {len(problemas)} arquivo(s) com schema "
          f"inválido, {len(dups)} id(s) duplicado(s).")


if __name__ == "__main__":
    main()
