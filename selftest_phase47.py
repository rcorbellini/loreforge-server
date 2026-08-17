"""Auto-teste da Fase 47 — o registro do turno (spec 044, US5).

(Número de FASE ≠ número de SPEC.)

O que este teste guarda não é o formato do registro — é o INVARIANTE que o torna
seguro de existir: **o registro é write-only para o jogo**.

Subir o racional da Mente ao mundo é útil para analisar uma temporada depois.
Deixar o mundo LER esse racional para arbitrar seria o mundo espiando o foro
íntimo do personagem — e mataria `server-never-owns-character-agency` sem que
ninguém percebesse. O risco nunca foi um ataque: era alguém, num dia de pressa,
"dar uma espiadinha no que ele pensou" para melhorar uma decisão.

Por isso a trava é ESTRUTURAL, no molde do `selftest_phase46` (que afirma que o
MCP não importa `motor`):

  1. o módulo do registro NÃO EXPÕE função de leitura;
  2. NENHUM módulo do caminho de jogo o importa;
  3. o registro não escreve dentro de `world/`;
  4. falhar registrando NÃO derruba o turno.

Sem disco de verdade: o destino vai para uma pasta temporária.

Uso:  python3 server/selftest_phase47.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SERVER_DIR))

FAILS = []


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}"
          + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="registro-")
    os.environ["LOREFORGE_REGISTRO_DIR"] = tmp
    import registro_turno  # noqa: E402  (depois do env: a raiz é lida no import)
    registro_turno.RAIZ = Path(tmp)

    fonte = (SERVER_DIR / "registro_turno.py").read_text(encoding="utf-8")

    # --- 1. nenhuma função de leitura --------------------------------------- #
    # só o que ESTE módulo define — o que ele importou (`Path`, `json`) é
    # ferramenta de dentro, não superfície oferecida a ninguém.
    publicas = [n for n in dir(registro_turno)
                if not n.startswith("_")
                and callable(getattr(registro_turno, n))
                and getattr(getattr(registro_turno, n), "__module__", "")
                    == "registro_turno"]
    leitoras = [n for n in publicas
                if re.search(r"^(ler|carregar|buscar|listar|obter|get|read|load)",
                             n)]
    check("o registro não expõe função de leitura", not leitoras,
          f"achei {leitoras}")
    check("só há funções de ESCRITA na superfície pública",
          set(publicas) <= {"anotar_proposta", "anotar_corpo"},
          f"públicas: {publicas}")

    # --- 2. o caminho de jogo não o importa --------------------------------- #
    # Se `motor`, `arbiter` ou `face` importassem o registro, o dado que subiu
    # para ser ANALISADO poderia voltar para DECIDIR — que é a coisa que este
    # arquivo inteiro existe para impedir.
    for modulo in ("arbiter.py", "face.py"):
        texto = (SERVER_DIR / modulo).read_text(encoding="utf-8")
        check(f"`{modulo}` não importa o registro",
              not re.search(r"^\s*(import registro_turno|from registro_turno)",
                            texto, re.M))
    motor_dir = SERVER_DIR / "motor"
    sujos = [str(p.relative_to(SERVER_DIR)) for p in motor_dir.rglob("*.py")
             if re.search(r"^\s*(import registro_turno|from registro_turno)",
                          p.read_text(encoding="utf-8"), re.M)]
    check("nenhum módulo do Motor importa o registro", not sujos, f"{sujos}")

    # --- 3. escreve fora de `world/` ---------------------------------------- #
    registro_turno.anotar_proposta(
        "fulano-de-tal", "t-1", "take", {"item": "corda"},
        {"acao": "pega a corda"},
        {"aconteceu": ["Fulano pegou a corda."], "viradas": []}, aceito=True)
    arquivos = list(Path(tmp).glob("*.jsonl"))
    check("gravou uma linha", len(arquivos) == 1, f"{arquivos}")
    check("não escreve dentro de world/",
          "world" not in str(registro_turno.RAIZ).split(os.sep))

    linha = json.loads(arquivos[0].read_text(encoding="utf-8").splitlines()[0])
    check("o envelope traz a versão do mundo", bool(linha.get("versao_mundo")))
    check("o envelope traz o turno_id que costura as duas metades",
          linha.get("turno_id") == "t-1")
    check("guarda o desfecho em linguagem de mundo",
          linha.get("aconteceu") == ["Fulano pegou a corda."])

    # --- a RECUSA nunca é silenciosa, nem no registro ----------------------- #
    registro_turno.anotar_proposta(
        "fulano-de-tal", "t-2", "give", {"to": "ninguem"},
        {"acao": "entrega"},
        {"erro": "não há ninguém com esse nome aqui"}, aceito=False)
    linhas = arquivos[0].read_text(encoding="utf-8").splitlines()
    recusa = json.loads(linhas[1])
    check("a recusa é registrada COM o motivo",
          recusa.get("aceito") is False
          and "ninguém" in (recusa.get("recusa") or ""))

    # --- O DEFEITO ACHADO JOGANDO: o registro não pode mentir --------------- #
    # A primeira versão inferia a aceitação de `resultado["ok"]`, chave que o
    # desfecho de SUCESSO não carrega — e gravava `aceito: false` em turnos em
    # que o item tinha acabado de mudar de mão, com `aconteceu` ao lado dizendo o
    # contrário. Registro que mente envenena toda análise futura, em silêncio.
    aceitos = [json.loads(l) for l in
               arquivos[0].read_text(encoding="utf-8").splitlines()]
    coerentes = [d for d in aceitos
                 if d.get("lado") == "mundo"
                 and d.get("aceito") is False and d.get("aconteceu")]
    check("nenhuma linha diz 'recusado' com desfecho ao lado", not coerentes,
          f"{coerentes}")

    # --- o corpo da Mente, e a supressão como DADO -------------------------- #
    registro_turno.anotar_corpo({"personagem": "fulano-de-tal", "turno_id": "t-3",
                                 "corpo_suprimido": True, "corpo": None})
    suprimido = json.loads(
        arquivos[0].read_text(encoding="utf-8").splitlines()[2])
    check("a supressão do corpo vira DADO, não vazio",
          suprimido.get("corpo_suprimido") is True
          and suprimido.get("lado") == "mente")

    # --- id malicioso não escapa da pasta ----------------------------------- #
    registro_turno.anotar_proposta("../../etc/passwd", "t-4", "take", {}, {}, {},
                                   aceito=True)
    fugiu = [p for p in Path(tmp).parent.glob("**/passwd*")
             if p.is_file() and "registro-" not in str(p.parent.name)]
    check("id com travessia de caminho não escapa da pasta", not fugiu, f"{fugiu}")

    # --- 4. falhar registrando não derruba o turno -------------------------- #
    registro_turno.RAIZ = Path("/proc/nao-da-para-escrever-aqui")
    try:
        registro_turno.anotar_proposta("fulano", "t-5", "take", {}, {}, {},
                                       aceito=True)
        caiu = False
    except Exception:
        caiu = True
    check("destino impossível NÃO levanta (o jogo segue)", not caiu)

    print()
    if FAILS:
        print(f"FALHAS ({len(FAILS)}): " + ", ".join(FAILS))
        return 1
    print("Fase 47 ok — o registro existe e o jogo não consegue lê-lo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
