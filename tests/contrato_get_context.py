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
_INTRUSOES_PT = {"conhecidos", "pertence_a", "fisico", "maos_livres", "maos_totais",
                 "pega_slot", "maos_ocupadas_por", "carga_livre_kg"}
_presentes = sorted({k for k, _ in chaves(CTX)} & _INTRUSOES_PT)
esperado_falhar("1b: nenhuma chave em português (o retrofit da US5)",
                not _presentes, f"ainda em PT: {_presentes}")

print("\n--- 2. OPCIONAL AUSENTE, NUNCA None ----------------------------------")

_nulos = sorted({c.rsplit(".", 1)[-1] for c, v in folhas(CTX) if v is None})
# O payload MISTURA DUAS CONVENÇÕES hoje, e é isso que o teste mede:
#   - `bond`/`sentiment`/`vinculo_com_o_local` (spec 066): OMITIDOS quando não se aplicam
#   - `slot`/`veste_em`/`description`/`action`... (anteriores): descem como `null`
#
# As duas são defensáveis isoladamente ("null explícito" é estilo legítimo de API); o
# que não é defensável é MISTURAR, porque quem escreve um conector precisa checar as
# duas formas. Uniformizar é mudança de contrato do tamanho da US5, e NÃO foi feita
# aqui: seria expandir uma spec de vínculo para reescrever a física de item.
#
# Por isso a lista abaixo é EXPLÍCITA e o check é PENDENTE, não falha. Se ela crescer,
# alguém acrescentou mais um `null` num payload que já devia estar caminhando para o
# outro estilo — e o teste avisa.
_NULOS_LEGADO = {"slot", "veste_em", "sono", "description", "interactions", "contem",
                 "em_trabalho", "action", "mood", "value", "narrative", "pertence_a",
                 "wearable", "container", "trabalho", "destination_name",
                 "destination_id", "prerequisites", "carrying", "conditions"}
_nulos_novos = sorted(set(_nulos) - _NULOS_LEGADO)
check("2a: nenhuma chave NOVA vale None (campo que não se aplica é omitido)",
      not _nulos_novos, f"nulos fora do legado conhecido: {_nulos_novos}")
esperado_falhar("2c: payload com UMA convenção só de opcional (hoje mistura null e ausente)",
                not (set(_nulos) & _NULOS_LEGADO),
                f"ainda descem como null: {sorted(set(_nulos) & _NULOS_LEGADO)}")
check("2b: `bond` e `sentiment` NUNCA aparecem como None",
      not [c for c, v in folhas(CTX)
           if c.rsplit(".", 1)[-1] in ("bond", "sentiment") and v is None])

print("\n--- 3. FORMA UNIFORME entre coleções ---------------------------------")

for col in ("characters_present", "items_present", "objects_present"):
    itens = CTX.get(col) or []
    check(f"3a: '{col}' — toda entrada expõe id e name",
          all("id" in e and "name" in e for e in itens),
          f"faltando em {[e for e in itens if 'id' not in e or 'name' not in e]}")

# `bond` tem de significar a MESMA coisa em toda coleção: string, nunca outro tipo.
_bonds = [(c, v) for c, v in folhas(CTX) if c.rsplit(".", 1)[-1] == "bond"]
check("3b: 'bond' é sempre string, em qualquer coleção",
      all(isinstance(v, str) and v.strip() for _, v in _bonds),
      f"{_bonds}")
check("3c: 'bond' aparece na entidade, nunca num bloco à parte",
      not any(k == "bonds" or k == "vinculos" for k, _ in chaves(CTX)))

print("\n--- 4. NENHUM NÚMERO DE MEDIDA INTERNA (Princípio V) -----------------")

# A FÍSICA DECLARADA é legítima e desce de propósito: peso, capacidade, tempo. Sem esta
# lista o teste seria inútil (nunca falharia) ou impossível (falharia sempre).
_FISICA_OK = {"weight_kg", "size", "max_size", "max_items", "itens", "maos_livres",
              "maos_totais", "carga_livre_kg", "hp", "hp_max", "fatigue", "fatigue_max",
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
              "mao", "dedo", "pernas", "pes", "capacidade", "capacidade_carga_kg",
              "capacidade_empurrar_kg", "peso_carregado_kg",
              # DECLARADOS PELO AUTOR do object, em `interactions` (spec 002): a
              # dificuldade e o nível que a PRÓPRIA entidade anuncia. Não é medida
              # derivada de crença vazando — é a regra que o objeto carrega escrita.
              "dc", "min_level"}
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
for campo in ("location", "characters_present", "items_present", "objects_present",
              "routes", "in_transit"):
    check(f"7: '{campo}' é idêntico em duas chamadas seguidas",
          _a.get(campo) == _b.get(campo))

print()
shutil.rmtree(_tmp, ignore_errors=True)
if avisos:
    print(f"{len(avisos)} PENDENTE(S) da US5 (retrofit): " + ", ".join(avisos))
if falhas:
    print(f"{len(falhas)} FALHA(S): " + ", ".join(falhas))
    sys.exit(1)
print("contrato de get_context: todas as invariantes exigíveis passaram.")
