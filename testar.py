#!/usr/bin/env python3
"""A SUÍTE INTEIRA, num alvo só — `selftest.py` mais as 70 fases.

POR QUE EXISTE. `selftest.py` NÃO roda as fases: ele é um arquivo entre setenta e
um, e quem digitasse `python3 selftest.py` via "todos os checks passaram" com cinco
checagens quebradas noutros arquivos. Aconteceu em 17/09 — três defeitos meus ficaram
escondidos por dois dias de trabalho, e um deles (a memória plantada no fixture
IMUTÁVEL) vinha sujando o mundo de teste a cada execução.

DUAS COISAS QUE ELE FAZ E UM `grep -c FALHA` NÃO FAZ:

  1. **CRASH NÃO É ZERO FALHAS.** Uma fase que estoura no meio não imprime `[FALHA]`
     nenhum, e `grep -c` devolve `0` — o número mais tranquilizador possível para o
     caso mais grave. Foi assim que a fase 35 passou por verde enquanto explodia num
     `NameError`. Aqui, sair com código != 0 conta como falha, sempre, e o traceback
     aparece.

  2. **O FIXTURE TEM DE VOLTAR LIMPO.** O `selftest.py` aponta `LOREFORGE_WORLD` para
     `tests/world`, que o cabeçalho dele chama de imutável — e nada verificava isso.
     No fim, este runner compara o `git status` daquele diretório e reprova se alguma
     fase deixou arquivo para trás.

Uso:
    python3 loreforge-server/testar.py            # tudo, em paralelo
    python3 loreforge-server/testar.py 35 42      # só as fases 35 e 42
    python3 loreforge-server/testar.py -v         # mostra a saída de quem falhou
"""
from __future__ import annotations

import concurrent.futures
import os
import re
import subprocess
import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent


def alvos(argv: list[str]) -> list[Path]:
    fases = sorted(AQUI.glob("selftest_phase*.py"),
                   key=lambda p: int(re.sub(r"\D", "", p.stem) or 0))
    pedidos = [a for a in argv if a.isdigit()]
    if pedidos:
        quero = {int(p) for p in pedidos}
        return [f for f in fases if int(re.sub(r"\D", "", f.stem) or 0) in quero]
    return [AQUI / "selftest.py"] + fases


def rodar(arquivo: Path) -> tuple[Path, int, str, float]:
    t0 = time.time()
    try:
        r = subprocess.run([sys.executable, arquivo.name], cwd=AQUI,
                           capture_output=True, text=True, timeout=900)
        saida = (r.stdout or "") + (r.stderr or "")
        falhas = saida.count("[FALHA]")
        # O CRASH CONTA COMO FALHA, mesmo sem `[FALHA]` na saída — ver o cabeçalho.
        if r.returncode != 0 and falhas == 0:
            falhas = 1
            saida += f"\n>>> saiu com código {r.returncode} sem imprimir falha alguma"
    except subprocess.TimeoutExpired:
        return arquivo, 1, ">>> ESTOUROU O PRAZO de 900s", time.time() - t0
    return arquivo, falhas, saida, time.time() - t0


def fixture_sujo() -> list[str]:
    """O que alguma fase deixou escrito no mundo de teste. Vazio = limpo."""
    try:
        r = subprocess.run(["git", "status", "--porcelain", "tests/world"],
                           cwd=AQUI, capture_output=True, text=True, timeout=60)
    except Exception:
        return []
    return [l for l in (r.stdout or "").splitlines() if l.strip()]


def main(argv: list[str]) -> int:
    verboso = "-v" in argv
    lista = alvos(argv)
    antes = fixture_sujo()
    print(f"rodando {len(lista)} arquivo(s)…\n")
    t0 = time.time()
    total = 0
    quebrados: list[tuple[Path, int, str]] = []
    # Em paralelo porque em série isto leva minutos, e suíte que ninguém roda não
    # protege nada. Cada arquivo monta o próprio mundo temporário, então não brigam.
    with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as ex:
        for arquivo, falhas, saida, seg in ex.map(rodar, lista):
            total += falhas
            marca = "ok  " if not falhas else "FALHA"
            if falhas:
                quebrados.append((arquivo, falhas, saida))
            print(f"[{marca}] {arquivo.name:28} {seg:5.1f}s"
                  + (f"   {falhas} falha(s)" if falhas else ""))

    if verboso:
        for arquivo, _f, saida in quebrados:
            print(f"\n{'=' * 74}\n{arquivo.name}\n{'=' * 74}")
            for linha in saida.splitlines():
                if "[FALHA]" in linha or ">>>" in linha or "Error" in linha:
                    print("   " + linha)

    depois = fixture_sujo()
    sujou = [l for l in depois if l not in antes]
    print(f"\n{'-' * 74}")
    print(f"{len(lista)} arquivo(s), {total} falha(s), {time.time() - t0:.0f}s")
    if sujou:
        print(f"\n!! O FIXTURE FICOU SUJO — alguma fase escreveu em tests/world:")
        for l in sujou[:8]:
            print("   " + l)
        print("   O `selftest.py` chama aquele mundo de IMUTÁVEL. Quem precisa plantar")
        print("   copia para um temporário, como as fases fazem.")
        total += 1
    if not total:
        print("tudo verde.")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
