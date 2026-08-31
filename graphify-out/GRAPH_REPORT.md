# Graph Report - loreforge-server  (2026-08-31)

## Corpus Check
- 248 files · ~280,853 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 2184 nodes · 5629 edges · 179 communities (166 shown, 13 thin omitted)
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS · INFERRED: 21 edges (avg confidence: 0.56)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `5964268d`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- deslocamento/executores.py
- read_doc
- fisica/__init__.py
- conhecimento/executores.py
- motor/__init__.py
- comercio/executores.py
- io.py
- consultas.py
- trabalho.py
- frontmatter.py
- registro.py
- craft/executores.py
- memoria/__init__.py
- memoria/primitivas.py
- forja/executores.py
- arbiter.py
- app.py
- Handler
- intencoes/executores.py
- selftest_helpers.py
- _rejection
- _is_alive
- validator.py
- get_context
- selftest_phase11.py
- selftest_phase14.py
- selftest_phase35.py
- llm.py
- selftest_phase15.py
- name_of
- selftest_phase17.py
- selftest_phase12.py
- selftest_phase13.py
- inworld
- fogo/executores.py
- itens/declaracao.py
- juizo.py
- selftest_phase59.py
- conhecimento/declaracao.py
- _write_memory
- selftest_phase32.py
- selftest_phase50.py
- comercio/declaracao.py
- _fail
- herbario/executores.py
- musica/executores.py
- selftest_phase18.py
- selftest_phase49.py
- selftest_phase56.py
- sondagem_sing_letra.py
- acougue/executores.py
- botica/executores.py
- cozinha/executores.py
- openapi.py
- sanea_duplicatas.py
- analisa_rodada.py
- face.py
- julgamento
- fatos.py
- selftest_phase51.py
- base.py
- mcp_core.py
- mcp_server.py
- ativacao.py
- hunger_label
- is_closed
- _record_witness
- sentiment_toward
- selftest_phase16.py
- selftest_phase26.py
- selftest_phase29.py
- selftest_phase48.py
- selftest_phase53.py
- sondagem_sing_letra2.py
- auth.py
- selftest_phase43.py
- selftest_phase30.py
- selftest_phase34.py
- selftest_phase52.py
- selftest_phase55.py
- selftest_phase57.py
- selftest_phase58.py
- sondagem_formato_payload.py
- devlog.py
- input_schema
- selftest_phase10.py
- selftest_phase20.py
- selftest_phase25.py
- selftest_phase33.py
- selftest_phase37.py
- selftest_phase46.py
- Sessao
- migra_rotas.py
- memoria/declaracao.py
- apply_op
- selftest_phase27.py
- selftest_phase31.py
- selftest_phase54.py
- selftest_phase21.py
- selftest_phase22.py
- sondagem_cadeia_sussurro.py
- sondagem_parada_do_laco.py
- sondagem_sing_regua.py
- selftest_phase38.py
- _insistencia
- selftest_phase19.py
- selftest_phase2.py
- levantar
- forja/declaracao.py
- musica/declaracao.py
- selftest_phase28.py
- selftest_phase40.py
- selftest_phase42.py
- selftest_phase44.py
- sondagem_custo_do_turno.py
- sondagem_resolucao_semantica.py
- _validate_item_physics
- proficiencies_for
- tempo.py
- sanea_mundo.py
- selftest_phase1.py
- selftest_phase4.py
- lab_descriptions.py
- sondagem_brew.py
- sondagem_forage.py
- sondagem_forage_nome.py
- new_id
- validate_world
- selftest_phase3.py
- selftest_phase36.py
- selftest_phase47.py
- por_esforco
- README.md

## God Nodes (most connected - your core abstractions)
1. `read_doc()` - 163 edges
2. `_fail()` - 81 edges
3. `name_of()` - 73 edges
4. `find_character_folder()` - 61 edges
5. `write_doc()` - 58 edges
6. `_rejection()` - 53 edges
7. `inworld()` - 50 edges
8. `attr_modifier()` - 42 edges
9. `_scene_entities()` - 36 edges
10. `get_context()` - 34 edges

## Surprising Connections (you probably didn't know these)
- `main()` --calls--> `_slug()`  [INFERRED]
  analisa_rodada.py → registro_turno.py
- `_loads_lenient()` --uses--> `LLMError`  [INFERRED]
  arbiter.py → llm.py
- `_vencer_todos_os_fogos()` --calls--> `resolver_vencidas()`  [EXTRACTED]
  selftest_phase54.py → motor/trabalho.py
- `verr()` --calls--> `validate()`  [EXTRACTED]
  selftest_phase22.py → validator.py
- `build_ask()` --calls--> `log()`  [EXTRACTED]
  app.py → devlog.py

## Import Cycles
- 3-file cycle: `motor/__init__.py -> motor/trabalho.py -> motor/turno.py -> motor/__init__.py`
- 3-file cycle: `motor/__init__.py -> motor/cozinha/__init__.py -> motor/cozinha/declaracao.py -> motor/__init__.py`
- 3-file cycle: `motor/__init__.py -> motor/cozinha/__init__.py -> motor/cozinha/executores.py -> motor/__init__.py`
- 3-file cycle: `motor/__init__.py -> motor/cozinha/__init__.py -> motor/cozinha/primitivas.py -> motor/__init__.py`
- 3-file cycle: `motor/__init__.py -> motor/fisica/__init__.py -> motor/fisica/primitivas.py -> motor/__init__.py`
- 3-file cycle: `motor/__init__.py -> motor/fogo/__init__.py -> motor/fogo/declaracao.py -> motor/__init__.py`
- 3-file cycle: `motor/__init__.py -> motor/fogo/__init__.py -> motor/fogo/executores.py -> motor/__init__.py`
- 3-file cycle: `motor/__init__.py -> motor/fogo/__init__.py -> motor/fogo/primitivas.py -> motor/__init__.py`
- 3-file cycle: `motor/__init__.py -> motor/memoria/__init__.py -> motor/memoria/executores.py -> motor/__init__.py`
- 3-file cycle: `motor/memoria/__init__.py -> motor/memoria/executores.py -> motor/trabalho.py -> motor/memoria/__init__.py`
- 4-file cycle: `motor/acougue/__init__.py -> motor/acougue/executores.py -> motor/trabalho.py -> motor/turno.py -> motor/acougue/__init__.py`
- 4-file cycle: `motor/combate/__init__.py -> motor/combate/executores.py -> motor/trabalho.py -> motor/turno.py -> motor/combate/__init__.py`
- 4-file cycle: `motor/comercio/__init__.py -> motor/comercio/executores.py -> motor/trabalho.py -> motor/turno.py -> motor/comercio/__init__.py`
- 4-file cycle: `motor/conhecimento/__init__.py -> motor/conhecimento/executores.py -> motor/trabalho.py -> motor/turno.py -> motor/conhecimento/__init__.py`
- 4-file cycle: `motor/conteiner/__init__.py -> motor/conteiner/executores.py -> motor/trabalho.py -> motor/turno.py -> motor/conteiner/__init__.py`
- 4-file cycle: `motor/cozinha/__init__.py -> motor/cozinha/executores.py -> motor/trabalho.py -> motor/turno.py -> motor/cozinha/__init__.py`
- 4-file cycle: `motor/cura/__init__.py -> motor/cura/executores.py -> motor/trabalho.py -> motor/turno.py -> motor/cura/__init__.py`
- 4-file cycle: `motor/deslocamento/__init__.py -> motor/deslocamento/executores.py -> motor/trabalho.py -> motor/turno.py -> motor/deslocamento/__init__.py`
- 4-file cycle: `motor/estado/__init__.py -> motor/estado/executores.py -> motor/trabalho.py -> motor/turno.py -> motor/estado/__init__.py`
- 4-file cycle: `motor/intencoes/__init__.py -> motor/intencoes/executores.py -> motor/trabalho.py -> motor/turno.py -> motor/intencoes/__init__.py`

