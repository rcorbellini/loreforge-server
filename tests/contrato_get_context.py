"""O CONTRATO DE `get_context` — boas práticas de API, travadas por teste (spec 066).

POR QUE ESTE ARQUIVO EXISTE, na palavra do mantenedor:

    "ele precisa respeitar padrão de API pra ser intuitivo, ele não deve se preocupar
     com contrato usado com a LLM. pois a LLM tem o conector e cada jogador no futuro
     poderá customizar isso."

O contexto NÃO é o prompt. Ele é a API que um jogador vai ler para escrever o próprio
conector, e por isso tem regras próprias — independentes de qualquer modelo:

    `get_context` devolve o mundo como ESTE personagem pode saber.

Disso saem duas coisas que estes testes protegem: o afeto/vínculo de TERCEIROS nunca
desce (a vista é subjetiva por definição, não para "esconder da LLM"), e a forma do
payload é estável e previsível para quem nunca leu o código.

AS SETE INVARIANTES, e o que cada uma impede:

  1. NOMENCLATURA — uma língua só de identificador, snake_case. **Este é o único teste
     que FALHA de propósito hoje**: ele lista as intrusões que o retrofit da US5 vai
     limpar, e vira o critério objetivo de "pronto" daquela fatia.
  2. OPCIONAL AUSENTE, NUNCA `None` — campo que não se aplica é omitido. É o contrato
     que `bond`/`sentiment` seguem, imposto a todos.
  3. FORMA UNIFORME entre coleções — `bond` significa o mesmo em characters/items/
     objects/location, e todas expõem `id`+`name`.
  4. NENHUM NÚMERO DE MEDIDA INTERNA (Princípio V) — afeto, apego, intensidade, saldo.
     Física declarada (peso, capacidade, tempo) é legítima e está numa lista explícita:
     sem essa distinção o teste seria inútil ou impossível de passar.
  5. NENHUM DETALHE INTERNO — caminho de disco, raiz do mundo, mtime.
  6. SERIALIZÁVEL — sobrevive a json.dumps/loads sem perda.
  7. ESTÁVEL — duas chamadas seguidas, sem mudança no mundo, dão o mesmo resultado.

Uso:  python3 tests/contrato_get_context.py
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent.parent
TAVERNA = "taverna-do-gancho"
_tmp = Path(tempfile.mkdtemp(prefix="loreforge-contrato-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
sys.path.insert(0, str(SERVER_DIR))

import motor
from motor import indice

falhas = []
avisos = []


def check(nome, cond, detalhe=""):
    if cond:
        print(f"[ok  ] {nome}")
    else:
        print(f"[FALHA] {nome}" + (f" — {detalhe}" if detalhe else ""))
        falhas.append(nome)


def esperado_falhar(nome, cond, detalhe=""):
    """Invariante que a US5 ainda não cumpriu. Reporta sem derrubar a suíte — e
    reporta TAMBÉM quando passa, para o retrofit ter um sinal de conclusão."""
    if cond:
        print(f"[ok  ] {nome}  <- o retrofit da US5 fechou este")
    else:
        print(f"[PENDENTE-US5] {nome}" + (f" — {detalhe}" if detalhe else ""))
        avisos.append(nome)


# --------------------------------------------------------------------------- #
# Fixture: um personagem com vínculo para pessoa, item e lugar.
# --------------------------------------------------------------------------- #
def _mk_char(cid, name, bonds=""):
    d = motor.WORLD_DIR / TAVERNA / cid
    d.mkdir(parents=True, exist_ok=True)
    (d / "character.md").write_text(
        f"---\ntype: character\nid: {cid}\nname: {name}\n"
        f"controlled_by: player_local\nweight_kg: 70\n"
        f"attributes:\n  STR: 10\n  DEX: 10\n  CON: 10\n  INT: 10\n  WIS: 10\n  CHA: 10\n"
        f"status:\n  hp: 50\n  hp_max: 50\n  hunger: saciado\n  fatigue: baixo\n"
        f"  action: parado\n  mood: neutro\n  conditions: []\n"
        f"origin: editorial\n{bonds}---\nAlguém.\n", encoding="utf-8")
    indice.invalidar(d / "character.md")
    return d


_mk_char("contrato-ator", "Ator",
         bonds="bonds:\n  - target: contrato-alvo\n    label: irmã\n")
_mk_char("contrato-alvo", "Alvo")
indice.sincronizar()

CTX = motor.get_context("contrato-ator")

# --------------------------------------------------------------------------- #
# Varredura recursiva — devolve (caminho, valor) de cada folha.
# --------------------------------------------------------------------------- #
def folhas(no, caminho=""):
    if isinstance(no, dict):
        for k, v in no.items():
            yield from folhas(v, f"{caminho}.{k}")
    elif isinstance(no, list):
        for i, v in enumerate(no):
            yield from folhas(v, f"{caminho}[{i}]")
    else:
        yield caminho, no


def chaves(no, caminho=""):
    if isinstance(no, dict):
        for k, v in no.items():
            yield k, f"{caminho}.{k}"
            yield from chaves(v, f"{caminho}.{k}")
    elif isinstance(no, list):
        for i, v in enumerate(no):
            yield from chaves(v, f"{caminho}[{i}]")


print("--- 1. NOMENCLATURA: uma língua, snake_case --------------------------")

import re
_SNAKE = re.compile(r"^[a-z][a-z0-9_]*$")
# Os SEIS ATRIBUTOS são acrônimos maiúsculos por convenção de domínio (STR/DEX/CON/
# INT/WIS/CHA), e isso é deliberado: mudá-los para minúsculas ganharia consistência
# tipográfica e perderia a convenção que qualquer jogador de RPG reconhece de imediato.
# Exceção EXPLÍCITA — a primeira versão deste teste os acusou, e o acusado estava certo.
_ATRIBUTOS = {"STR", "DEX", "CON", "INT", "WIS", "CHA"}
_fora_do_padrao = sorted({k for k, _ in chaves(CTX)
                          if not _SNAKE.match(k) and k not in _ATRIBUTOS})
check("1a: toda chave é snake_case (fora os 6 atributos, acrônimos por convenção)",
      not _fora_do_padrao, f"fora: {_fora_do_padrao}")

# As intrusões conhecidas. A lista é EXPLÍCITA de propósito: um teste que tentasse
# adivinhar "isto é português" por heurística daria falso positivo em `id`, `action`,
# `narrative` e em qualquer nome próprio do mundo.
#
# CUIDADO AO RENOMEAR: esta lista contém os nomes ANTIGOS de propósito. Um
# `sed` de retrofit que rode sobre este arquivo a reescreve para os nomes NOVOS e o
# teste passa a se auto-satisfazer — aconteceu na primeira execução do retrofit da US5.
# As strings abaixo são dados históricos, não identificadores: nunca devem ser
# renomeadas junto com o código.
_INTRUSOES_PT = {"conhecid" + "os", "pertence" + "_a", "fisic" + "o",
                 "maos" + "_livres", "maos" + "_totais", "pega" + "_slot",
                 "maos" + "_ocupadas_por", "carga" + "_livre_kg"}
_presentes = sorted({k for k, _ in chaves(CTX)} & _INTRUSOES_PT)
esperado_falhar("1b: nenhuma chave em português (o retrofit da US5)",
                not _presentes, f"ainda em PT: {_presentes}")

print("\n--- 2. OPCIONAL SEMPRE PRESENTE, `null` quando vazio -----------------")

# A CONVENÇÃO ÚNICA (spec 067). A versão anterior deste teste cobrava o OPOSTO — "campo
# que não se aplica é omitido" — e o payload real convivia com as DUAS: `bond` sumia,
# `slot` descia como `null`. Duas convenções no mesmo objeto obrigam quem escreve um
# conector a checar as duas formas para a mesma pergunta.
#
# `null` sempre presente vence porque distingue "consultei e não há" de "nem consultei",
# e porque `Object.keys()` deixa de variar com o conteúdo: o leitor vê a forma inteira do
# contrato em qualquer resposta. O payload cresce, e isso é decisão registrada do
# mantenedor — "não tem problema inflar a resposta da API, desde que seja algo útil da
# forma que vier".
_OPCIONAIS = ("prose", "relation", "sentiment", "physics")
_faltando = []
for col in ("characters", "items", "objects"):
    for e in (CTX["scene"].get(col) or []):
        for campo in _OPCIONAIS:
            if campo not in e:
                _faltando.append(f"scene.{col}[{e.get('id')}].{campo}")
check("2a: todo campo opcional está PRESENTE em toda entidade (null quando vazio)",
      not _faltando, f"faltando: {_faltando[:6]}")

check("2b: `sentiment` está presente em 100% das entidades da cena (SC-005)",
      all("sentiment" in e
          for col in ("characters", "items", "objects")
          for e in (CTX["scene"].get(col) or [])))

check("2c: `transit` está presente em `self`, mesmo parado (null)",
      "transit" in CTX["self"])

print("\n--- 3. FORMA UNIFORME, EM QUALQUER PROFUNDIDADE --------------------")

# A DÍVIDA QUE DEIXOU TRÊS DEFEITOS PASSAREM. A primeira versão deste bloco só olhava
# as coleções de TOPO (`characters`, `items`, `objects`) e só checava `id`+`name`.
# Passaram por baixo dela, um de cada vez, e cada um só apareceu quando alguém leu o
# payload de verdade:
#
#   - a física SOLTA em `carrying`/`inventory` enquanto `scene.items` a trazia agrupada
#   - o lugar-PAI em `belongs_to` sem `relation`/`sentiment`
#   - itens em `carrying`/`contains` sem prosa: o mesmo pé de cabra descrito no chão e
#     mudo na mão de alguém
#
# Agora a varredura é RECURSIVA e a regra é uma só.
_NUCLEO = ("prose", "relation", "sentiment")


def entidades(no, caminho="$"):
    """Todo nó com `id` E `name` é uma ENTIDADE, esteja onde estiver."""
    if isinstance(no, dict):
        if "id" in no and "name" in no:
            yield caminho, no
        for k, v in no.items():
            yield from entidades(v, f"{caminho}.{k}")
    elif isinstance(no, list):
        for v in no:
            yield from entidades(v, f"{caminho}[]")


# `known_elsewhere` é REFERÊNCIA, não entidade: são nomes que o personagem sabe
# pronunciar sobre quem NÃO está na cena. Dar-lhe `prose` seria vazamento — ele não
# está vendo ninguém. A exceção é EXPLÍCITA para não virar buraco por descuido.
_REFERENCIAS = ("$.self.known_elsewhere[]",)

_incompletas = []
for cam, e in entidades(CTX.get("scene") or {}, "$.scene"):
    faltando = [c for c in _NUCLEO if c not in e]
    if faltando:
        _incompletas.append(f"{cam}[{e.get('id')}] sem {faltando}")
check("3a: toda entidade da CENA tem o núcleo, em qualquer profundidade",
      not _incompletas, f"{_incompletas[:4]}")

_refs = [cam for cam, _ in entidades(CTX.get("self") or {}, "$.self")
         if cam not in _REFERENCIAS and cam != "$.self"]
_self_incompletas = []
for cam, e in entidades(CTX.get("self") or {}, "$.self"):
    if cam in _REFERENCIAS or cam == "$.self":
        continue
    faltando = [c for c in _NUCLEO if c not in e]
    if faltando:
        _self_incompletas.append(f"{cam}[{e.get('id')}] sem {faltando}")
check("3b: e as entidades dentro de `self` (inventário) também",
      not _self_incompletas, f"{_self_incompletas[:4]}")

# `bond`/`relation` tem de significar a MESMA coisa em toda profundidade
_rel = [(c, v) for c, v in folhas(CTX) if c.rsplit(".", 1)[-1] == "relation"]
check("3c: `relation` é sempre string ou None, nunca outro tipo",
      all(v is None or (isinstance(v, str) and v.strip()) for _, v in _rel),
      f"{[x for x in _rel if x[1] is not None and not isinstance(x[1], str)][:3]}")
_sent = [(c, v) for c, v in folhas(CTX) if c.rsplit(".", 1)[-1] == "sentiment"]
check("3d: `sentiment` é sempre string ou None",
      all(v is None or isinstance(v, str) for _, v in _sent))

# a física, onde existe, é sempre um BLOCO — nunca campos soltos na raiz da entidade
_solta = []
for cam, e in entidades(CTX, "$"):
    for campo in ("size", "weight_kg", "worn_at", "slot", "free_hands", "grasp_slot"):
        if campo in e:
            _solta.append(f"{cam}[{e.get('id')}].{campo}")
check("3e: nenhuma entidade traz física SOLTA — ela mora em `physics`",
      not _solta, f"{_solta[:4]}")

print("\n--- 4. NENHUM NÚMERO DE MEDIDA INTERNA (Princípio V) -----------------")

# A FÍSICA DECLARADA é legítima e desce de propósito: peso, capacidade, tempo. Sem esta
# lista o teste seria inútil (nunca falharia) ou impossível (falharia sempre).
_FISICA_OK = {"weight_kg", "size", "max_size", "max_items", "itens", "free_hands",
              "total_hands", "free_load_kg", "hp", "hp_max", "fatigue", "fatigue_max",
              "travel_time_base", "value", "seq", "timestamp_start", "timestamp_end",
              "criado_em", "ttl_seconds", "turno", "hunger_ts", "hunger_note",
              "thirst_ts", "thirst_note", "descansando_desde", "free_load_kg",
              "free_hands", "total_hands",
              # os SEIS ATRIBUTOS — identidade do corpo, não medida derivada
              "STR", "DEX", "CON", "INT", "WIS", "CHA",
              # os SLOTS DO CORPO (spec 019): capacidade por slot, física declarada.
              # O vocabulário é ABERTO por desenho (a boca do cão, a garupa do cavalo),
              # então esta lista cobre o corpo humano padrão do mundo de teste e vai
              # crescer com corpos novos — o que é o comportamento certo: um slot novo
              # aparece aqui e alguém confere que é física, não vazamento.
              "cabeca", "rosto", "pescoco", "torso", "costas", "cintura", "bracos",
              "mao", "dedo", "pernas", "pes", "capacidade", "carry_capacity_kg",
              "push_capacity_kg", "carried_weight_kg",
              # DECLARADOS PELO AUTOR do object, em `interactions` (spec 002): a
              # dificuldade e o nível que a PRÓPRIA entidade anuncia. Não é medida
              # derivada de crença vazando — é a regra que o objeto carrega escrita.
              "dc", "min_level",
              # itens dentro de um contêiner aberto — contagem visível (spec 005)
              "count"}
# O que NUNCA pode ser número: medida de crença. O número morre no server.
_PROIBIDO_NUMERO = {"sentiment", "bond", "afeto", "apego", "saldo", "familiaridade",
                    "intensity", "salience", "recency", "disposicao", "nota",
                    "certeza", "proficiencia"}
_vazou = [(c, v) for c, v in folhas(CTX)
          if isinstance(v, (int, float)) and not isinstance(v, bool)
          and c.rsplit(".", 1)[-1] in _PROIBIDO_NUMERO]
check("4a: nenhuma medida de CRENÇA sai como número (afeto, apego, intensidade)",
      not _vazou, f"vazou: {_vazou}")

_desconhecidos = sorted({c.rsplit(".", 1)[-1] for c, v in folhas(CTX)
                         if isinstance(v, (int, float)) and not isinstance(v, bool)
                         and c.rsplit(".", 1)[-1] not in _FISICA_OK})
check("4b: todo número no payload é física declarada e conhecida",
      not _desconhecidos,
      f"números não catalogados (física nova? ou vazamento?): {_desconhecidos}")

print("\n--- 5. NENHUM DETALHE INTERNO ----------------------------------------")

_raiz = str(motor.WORLD_DIR)
_caminhos = [(c, v) for c, v in folhas(CTX)
             if isinstance(v, str) and (_raiz in v or v.startswith("/")
                                        or "\\" in v or v.endswith(".md"))]
check("5a: nenhum caminho de disco atravessa o payload",
      not _caminhos, f"{_caminhos[:5]}")
# `body` NÃO entra nesta lista: é o mapa de slots do corpo (spec 019), dado de mundo,
# não campo de implementação. A primeira versão deste teste o acusou por casar com a
# palavra, e o acusado estava certo.
_internos = sorted({k for k, _ in chaves(CTX)
                    if k in ("mtime_ns", "arquivo", "caminho", "folder", "path",
                             "_estado", "fm", "world_dir", "raiz")})
check("5b: nenhum campo de implementação (mtime, arquivo, caminho) desce",
      not _internos, f"{_internos}")

print("\n--- 6 e 7. SERIALIZÁVEL e ESTÁVEL ------------------------------------")

try:
    _txt = json.dumps(CTX, ensure_ascii=False)
    _volta = json.loads(_txt)
    check("6: o payload sobrevive a json.dumps/loads sem perda", _volta == CTX)
except (TypeError, ValueError) as e:
    check("6: o payload sobrevive a json.dumps/loads sem perda", False, str(e))

_a = motor.get_context("contrato-ator")
_b = motor.get_context("contrato-ator")
# `memories` carrega recência/saliência, que são função do relógio — comparar o payload
# inteiro daria falso negativo por motivo legítimo. A estabilidade que interessa é a da
# ESTRUTURA da cena.
for campo in ("place", "characters", "items", "objects", "exits"):
    check(f"7: scene.'{campo}' é idêntico em duas chamadas seguidas",
          _a["scene"].get(campo) == _b["scene"].get(campo))
check("7: self.transit é idêntico em duas chamadas seguidas",
      _a["self"].get("transit") == _b["self"].get("transit"))

print()
shutil.rmtree(_tmp, ignore_errors=True)
if avisos:
    print(f"{len(avisos)} PENDENTE(S) da US5 (retrofit): " + ", ".join(avisos))
if falhas:
    print(f"{len(falhas)} FALHA(S): " + ", ".join(falhas))
    sys.exit(1)
print("contrato de get_context: todas as invariantes exigíveis passaram.")
