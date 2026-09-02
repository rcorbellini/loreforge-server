"""Fase 62 (spec 063) — A GUARDA DA VARREDURA.

No molde do `selftest_phase38.py`, que já lê o fonte e reprova `os.replace` fora de
`io.py`. Aqui a regra é a FR-007: depois que o índice existe, ninguém volta a responder
por varredura a pergunta que ele responde por chave.

O QUE ESTA FASE REPROVA, e por quê a régua é essa:

  - **`WORLD_DIR.rglob(...)` fora de `motor/io.py`** — a varredura MUNDIAL. É o defeito
    que a spec 063 veio consertar: 855 926 leituras de documento numa única montagem de
    face, porque cada pergunta por id repassava o mundo inteiro. Dentro de `io.py` ela
    é legítima e necessária: é o caminho SEM ÍNDICE, que a FR-010 exige manter vivo.

  - **`rglob(...)` de subárvore** só na lista de exceções abaixo, e cada entrada tem de
    dizer por quê no próprio ponto.

O QUE ELA NÃO REPROVA, e isso é decisão consciente:

  - **`iterdir()` numa pasta** — é travessia de CONTENÇÃO local, uma syscall sobre os
    filhos diretos de um nó. Medida na face mais cara do mundo: 1 817 chamadas somando
    **0,03 s**. Não é o defeito que a FR-007 nomeia (varredura mundial), e trocá-la por
    `indice.filhos` seria risco sem ganho. Se um dia ela aparecer num perfil, migra-se —
    a peça já está pronta.
"""
import ast
import sys
from pathlib import Path

MOTOR = Path(__file__).resolve().parent / "motor"

falhas = []


def check(nome, cond, detalhe=""):
    if cond:
        print(f"[ok  ] {nome}")
    else:
        print(f"[FALHA] {nome}" + (f" — {detalhe}" if detalhe else ""))
        falhas.append(nome)


# ---------------------------------------------------------------------------
# EXCEÇÕES — nasce com o que a spec 063 deixou de propósito, e cada uma diz por quê.
# Acrescentar entrada aqui é decisão de desenho: exige a justificativa no ponto do
# código E nesta lista. Sem isso a lista vira depósito, que é como a varredura volta.
# ---------------------------------------------------------------------------
EXCECOES_RGLOB = {
    # A FÍSICA anda a subárvore de um item para somar peso e vagas. É contenção local
    # (o que está DENTRO desta mochila), não busca no mundo, e o índice já a responderia
    # por `subarvore` — mas a migração muda a ordem de visita, e peso/vagas dependem
    # dela em casos de encaixe. Fica para uma spec própria, com medição.
    "fisica/primitivas.py",
    # `prose_of` resolve a pasta pelo índice e depois procura o arquivo de definição
    # DENTRO dela — subárvore de uma entidade só.
    "percepcao/consultas.py",
    # O validador roda no BOOT, antes de o índice existir: é ele quem reprova o mundo
    # duplicado (`duplicate_ids`), e essa recusa não pode depender da peça que está
    # sendo validada. Ver `io.arquivos_no_mundo`, que devolve padrão glob ao disco.
    "validador.py",
    # `_route_items` anda a subárvore do ator para achar item de pré-requisito.
    "rotas/primitivas.py",
}

print("--- Bloco A: a varredura MUNDIAL não voltou (FR-007) -------------------")

for arquivo in sorted(MOTOR.rglob("*.py")):
    rel = arquivo.relative_to(MOTOR).as_posix()
    if rel in ("indice.py", "io.py"):
        continue
    src = arquivo.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=rel)
    mundiais = []
    subarvores = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "rglob":
            continue
        alvo = node.func.value
        if isinstance(alvo, ast.Name) and alvo.id == "WORLD_DIR":
            mundiais.append(node.lineno)
        else:
            subarvores.append(node.lineno)
    check(f"A1 {rel}: sem varredura mundial (WORLD_DIR.rglob)",
          not mundiais, f"linhas {mundiais} — use motor.io.arquivos_no_mundo/arquivo_por_id")
    if subarvores:
        check(f"A2 {rel}: rglob de subárvore está na lista de exceções",
              rel in EXCECOES_RGLOB,
              f"linhas {subarvores} — migre para o índice ou justifique em EXCECOES_RGLOB")

print("\n--- Bloco B: o índice é nível 0 (não importa outro módulo do Motor) ----")

INDICE = MOTOR / "indice.py"
tree = ast.parse(INDICE.read_text(encoding="utf-8"), filename="indice.py")
proibidos = []
for node in ast.walk(tree):
    if isinstance(node, ast.ImportFrom) and node.level and node.level > 0:
        if node.module not in (None, "frontmatter", "validator"):
            proibidos.append(node.module)
    if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
        if node.module.startswith("motor"):
            proibidos.append(node.module)
check("B1: indice.py não importa nenhum outro módulo do Motor",
      not proibidos, f"importa {proibidos} — quebraria o DAG do pacote (spec 021)")

print("\n--- Bloco C: nenhuma relação DERIVADA é gravada no mundo (FR-003/SC-006) ---")

