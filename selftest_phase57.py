"""Auto-teste da Fase 57 — Craft genérico (spec 057, US1+US2+US3).

Sem modelo/LLM ligado — exercita o Motor direto (`motor.apply_resolution`) para o
comportamento DETERMINÍSTICO do executor, e `arbiter.build_ctx`/`execute` (com `ask`
forçado) para o comportamento da GUARDA (gate `is_busy`, veredito único, retomada
zero-LLM). Cobre:

  - US1: craft SÍNCRONO (duração baixa) materializa no mesmo ato, sem bloco
    `trabalho` nenhum; nota 0 recusa sem consumir nada e sem rolar; nota 10 nunca
    sai em banda 'falha', mesmo com o pior d20 possível
  - US2: craft ASSÍNCRONO (duração alta) nasce peça em processo no relógio de
    ESFORÇO; retomar credita tempo com CLAMP e não chama o Árbitro; conclusão
    materializa os campos decididos na abertura
  - US3: testemunha na ABERTURA e na CONCLUSÃO forma DUAS memórias (não uma por
    retomada intermediária); `dono()` aponta o autor; sem testemunha nenhuma, só o
    autor reconhece a posse
  - US4: retrofit dos 6 ofícios legados — forja (ESFORÇO, Mecanismo A, domínio
    POR-INSTÂNCIA ferraria/armaria); cozinha/botica (PRAZO, abertura por Mecanismo
    A + conclusão por Mecanismo B, `trabalho.resolver_vencidas`, testemunhas
    DIFERENTES em cada fase); forage/esquartejar (síncrono, ato único); fogo
    (síncrono, testemunha pública mas NUNCA confere posse)
  - US5: item nasce solto OU com o personagem por `posicao`; object sempre fixo;
    location sempre subpasta nova, sem `route`; item "com_personagem" assíncrono só
    migra pro autor na conclusão

ACHADO empírico (vale registrar): `motor.apply_resolution` (usado em todos os
testes abaixo) JÁ dispara o leque de testemunha — `apply_op`/`_spread` publicam
`Fato`s e `react_witness` reage a eles, sem precisar do caminho `ctx.execute`/
`arbiter`. O comentário da seção US3 que dizia o contrário (herdado da v1 deste
arquivo) estava errado; mantido ali só como nota histórica.

Uso:  python3 selftest_phase57.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test57-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
os.environ["LOREFORGE_LOG"] = "0"
sys.path.insert(0, str(SERVER_DIR))
import motor  # noqa: E402
import arbiter  # noqa: E402
import validator  # noqa: E402

FAILS = []
TAVERNA = "taverna-do-gancho"


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _mk_char(cid: str, name: str, intel: int = 10, conditions=None, hp=20):
    d = motor.WORLD_DIR / TAVERNA / cid
    d.mkdir(parents=True, exist_ok=True)
    cond_yaml = str(list(conditions or []))
    (d / "character.md").write_text(
        f"---\ntype: character\nid: {cid}\nname: {name}\n"
        f"controlled_by: player_local\nweight_kg: 70\n"
        f"attributes:\n  STR: 10\n  DEX: 10\n  CON: 10\n  INT: {intel}\n  WIS: 10\n  CHA: 10\n"
        f"skills: {{}}\n"
        f"status:\n  hp: {hp}\n  hp_max: 20\n  hunger: sem fome\n  fatigue: 0\n"
        f"  action: parado\n  mood: neutro\n  conditions: {cond_yaml}\n"
        f"origin: editorial\n---\nUm presente qualquer.\n", encoding="utf-8")
    return d


def _mk_item(parent_folder: Path, item_id: str, name: str, descricao: str,
            weight_kg: float = 0.2):
    d = parent_folder / item_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "item.md").write_text(
        f"---\ntype: item\nid: {item_id}\nname: {name}\nsize: P\nweight_kg: {weight_kg}\n"
        f"origin: editorial\n---\n{descricao}\n", encoding="utf-8")
    return d


def _mk_object(location_folder: Path, object_id: str, name: str, descricao: str):
    d = location_folder / object_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "object.md").write_text(
        f"---\ntype: object\nid: {object_id}\nname: {name}\n"
        f"origin: editorial\n---\n{descricao}\n", encoding="utf-8")
    return d


def craft_op(materiais, viabilidade=7, duracao=0, tipo="item", tamanho="P",
            nome="Coisa de Teste",
            descricao_alta="ótimo", descricao_baixa="tosco"):
    return {"materiais": list(materiais), "viabilidade": viabilidade,
            "duracao": duracao, "tipo": tipo, "tamanho": tamanho, "nome": nome,
            "descricao_alta": descricao_alta, "descricao_baixa": descricao_baixa}


def peca_de(cid: str):
    return motor.trabalho.peca_pendente_de(motor.find_character_folder(cid))


def em_processo_de(cid: str):
    achado = peca_de(cid)
    return motor.trabalho.ler(achado[0]) if achado else None


def memorias_evento(cid: str, evento: str) -> list:
    return [fm for fm in motor.memoria._iter_memories(cid) if fm.get("evento") == evento]


force = motor._roll_d20

# =========================================================================== #
# US1 — SÍNCRONO: nota 0 recusa sem custo/sem dado; duração baixa conclui no
# mesmo ato sem bloco `trabalho`; nota 10 nunca sai em banda 'falha'
# =========================================================================== #

_mk_char("artesao-p57", "Artesão de Teste")
ART = "artesao-p57"
art_folder = motor.find_character_folder(ART)
taverna_folder = art_folder.parent
_mk_item(art_folder, "fibra-p57", "Fibra Seca", "Um punhado de fibras secas e resistentes.")

motor._roll_d20 = lambda: 20
res_zero = motor.apply_resolution(ART, {"craft_ops": [
    craft_op(["fibra-p57"], viabilidade=0, duracao=0)]})
check("US1: nota 0 -> recusada, regra 'sem_viabilidade'",
      any(r.get("regra") == "sem_viabilidade" for r in res_zero.get("rejected", [])),
      str(res_zero.get("rejected")))
check("US1: nota 0 -> NADA consumido",
      (art_folder / "fibra-p57").exists())

res_ok = motor.apply_resolution(ART, {"craft_ops": [
    craft_op(["fibra-p57"], viabilidade=7, duracao=0, nome="Feixe de Fibra",
            descricao_alta="um feixe bem amarrado", descricao_baixa="um feixe torto")]})
motor._roll_d20 = force
applied_ok = res_ok.get("craft_ops_applied") or []
check("US1: craft síncrono aplicado", len(applied_ok) == 1, str(res_ok))
check("US1: material CONSUMIDO no ato", not (art_folder / "fibra-p57").exists())
check("US1: op aplicada marca sincrono=True, concluido=True, fase='conclusao'",
      bool(applied_ok) and applied_ok[0].get("sincrono") and applied_ok[0].get("concluido")
      and applied_ok[0].get("fase") == "conclusao", str(applied_ok))
peca_id_sinc = applied_ok[0]["peca"] if applied_ok else None
check("US1: a entidade item NASCE pronta COM o autor (posse física, sem bloco "
     "`trabalho`) — é o que faz dono() resolver sem testemunha nenhuma",
      peca_id_sinc is not None
      and (art_folder / peca_id_sinc / "item.md").exists()
      and motor.trabalho.ler(art_folder / peca_id_sinc) is None)
item_fm, item_body = motor.read_doc(art_folder / peca_id_sinc / "item.md") \
    if peca_id_sinc else ({}, "")
check("US1: nome/descrição vieram da candidata certa pela banda",
      item_fm.get("name") == "Feixe de Fibra", str(item_fm))
check("US1: memória do autor gravada no ato (evento 'craft')",
      len(memorias_evento(ART, "craft")) == 1, str(memorias_evento(ART, "craft")))

# nota 10: com o PIOR d20 SEM ser crítico natural (persuade_dc(10)=0, margem
# nunca < 0), a banda nunca deve ser 'falha' — d20=1 fica de fora de propósito
# aqui: um NATURAL 1 é o extremo do dado (rebaixa um degrau DEPOIS da margem,
# mesma catraca de `banda_final`/forge) e é o único jeito de nota 10 ainda
# sair em 'falha' — comportamento correto, testado à parte logo abaixo.
_mk_char("sortudo-p57", "Sortudo de Teste")
SOR = "sortudo-p57"
sor_folder = motor.find_character_folder(SOR)
_mk_item(sor_folder, "argila-p57", "Argila", "Um bloco de argila fresca.")
motor._roll_d20 = lambda: 2  # pior rolagem NÃO-crítica possível
res_10 = motor.apply_resolution(SOR, {"craft_ops": [
    craft_op(["argila-p57"], viabilidade=10, duracao=0, nome="Vaso",
            descricao_alta="um vaso perfeito", descricao_baixa="um vaso rachado")]})
motor._roll_d20 = force
applied_10 = res_10.get("craft_ops_applied") or []
check("US1: nota 10 com d20=2 (não-crítico) produz banda >= comum (DC chegou a 0)",
      bool(applied_10) and applied_10[0].get("banda") in ("comum", "incomum", "raro", "lendario"),
      str(applied_10))

# o NATURAL 1 é a única forma de nota 10 sair em 'falha' — o extremo do dado
# rebaixa um degrau DEPOIS da margem (mesma catraca de `forja`), nunca recusa
# a criação em si (o gate já passou: viabilidade=10 > 0, materiais consomem).
_mk_char("azarado-p57", "Azarado de Teste")
AZA = "azarado-p57"
aza_folder = motor.find_character_folder(AZA)
_mk_item(aza_folder, "argila2-p57", "Argila", "Outro bloco de argila fresca.")
motor._roll_d20 = lambda: 1  # crítico natural
res_critico = motor.apply_resolution(AZA, {"craft_ops": [
    craft_op(["argila2-p57"], viabilidade=10, duracao=0, nome="Vaso")]})
motor._roll_d20 = force
applied_critico = res_critico.get("craft_ops_applied") or []
check("US1: natural 1 rebaixa a banda um degrau, mas a criação AINDA ACONTECE "
     "(não é recusa — materiais consomem, entidade nasce)",
      bool(applied_critico) and applied_critico[0].get("banda") == "falha"
      and not (aza_folder / "argila2-p57").exists(), str(applied_critico))

# =========================================================================== #
# US2 — ASSÍNCRONO: duração alta nasce peça em processo (ESFORÇO); retomar
# credita tempo com CLAMP, zero LLM; conclusão materializa o congelado na abertura
# =========================================================================== #

_mk_char("construtor-p57", "Construtor de Teste")
CON = "construtor-p57"
con_folder = motor.find_character_folder(CON)
con_taverna = con_folder.parent
_mk_item(con_folder, "madeira-p57", "Madeira", "Vigas de madeira rústica.")

check("US2 (baseline): nenhum trabalho pendente antes de começar",
      peca_de(CON) is None)

motor._roll_d20 = lambda: 15
res_abrir = motor.apply_resolution(CON, {"craft_ops": [
    craft_op(["madeira-p57"], viabilidade=8, duracao=8, tipo="object",
            nome="Prateleira", descricao_alta="uma prateleira firme",
            descricao_baixa="uma prateleira bamba")]})
motor._roll_d20 = force
applied_abrir = res_abrir.get("craft_ops_applied") or []
check("US2: abertura aplicada, NÃO concluída, fase='abertura'",
      bool(applied_abrir) and not applied_abrir[0].get("concluido")
      and applied_abrir[0].get("fase") == "abertura", str(applied_abrir))
check("US2: material CONSUMIDO já na abertura", not (con_folder / "madeira-p57").exists())

bloco_aberto = em_processo_de(CON)
check("US2: peça em processo tem relógio de ESFORÇO (tempo_necessario_s, sem pronto_ts)",
      isinstance(bloco_aberto, dict) and "tempo_necessario_s" in bloco_aberto
      and "pronto_ts" not in bloco_aberto, str(bloco_aberto))
check("US2: tempo_trabalhado_s começa em 0", bloco_aberto.get("tempo_trabalhado_s") == 0)

peca_folder_async, _ = peca_de(CON)
peca_id_async = peca_folder_async.name
necessario = bloco_aberto["tempo_necessario_s"]

# retomada 1: credita pouco tempo (sessão curta) — NÃO conclui
motor.trabalho.atualizar(peca_folder_async,
                         trabalhando_desde=time.time() - (necessario * 0.2))
res_retomar1 = motor.apply_resolution(CON, {"craft_ops": [
    {"peca": peca_id_async, "retomada": True, "narracao": "continuo trabalhando"}]})
applied_r1 = res_retomar1.get("craft_ops_applied") or []
check("US2: retomada credita tempo e NÃO conclui ainda",
      bool(applied_r1) and not applied_r1[0].get("concluido")
      and applied_r1[0].get("fase") == "retomada", str(applied_r1))
bloco_meio = em_processo_de(CON)
check("US2: tempo_trabalhado_s cresceu, mas segue < necessario",
      0 < bloco_meio.get("tempo_trabalhado_s", 0) < necessario, str(bloco_meio))

# CLAMP: uma sessão "esquecida" por muito mais tempo do que falta não credita além
falta = necessario - bloco_meio["tempo_trabalhado_s"]
motor.trabalho.atualizar(peca_folder_async,
                         trabalhando_desde=time.time() - (falta * 100))
motor.trabalho.creditar_e_fechar(peca_folder_async)
bloco_pos_clamp = motor.trabalho.ler(peca_folder_async)
check("US2 (CLAMP): tempo creditado nunca passa de tempo_necessario_s",
      bloco_pos_clamp.get("tempo_trabalhado_s") <= necessario + 1e-6,
      str(bloco_pos_clamp))

# retomada final: conclui
motor.trabalho.atualizar(peca_folder_async, trabalhando_desde=time.time())
res_concluir = motor.apply_resolution(CON, {"craft_ops": [
    {"peca": peca_id_async, "retomada": True, "narracao": "termino"}]})
applied_fim = res_concluir.get("craft_ops_applied") or []
check("US2: conclusão materializa (concluido=True, fase='conclusao')",
      bool(applied_fim) and applied_fim[0].get("concluido")
      and applied_fim[0].get("fase") == "conclusao", str(applied_fim))
check("US2: a entidade final é um OBJECT (tipo julgado na abertura, congelado)",
      (con_taverna / peca_id_async / "object.md").exists()
      and motor.trabalho.ler(con_taverna / peca_id_async) is None)
obj_fm, _ = motor.read_doc(con_taverna / peca_id_async / "object.md")
check("US2: nome final é o congelado na abertura", obj_fm.get("name") == "Prateleira",
      str(obj_fm))

# conserto pós-057 (Conserto 3): retomar uma peça JÁ CONCLUÍDA (sem bloco
# `trabalho` mais, mas `origin: emergente`) precisa dizer "já terminou", não
# confundir com "é de outro tipo de trabalho".
res_ja_concluida = motor.apply_resolution(CON, {"craft_ops": [
    {"peca": peca_id_async, "retomada": True, "narracao": "continuo mesmo assim"}]})
check("Conserto 3: retomar peça já concluída recusa com 'peca_ja_concluida'",
      any(r.get("regra") == "peca_ja_concluida"
          for r in res_ja_concluida.get("rejected", [])),
      str(res_ja_concluida.get("rejected")))

# retomada é ZERO LLM: abre uma peça pelo caminho determinístico (já provado
# acima), depois retoma via `ctx.execute` com um `ask` que ESTOURA se chamado —
# se a retomada consultasse o Árbitro, o teste quebraria com AssertionError.
_mk_item(con_folder, "madeira2-p57", "Madeira", "Mais vigas rústicas.")
motor._roll_d20 = lambda: 15
motor.apply_resolution(CON, {"craft_ops": [
    craft_op(["madeira2-p57"], viabilidade=8, duracao=8, tipo="item", nome="Banco")]})
motor._roll_d20 = force
peca_folder_2, _ = peca_de(CON)
peca_id_2 = peca_folder_2.name

ctx_retomada = arbiter.build_ctx(
    motor.get_context(CON),
    ask=lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("Árbitro consultado em retomada!")),
    prosa={"acao": "retomo o trabalho"})
res_ctx_retomar = ctx_retomada.execute(
    "craft", {"narracao": "continuo o banco", "peca": peca_id_2})
check("US2 (guarda): retomada via ctx.execute NÃO consulta o Árbitro (ask não estourou)",
      res_ctx_retomar[0].get("ok") is True, str(res_ctx_retomar))

# revisão pós-057: abrir OUTRA coisa enquanto uma peça de esforço está aberta
# não é mais bloqueada — é uma INTERRUPÇÃO (`turno.apply_op` fecha a sessão
# pendente, creditando o que já correu, ANTES de despachar a ação nova). Quem
# quiser terminar o banco depois faz uma retomada explícita, igual qualquer
# outra peça fechada-mas-incompleta — não existe mais "ja_trabalhando" pra
# abertura, só pra retomar a peça ERRADA enquanto outra está de fato aberta.
_mk_item(con_folder, "pedra-p57", "Pedra", "Uma pedra lisa qualquer.")
ask_fixo_generico = lambda _s, _u: (
    '{"viabilidade": 7, "duracao": 0, "tipo": "item", "tamanho": "P", '
    '"nome": "X", "descricao_alta": "x", "descricao_baixa": "x"}')
ctx_ocupado = arbiter.build_ctx(motor.get_context(CON), ask=ask_fixo_generico,
                                prosa={"acao": "tento outra coisa"})
res_ocupado = ctx_ocupado.execute(
    "craft", {"narracao": "faço outra coisa", "materiais": ["pedra-p57"]})
check("US2 (interrupção): outra ação NÃO é mais bloqueada por peça pendente",
      res_ocupado[0].get("ok") is True, str(res_ocupado))
check("US2 (interrupção): o material da ação nova FOI consumido",
      not (con_folder / "pedra-p57").exists())
bloco_banco_fechado = motor.trabalho.ler(peca_folder_2)
check("US2 (interrupção): a peça antiga (Banco) foi FECHADA, não perdida nem concluída",
      bloco_banco_fechado is not None
      and not motor.trabalho.sessao_aberta(bloco_banco_fechado),
      str(bloco_banco_fechado))

# =========================================================================== #
# US3 — testemunha vira dono: abertura+conclusão viram fato, retomada
# intermediária NÃO; sem testemunha, só o autor reconhece a posse
# =========================================================================== #

_mk_char("curioso-p57", "Curioso de Teste")  # controle: nunca presencia nada abaixo
CUR = "curioso-p57"
cur_folder = motor.find_character_folder(CUR)

# CORREÇÃO (achado em US4/T041): `motor.apply_resolution` JÁ aciona o leque de
# testemunha — `apply_op`/`_spread` publicam `Fato`s via `motor/fatos.py`, e
# `react_witness` reage a eles no mesmo `WRITE_LOCK`, sem precisar do caminho
# `ctx.execute`/arbiter. Este teste continua usando `ctx.execute` (o caminho real
# de produção) porque também quer provar a GUARDA (veredito único, retomada
# zero-LLM) ao mesmo tempo — não porque seja a única forma de exercitar
# testemunha (US4 usa `motor.apply_resolution` direto para isso, mais simples).
_mk_char("oleiro2-p57", "Segundo Oleiro")
_mk_char("testemunha-p57", "Testemunha de Teste")
OLE2, TEST = "oleiro2-p57", "testemunha-p57"
ole2_folder = motor.find_character_folder(OLE2)
test_folder = motor.find_character_folder(TEST)
ole2_taverna = ole2_folder.parent
_mk_item(ole2_folder, "barro2-p57", "Barro", "Outro bloco de barro úmido.")

ask_fixo = lambda _s, _u: (
    '{"viabilidade": 8, "duracao": 8, "tipo": "item", "tamanho": "P", '
    '"nome": "Vaso Grande", '
    '"descricao_alta": "um vaso bem torneado", "descricao_baixa": "um vaso torto"}')
motor._roll_d20 = lambda: 15
ctx_abrir = arbiter.build_ctx(motor.get_context(OLE2), ask=ask_fixo,
                              prosa={"acao": "faço um vaso"})
res_abrir_test = ctx_abrir.execute("craft", {"narracao": "faço um vaso grande",
                                             "materiais": ["barro2-p57"]})
motor._roll_d20 = force
check("US3: abertura testemunhada aplicada com sucesso",
      res_abrir_test[0].get("ok") is True, str(res_abrir_test))

mem_test_abertura = memorias_evento(TEST, "witness_craft")
check("US3: a testemunha presente na ABERTURA forma UMA memória witness_craft",
      len(mem_test_abertura) == 1, str(mem_test_abertura))

peca_folder_ole2, bloco_ole2 = peca_de(OLE2)
peca_id_ole2 = peca_folder_ole2.name
dono_visto = motor.memoria.dono(peca_id_ole2, TEST)
check("US3: dono() já aponta o AUTOR para quem testemunhou a abertura",
      dono_visto == OLE2, str(dono_visto))

# retomada intermediária: credita tempo, mas NÃO deve gerar segunda memória
necessario2 = bloco_ole2["tempo_necessario_s"]
motor.trabalho.atualizar(peca_folder_ole2,
                         trabalhando_desde=time.time() - (necessario2 * 0.3))
ctx_retomar2 = arbiter.build_ctx(motor.get_context(OLE2), ask=ask_fixo,
                                 prosa={"acao": "continuo o vaso"})
ctx_retomar2.execute("craft", {"narracao": "continuo o vaso", "peca": peca_id_ole2})
mem_test_meio = memorias_evento(TEST, "witness_craft")
check("US3: retomada intermediária NÃO gera segunda memória de testemunha",
      len(mem_test_meio) == 1, str(mem_test_meio))

# conclusão: credita o resto — revisão pós-057, a conclusão virou PREGUIÇOSA
# (`trabalho.resolver_esforco_pendente`): a própria leitura de contexto já
# credita e materializa via retomada sintética, então não sobra peça "em
# processo" pra uma chamada explícita concluir depois — testar isso É testar
# que a leitura de contexto já bastou.
bloco_meio2 = em_processo_de(OLE2)
falta2 = bloco_meio2["tempo_necessario_s"] - bloco_meio2["tempo_trabalhado_s"]
motor.trabalho.atualizar(peca_folder_ole2, trabalhando_desde=time.time() - falta2)
motor.get_context(OLE2)
check("US3: conclusão aplicada (preguiçosa, na própria leitura de contexto)",
      em_processo_de(OLE2) is None, str(em_processo_de(OLE2)))
mem_test_fim = memorias_evento(TEST, "witness_craft")
check("US3: a CONCLUSÃO gera a SEGUNDA memória de testemunha (abertura + conclusão)",
      len(mem_test_fim) == 2, str(mem_test_fim))
check("US3: dono() do item CONCLUÍDO ainda aponta o autor",
      motor.memoria.dono(peca_id_ole2, TEST) == OLE2)

# sem testemunha nenhuma: só o autor reconhece a posse — precisa de uma
# location REALMENTE vazia (a taverna compartilhada acima tem Elga/Torvin e os
# outros personagens de teste; craft ali sempre tem plateia)
CLAREIRA = "clareira-vazia-p57"
clareira_folder = motor.WORLD_DIR / CLAREIRA
clareira_folder.mkdir(parents=True, exist_ok=True)
(clareira_folder / "location.md").write_text(
    "---\ntype: location\nid: clareira-vazia-p57\nname: Clareira Vazia\nsize: P\n"
    "origin: editorial\n---\nUma clareira deserta, longe de qualquer caminho.\n",
    encoding="utf-8")
sol_folder = clareira_folder / "solitario-p57"
sol_folder.mkdir(parents=True, exist_ok=True)
(sol_folder / "character.md").write_text(
    "---\ntype: character\nid: solitario-p57\nname: Solitário de Teste\n"
    "controlled_by: player_local\nweight_kg: 70\n"
    "attributes:\n  STR: 10\n  DEX: 10\n  CON: 10\n  INT: 10\n  WIS: 10\n  CHA: 10\n"
    "skills: {}\nstatus:\n  hp: 20\n  hp_max: 20\n  hunger: sem fome\n  fatigue: 0\n"
    "  action: parado\n  mood: neutro\n  conditions: []\norigin: editorial\n---\nx\n",
    encoding="utf-8")
SOL = "solitario-p57"
_mk_item(sol_folder, "graveto-p57", "Graveto", "Um graveto seco qualquer.")
motor._roll_d20 = lambda: 20
motor.apply_resolution(SOL, {"craft_ops": [
    craft_op(["graveto-p57"], viabilidade=8, duracao=0, nome="Espeto")]})
motor._roll_d20 = force
mem_sol = memorias_evento(SOL, "craft")
peca_id_sol = None
for fm in mem_sol:
    involved = fm.get("involved") or []
    if involved:
        peca_id_sol = involved[0]
check("US3: sem testemunha, dono() reconhece o AUTOR para ele mesmo (posse "
     "física — o item nasceu COM ele, não solto)",
      peca_id_sol is not None and motor.memoria.dono(peca_id_sol, SOL) == SOL,
      str((peca_id_sol, mem_sol)))
check("US3: sem testemunha, NINGUÉM MAIS tem memória witness_craft sobre esta peça",
      not any(peca_id_sol in (fm.get("involved") or [])
             for fm in memorias_evento(CUR, "witness_craft")))

# =========================================================================== #
# US5 — onde a coisa nasce, por tipo: item solto/com personagem; object fixo;
# location como SUBPASTA NOVA da location atual, sem `route` nenhuma.
# =========================================================================== #

_mk_char("marceneiro-p57", "Marceneiro de Teste")
MAR = "marceneiro-p57"
mar_folder = motor.find_character_folder(MAR)
mar_taverna = mar_folder.parent
_mk_item(mar_folder, "tora-p57", "Tora de Madeira", "Uma tora grande de madeira crua.")

motor._roll_d20 = lambda: 20
res_solto = motor.apply_resolution(MAR, {"craft_ops": [
    craft_op(["tora-p57"], viabilidade=8, duracao=0, tipo="item",
            tamanho="XG", nome="Banco Pesado")]})
motor._roll_d20 = force
applied_solto = res_solto.get("craft_ops_applied") or []
peca_solto = applied_solto[0]["peca"] if applied_solto else None
check("US5: item 'solto_na_location' NASCE na location, não com o personagem",
      peca_solto is not None
      and (mar_taverna / peca_solto / "item.md").exists()
      and not (mar_folder / peca_solto).exists(),
      str(applied_solto))

_mk_item(mar_folder, "prego-p57", "Prego", "Um prego de ferro qualquer.")
res_com = motor.apply_resolution(MAR, {"craft_ops": [
    craft_op(["prego-p57"], viabilidade=8, duracao=0, tipo="item",
            tamanho="PP", nome="Grampo")]})
applied_com = res_com.get("craft_ops_applied") or []
peca_com = applied_com[0]["peca"] if applied_com else None
check("US5: item 'com_personagem' (default) NASCE com o autor",
      peca_com is not None and (mar_folder / peca_com / "item.md").exists(),
      str(applied_com))

_mk_item(mar_folder, "prego2-p57", "Prego", "Outro prego de ferro.")
res_obj = motor.apply_resolution(MAR, {"craft_ops": [
    craft_op(["prego2-p57"], viabilidade=8, duracao=0, tipo="object",
            nome="Prateleira Fixa")]})
applied_obj = res_obj.get("craft_ops_applied") or []
peca_obj = applied_obj[0]["peca"] if applied_obj else None
check("US5: object SEMPRE fica fixo na location, mesmo pedindo 'com_personagem'",
      peca_obj is not None
      and (mar_taverna / peca_obj / "object.md").exists()
      and not (mar_folder / peca_obj).exists(),
      str(applied_obj))

_mk_item(mar_folder, "pedra-p57", "Pedra", "Um bloco de pedra lavrada.")
res_loc = motor.apply_resolution(MAR, {"craft_ops": [
    craft_op(["pedra-p57"], viabilidade=8, duracao=0, tipo="location",
            nome="Cantinho da Lareira")]})
applied_loc = res_loc.get("craft_ops_applied") or []
peca_loc = applied_loc[0]["peca"] if applied_loc else None
loc_fm, _ = motor.read_doc(mar_taverna / peca_loc / "location.md") if peca_loc else ({}, "")
check("US5: location nasce como SUBPASTA da location atual, com `size`",
      peca_loc is not None and (mar_taverna / peca_loc / "location.md").exists()
      and loc_fm.get("size") in validator.SIZES, str((peca_loc, loc_fm)))
routes_dir = mar_taverna.parent / "routes" if (mar_taverna.parent / "routes").exists() else None
check("US5: craft de location NÃO cria nenhuma `route` nova",
      routes_dir is None or not any(
          peca_loc in r.name for r in routes_dir.iterdir()) if peca_loc else True)

# item grande "com_personagem" via trabalho ASSÍNCRONO: a peça em processo mora
# na location (US6); só migra pro personagem NA CONCLUSÃO.
_mk_char("carpinteiro-p57", "Carpinteiro de Teste")
CAR = "carpinteiro-p57"
car_folder = motor.find_character_folder(CAR)
car_taverna = car_folder.parent
_mk_item(car_folder, "madeira2-p57", "Tábuas", "Um maço de tábuas boas.")
motor._roll_d20 = lambda: 20
res_abrir5 = motor.apply_resolution(CAR, {"craft_ops": [
    craft_op(["madeira2-p57"], viabilidade=8, duracao=6, tipo="item",
            nome="Baú Pequeno")]})
peca_car = (res_abrir5.get("craft_ops_applied") or [{}])[0].get("peca")
check("US5: peça de ITEM em processo mora na LOCATION durante o trabalho",
      peca_car is not None and (car_taverna / peca_car).exists()
      and not (car_folder / peca_car).exists(), str(res_abrir5))
bloco_car = motor.trabalho.ler(car_taverna / peca_car) if peca_car else None
tempo_necessario = bloco_car.get("tempo_necessario_s") if bloco_car else 0
# credita o tempo inteiro de uma vez via um `trabalhando_desde` manualmente
# recuado, igual US2 já faz — evita depender de `time.sleep`.
fm_bloco, corpo_bloco = motor.read_doc(car_taverna / peca_car / "item.md")
fm_bloco["trabalho"]["trabalhando_desde"] = time.time() - (tempo_necessario + 10)
motor.write_doc(car_taverna / peca_car / "item.md", fm_bloco, corpo_bloco)
res_concluir5 = motor.apply_resolution(CAR, {"craft_ops": [
    {"peca": peca_car, "narracao": "termino o baú", "retomada": True}]})
motor._roll_d20 = force
concluido5 = (res_concluir5.get("craft_ops_applied") or [{}])[0]
check("US5: na CONCLUSÃO, item 'com_personagem' MIGRA da location pro autor",
      concluido5.get("concluido") is True
      and (car_folder / peca_car / "item.md").exists()
      and not (car_taverna / peca_car).exists(), str(res_concluir5))

# =========================================================================== #
# US4 — retrofit: os seis ofícios legados alimentam o mesmo leque de testemunha.
# =========================================================================== #

# --- FORJA (ESFORÇO, Mecanismo A) — domínio POR-INSTÂNCIA (armaria != ferraria) ---
_mk_char("ferreiro-p57", "Ferreiro de Teste")
_mk_char("testef-p57", "Testemunha da Forja")
FER, TESTF = "ferreiro-p57", "testef-p57"
fer_folder = motor.find_character_folder(FER)
fer_taverna = fer_folder.parent
_mk_item(fer_folder, "metal-p57", "Barra de Metal", "Uma barra de metal maleável.")
_mk_object(fer_taverna, "forja-obj-p57", "Forja", "Uma forja com brasas quentes.")

forja_op_abrir = {
    "materiais": ["metal-p57"], "fonte_calor": "forja-obj-p57", "tipo": "armadura",
    "forjabilidade": 8, "qualidade_material": 8, "fogo_de_forja": 8, "ferramental": 8,
    "duracao": 5, "nome": "Peitoral de Teste",
    "descricao_alta": "um peitoral bem batido", "descricao_baixa": "um peitoral tosco",
}
motor._roll_d20 = lambda: 15
res_forja_abrir = motor.apply_resolution(FER, {"forja_ops": [forja_op_abrir]})
motor._roll_d20 = force
mem_testf_1 = memorias_evento(TESTF, "witness_forja")
check("US4 (forja): testemunha na ABERTURA forma UMA memória witness_forja",
      len(mem_testf_1) == 1, str(mem_testf_1))
check("US4 (forja): domínio da testemunha é 'armaria' (POR-INSTÂNCIA, não "
     "'ferraria' fixo) — prova o conserto do T034",
      bool(mem_testf_1) and mem_testf_1[0].get("domain") == "armaria",
      str(mem_testf_1))
peca_folder_fer, bloco_fer = motor.trabalho.peca_pendente_de(fer_folder)
peca_id_fer = peca_folder_fer.name
# credita o tempo inteiro via `trabalhando_desde` recuado (mesmo truque de US2/US5)
fm_fer, corpo_fer = motor.read_doc(peca_folder_fer / "item.md")
fm_fer["trabalho"]["trabalhando_desde"] = time.time() - (bloco_fer["tempo_necessario_s"] + 10)
motor.write_doc(peca_folder_fer / "item.md", fm_fer, corpo_fer)
res_forja_concluir = motor.apply_resolution(FER, {"forja_ops": [
    {"peca": peca_id_fer, "tipo": "armadura", "retomada": True}]})
mem_testf_2 = memorias_evento(TESTF, "witness_forja")
check("US4 (forja): a CONCLUSÃO gera a SEGUNDA memória de testemunha",
      len(mem_testf_2) == 2, str((res_forja_concluir, mem_testf_2)))
check("US4 (forja): dono() da peça aponta o ferreiro, do ponto de vista da "
     "testemunha",
      motor.memoria.dono(peca_id_fer, TESTF) == FER)

# --- COZINHA (PRAZO, Mecanismo A + B) — testemunhas DIFERENTES em cada fase ---
_mk_char("cozinheiro-p57", "Cozinheiro de Teste")
_mk_char("testec1-p57", "Testemunha 1 da Cozinha")
COZ, TESTC1 = "cozinheiro-p57", "testec1-p57"
coz_folder = motor.find_character_folder(COZ)
coz_taverna = coz_folder.parent
_mk_item(coz_folder, "legume-p57", "Legume", "Um legume fresco qualquer.")
_mk_object(coz_taverna, "fogao-p57", "Fogão", "Um fogão aceso.")

cozinha_op = {
    "ingredientes": ["legume-p57"], "fonte_calor": "fogao-p57",
    "fonte_de_calor": 8, "cozinhabilidade": 8, "favorabilidade": 7, "duracao": 0,
    "nome": "Sopa de Teste", "descricao_media": "uma sopa razoável",
}
res_cozinha_abrir = motor.apply_resolution(COZ, {"cozinha_ops": [cozinha_op]})
mem_testc1 = memorias_evento(TESTC1, "witness_cozinha")
check("US4 (cozinha): testemunha presente na ABERTURA (Mecanismo A) forma "
     "witness_cozinha",
      len(mem_testc1) == 1, str((res_cozinha_abrir, mem_testc1)))

# TESTC1 "vai embora" — pasta movida pra outro lugar, fora da cena da conclusão.
outro_lugar = motor.WORLD_DIR / "outro-lugar-p57"
outro_lugar.mkdir(parents=True, exist_ok=True)
(outro_lugar / "location.md").write_text(
    "---\ntype: location\nid: outro-lugar-p57\nname: Outro Lugar\nsize: P\n"
    "origin: editorial\n---\nUm lugar qualquer, longe.\n", encoding="utf-8")
motor.io.move_entity(motor.find_character_folder(TESTC1),
                     outro_lugar / TESTC1)
_mk_char("testec2-p57", "Testemunha 2 da Cozinha")  # chega DEPOIS da abertura
TESTC2 = "testec2-p57"

panela_folder, bloco_panela = motor.trabalho.peca_pendente_de(coz_folder,
                                                               apenas_prazo=True)
fm_panela, corpo_panela = motor.read_doc(panela_folder / "item.md")
fm_panela["trabalho"]["pronto_ts"] = time.time() - 10
motor.write_doc(panela_folder / "item.md", fm_panela, corpo_panela)
motor.get_context(COZ)  # dispara resolver_vencidas() -> Mecanismo B

mem_testc1_final = memorias_evento(TESTC1, "witness_cozinha")
mem_testc2 = memorias_evento(TESTC2, "witness_cozinha")
check("US4 (cozinha): quem SAIU antes da conclusão continua com só a memória "
     "da ABERTURA (Mecanismo B não a alcança mais)",
      len(mem_testc1_final) == 1, str(mem_testc1_final))
check("US4 (cozinha): quem CHEGOU só na conclusão forma witness_cozinha via "
     "Mecanismo B (resolver_vencidas, fora do pipeline de Fato)",
      len(mem_testc2) == 1, str(mem_testc2))
check("US4 (cozinha): dono() da panela concluída aponta o cozinheiro, do ponto "
     "de vista de quem só viu o FIM",
      bool(mem_testc2) and motor.memoria.dono(panela_folder.name, TESTC2) == COZ)

# --- BOTICA (PRAZO, mesma dupla A+B — confirmação mais leve) ---
_mk_char("boticario-p57", "Boticário de Teste")
_mk_char("testeb-p57", "Testemunha da Botica")
BOT, TESTB = "boticario-p57", "testeb-p57"
bot_folder = motor.find_character_folder(BOT)
bot_taverna = bot_folder.parent
_mk_item(bot_folder, "erva-p57", "Erva", "Uma erva medicinal qualquer.")
_mk_object(bot_taverna, "caldeirao-p57", "Caldeirão", "Um caldeirão de cobre.")
res_botica_abrir = motor.apply_resolution(BOT, {"botica_ops": [{
    "ingredientes": ["erva-p57"], "recipiente": "caldeirao-p57",
    "recipiente_adequado": 8, "preparabilidade": 8, "favorabilidade": 7,
    "duracao": 0, "nome": "Tônico de Teste", "descricao_media": "um tônico razoável",
}]})
check("US4 (botica): abertura (Mecanismo A) forma witness_botica",
      len(memorias_evento(TESTB, "witness_botica")) == 1, str(res_botica_abrir))
peca_bot, bloco_bot = motor.trabalho.peca_pendente_de(bot_folder, apenas_prazo=True)
fm_bot, corpo_bot = motor.read_doc(peca_bot / "item.md")
fm_bot["trabalho"]["pronto_ts"] = time.time() - 10
motor.write_doc(peca_bot / "item.md", fm_bot, corpo_bot)
motor.get_context(BOT)  # Mecanismo B
mem_testb_final = memorias_evento(TESTB, "witness_botica")
check("US4 (botica): conclusão (Mecanismo B) gera a SEGUNDA memória "
     "witness_botica (mesma testemunha viu as duas fases)",
      len(mem_testb_final) == 2, str(mem_testb_final))
check("US4 (botica): dono() do preparo concluído aponta o boticário",
      motor.memoria.dono(peca_bot.name, TESTB) == BOT)

# --- FORAGE (síncrono, NÃO confere posse) ---
# `base: "small"` (ao contrário de craft/forja/cozinha/botica/esquartejar —
# "medium" DE PROPÓSITO, porque eles precisam ser memoráveis a ESTRANHOS para a
# posse por testemunha funcionar). Colher/acender não conferem posse, então
# "small" — memorável só para quem já tem vínculo — é o comportamento CORRETO,
# não um bug: um estranho colhendo ervas ao longe não é o tipo de coisa que
# marca a vida de quem vê. O teste estabelece familiaridade prévia de propósito,
# para exercitar o caso em que a memória DEVE se formar.
_mk_char("coletor-p57", "Coletor de Teste")
_mk_char("testecol-p57", "Testemunha do Coletor")
COL, TESTCOL = "coletor-p57", "testecol-p57"
col_folder = motor.find_character_folder(COL)
motor.memoria._write_memory(motor.find_character_folder(TESTCOL),
                            "Já cruzei com este coletor por aqui antes.",
                            intensity="small", involved=[COL], evento="hearsay",
                            domain="nenhuma")
res_forage = motor.apply_resolution(COL, {"forage_ops": [{
    "onde": col_folder.parent.name, "herbabilidade": 7, "riqueza": 6,
    "nome_util": "Ervas Colhidas", "descricao_util": "um punhado de ervas úteis",
}]})
mem_testcol = memorias_evento(TESTCOL, "witness_forage")
check("US4 (forage): ato único gera witness_forage",
      len(mem_testcol) == 1, str(res_forage))
itens_colhidos = (res_forage.get("forage_ops_applied") or [{}])[0].get("itens") or []
check("US4 (forage): dono() NÃO resolve (colher não confere posse — FR-020/021)",
      bool(itens_colhidos)
      and motor.memoria.dono(itens_colhidos[0], TESTCOL) is None,
      str(itens_colhidos))

# --- ESQUARTEJAR (síncrono, CONFERE posse) ---
_mk_char("acougueiro-p57", "Açougueiro de Teste")
_mk_char("testeacg-p57", "Testemunha do Açougue")
ACG, TESTACG = "acougueiro-p57", "testeacg-p57"
acg_folder = motor.find_character_folder(ACG)
_mk_char("presa-p57", "Presa Abatida", conditions=["morto"])
res_esquartejar = motor.apply_resolution(ACG, {"esquartejar_ops": [{
    "alvo": "presa-p57", "esquartejabilidade": 7, "rendimento": 6,
    "nome": "Carne de Teste", "descricao": "um corte de carne fresca",
}]})
mem_testacg = memorias_evento(TESTACG, "witness_esquartejar")
check("US4 (esquartejar): ato único gera witness_esquartejar",
      len(mem_testacg) == 1, str(res_esquartejar))
itens_carne = (res_esquartejar.get("esquartejar_ops_applied") or [{}])[0].get("itens") or []
check("US4 (esquartejar): dono() aponta o açougueiro (confere posse)",
      bool(itens_carne)
      and motor.memoria.dono(itens_carne[0], TESTACG) == ACG, str(itens_carne))

# --- FOGO (síncrono, PÚBLICO mas NUNCA confere posse — FR-020) ---
_mk_char("acendedor-p57", "Acendedor de Teste")
_mk_char("testefogo-p57", "Testemunha do Fogo")
ACE, TESTFOGO = "acendedor-p57", "testefogo-p57"
ace_folder = motor.find_character_folder(ACE)
_mk_item(ace_folder, "gravetos-p57", "Gravetos", "Um feixe de gravetos secos.")
motor.memoria._write_memory(motor.find_character_folder(TESTFOGO),
                            "Já vi este acendedor por aqui antes.",
                            intensity="small", involved=[ACE], evento="hearsay",
                            domain="nenhuma")
motor._roll_d20 = lambda: 20  # ignição precisa PEGAR pra witness_fogo existir
res_fogo = motor.apply_resolution(ACE, {"fogo_ops": [{
    "materiais": ["gravetos-p57"], "combustibilidade": 8, "favorabilidade": 7,
    "duracao": 3, "nome": "Fogueira de Teste", "descricao": "uma fogueira acesa",
}]})
motor._roll_d20 = force
mem_testfogo = memorias_evento(TESTFOGO, "witness_fogo")
check("US4 (fogo): acender gera witness_fogo (ato público)",
      len(mem_testfogo) == 1, str(res_fogo))
fogo_id = (res_fogo.get("fogo_ops_applied") or [{}])[0].get("fogo")
check("US4 (fogo): dono() NÃO resolve (acender fogo não confere posse — FR-020)",
      bool(fogo_id) and motor.memoria.dono(fogo_id, TESTFOGO) is None, str(fogo_id))

# =========================================================================== #
# US6 — o trabalho sobrevive a quem o começou: expulsão não afeta a peça;
# retomável por outro presente; destrutível.
# =========================================================================== #

_mk_char("pedreiro-p57", "Construtor de Teste")
PEDR = "pedreiro-p57"
cons_folder = motor.find_character_folder(PEDR)
cons_taverna = cons_folder.parent  # taverna-do-gancho — torvin-ferreiro já mora aqui
_mk_item(cons_folder, "pedra-cons-p57", "Pedras", "Um monte de pedras lavradas.")

motor._roll_d20 = lambda: 20
res_cons_abrir = motor.apply_resolution(PEDR, {"craft_ops": [
    craft_op(["pedra-cons-p57"], viabilidade=8, duracao=7, tipo="location",
            nome="Cômodo Novo")]})
motor._roll_d20 = force
peca_cons = (res_cons_abrir.get("craft_ops_applied") or [{}])[0].get("peca")
check("US6: craft de LOCATION assíncrona nasce como subpasta EM PROCESSO",
      peca_cons is not None and (cons_taverna / peca_cons / "location.md").exists()
      and motor.trabalho.ler(cons_taverna / peca_cons) is not None, str(res_cons_abrir))

# ACHADO (fora do que as tasks previam): `peca_pendente_de`/`present_pecas` em
# `motor/craft/executores.py` só varriam item/object — uma location-em-processo
# NUNCA era encontrada (nem para o gate `is_busy` equivalente do craft, nem para
# retomar). Corrigido com `trabalho.pecas_location_em` (varredura rasa dos
# filhos diretos da location atual) — sem isso, US5+US2 combinados (o caso
# citado na sessão de design: "construir uma casa") não funcionava de verdade.
check("US6: com a location em processo, o gate de craft detecta 'já trabalhando' "
     "(achado: location não era vista antes deste conserto)",
      motor.trabalho.peca_pendente_de(cons_folder) is not None)

# EXPULSÃO — Torvin (STR 16, fixture) põe o construtor pra fora à força.
motor._roll_d20 = lambda: 20
res_expulsar = motor.apply_resolution("torvin-ferreiro", {"expel_ops": [
    {"alvo": PEDR, "rota": "portao-lateral"}]}, ensure_action=False)
motor._roll_d20 = force
check("US6: expulsão aplicada com sucesso (Torvin é bem mais forte)",
      bool(res_expulsar.get("expel_ops_applied")), str(res_expulsar))
check("US6: o construtor SAIU da taverna (mudou de location)",
      not (cons_taverna / PEDR).exists())
bloco_cons_pos = motor.trabalho.ler(cons_taverna / peca_cons)
check("US6: a peça em processo CONTINUA na taverna, intacta, tempo preservado",
      bloco_cons_pos is not None
      and bloco_cons_pos.get("tempo_trabalhado_s") == 0)

# RETOMADA por OUTRO personagem, fisicamente presente — nunca precisou ser o
# construtor original (spec: "quem tiver acesso físico", não "só o autor").
fm_cons, corpo_cons = motor.read_doc(cons_taverna / peca_cons / "location.md")
necessario_cons = fm_cons["trabalho"]["tempo_necessario_s"]
fm_cons["trabalho"]["trabalhando_desde"] = time.time() - (necessario_cons + 10)
motor.write_doc(cons_taverna / peca_cons / "location.md", fm_cons, corpo_cons)
res_retomar_terceiro = motor.apply_resolution("torvin-ferreiro", {"craft_ops": [
    {"peca": peca_cons, "narracao": "termino o cômodo que outro começou",
     "retomada": True}]})
concluido_terceiro = (res_retomar_terceiro.get("craft_ops_applied") or [{}])[0]
check("US6: um TERCEIRO (não o autor) retoma e CONCLUI a peça abandonada",
      concluido_terceiro.get("concluido") is True, str(res_retomar_terceiro))
loc_final_fm, _ = motor.read_doc(cons_taverna / peca_cons / "location.md")
check("US6: a location concluída tem `size` válido e nenhum bloco `trabalho` sobrando",
      loc_final_fm.get("size") in validator.SIZES and "trabalho" not in loc_final_fm,
      str(loc_final_fm))

# =========================================================================== #
# Conserto 4 (achado da exploração): sem `route`, a location criada por craft
# nasce ILHADA — ninguém entra formalmente nela. Teste de PONTA A PONTA de
# verdade: acha a route gerada, USA `enter_route`, confirma chegada, e volta
# (bidirecional) — não basta o arquivo existir, precisa FUNCIONAR.
# =========================================================================== #
rota_nova_id = None
for _p in cons_taverna.glob("*/route.md"):
    _fm_r, _ = motor.read_doc(_p)
    if _fm_r.get("to") == peca_cons:
        rota_nova_id = _fm_r.get("id")
        rota_nova_fm = _fm_r
        break
check("Conserto 4: craft de location GEROU uma route de acesso",
      rota_nova_id is not None
      and rota_nova_fm.get("from") == TAVERNA
      and rota_nova_fm.get("bidirectional") is True,
      str(rota_nova_id))

torvin_folder = motor.find_character_folder("torvin-ferreiro")
res_entrar = motor.enter_route("torvin-ferreiro", rota_nova_id)
check("Conserto 4: enter_route ACEITA (sem prerequisites, sem restrição)",
      res_entrar.get("moved") is True, str(res_entrar))
# a chegada é preguiçosa (spec 012) — força o relógio e resolve via get_context,
# mesmo padrão de `backdate_arrival` já usado no restante da suíte.
torvin_em_transito = None
for _p in motor.WORLD_DIR.rglob("character.md"):
    _fm_t, _ = motor.read_doc(_p)
    if _fm_t.get("id") == "torvin-ferreiro":
        torvin_em_transito = _p.parent
        _fm_t["transit"]["arrive_ts"] = int(time.time()) - 100
        motor.write_doc(_p, _fm_t, "")
        break
motor.get_context("torvin-ferreiro")
check("Conserto 4: Torvin está DENTRO da location que craft criou",
      (cons_taverna / peca_cons / "torvin-ferreiro").exists(), "")

# VOLTA — bidirecional: a mesma route, sentido inverso.
res_voltar = motor.enter_route("torvin-ferreiro", rota_nova_id)
check("Conserto 4: bidirectional permite voltar pela MESMA route",
      res_voltar.get("moved") is True, str(res_voltar))
for _p in motor.WORLD_DIR.rglob("character.md"):
    _fm_t, _ = motor.read_doc(_p)
    if _fm_t.get("id") == "torvin-ferreiro":
        _fm_t["transit"]["arrive_ts"] = int(time.time()) - 100
        motor.write_doc(_p, _fm_t, "")
        break
motor.get_context("torvin-ferreiro")
check("Conserto 4: Torvin voltou pra taverna",
      (cons_taverna / "torvin-ferreiro").exists(), "")

# DESTRUIÇÃO por terceiro — outra peça, abandonada e destruída (primitiva geral,
# sem mecanismo próprio de proteção — craft não precisa de nenhum). PEDR já foi
# expulso da taverna (folder mudou) — usa um personagem NOVO, ainda lá dentro.
_mk_char("vandalo-p57", "Personagem Qualquer")
VAND = "vandalo-p57"
vand_folder = motor.find_character_folder(VAND)
_mk_item(vand_folder, "pedra2-cons-p57", "Pedras", "Outro monte de pedras.")
motor._roll_d20 = lambda: 20
res_cons_abrir2 = motor.apply_resolution(VAND, {"craft_ops": [
    craft_op(["pedra2-cons-p57"], viabilidade=8, duracao=7, tipo="object",
            nome="Bancada Nova")]})
motor._roll_d20 = force
peca_cons2 = (res_cons_abrir2.get("craft_ops_applied") or [{}])[0].get("peca")
alvo_destruir = cons_taverna / peca_cons2
check("US6 (setup): segunda peça em processo existe antes da destruição",
      alvo_destruir.exists())
motor.io.remove_entity(alvo_destruir)
check("US6: peça em processo abandonada é destrutível por uma primitiva genérica "
     "(nenhum mecanismo de proteção próprio)",
      not alvo_destruir.exists())

print()
if FAILS:
    print(f"Fase 57 (Craft genérico, spec 057): {len(FAILS)} FALHA(S): " + "; ".join(FAILS))
    sys.exit(1)
print("Fase 57 (Craft genérico, spec 057) OK.")
