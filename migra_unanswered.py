"""Funde as memórias `unanswered` duplicadas — uma por ASSUNTO (item 53.4).

POR QUE EXISTE. O item 53.4 fez a pergunta repetida RENOVAR uma memória em vez de
criar outra, mas só daqui pra frente. O que já estava no disco continuou: 114
arquivos, dos quais o Irmão Tobias sozinho tinha 38 — e 35 das 40 memórias VIVAS
dele eram a MESMA recusa. Isso não é só ruído: sem intenção e sem urgência
biológica, a memória é a única bússola do tick autônomo, e 35 cópias do mesmo
fracasso a fazem apontar sempre para o buraco. Medido: o contexto dele dobrou
(9.128 → 20.631 tokens) e o turno foi de 68s a 260s, batendo em timeout em 34%
das vezes.

O QUE FAZ. Agrupa por (personagem, texto do corpo) — que é o mesmo par
informante+assunto —, mantém o arquivo MAIS RECENTE do grupo (o prazo mais longo,
para não encurtar nada), carimba `vezes` e adensa o texto como
`_remember_recurring` faria, e apaga os demais.

O QUE NÃO FAZ. Não toca em memória de outro evento, não funde assuntos
diferentes, e não cria nada. `--dry-run` (padrão) só relata.

Uso:  python3 server/migra_unanswered.py [--aplicar]
"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import motor                                              # noqa: E402
from motor.memoria.primitivas import _insistencia          # noqa: E402


def _corpo_base(texto: str) -> str:
    """O texto SEM a cláusula de insistência — para reagrupar uma migração já
    rodada sem que a frase acumule."""
    for n in (2, 3, 6):
        suf = _insistencia(n)
        if suf and texto.endswith(suf):
            return texto[: -len(suf)]
    return texto


def main(aplicar: bool) -> int:
    grupos: dict[tuple, list] = collections.defaultdict(list)
    for path in motor.WORLD_DIR.rglob("memories/*.md"):
        fm, corpo = motor.read_doc(path)
        if fm.get("evento") != "unanswered":
            continue
        dono = next((a for a in path.parents if (a / "character.md").exists()), None)
        if dono is None:
            continue
        grupos[(dono.name, _corpo_base(corpo.strip()))].append((path, fm, corpo))

    fundidos = apagados = 0
    for (dono, base), itens in sorted(grupos.items()):
        if len(itens) < 2:
            continue
        itens.sort(key=lambda x: int(x[1].get("timestamp_start") or 0))
        _p, fm, _c = itens[-1]
        vezes = sum(int(f.get("vezes") or 1) for _p2, f, _c2 in itens)
        print(f"  {dono:24} {len(itens):3} → 1  (vezes={vezes})  {base[:56]}")
        if aplicar:
            fm["vezes"] = vezes
            envolvidos: list[str] = []
            for _p2, f, _c2 in itens:
                for i in (f.get("involved") or []):
                    if i not in envolvidos:
                        envolvidos.append(i)
            fm["involved"] = envolvidos
            corpo = base + _insistencia(vezes)
            fm["summary"] = motor._short_summary(base) + _insistencia(vezes)
            motor.write_doc(itens[-1][0], fm, corpo)
            for p2, _f, _c2 in itens[:-1]:
                p2.unlink()
        fundidos += 1
        apagados += len(itens) - 1

    print(f"\n{fundidos} assunto(s) fundido(s); {apagados} arquivo(s) "
          + ("APAGADOS." if aplicar else "seriam apagados (dry-run)."))
    if not aplicar:
        print("Rode com --aplicar para valer.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main("--aplicar" in sys.argv))
