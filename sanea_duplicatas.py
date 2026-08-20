"""Resolve ENTIDADE DUPLICADA — o mesmo `id` em duas pastas do mundo (2026-08-20).

DE ONDE VEM O DUPLICADO. Não do Motor. Deslocar é `rename` de pasta
(`io.move_entity`, Princípio XII); para o git isso é `D <antigo>` + `?? <novo>`.
Qualquer restauração do índice — `git checkout -- .`, `git stash`, `git reset
--hard`, `git submodule update` — traz o caminho antigo de volta enquanto o novo
segue no disco. Duas pastas, mesmo id, ambas vivas. Diagnóstico completo em
`analises/bug-personagem-duplicado.md`.

QUAL COPIA FICA: a de MEMÓRIA MAIS RECENTE. Não a que tem mais arquivos — o
fantasma costuma ser uma foto antiga e gorda, e a viva é onde o jogo continuou.
Desempate: mais memórias, depois mtime do `character.md`.

MEMÓRIA SE FUNDE, ITEM NÃO. A assimetria é de propósito:

  · MEMÓRIA é histórico append-only. Nos casos reais os DOIS lados foram jogados
    (a Hulda descartada tinha 249 memórias que só existiam nela, de uma semana
    inteira). Descartar é perder mundo — a mesma regra do `sanea_mundo.py`.

  · ITEM é estado EXCLUSIVO: quem segura o quê. A cópia viva é a autoridade, e o
    que só existe no fantasma é foto velha de um desfecho que o mundo já resolveu
    — o Torvin fantasma ainda segurava os `cravos-de-ferro` que o vivo já havia
    entregado ao Obadiah. Trazer de volta seria repetir o bug um nível abaixo.

Uso:
  python3 loreforge-server/sanea_duplicatas.py            # relatório, não altera
  python3 loreforge-server/sanea_duplicatas.py --aplicar  # funde e remove
"""
from __future__ import annotations

import argparse
import collections
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "loreforge-server"))

from motor import io as motor_io  # noqa: E402

W = motor_io.WORLD_DIR
_TS = re.compile(r"^mem-(\d{13})-")


def _mem_ts(nome: str) -> float:
    m = _TS.match(nome)
    return int(m.group(1)) / 1000 if m else 0.0


def _memorias(pasta: Path) -> dict[str, Path]:
    d = pasta / "memories"
    return {p.name: p for p in d.glob("*.md")} if d.is_dir() else {}


def _itens(pasta: Path) -> set[str]:
    return {p.name for p in pasta.iterdir() if p.is_dir() and (p / "item.md").exists()}


def _chave_de_escolha(pasta: Path) -> tuple:
    mems = _memorias(pasta)
    ultima = max((_mem_ts(n) for n in mems), default=0.0)
    try:
        mtime = (pasta / "character.md").stat().st_mtime
    except OSError:
        mtime = 0.0
    return (ultima, len(mems), mtime)


def _nascimento(arquivo: Path) -> str:
    """Data mais ANTIGA em que este caminho aparece no histórico — em qualquer um
    dos repositórios onde o mundo já morou.

    É a evidência que distingue as duas cópias de um ITEM, onde `state.slot` não
    resolve: a pasta que o RUNTIME criou entra no histórico depois, porque só
    aparece quando alguém commita o working tree; a antiga é a editorial, que o
    `checkout` ressuscitou. O slot NÃO serve: em 4 dos 9 casos reais o vivo era a
    cópia largada no CHÃO (o alaúde que Renn deixou na taverna) e o fantasma é que
    estava "na mão".

    Procura no submódulo E no repositório-pai sob o caminho HISTÓRICO (`world/…`,
    de antes da divisão em submódulos, 5f3b142): o submódulo nasceu de um import
    achatado, então sozinho ele data tudo no mesmo dia e não separa nada.
    """
    rel_mundo = arquivo.relative_to(W)
    candidatos = [
        (RAIZ / "loreforge-world" / "tardenia", str(rel_mundo)),
        (RAIZ, f"world/{rel_mundo}"),
        (RAIZ, str(arquivo.relative_to(RAIZ))),
    ]
    datas = []
    for repo, spec in candidatos:
        if not (repo / ".git").exists():
            continue
        out = subprocess.run(
            ["git", "-C", str(repo), "log", "--diff-filter=A", "--format=%ad",
             "--date=short", "--", spec],
            capture_output=True, text=True).stdout.strip().splitlines()
        if out:
            datas.append(out[-1])
    return min(datas) if datas else ""


