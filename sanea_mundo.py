"""Saneamento do save: zera INTENÇÕES e funde MEMÓRIAS idênticas (2026-08-14).

PEDIDO DO MANTENEDOR: *"sanetiza o mundo, pode remover intenções de todos, deixa
que vai ser criadas ao longo dos jogos, se tiver memórias repetidas pode remover."*

POR QUE AS INTENÇÕES SAEM TODAS. O ramo que CRIA intenção esteve morto por uma
semana (item 53.6), então as 24 que existem nasceram tortas ou de refactor: uma com
`status: false` (inválida no validador), uma meta-circular ("registrar um plano de
longo prazo"), uma com o sujeito errado ("que VOCÊ me ajude a vigiar o portão" — a
fala de outro, salva como decisão própria). Com a bifurcação religada e a face
recortada (5/5 na medição), elas voltam a nascer sozinhas e melhores. Zerar é mais
honesto que remendar.

POR QUE AS MEMÓRIAS SÓ SE FUNDEM. Memória é a espinha do jogo — apagar é perder
mundo. Aqui só o EXCEDENTE sai: corpo byte-a-byte idêntico dentro do MESMO
personagem é o mesmo fato gravado N vezes, não N fatos.

O que se preserva na fusão:
  · o arquivo de prazo mais LONGO (renovar nunca encurta — spec 013);
  · a união de `involved` (é o que costura o mundo);
  · o carimbo `vezes`, para o fato dizer que se repetiu.

O TEXTO NÃO É REESCRITO. `_remember_recurring` adensa a prosa ("já insisti muitas
vezes") porque ali o fato é uma PERGUNTA insistida; aqui a mesma frase serviria a
"Vi X acusar Y", onde "insisti" é o verbo errado. Preferir não inventar texto.

De onde veio o excedente: 931 arquivos em 349 grupos, e um único turno responde por
153 deles — a Petrila emitiu 14 `accuse` de uma vez (item 53.2), o que gravou 17 em
quem foi acusada e 17 de TESTEMUNHA em cada um dos 8 presentes.

Uso:  python3 server/sanea_mundo.py [--aplicar]
"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import motor  # noqa: E402


def _dono(path: Path) -> Path | None:
    return next((a for a in path.parents if (a / "character.md").exists()), None)


def main(aplicar: bool, somente_memorias: bool = False) -> int:
    # --- 1) intenções: todas fora ------------------------------------------- #
    # ZERAR INTENÇÃO É RITUAL PONTUAL, NÃO ROTINA. O pedido de 2026-08-14 valia
    # para aquelas 24, que haviam nascido tortas com o ramo de criação morto. Com
    # a bifurcação religada, intenção nova é conteúdo legítimo — e este script
    # passou a ser rodado de novo (a fusão de memórias é útil sempre). Sem este
    # recorte, quem quisesse limpar memória apagaria o compromisso de todo mundo
    # junto, em silêncio.
    ints = [] if somente_memorias else sorted(motor.WORLD_DIR.rglob("intentions/*.md"))
    por = collections.Counter()
    for p in ints:
        d = _dono(p)
        if d:
            por[d.name] += 1
    print(f"INTENÇÕES — {len(ints)} arquivo(s) em {len(por)} personagem(ns)")
    for k, v in por.most_common():
        print(f"   {v:3}  {k}")
    if aplicar:
        for p in ints:
            p.unlink()
        # a pasta vazia fica: é onde as novas vão nascer

    # --- 2) memórias: funde o corpo idêntico do mesmo personagem ------------ #
    grupos: dict[tuple, list] = collections.defaultdict(list)
    total = 0
    for p in motor.WORLD_DIR.rglob("memories/*.md"):
        total += 1
        d = _dono(p)
        if d is None:
            continue
        fm, corpo = motor.read_doc(p)
        grupos[(d.name, corpo.strip())].append((p, fm))

    fundidos = apagados = 0
    for (dono, _corpo), itens in sorted(grupos.items()):
        if len(itens) < 2:
            continue
        # o de prazo mais LONGO fica; renovar nunca encurta uma memória
        itens.sort(key=lambda x: int(x[1].get("timestamp_end") or 0))
        alvo, fm = itens[-1]
        if aplicar:
            fm["vezes"] = sum(int(f.get("vezes") or 1) for _p, f in itens)
            juntos: list[str] = []
            for _p, f in itens:
                for i in (f.get("involved") or []):
                    if i not in juntos:
                        juntos.append(i)
            fm["involved"] = juntos
            _fm0, corpo0 = motor.read_doc(alvo)
            motor.write_doc(alvo, fm, corpo0)
            for p, _f in itens[:-1]:
                p.unlink()
        fundidos += 1
        apagados += len(itens) - 1

    print(f"\nMEMÓRIAS — {total} arquivo(s); {fundidos} grupo(s) idêntico(s), "
          f"{apagados} excedente(s) "
          + ("APAGADOS." if aplicar else "a apagar (dry-run)."))
    if not aplicar:
        print("\nRode com --aplicar para valer.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main("--aplicar" in sys.argv,
                          "--somente-memorias" in sys.argv))