## Communities (179 total, 13 thin omitted)

### Community 0 - "deslocamento/executores.py"
Cohesion: 0.06
Nodes (81): _apply_travel_ops(), _h_carry(), _h_persuade(), _h_travel(), O Motor / deslocamento — EXECUTORES (item 31 §3: DDD por domínio).…, Inicia uma viagem longa: calcula o trajeto e parte na primeira perna. O plano…, O Motor / deslocamento (pacote, item 31 §3) — fachada do domínio. Reexporta a…, _cancel_travel() (+73 more)

### Community 1 - "read_doc"
Cohesion: 0.09
Nodes (64): check_carga(), check_empurrar(), check_mao(), check_slot(), porter_of(), Personagem no topo da cadeia de contenção de um item, ou None (chão/object).…, Checagem de LIMITES do empurrar (guarda e Motor): só nega a zona impossível (>…, move_entity() (+56 more)

### Community 2 - "fisica/__init__.py"
Cohesion: 0.07
Nodes (64): O Motor / fisica (pacote, item 31 §3) — domínio puro (primitivas). Sem…, body_of(), body_weight_of(), carried_item_ids(), carried_weight(), check_encaixe(), check_vaga(), custo_da_falha() (+56 more)

### Community 3 - "conhecimento/executores.py"
Cohesion: 0.07
Nodes (52): _apply_hearsay_ops(), _apply_learn_ops(), _apply_unanswered_ops(), _apply_write_ops(), _h_hearsay(), _h_learn(), _h_unanswered(), _h_write() (+44 more)

### Community 4 - "motor/__init__.py"
Cohesion: 0.09
Nodes (44): _apply_attack_ops(), _h_attack(), Path, O Motor / combate — EXECUTORES (item 31 §3: DDD por domínio). `_apply_*_ops` +…, Golpear outro personagem presente (`attack_ops`, spec 008). Ponto autoritativo…, O Motor / combate (pacote, item 31 §3) — fachada do domínio. Reexporta a API…, O Motor / combate — PRIMITIVAS (item 31 §3: DDD por domínio). Funções puras…, Teste oposto do golpe (spec 008). Retorna (rejeicao, roll_info). Rolagem ÚNICA:… (+36 more)

### Community 5 - "comercio/executores.py"
Cohesion: 0.10
Nodes (41): _apply_persuade_give_ops(), _apply_trade_ops(), _h_persuade_give(), _h_trade(), Path, O Motor / comercio — EXECUTORES (item 31 §3: DDD por domínio). `_apply_*_ops` +…, Convencer o DONO (alvo) a ENTREGAR um item ao ATOR ou a outro presente. No…, Comprar e trocar (`trade_ops`, spec 011) — um pipeline, dois julgamentos. Três… (+33 more)

### Community 6 - "io.py"
Cohesion: 0.08
Nodes (39): _apply_mutations(), _h_mutations(), Path, O Motor / estado — EXECUTORES (item 31 §3: DDD por domínio). `_apply_*_ops` +…, Aplica as `mutations` (status.* de personagem, state.* de object/item da cena).…, O Motor / estado (pacote, item 31 §3) — fachada do domínio. Reexporta a API por…, _clear_condition(), Path (+31 more)

### Community 7 - "consultas.py"
Cohesion: 0.10
Nodes (41): _is_wide_open(), Contêiner deixado aberto DE PROPÓSITO: `state.fechado` declarado como false.…, MotorError, Exception, Erro operacional do Motor com mensagem legível., craftable_entities(), get_character(), get_entity_detail() (+33 more)

### Community 8 - "trabalho.py"
Cohesion: 0.10
Nodes (41): abrir_sessao(), _arquivo_de(), atualizar(), concluido(), creditar_e_fechar(), encerrar(), esforco_pronto(), _grava_bloco() (+33 more)

### Community 9 - "frontmatter.py"
Cohesion: 0.09
Nodes (32): _clean_lines(), dump(), _dump_flow_list(), _dump_mapping(), _dump_scalar(), _dump_sequence(), _is_scalar_list(), join() (+24 more)

### Community 10 - "registro.py"
Cohesion: 0.08
Nodes (25): _iw_promise(), DECLARAÇÃO + CORPO da tool de COMPROMISSO (spec 038, L3). promise — migrada de…, _cook(), _iw_cook(), DECLARAÇÃO + CORPO da tool de COZINHAR (spec 048). `cook` combina N…, _iw_craft(), DECLARAÇÃO + CORPO da tool `craft` (spec 057). `craft` cria item, object OU…, _iw_kindle() (+17 more)

### Community 11 - "craft/executores.py"
Cohesion: 0.11
Nodes (32): _craft(), O corpo de `craft`. Dois caminhos, molde EXATO de `_forjar` (spec 052): -…, _abrir(), _apply_craft_ops(), _gerar_route_de_acesso(), _h_craft(), _memoria_ator(), _posicao_e_peso_kg() (+24 more)

### Community 12 - "memoria/__init__.py"
Cohesion: 0.10
Nodes (33): _apply_accuse(), _apply_rest_ops(), _h_accuse(), _h_dormir(), Path, O Motor / memoria — EXECUTORES (item 31 §3: DDD por domínio). `_apply_*_ops` +…, Por op (`alvo`, `memoria_id`): valida que a memória referenciada é da PRÓPRIA…, Duas ações, não um alternador (item 50). A intenção vem no `op` da própria op —… (+25 more)

### Community 13 - "memoria/primitivas.py"
Cohesion: 0.18
Nodes (32): _char_name(), O Motor / memoria — PRIMITIVAS (item 31 §3: DDD por domínio). Funções puras…, Memória de USO da arma (spec 016 §3a) — à parte do golpe, e `small`., Memória nova nos DOIS lados de um resgate bem-sucedido (spec 032) — além do…, Persuadir a dar (spec 023): quem DOOU foi o ALVO, não o ator que persuadiu.…, Furto (spec 023): o FLAGRANTE deixa no DONO memória NEGATIVA `large` dirigida…, O outro lado do reconto: o que QUEM CONTOU guarda de ter contado. Item 52:…, A mudança de estado EM LINGUAGEM DE MUNDO (item 52.6). Era `f"Mudou em mim:… (+24 more)

### Community 14 - "forja/executores.py"
Cohesion: 0.14
Nodes (30): _abrir(), _apply_forja_ops(), _h_forja(), _memoria_peca(), Path, O Motor / forja — EXECUTORES (item 31 §3: DDD por domínio; spec 052).…, Continuar (ou terminar) uma peça. NENHUMA chamada ao Árbitro, nunca., A PROCEDÊNCIA: a peça guarda quem passou por ela (spec 052, FR-036). É… (+22 more)

### Community 15 - "arbiter.py"
Cohesion: 0.09
Nodes (27): build_ctx(), build_tools(), _context_for_prompt(), _item_entry(), _json_objects(), _loads_lenient(), normalize(), _pertence_a() (+19 more)

### Community 16 - "app.py"
Cohesion: 0.08
Nodes (21): _claim_turn(), _dedupe_por_id(), fate_twists(), inworld_failures(), _MundoLocal, nomear_sujeito(), _passo_nao_dado(), Server-side do Loreforge — A FRONTEIRA entre client e mundo. (Este módulo já se… (+13 more)

### Community 17 - "Handler"
Cohesion: 0.18
Nodes (7): Handler, POST /api/mcp — o Model Context Protocol sobre HTTP (spec 043). É O CAMINHO DA…, POST /api/registro — a metade do turno que SÓ O CONECTOR sabe. Canal PRÓPRIO,…, POST /api/tools/<nome> — a BANCADA DO MANTENEDOR (spec 043). Uma rota por…, A PROPOSTA, resolvida — o caminho único dos dois transportes. A ordem importa e…, Recusa in-world de agir por quem está caído, ou None se ele pode agir. O client…, BaseHTTPRequestHandler

### Community 18 - "intencoes/executores.py"
Cohesion: 0.14
Nodes (20): _apply_promise(), _h_promise(), Path, O Motor / compromisso — EXECUTORES (item 31 §3: DDD por domínio).…, Aplica cada op de `promise_ops`: puramente verbal — memória nos dois lados…, O Motor / compromisso (pacote, item 31 §3) — fachada do domínio. Reexporta a…, _h_intentions(), O Motor / intencoes — EXECUTORES (item 31 §3: DDD por domínio). `_apply_*_ops`… (+12 more)

### Community 19 - "selftest_helpers.py"
Cohesion: 0.08
Nodes (9): Helper compartilhado dos selftests (spec 045) — substitui…, Substitui `resolve_with_tools(intent, context, scripted_loop(script, ...))`.…, resolve_scripted(), Auto-teste da Fase 23 — Turno de fase única (spec 020). Dirige…, Roda o roteiro via selftest_helpers e devolve (outcome, por_nome), onde…, rodar(), Auto-teste da Fase 7 — Equipamentos, Partes do Corpo e Física (spec 004). Cobre…, Auto-teste da Fase 8 — Contêineres Abertos/Fechados e Travas (spec 005). Cobre… (+1 more)

### Community 20 - "_rejection"
Cohesion: 0.14
Nodes (21): _apply_cura_ops(), _h_cura(), Path, O Motor / cura — EXECUTORES (item 31 §3: DDD por domínio). `_apply_*_ops` +…, Executor AUTO-SUFICIENTE (spec 025): lê a própria cena fresca e valida o alvo…, O Motor / cura (pacote, item 31 §3) — fachada do domínio. Reexporta a API por…, O Motor / cura — PRIMITIVAS (item 31 §3: DDD por domínio). Funções puras…, Devolve (banda, roll_info). banda ∈ {'baixa', 'media', 'alta'}. Nota 0-10 =… (+13 more)

### Community 21 - "_is_alive"
Cohesion: 0.15
Nodes (24): dono(), _expire_memories(), _forget_memories(), get_active_memories(), _is_alive(), memory_involved(), memory_kind(), _memory_salience() (+16 more)

### Community 22 - "validator.py"
Cohesion: 0.14
Nodes (22): World Validator — checagem de schema pura, sem LLM (camada zero). Princípio VI:…, Valida um frontmatter de entidade. Retorna lista de erros (vazia = ok)., Tamanho do lugar (spec 012): é dele que sai o tempo de atravessar., Intenção (spec 026): compromisso/plano de médio-longo prazo, mutável no lugar.…, Checagem leve e comum a item/object: 'interactions' é opcional e consultivo…, Fecho e travas (spec 005): `state.fechado` bool e bloco `locks` com listas…, O bloco `trabalho` — comum a item e object desde a spec 053. Extraído de…, A PEÇA EM PROCESSO e a BANDA de qualidade (spec 052). Nenhum dos dois é campo… (+14 more)

### Community 23 - "get_context"
Cohesion: 0.15
Nodes (22): grasp_slot_of(), Capacidade de um valor de slot: `int` cru, ou o `capacidade` da forma rica…, Quantas peças o corpo deste personagem comporta neste slot (0 se não tem)., O slot de PEGA do corpo: onde os itens pegos/recebidos vão (spec 019). A mão do…, _slot_cap(), slot_capacity(), esta_extinto(), _is_valid() (+14 more)

### Community 24 - "selftest_phase11.py"
Cohesion: 0.11
Nodes (15): attach(), attack(), char_folder(), detach(), Path, Auto-teste da Fase 11 — Teste Oposto de Combate (spec 008). Cobre, com rolagem…, Acopla um item da cena ao corpo do personagem (montagem de cenário)., Devolve o item ao chão da taverna, sem slot. (+7 more)

### Community 25 - "selftest_phase14.py"
Cohesion: 0.13
Nodes (15): chao(), dar(), digital(), dono(), guardar(), ifolder(), marcar(), negociar() (+7 more)

### Community 26 - "selftest_phase35.py"
Cohesion: 0.13
Nodes (14): adianta(), andar(), _ask(), chega(), mems_de(), onde(), pasta(), planta_familiaridade() (+6 more)

### Community 27 - "llm.py"
Cohesion: 0.13
Nodes (18): build_ask(), O transporte do JUÍZO (spec 043) — `ask(system, user) -> str`, de um tiro.…, anthropic_chat(), LLMError, make_anthropic_fn(), make_ollama_fn(), make_openrouter_fn(), ollama_chat() (+10 more)

### Community 28 - "selftest_phase15.py"
Cohesion: 0.13
Nodes (16): inworld_effects(), O que REALMENTE aconteceu, em linguagem de mundo, para A Mente narrar.…, acontecimentos_de(), canal(), check(), _limpa(), mems(), Auto-teste da Fase 15 — Memória com Classes (spec 013). Cobre: -… (+8 more)

### Community 29 - "name_of"
Cohesion: 0.14
Nodes (11): _iw_lock(), DECLARAÇÃO + CORPO das tools de CONTÊINER (spec 038, L3). open/close — MESMO…, _iw_carry(), _iw_expel(), _iw_persuade(), _iw_travel(), DECLARAÇÃO + CORPO das tools de DESLOCAMENTO (spec 038, L3). enter_route,…, _iw_mutate() (+3 more)

### Community 30 - "selftest_phase17.py"
Cohesion: 0.12
Nodes (10): _anexar(), anotar_corpo(), anotar_proposta(), O REGISTRO DO TURNO — append-only, e INVISÍVEL PARA O JOGO (spec 044). Uma…, A metade que SÓ O CONECTOR sabe — o racional, o modelo, o custo. Chega por…, Nome de arquivo seguro. Um `character_id` vem de fora; sem isto, um id com…, A metade que O MUNDO sabe, escrita no CAMINHO ÚNICO (`resolver_proposta`). Um…, _slug() (+2 more)

### Community 31 - "selftest_phase12.py"
Cohesion: 0.15
Nodes (15): bring_back(), char_folder(), drop(), item_folder(), Path, Auto-teste da Fase 12 — Velocidade de Viagem por Item Vestido (spec 009).…, Devolve o item ao chão da taverna, sem slot., Entra na rota, lê o tempo aplicado e devolve o personagem à taverna. (+7 more)

### Community 32 - "selftest_phase13.py"
Cohesion: 0.15
Nodes (11): carry(), cfm(), cfolder(), give_item(), knock_down(), patch_char(), Path, Auto-teste da Fase 13 — Carregar e Arrastar Personagem (spec 010). Cobre, com… (+3 more)

### Community 33 - "inworld"
Cohesion: 0.14
Nodes (14): _iw_butcher(), DECLARAÇÃO + CORPO da tool de ESQUARTEJAR (spec 050). `butcher` extrai carne de…, _brew(), _iw_brew(), DECLARAÇÃO + CORPO da tool de PREPARAR (spec 055). `brew` combina N…, _heal(), _iw_cura(), DECLARAÇÃO + CORPO da tool de CURA (spec 038, L3). `heal` migrada de… (+6 more)

### Community 34 - "fogo/executores.py"
Cohesion: 0.19
Nodes (15): _apply_fogo_ops(), _h_fogo(), _lista(), Path, O Motor / fogo — EXECUTORES (item 31 §3: DDD por domínio; spec 053).…, a, b e c" — nomes legíveis, nunca ids (spec 053). Um personagem não lembra de…, O QUANTO foi notável — do dado, sem NENHUM número (Princípio V). A memória é o…, Acender fogo (spec 053). O gate de admissão (combustibilidade) rejeita — COM… (+7 more)

### Community 35 - "itens/declaracao.py"
Cohesion: 0.16
Nodes (16): _drop(), _eat(), _equip(), _give(), _item_setup(), _iw_drink(), _iw_eat(), _iw_equip() (+8 more)

### Community 36 - "juizo.py"
Cohesion: 0.11
Nodes (4): O Motor / juizo — a primitiva do JUÍZO (spec 043). NÍVEL 0. O VOCABULÁRIO…, LABORATÓRIO DE LETRA — `sing`, QUINTA LEVA: o contrato final. A quarta leva…, LABORATÓRIO DE RÉGUA — `sing`, EXPERIMENTO 4: quem julga a plateia? Complementa…, LABORATÓRIO DE RÉGUA — `sing`, SEGUNDA LEVA (spec 058). A primeira leva…

### Community 37 - "selftest_phase59.py"
Cohesion: 0.12
Nodes (10): _corpo(), _mk_instrumento(), _mk_item_cena(), _mk_item_guardado(), _mk_memoria(), pasta(), Path, Auto-teste da Fase 59 — Escrever (spec 059). Sem modelo/LLM ligado para a maior… (+2 more)

### Community 38 - "conhecimento/declaracao.py"
Cohesion: 0.13
Nodes (11): _ask_about(), _assunto_legivel(), _conta_o_que_lembra(), _iw_hearsay(), _iw_learn(), _iw_unanswered(), _iw_write(), DECLARAÇÃO + CORPO das tools de CONHECIMENTO (spec 038, L3).… (+3 more)

### Community 39 - "_write_memory"
Cohesion: 0.15
Nodes (17): _iter_memories_in(), Path, Frontmatter das memórias de uma PASTA qualquer, vivas e vencidas. Genérica por…, Grava uma memória na pasta de quem lembra. Ponto único de escrita. `evento`…, A mesma escala de `_insistencia`, com o VERBO de quem chama. `_insistencia`…, UMA memória por assunto que SE REPETE — renovada, nunca duplicada. Generaliza o…, Cria OU renova a memória de rota — nunca duplica (spec 013, FR-008). Esta é a…, Grava no ouvinte a memória de RECONTO — UMA, do conjunto das fontes (spec 017,… (+9 more)

### Community 40 - "selftest_phase32.py"
Cohesion: 0.12
Nodes (6): dar(), _dormir_noite_inteira(), ifolder(), Path, Auto-teste da Fase 32 — Fadiga como recurso + réguas moduladas (spec 030,…, spec 031: `dormir` virou alternador (iniciar/acordar) — os testes desta fase…

### Community 41 - "selftest_phase50.py"
Cohesion: 0.14
Nodes (10): cooking_de(), _forcar_pronto(), _mk_item(), _mk_object(), panela_de(), Path, Auto-teste da Fase 50 — Cozinhar (spec 048, US1+US2+US3+US4). Sem modelo/LLM…, Backdate `pronto_ts` pro passado — mesmo truque que outros testes de resolução… (+2 more)

### Community 42 - "comercio/declaracao.py"
Cohesion: 0.13
Nodes (13): _attack(), _iw_attack(), DECLARAÇÃO + CORPO da tool de COMBATE (spec 038, L3). `attack` migrada de…, _buy_trade(), _iw_persuade_give(), _iw_trade(), _persuade_give(), DECLARAÇÃO + CORPO das tools de COMÉRCIO (spec 038, L3). ask_wares… (+5 more)

### Community 43 - "_fail"
Cohesion: 0.24
Nodes (13): _apply_lock_ops(), _h_lock(), Path, O Motor / conteiner — EXECUTORES (item 31 §3: DDD por domínio). `_apply_*_ops`…, Aplica open/close (`lock_ops`) da fase pedida ("open" roda antes das…, O Motor / conteiner (pacote, item 31 §3) — fachada do domínio. Reexporta a API…, check_trava_item(), _find_lockable() (+5 more)

### Community 44 - "herbario/executores.py"
Cohesion: 0.23
Nodes (13): _apply_forage_ops(), _h_forage(), Path, O Motor / herbario — EXECUTORES (item 31 §3: DDD por domínio; spec 054).…, Colher (spec 054). Os dois GATES (herbabilidade, riqueza) rejeitam — COM…, O Motor / herbario (pacote, item 31 §3) — fachada do domínio (spec 054).…, porcoes_de_erva(), O Motor / herbario — PRIMITIVAS (item 31 §3: DDD por domínio; spec 054).… (+5 more)

### Community 45 - "musica/executores.py"
Cohesion: 0.23
Nodes (13): _apply_sing_ops(), _h_sing(), Path, O Motor / musica — EXECUTORES (item 31 §3: DDD por domínio; spec 058).…, Cantar (spec 058). Por op (`memoria_id`, `instrumento`, `letra`,…, O Motor / musica (pacote, item 31 §3) — fachada do domínio (spec 058).…, bonus_instrumento(), degraus_por_desfecho() (+5 more)

### Community 46 - "selftest_phase18.py"
Cohesion: 0.17
Nodes (10): dados(), ensinar(), limpar_memorias(), montar_mundo(), pasta(), prosa_de(), Auto-teste da Fase 18 — Perguntar o Caminho a Alguém (spec 015). Cobre: - o…, Uma op de aprendizado por CONVERSA, com a citação tirada da prosa real. (+2 more)

### Community 47 - "selftest_phase49.py"
Cohesion: 0.16
Nodes (6): item_fm_body(), _mk_item(), _mk_object(), object_raw(), Path, Auto-teste da Fase 49 — Beber (spec 047, US1+US2+US3+US4+US5). Sem modelo/LLM…

### Community 48 - "selftest_phase56.py"
Cohesion: 0.17
Nodes (9): _forcar_pronto(), _hash(), _mk_item(), _mk_object(), peca_de(), preparando_de(), Path, Auto-teste da Fase 56 — Preparar (spec 055, US1+US2+US3). Sem modelo/LLM ligado… (+1 more)

### Community 49 - "sondagem_sing_letra.py"
Cohesion: 0.22
Nodes (13): ancora(), ask(), base_de(), cita_cena(), eco4(), novos_nomes(), palavras(), payload() (+5 more)

### Community 50 - "acougue/executores.py"
Cohesion: 0.25
Nodes (11): _apply_esquartejar_ops(), _h_esquartejar(), Path, O Motor / acougue — EXECUTORES (item 31 §3: DDD por domínio; spec 050).…, Esquartejar (spec 050). Os dois GATES (esquartejabilidade, rendimento) rejeitam…, O Motor / acougue (pacote, item 31 §3) — fachada do domínio (spec 050).…, porcoes_de_carne(), O Motor / acougue — PRIMITIVAS (item 31 §3: DDD por domínio; spec 050). Funções… (+3 more)

### Community 51 - "botica/executores.py"
Cohesion: 0.25
Nodes (11): _apply_botica_ops(), _h_botica(), Path, O Motor / botica — EXECUTORES (item 31 §3: DDD por domínio; spec 055).…, Preparar (spec 055). Os dois GATES de admissão (recipiente, preparabilidade)…, O Motor / botica (pacote, item 31 §3) — fachada do domínio (spec 055).…, duracao_segundos_preparo(), O Motor / botica — PRIMITIVAS (item 31 §3: DDD por domínio; spec 055). Funções… (+3 more)

### Community 52 - "cozinha/executores.py"
Cohesion: 0.25
Nodes (11): _apply_cozinha_ops(), _h_cozinha(), Path, O Motor / cozinha — EXECUTORES (item 31 §3: DDD por domínio; spec 048).…, Cozinhar (spec 048). Os dois GATES de admissão (fonte de calor,…, O Motor / cozinha (pacote, item 31 §3) — fachada do domínio (spec 048).…, duracao_segundos(), O Motor / cozinha — PRIMITIVAS (item 31 §3: DDD por domínio; spec 048). Funções… (+3 more)

### Community 53 - "openapi.py"
Cohesion: 0.22
Nodes (12): _capacidades(), _classe(), gerar(), _paths(), _q(), OpenAPI 3.1 GERADO do código — a fronteira HTTP e o catálogo de capacidades.…, ESCOLHA · VOZ · JUIZO · SISTEMA — as quatro classes da spec 043. O JUÍZO sai da…, Uma entrada por capacidade: descrição player-facing + params classificados. (+4 more)

### Community 54 - "sanea_duplicatas.py"
Cohesion: 0.30
Nodes (13): _chave_de_escolha(), _duplicados(), _itens(), _itens_duplicados(), main(), _mem_ts(), _memorias(), _nascimento() (+5 more)

### Community 55 - "analisa_rodada.py"
Cohesion: 0.24
Nodes (12): cadeias(), familia(), _instante_local(), le_devlog(), main(), Path, Relatório de uma RODADA de um personagem — os números que a análise usa. Nasceu…, Recorta os turnos DESTE personagem, com a janela correta (até a próxima… (+4 more)

### Community 56 - "face.py"
Cohesion: 0.21
Nodes (10): _alvos(), build(), _consultas(), _gate_de_caido(), A FACE EXPOSTA — o que o personagem enxerga que pode tentar AQUI (spec 043). O…, A LANE DE CONSULTA na face (spec 040, lane paralela) — o que a Mente pode…, Os alvos possíveis por parâmetro — só o que EXISTE na cena, agora. Vem do enum…, A face da cena para A Mente. Lista vazia é resposta legítima (caído/morto).… (+2 more)

### Community 57 - "julgamento"
Cohesion: 0.19
Nodes (12): _butcher(), _write(), _drink(), julgamento(), Escapa `\\n`/`\\r`/`\\t` CRUS que estejam DENTRO de uma string JSON, antes do…, Várias notas NOMEADAS (e, opcionalmente, um ou mais textos) na MESMA resposta —…, _sanear_quebras_em_string(), ask() (+4 more)

### Community 58 - "fatos.py"
Cohesion: 0.19
Nodes (10): Fato, _matches(), publish(), O Motor / fatos (spec 038, L1) — o BARRAMENTO DE FATOS. O 5º ancoradouro…, Uma op aplicada/rejeitada, auto-descritiva (data-model.md). `status` =…, Registra um subscriber transversal. `kinds`: str, tupla de str, ou "*"/None…, Publica o fato: roda cada reação interessada, na ordem de registro, e ACUMULA…, reacao() (+2 more)

### Community 59 - "selftest_phase51.py"
Cohesion: 0.15
Nodes (5): _mk_item(), Path, Auto-teste da Fase 51 — Fome e sede aumentam com o tempo real (spec 049,…, Simula 'avançar o relógio': escreve *_ts/*_note direto no frontmatter, fora do…, set_status_field()

### Community 60 - "base.py"
Cohesion: 0.21
Nodes (10): _arb_deny(), build_face(), manifest(), Camada TOOLS (item 31 §3) — BASE compartilhada do pacote por domínio. Os…, Recusa de tool ARBITRADA vinda do executor (item 31 §2). SEMPRE registra em…, Registra a função como handler de uma ou mais tools (o canal Open/Closed do…, Builder de FACE GENÉRICO (spec 038, T021): monta o dict do manifest de UMA tool…, Registra a FACE da tool (o dict do manifest do turno). Co-localizada com o… (+2 more)

### Community 61 - "mcp_core.py"
Cohesion: 0.21
Nodes (9): _frase(), O NÚCLEO do Model Context Protocol — comum aos dois transportes (spec 043). O…, Uma linha de mundo, venha ela como texto ou como registro estruturado.…, O que voltou, em linguagem de mundo — nunca a nota, nunca a rolagem., Trata UMA mensagem JSON-RPC. Devolve a lista de mensagens a emitir (a resposta,…, resumo(), _texto(), tratar() (+1 more)

### Community 62 - "mcp_server.py"
Cohesion: 0.24
Nodes (7): _escrever(), main(), Mundo, Model Context Protocol sobre stdio — a fronteira ABERTA (spec 043, Fase 8).…, O transporte HTTP para o server do mundo. A única porta deste módulo., O laço stdio. A tradução JSON-RPC mora em `mcp_core` — este arquivo é só o…, servir()

### Community 63 - "ativacao.py"
Cohesion: 0.26
Nodes (11): active_tool_ids(), _ids(), is_active(), _manifest(), orphan_tool_ids(), O Motor / ativacao (spec 038, US2) — o Manifesto de Ativação de tools por-…, Conjunto de ids de tools ATIVAS neste mundo, ou None = TODAS (default).…, A tool `name` é oferecida/resolvível neste mundo? (None = todas ⇒ True.) (+3 more)

### Community 64 - "hunger_label"
Cohesion: 0.17
Nodes (12): _horas_ate_com_fome(), _horas_ate_com_sede(), _horas_ate_faminto(), _horas_ate_sedento(), hunger_label(), _hunger_note_de(), 3 estágios a partir do tempo real decorrido desde `ts`, contra dois limiares…, O que ele SENTE de fome, em rótulo canônico. Com `status.hunger_ts` presente… (+4 more)

### Community 65 - "is_closed"
Cohesion: 0.23
Nodes (11): is_closed(), Contêiner fechado (spec 005). Ausência do campo ⇒ aberto (legado)., deadlock_warnings(), migration_warnings(), O Motor / validador (spec 021 — extraído de __init__). Parte do pacote em…, Aviso AUTORAL (spec 005): contêiner fechado cuja trava de abertura exige um…, Ids do manifesto de ativação (spec 038, US2) que não casam nenhuma tool…, Todos os avisos não-fatais do mundo: migração (spec 004) + deadlock autoral… (+3 more)

### Community 66 - "_record_witness"
Cohesion: 0.17
Nodes (12): _derive_observer_valence(), fatigue_penalty(), _perceive_dc(), DC de percepção de uma testemunha para um ato FURTIVO (spec 024). Inverte a…, Traduz o outcome nas cenas testemunháveis (spec 024). Cada fato: envolvidos (a…, O LEQUE (spec 024): espalha memória factual pelos presentes que PERCEBEM. Roda…, VALÊNCIA RELATIVA AO OBSERVADOR (spec 041): como uma testemunha passa a sentir…, A penalidade determinística que a fração de fadiga aplica a uma rolagem… (+4 more)

### Community 67 - "sentiment_toward"
Cohesion: 0.18
Nodes (12): familiarity_with(), has_trauma_from(), memory_valence(), Intensidade da memória de testemunha, modulada pelo AFETO/FAMILIARIDADE (spec…, `quem_id` guarda um TRAUMA GRAVE vivo às mãos de `agressor_id`? O portão é…, Soma as memórias de `character_id` que envolvem `target_id`. `signed=False` →…, APEGO: quanto algo/alguém importa, pelo VOLUME de lembranças que o envolvem.…, AFETO: para que lado a relação pende — a mesma soma de `familiarity_with`,… (+4 more)

### Community 68 - "selftest_phase16.py"
Cohesion: 0.21
Nodes (7): adianta(), onde(), Auto-teste da Fase 16 — Viagem Longa por Caminho Conhecido (spec 012). Cobre: -…, Empurra o prazo do trânsito atual para o passado e deixa o mundo avançar., Deixa a viagem correr até acabar, devolvendo os lugares visitados., tempo_de_um_trajeto(), viajar_ate_parar()

### Community 69 - "selftest_phase26.py"
Cohesion: 0.17
Nodes (5): _planta_memoria_crime(), Auto-teste da Fase 26 — steal: roubar (spec 023, US2). Rolagem forçada…, Planta uma memória de prática de furto (spec 029/051) sem passar por um furto…, O dono guarda memória de furto (stolen, large, negativa) do ladrão?, _tem_memoria_furto()

### Community 70 - "selftest_phase29.py"
Cohesion: 0.20
Nodes (6): dar(), dono(), ifolder(), Path, Auto-teste da Fase 29 — Compromisso Lembrado (spec 027). Sem nenhum modelo/LLM…, Sobe a cadeia de pastas até achar um character.md (molde de selftest_phase14).

### Community 71 - "selftest_phase48.py"
Cohesion: 0.18
Nodes (4): item_fm_body(), _mk_item(), Path, Auto-teste da Fase 48 — Comer (spec 046, US1+US2+US3). Sem modelo/LLM ligado —…

### Community 72 - "selftest_phase53.py"
Cohesion: 0.23
Nodes (7): _forcar_d20(), forge_op(), _forja_completa(), _mk_item(), peca_de(), Auto-teste da Fase 53 — Forjar equipamento (spec 052, US1..US6). Sem modelo/LLM…, Abre, conclui e devolve o frontmatter final da peça.

### Community 73 - "sondagem_sing_letra2.py"
Cohesion: 0.21
Nodes (6): ancora(), eco4(), julgar(), palavras(), LABORATÓRIO DE LETRA — `sing` (spec 058), QUARTA LEVA: o parser era o gargalo.…, sanear()

### Community 74 - "auth.py"
Cohesion: 0.24
Nodes (10): _b64url_decode(), _b64url_encode(), jwt_decode(), jwt_encode(), Base64Url encoding without padding., Base64Url decoding, automatically adding missing padding., Creates a JWT token with HS256 signature using Python stdlib. No expiration…, Decodes and verifies JWT signature. Returns payload dict or None if invalid. (+2 more)

### Community 75 - "selftest_phase43.py"
Cohesion: 0.31
Nodes (10): _expel(), Pôr OUTRO para fora à força (spec 041). Guarda: alvo≠ator, presente, rota parte…, check(), _force_roll(), _local(), _mk_char(), _presentes(), Auto-teste da Fase 43 — Expulsar (spec 041), fatia MOVIMENTO (US1/US2) + dedup.… (+2 more)

### Community 76 - "selftest_phase30.py"
Cohesion: 0.22
Nodes (6): dar(), ifolder(), last_evento(), memories(), Path, Auto-teste da Fase 30 — Acusar (spec 028). Sem nenhum modelo/LLM — exercita o…

### Community 77 - "selftest_phase34.py"
Cohesion: 0.18
Nodes (3): _derrubar(), Auto-teste da Fase 34 — Cura e socorro (spec 032, US1+US2+US3). Sem nenhum…, Deixa cid em hp=0, incapacitado — sem passar por combate de verdade (o QUE…

### Community 78 - "selftest_phase52.py"
Cohesion: 0.18
Nodes (3): carnes_da(), Path, Auto-teste da Fase 52 — Esquartejar (spec 050, US1+US2+US3). Sem modelo/LLM…

### Community 79 - "selftest_phase55.py"
Cohesion: 0.20
Nodes (4): _hash(), _mk_object(), Path, Auto-teste da Fase 55 — Colher (spec 054, US1+US2+US3). Sem modelo/LLM ligado —…

### Community 80 - "selftest_phase57.py"
Cohesion: 0.22
Nodes (6): em_processo_de(), _mk_item(), _mk_object(), peca_de(), Path, Auto-teste da Fase 57 — Craft genérico (spec 057, US1+US2+US3). Sem modelo/LLM…

### Community 81 - "selftest_phase58.py"
Cohesion: 0.22
Nodes (5): _mk_memoria(), pasta(), _proficiencia_alta(), Auto-teste da Fase 58 — Cantar o feito (spec 058). Sem modelo/LLM ligado —…, Empurra `proficiencies_for(cid)['musica']` bem acima de 0, via memórias reais…

### Community 82 - "sondagem_formato_payload.py"
Cohesion: 0.20
Nodes (9): f_json_compacto(), f_json_indent(), f_linhas(), f_prosa(), f_tabular(), O FORMATO DO PEDIDO — dá pra gastar menos token com resultado igual ou melhor?…, Uma linha por fato, `chave: valor` — sem chaves, colchetes nem aspas., As LISTAS viram tabela: o cabeçalho aparece UMA vez, não por linha. É o… (+1 more)

### Community 83 - "devlog.py"
Cohesion: 0.22
Nodes (7): finalize_turn(), FECHA o turno e monta o outcome — comum aos DOIS caminhos (spec 043). Extraído…, log(), Log de desenvolvimento — terminal do server + arquivo persistente. Mostra o…, Registra um POST **por inteiro, reproduzível como curl** (spec 053). POR QUE…, requisicao(), Auto-teste da Fase 6 — Árbitro com Tool Calling (spec 003). Cobre (tudo com…

### Community 84 - "input_schema"
Cohesion: 0.20
Nodes (7): input_schema(), O schema de uma capacidade, no formato que um host MCP entende. Os alvos viram…, _descricoes_antigas(), montar(), A RÉGUA DA RELEVÂNCIA — a description mais enxuta escolhe igual ou melhor? A…, As descrições de ANTES, lidas do git — nunca de uma cópia à mão que envelhece…, tools_de()

### Community 85 - "selftest_phase10.py"
Cohesion: 0.22
Nodes (5): bring_back(), persuade(), Auto-teste da Fase 10 — Persuadir Personagem a Se Mover (spec 007). Cobre, com…, Devolve um persuadido da rota à taverna (manutenção de cenário do teste)., res()

### Community 86 - "selftest_phase20.py"
Cohesion: 0.24
Nodes (4): limpar(), pasta(), Auto-teste da Fase 20 — Boato e Reputação (spec 017). Cobre: - GRAVAÇÃO: 1º→2º…, ult_mem()

### Community 87 - "selftest_phase25.py"
Cohesion: 0.20
Nodes (3): _mk_item(), Path, Auto-teste da Fase 25 — persuade_give: convencer a DAR um item (spec 023, US1).…

### Community 88 - "selftest_phase33.py"
Cohesion: 0.20
Nodes (3): _backdate_descansando_desde(), Auto-teste da Fase 33 — Duração real de dormir/descansar (spec 031,…, Simula tempo real decorrido sem esperar de verdade — mesmo truque que testes de…

### Community 89 - "selftest_phase37.py"
Cohesion: 0.24
Nodes (7): _mk_char(), _mk_item(), _mk_object(), Path, Auto-teste da Fase 37 — Pertencimento por memória (spec 036, US4). Sem nenhum…, Crafta uma memória de reivindicação diretamente em disco — testa o lado de…, _write_owner_memory()

### Community 90 - "selftest_phase46.py"
Cohesion: 0.27
Nodes (6): check(), MundoFalso, Auto-teste da Fase 46 — o Model Context Protocol (spec 043, Fase 8). (Número de…, Roda o laço do servidor sobre um stdin de mentira; devolve as mensagens., _rodar(), run()

### Community 91 - "Sessao"
Cohesion: 0.33
Nodes (4): O que precisa mudar para o host relistar: nomes e alvos, não a prosa., A cena mudou desde a última listagem? LIMITAÇÃO HONESTA: a checagem é…, Uma sessão = UM personagem. Um host não passa "de quem é o turno" em…, Sessao

### Community 92 - "migra_rotas.py"
Cohesion: 0.36
Nodes (8): _ancestral_comum(), levantar(), _lugares(), main(), Path, Move cada ROTA para a estrutura que contém as duas pontas dela. O QUE ESTAVA…, id de lugar -> pasta., A menor pasta que contém as duas. Se uma contém a outra, é ela mesma.

### Community 93 - "memoria/declaracao.py"
Cohesion: 0.22
Nodes (5): _iw_accuse(), _iw_rest(), DECLARAÇÃO + CORPO das tools de MEMÓRIA (spec 038, L3). create_memory + sleep…, O corpo de `sleep` e o de `wake_up` — DOIS corpos, um molde. Item 50 (decisão…, _rest()

### Community 94 - "apply_op"
Cohesion: 0.25
Nodes (9): get(), O handler do canal, ou None se não há tool para ele., A conclusão PREGUIÇOSA do relógio de ESFORÇO (revisão pós-057) — molde de…, resolver_esforco_pendente(), apply_op(), _publish_facts(), Path, A PORTA ÚNICA de UMA ação (spec 025, 021 Fase C): aplica-e-registra uma op.… (+1 more)

### Community 95 - "selftest_phase27.py"
Cohesion: 0.25
Nodes (4): _mems(), Auto-teste da Fase 27 — memória de testemunha: a cena tem plateia (spec 024).…, cid guarda memória de testemunha contendo `trecho`?, _viu()

### Community 96 - "selftest_phase31.py"
Cohesion: 0.28
Nodes (6): dar(), ifolder(), last_domain(), memories(), Path, Auto-teste da Fase 31 — Domínio da Memória (spec 029). Sem nenhum modelo/LLM —…

### Community 98 - "selftest_phase21.py"
Cohesion: 0.29
Nodes (5): limpar(), pasta(), Auto-teste da Fase 21 — Reconhecer pela Vivência (spec 018). Cobre: - a LEITURA…, Há algum float/int (não-bool) em qualquer profundidade? (sigilo do número), tem_numero()

### Community 100 - "sondagem_cadeia_sussurro.py"
Cohesion: 0.36
Nodes (7): _chat(), main(), _payload(), O SUSSURRO QUE PEDE UMA CADEIA — a Mente encadeia, ou faz só o primeiro passo?…, O mesmo recorte de `_contextoPayload(context, {comCapacidades:false})`., A face REAL, no formato OpenAI que o adaptador do Ollama exige., _tools()

### Community 101 - "sondagem_parada_do_laco.py"
Cohesion: 0.25
Nodes (4): call(), O laço PARA sozinho? Simula continuar-no-sucesso até a Mente não pedir mais…, LABORATÓRIO DE DESCRIPTION — `sing` (spec 058), a FACE que desce à Mente. Molde…, tools()

### Community 102 - "sondagem_sing_regua.py"
Cohesion: 0.25
Nodes (3): LABORATÓRIO DE RÉGUA — `sing` (spec 058). Diferente de…, As quatro estruturas de nota do E1 (todas com o MESMO contrato de letra)., variantes()

### Community 103 - "selftest_phase38.py"
Cohesion: 0.29
Nodes (5): Call, _called_name(), _is_core(), Auto-teste da Fase 38 — Fronteira Primitiva × Tool (spec 037, Princípio XII).…, Executor de tool: `_apply_*_ops` ou o core de transferência…

### Community 104 - "_insistencia"
Cohesion: 0.43
Nodes (6): _corpo_base(), main(), Funde as memórias `unanswered` duplicadas — uma por ASSUNTO (item 53.4). POR…, O texto SEM a cláusula de insistência — para reagrupar uma migração já rodada…, _insistencia(), Como o personagem LEMBRA de ter repetido — em linguagem de mundo, nunca um…

### Community 105 - "selftest_phase19.py"
Cohesion: 0.38
Nodes (4): limpar(), pasta(), Auto-teste da Fase 19 — Memória Ligada a Tudo: Apego e Afeto (spec 016). Cobre:…, registrar()

### Community 107 - "levantar"
Cohesion: 0.40
Nodes (5): levantar(), main(), Path, Move os RASTROS de pasta-por-registro para uma pasta de rastros por estrutura.…, (origem, destino) de cada rastro ainda no formato antigo.

### Community 108 - "forja/declaracao.py"
Cohesion: 0.33
Nodes (4): _forjar(), _iw_forja(), DECLARAÇÃO + CORPO das tools de FORJAR (spec 052). `forge_weapon` e…, O corpo ÚNICO das duas tools. `tipo` ∈ {'arma', 'armadura'}. Dois caminhos, e a…

### Community 109 - "musica/declaracao.py"
Cohesion: 0.40
Nodes (4): _iw_sing(), DECLARAÇÃO + CORPO da tool de CANTAR (spec 058). Cantar não é cozinhar: não há…, _regua_sing(), _sing()

### Community 110 - "selftest_phase28.py"
Cohesion: 0.40
Nodes (3): _files(), _intentions_dir(), Auto-teste da Fase 28 — Intenções Persistentes (spec 026, US1). Sem nenhum…

### Community 111 - "selftest_phase40.py"
Cohesion: 0.40
Nodes (4): _make_world(), probe(), Path, Auto-teste da Fase 40 — US2 do item 038: ativação de tools por-mundo (SC-005).…

### Community 112 - "selftest_phase42.py"
Cohesion: 0.47
Nodes (5): check(), Auto-teste da Fase 42 — Tools de Consulta da Mente (spec 040). (Número de FASE…, Uma memória de FURTO de Torvin envolvendo Elga (fixture determinística)., run(), _seed_memory()

### Community 113 - "selftest_phase44.py"
Cohesion: 0.47
Nodes (5): check(), Auto-teste da Fase 44 — a DESCRIÇÃO da capacidade é player-facing (spec 043).…, A descrição RESOLVIDA — a callable é chamada, porque é ela que desce., run(), _texto()

### Community 114 - "sondagem_custo_do_turno.py"
Cohesion: 0.40
Nodes (4): call(), narrar(), CUSTO REAL: dois turnos de hoje x um turno com duas rodadas. Mede…, tools_de()

### Community 115 - "sondagem_resolucao_semantica.py"
Cohesion: 0.33
Nodes (3): cena(), RESOLVER O ALVO POR SEMÂNTICA — o id sai do contexto e a Mente aponta por…, Os candidatos reais: (id, texto que o representa).

### Community 116 - "_validate_item_physics"
Cohesion: 0.33
Nodes (6): Física do item (spec 004): size/weight_kg/wearable/container/state.slot. Todos…, Preço e disponibilidade do item (spec 011): value/for_sale/negotiable/currency.…, Arma e armadura do item (spec 008): weapon/armor. Ambos opcionais (item sem…, _validate_item_combat(), _validate_item_commerce(), _validate_item_physics()

### Community 117 - "proficiencies_for"
Cohesion: 0.40
Nodes (5): _peso_das_repeticoes(), proficiencies_for(), _proficiency_factor(), Quanto uma memória RECORRENTE vale a mais por ter acontecido N vezes (053). O…, Fator de proficiência por domínio — consulta de CLIENT (Princípio IX). Não é…

### Community 118 - "tempo.py"
Cohesion: 0.50
Nodes (4): current_moment(), _periodo(), O Motor / tempo (spec 040) — a consulta de MOMENTO do dia. Deriva a faixa do…, Que momento do dia é agora, em prosa. `character_id`/`args` ignorados (a hora é…

### Community 119 - "sanea_mundo.py"
Cohesion: 0.50
Nodes (4): _dono(), main(), Path, Saneamento do save: zera INTENÇÕES e funde MEMÓRIAS idênticas (2026-08-14).…

### Community 126 - "new_id"
Cohesion: 0.50
Nodes (4): new_id(), Id único para entidade CRIADA em runtime (memória, e o que vier depois). O…, _create_memories(), Cria memórias de 1ª classe ancoradas aos personagens afetados (FR-025). Cada…

### Community 127 - "validate_world"
Cohesion: 0.50
Nodes (4): duplicate_ids(), Ids que aparecem em mais de um arquivo — integridade, não estilo. O mundo é…, Varre o mundo e retorna os arquivos de entidade com schema inválido. Cada…, validate_world()

### Community 130 - "selftest_phase47.py"
Cohesion: 0.67
Nodes (3): check(), main(), Auto-teste da Fase 47 — o registro do turno (spec 044, US5). (Número de FASE ≠…

## Knowledge Gaps
- **1 isolated node(s):** `Fixture de mundo (imutável, só para testes)`
  These have ≤1 connection - possible missing edges or undocumented components.
- **13 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `read_doc()` connect `read_doc` to `deslocamento/executores.py`, `fisica/__init__.py`, `conhecimento/executores.py`, `motor/__init__.py`, `comercio/executores.py`, `io.py`, `consultas.py`, `trabalho.py`, `frontmatter.py`, `craft/executores.py`, `memoria/__init__.py`, `memoria/primitivas.py`, `forja/executores.py`, `intencoes/executores.py`, `_rejection`, `_is_alive`, `get_context`, `fogo/executores.py`, `_write_memory`, `_fail`, `herbario/executores.py`, `musica/executores.py`, `acougue/executores.py`, `botica/executores.py`, `cozinha/executores.py`, `sanea_duplicatas.py`, `ativacao.py`, `is_closed`, `_record_witness`, `validate_world`?**
  _High betweenness centrality (0.035) - this node is a cross-community bridge._
- **Why does `name_of()` connect `name_of` to `deslocamento/executores.py`, `read_doc`, `conhecimento/executores.py`, `motor/__init__.py`, `io.py`, `registro.py`, `memoria/__init__.py`, `memoria/primitivas.py`, `forja/executores.py`, `_rejection`, `inworld`, `fogo/executores.py`, `itens/declaracao.py`, `conhecimento/declaracao.py`, `_write_memory`, `comercio/declaracao.py`, `herbario/executores.py`, `acougue/executores.py`, `cozinha/executores.py`, `_record_witness`, `memoria/declaracao.py`?**
  _High betweenness centrality (0.024) - this node is a cross-community bridge._
- **Why does `_fail()` connect `_fail` to `deslocamento/executores.py`, `read_doc`, `fisica/__init__.py`, `conhecimento/executores.py`, `motor/__init__.py`, `comercio/executores.py`, `io.py`, `fogo/executores.py`, `craft/executores.py`, `herbario/executores.py`, `memoria/__init__.py`, `forja/executores.py`, `musica/executores.py`, `intencoes/executores.py`, `acougue/executores.py`, `botica/executores.py`, `cozinha/executores.py`, `_rejection`?**
  _High betweenness centrality (0.013) - this node is a cross-community bridge._
- **What connects `Fixture de mundo (imutável, só para testes)` to the rest of the system?**
  _1 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `deslocamento/executores.py` be split into smaller, more focused modules?**
  _Cohesion score 0.06255012028869286 - nodes in this community are weakly interconnected._
- **Should `read_doc` be split into smaller, more focused modules?**
  _Cohesion score 0.08593396653098145 - nodes in this community are weakly interconnected._
- **Should `fisica/__init__.py` be split into smaller, more focused modules?**
  _Cohesion score 0.06573426573426573 - nodes in this community are weakly interconnected._