def _itens_duplicados() -> dict[str, list[Path]]:
    """Itens (não personagens) com o mesmo id em dois lugares."""
    por_id: dict[str, list[Path]] = collections.defaultdict(list)
    for p in W.rglob("item.md"):
        fm, _ = motor_io.read_doc(p)
        ident = fm.get("id")
        if ident:
            por_id[ident].append(p)
    return {i: v for i, v in sorted(por_id.items()) if len(v) > 1}


def _resolve_itens(aplicar: bool) -> int:
    dups = _itens_duplicados()
    if not dups:
        return 0
    print(f"\n{len(dups)} item(ns) com id duplicado\n")
    indecisos = 0
    for ident, arquivos in dups.items():
        datado = sorted(((_nascimento(a), a) for a in arquivos), reverse=True)
        print(f"## {ident}")
        if not datado[0][0] or datado[0][0] == datado[1][0]:
            print("   ⚠ o histórico não separa as cópias — resolva à mão:")
            for _, a in datado:
                print(f"      {a.parent.relative_to(W)}")
            indecisos += 1
            continue
        (dt_fica, fica), *resto = datado
        print(f"   FICA  {fica.parent.relative_to(W)}  (entrou em {dt_fica} — runtime)")
        for dt_sai, sai in resto:
            print(f"   SAI   {sai.parent.relative_to(W)}  (entrou em {dt_sai} — editorial)")
            if aplicar and sai.parent.exists():
                shutil.rmtree(sai.parent)
    return indecisos


def _duplicados() -> dict[str, list[Path]]:
    por_id: dict[str, list[Path]] = collections.defaultdict(list)
    for p in W.rglob("character.md"):
        fm, _ = motor_io.read_doc(p)
        ident = fm.get("id")
        if ident:
            por_id[ident].append(p.parent)
    return {i: v for i, v in sorted(por_id.items()) if len(v) > 1}


def main(aplicar: bool) -> int:
    dups = _duplicados()
    if not dups:
        print("nenhum personagem duplicado no mundo.")
        _resolve_itens(aplicar)
        if not aplicar:
            print("\n(relatório apenas — rode com --aplicar para efetivar)")
        return 0

    print(f"{len(dups)} personagem(ns) com id duplicado em {W}\n")
    total_mem = total_desc = 0
    for ident, pastas in dups.items():
        ranked = sorted(pastas, key=_chave_de_escolha, reverse=True)
        fica, perdedores = ranked[0], ranked[1:]
        mems_fica = _memorias(fica)
        itens_fica = _itens(fica)
        print(f"## {ident}")
        print(f"   FICA  {fica.relative_to(W)}  "
              f"({len(mems_fica)} mem, última "
              f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(_chave_de_escolha(fica)[0]))})")
        for perde in perdedores:
            mems_perde = _memorias(perde)
            novas = {n: p for n, p in mems_perde.items() if n not in mems_fica}
            itens_perdidos = sorted(_itens(perde) - itens_fica)
            print(f"   SAI   {perde.relative_to(W)}  ({len(mems_perde)} mem)")
            print(f"         funde {len(novas)} memória(s) que só existiam aqui")
            if itens_perdidos:
                print(f"         DESCARTA itens (foto velha): {', '.join(itens_perdidos)}")
            total_mem += len(novas)
            total_desc += len(itens_perdidos)
            if aplicar:
                destino = fica / "memories"
                destino.mkdir(exist_ok=True)
                for nome, origem in novas.items():
                    shutil.move(str(origem), str(destino / nome))
                shutil.rmtree(perde)
        print()

    print(f"total: {total_mem} memória(s) fundida(s), {total_desc} item(ns) descartado(s)")
    _resolve_itens(aplicar)
    if not aplicar:
        print("\n(relatório apenas — rode com --aplicar para efetivar)")
    else:
        restantes = _duplicados()
        print(f"\npersonagens duplicados restantes: {len(restantes)}")
        print("→ rode `sanea_mundo.py --aplicar` em seguida: a fusão pode ter "
              "trazido memórias de corpo idêntico.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true",
                    help="efetiva (sem isto, só relata)")
    raise SystemExit(main(ap.parse_args().aplicar))
