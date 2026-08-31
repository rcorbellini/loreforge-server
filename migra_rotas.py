"""Move cada ROTA para a estrutura que contém as duas pontas dela.

O QUE ESTAVA ERRADO. As 14 rotas editoriais moravam todas em `<mundo>/routes/`,
na RAIZ — um balaio plano, sem relação com a topologia que elas ligam. A rota
entre dois quartos da taverna e a rota entre duas cidades ficavam lado a lado.

A REGRA. Uma rota mora na MENOR estrutura que contém as suas duas pontas:

    escada-de-elga     taverna-do-gancho <-> quarto-da-elga   ->  taverna-do-gancho
    rua-do-mercador    praca-do-mercado  <-> taverna-do-gancho ->  porto-negro
    estrada-do-vau     porto-negro       <-> vau-de-pedra      ->  costa-de-ferro

Quando uma ponta CONTÉM a outra (`porto-negro` <-> `praca-do-mercado`), a
estrutura é a própria ponta continente.

O CAMINHO DE RUNTIME JÁ FAZIA ASSIM. A rota `acesso-1787857637863-077fb4fc`,
nascida de um `craft` que criou um quarto dentro da Forja, foi gravada em
`forja-de-ferro/` — exatamente esta regra. As editoriais é que estavam fora.

NENHUM CÓDIGO DEPENDE DISTO: `find_route` varre o mundo inteiro
(`WORLD_DIR.rglob("route.md")`), e não há nenhuma referência a `WORLD_DIR /
"routes"` no projeto. É layout editorial, não contrato.

Uso:
    python3 migra_rotas.py            # relatório, não escreve nada
    python3 migra_rotas.py --aplicar  # move de verdade
"""
from __future__ import annotations

import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SERVER_DIR))

import motor  # noqa: E402


def _lugares() -> dict[str, Path]:
    """id de lugar -> pasta."""
    out = {}
    for path in motor.WORLD_DIR.rglob("location.md"):
        fm, _ = motor.read_doc(path)
        if fm.get("id"):
            out[fm["id"]] = path.parent
    return out


def _ancestral_comum(a: Path, b: Path) -> Path:
    """A menor pasta que contém as duas. Se uma contém a outra, é ela mesma."""
    pa, pb = list(a.parts), list(b.parts)
    comum = []
    for x, y in zip(pa, pb):
        if x != y:
            break
        comum.append(x)
    return Path(*comum)


def levantar() -> list[tuple[Path, Path, str]]:
    lugares = _lugares()
    mudancas = []
    for route_md in sorted(motor.WORLD_DIR.rglob("route.md")):
        fm, _ = motor.read_doc(route_md)
        if fm.get("type") != "route":
            continue
        de, para = fm.get("from"), fm.get("to")
        if de not in lugares or para not in lugares:
            print(f"⚠ rota {fm.get('id')} aponta para lugar inexistente "
                  f"({de} -> {para}) — deixada onde está.")
            continue
        casa = _ancestral_comum(lugares[de], lugares[para])
        destino = casa / route_md.parent.name
        if destino == route_md.parent:
            continue                       # já está no lugar certo
        mudancas.append((route_md.parent, destino,
                         str(casa.relative_to(motor.WORLD_DIR)) or "<raiz>"))
    return mudancas


def main() -> None:
    aplicar = "--aplicar" in sys.argv
    mudancas = levantar()
    if not mudancas:
        print("Toda rota já mora na estrutura das suas pontas — nada a fazer.")
        return
    print(f"{len(mudancas)} rota(s) fora de lugar:\n")
    for origem, _destino, casa in mudancas:
        print(f"   {origem.name:26} -> {casa}")
    if not aplicar:
        print("\n(relatório só — rode com --aplicar para mover)")
        return
    for origem, destino, _casa in mudancas:
        if destino.exists():
            print(f"⚠ destino já existe, pulando: {destino}")
            continue
        destino.parent.mkdir(parents=True, exist_ok=True)
        origem.rename(destino)
    # a `routes/` da raiz some se ficar vazia
    velha = motor.WORLD_DIR / "routes"
    if velha.is_dir() and not list(velha.iterdir()):
        velha.rmdir()
        print("\n`routes/` da raiz ficou vazia e foi removida.")
    print(f"\n{len(mudancas)} rota(s) movida(s).")
    print(f"validação: {len(motor.validate_world())} arquivo(s) com schema "
          f"inválido, {len(motor.duplicate_ids())} id(s) duplicado(s).")


if __name__ == "__main__":
    main()