# O índice não pode ter função que ESCREVA, e nenhum módulo pode gravar um campo de
# relação derivada. Apego/afeto/reputação são função do tempo: valor gravado nasce
# errado, e seria a segunda verdade que o Invariante 10/17 proíbe.
src_indice = INDICE.read_text(encoding="utf-8")

# Por AST, não por casamento de texto: a primeira versão desta checagem lia a própria
# docstring do módulo e reprovava sozinha. Regra do projeto — auditoria de fonte olha a
# ÁRVORE, que é o que o `selftest_phase38` já faz para as dependências entre módulos.
# `remove` e `replace` ficam de FORA da lista crua: são métodos de list e de str, e o
# índice usa os dois (`lista.remove(...)`). O que se procura é escrita em DISCO —
# ou um nome que só Path tem, ou uma chamada qualificada por `os`/`shutil`.
SO_DE_PATH = {"write_text", "unlink", "mkdir", "touch", "rmdir", "write_bytes"}
QUALIFICADAS = {("os", "replace"), ("os", "remove"), ("os", "rename"),
                ("shutil", "rmtree"), ("shutil", "move"), ("shutil", "copytree")}
escritas_no_indice = []
for n_ in ast.walk(tree):
    if not (isinstance(n_, ast.Call) and isinstance(n_.func, ast.Attribute)):
        continue
    if n_.func.attr in SO_DE_PATH:
        escritas_no_indice.append(f"{n_.func.attr} (linha {n_.lineno})")
    elif (isinstance(n_.func.value, ast.Name)
          and (n_.func.value.id, n_.func.attr) in QUALIFICADAS):
        escritas_no_indice.append(f"{n_.func.value.id}.{n_.func.attr} (linha {n_.lineno})")
check("C1: indice.py não escreve em disco",
      not escritas_no_indice,
      f"chama {escritas_no_indice} — o índice é derivado; quem escreve é io.py, "
      "e é ele que NOTIFICA o índice")

# Relação derivada gravada seria a SEGUNDA VERDADE do Invariante 10/17: apego e afeto
# são função do tempo, e um valor gravado nasce errado. A checagem procura ATRIBUIÇÃO
# a uma chave de frontmatter, não a menção do nome — `afeto` e `familiaridade` são
# chaves legítimas do CONTEXTO que desce à Mente, e a primeira versão reprovava isso.
CAMPOS_PROIBIDOS = {"apego", "afeto", "reputacao", "relacoes", "familiaridade",
                    "crê_dono", "cre_dono"}
achados = []
for arquivo in sorted(MOTOR.rglob("*.py")):
    arv = ast.parse(arquivo.read_text(encoding="utf-8"), filename=arquivo.name)
    for node in ast.walk(arv):
        if not isinstance(node, ast.Assign):
            continue
        for alvo in node.targets:
            if (isinstance(alvo, ast.Subscript)
                    and isinstance(alvo.value, ast.Name)
                    and "fm" in alvo.value.id
                    and isinstance(alvo.slice, ast.Constant)
                    and alvo.slice.value in CAMPOS_PROIBIDOS):
                achados.append((arquivo.name, alvo.slice.value, node.lineno))
check("C2: nenhum módulo grava campo de relação derivada no frontmatter",
      not achados, f"{achados} — relação derivada se CALCULA, nunca se guarda")

print("\n--- Bloco D: as portas de escrita do índice estão ligadas (FR-004) -----")

src_io = (MOTOR / "io.py").read_text(encoding="utf-8")
tree_io = ast.parse(src_io, filename="io.py")
corpo = {n.name: ast.get_source_segment(src_io, n)
         for n in ast.walk(tree_io) if isinstance(n, ast.FunctionDef)}
check("D1: write_doc notifica o índice", "indice.invalidar(" in (corpo.get("write_doc") or ""),
      "sem isto a op 2 de um turno não veria a escrita da op 1 (item 63 §3.4)")
check("D2: move_entity notifica o índice", "indice.mover(" in (corpo.get("move_entity") or ""),
      "mover pasta muda a contenção da subárvore inteira")
check("D3: remove_entity notifica o índice", "indice.remover(" in (corpo.get("remove_entity") or ""))
check("D4: rewrite_description grava por write_doc (herda a porta)",
      "write_doc(" in (corpo.get("rewrite_description") or ""))
check("D5: create_entity grava por write_doc (herda a porta)",
      "write_doc(" in (corpo.get("create_entity") or ""))

print("\n--- Bloco E: o modo sem índice continua existindo (FR-010) -------------")

check("E1: indice.ativo() lê LOREFORGE_SEM_INDICE",
      "LOREFORGE_SEM_INDICE" in src_indice,
      "é a alternativa 'apenas .md' que o Princípio I exige manter testada")
check("E2: io tem o caminho de disco atrás de indice_pronto()",
      "def indice_pronto" in src_io and src_io.count("WORLD_DIR.rglob") >= 3,
      "sem o fallback, apagar o índice mudaria o comportamento, não só a velocidade")

print()
if falhas:
    print(f"{len(falhas)} FALHA(S): " + ", ".join(falhas))
    sys.exit(1)
print("todos os checks da Fase 62 (spec 063) passaram.")
