"""O Motor — a camada que lê e escreve os arquivos do mundo (pacote, spec 021).

Era um monólito `motor.py`; virou um PACOTE em níveis (o grafo de dependências,
mapeado por AST, é um DAG — ver `specs/021-motor-split-drop-mirror/research.md`):

  nível 0 (primitivas):  io · rolagem · fisica · memoria · rotas · validador
  nível 1 (executores):  estado · combate · deslocamento · itens · comercio ·
                         conhecimento · conteiner · percepcao
  nível 2 (orquestração): turno (apply_resolution)

Este `__init__.py` é a FACHADA: reexporta a API pública por NOME (nada de
`import *`) para que `import motor; motor.X` continue funcionando sem que
arbiter/app/testes troquem um import (SC-002). Um só seam de teste sobrevive ao
split — a injeção do dado por `motor._roll_d20 = fake` — via o forwarding abaixo.

O Motor nunca chama LLM. Toda escrita passa antes pelo World Validator.
Fonte de verdade: os arquivos sob WORLD_DIR (server-side).
"""

from __future__ import annotations

import os
import random
import threading
import time
import uuid
import unicodedata
from pathlib import Path

import frontmatter
import validator


# --- spec 043: a primitiva do JUÍZO (nível 0, pura) ---
from . import juizo  # noqa: F401


# --- spec 052: A PEÇA EM PROCESSO (nível 0) — a entidade que `forge_*` (relógio de
# ESFORÇO) e `cook` (relógio de PRAZO) compartilham. Não mora em nenhum dos dois
# domínios de propósito: as duas a usam, e o reuso mora na primitiva (Princípio XII).
from . import trabalho  # noqa: F401


# --- extraído para motor/turno.py (spec 021) ---
from .turno import (  # noqa: F401
    apply_resolution,
)


# --- extraído para motor/percepcao.py (spec 021) ---
from .percepcao import (  # noqa: F401
    _RECOGNITION_SCENE_CAP,
    _character_summary,
    _inventory_nodes,
    _nested_item_refs,
    _observer_can_look,
    _perceivable_ids,
    _scene_entities,
    _visible_item_refs,
    get_character,
    get_context,
    get_entity_detail,
    get_inventory,
    item_physics,
    list_characters,
    observe_entity,
    prose_of,
    recognition_of,
    remembered_about,
    scene_recognitions,
)


# --- extraído para motor/conteiner.py (spec 021) ---
from .conteiner import (  # noqa: F401
    _apply_lock_ops,
    _find_lockable,
    check_trava_item,
)


# --- extraído para motor/conhecimento.py (spec 021) ---
from .conhecimento import (  # noqa: F401
    _apply_hearsay_ops,
    _apply_learn_ops,
    _find_hearsay_source,
    _normalize_for_search,
    _reject_all,
    quote_matches,
    roll_confidencia,
    roll_disposicao,
    roll_learn_check,
)


# --- extraído para motor/comercio.py (spec 021) ---
from .comercio import (  # noqa: F401
    _apply_persuade_give_ops,
    _apply_trade_ops,
    _open_container_for,
    _validate_negotiation,
    check_availability,
    check_purchase_affordable,
    trade_terms,
    offered_by,
    roll_persuade_give_check,
    roll_trade_check,
)


# --- extraído para motor/itens.py (spec 021) ---
from .itens import (  # noqa: F401
    _apply_equip_ops,
    _apply_item_transfers,
    _apply_movement,
    transfer_item,
    _find_item_folder_in_scene,
    _find_item_under,
    _match_scene_ref,
    _set_item_slot,
    _validate_move,
    has_accessible_item,
)


# --- extraído para motor/deslocamento.py (spec 021) ---
from .deslocamento import (  # noqa: F401
    _apply_carry_ops,
    _apply_persuade_ops,
    _apply_travel_ops,
    _cancel_travel,
    _enter_route_locked,
    _interrupt_travels,
    _resolve_arrivals,
    _witness_movement,
    cancel_travel_plan,
    carry_time_penalty,
    current_location_id,
    directions_from,
    enter_route,
    known_routes,
    lazy_evaluate,
    reachable_destinations,
    roll_persuasion_check,
    route_plan,
    set_travel_plan,
)


# --- extraído para motor/combate.py (spec 021) ---
from .combate import (  # noqa: F401
    _apply_attack_ops,
    roll_attack_check,
    roll_push_check,
    roll_resist_check,
)


# --- extraído para motor/estado.py (spec 021) ---
from .estado import (  # noqa: F401
    _set_field,
    _set_condition,
)


# --- extraído para motor/validador.py (spec 021) ---
from .validador import (  # noqa: F401
    deadlock_warnings,
    duplicate_ids,
    migration_warnings,
    validate_world,
    world_warnings,
)


# --- extraído para motor/rotas.py (spec 021) ---
from .rotas import (  # noqa: F401
    _STATIC_PREREQ_TYPES,
    _available_routes,
    _check_prerequisites,
    _crossing_time_of,
    _eval_prereq,
    _has_item,
    _is_static_prereq,
    _location_folder_by_id,
    _location_name,
    _route_destination,
    _travel_modifier,
    all_route_ids,
    crossing_time,
    find_route,
    knows_route,
    recognizes_route,
)


# --- extraído para motor/memoria.py (spec 021) ---
from .memoria import (  # noqa: F401
    ACONTECIMENTO,
    DOMAINS,
    NEGATIVA,
    POSITIVA,
    ROTA,
    _DAY,
    _DEFAULT_TTL_SECONDS,
    _DOMAIN_BY_EVENT,
    _PROFICIENCY_TETO,
    _PROFICIENCY_K,
    _FAMILIARIDADE_PISO,
    _INTENSITY_ORDER,
    _MEMORY_CONTEXT_CAP,
    _MEMORY_INTENSITIES,
    _MEMORY_WEIGHT,
    _TTL_BY_INTENSITY,
    _TTL_ROTA,
    _VIVID_WINDOW,
    _apply_accuse,
    _char_name,
    _create_memories,
    _expire_memories,
    _leave_trace,
    _h_accuse,
    _is_alive,
    _iter_memories,
    _lower_intensity,
    _memory_salience,
    _is_trace_active,
    _rec,
    _roll_trace_d20,
    _recency_label,
    _record_arma,
    _record_attack,
    _record_carry,
    _record_equip,
    _record_events,
    _record_hearsay,
    _record_hearsay_narrator,
    _record_learn,
    _record_lock,
    _record_mutations,
    _record_persuade,
    _record_trade,
    _record_transfer,
    _record_travel,
    _remember_route,
    _short_summary,
    _weigh_memories,
    _witness_intensity,
    _write_memory,
    sentiment_label,
    fatigue_penalty,
    fatigue_label,
    familiarity_label,
    familiarity_with,
    get_active_memories,
    memory_about,
    memory_involved,
    memory_kind,
    memory_ouvido_de,
    memory_valence,
    proficiencies_for,
    record_event,
    remember,
    sentiment_toward,
    has_trauma_from,
    ttl_for,
)


# --- extraído para motor/intencoes.py (spec 026) ---
from .intencoes import (  # noqa: F401
    _INTENTION_CONTEXT_CAP,
    _INTENTION_STATUSES,
    _h_intentions,
    close_intention,
    create_intention,
    get_active_intentions,
    update_intention,
)


# --- extraído para motor/compromisso.py (spec 027) ---
from .compromisso import (  # noqa: F401
    _apply_promise,
    _h_promise,
)


# --- extraído para motor/cura.py (spec 032) ---
from .cura import (  # noqa: F401
    _apply_cura_ops,
    _h_cura,
    roll_cura_check,
)


# --- motor/cozinha.py (spec 048) ---
from .forja import (  # noqa: F401
    BANDAS,
    banda_final,
    bloco_mecanico,
    duracao_segundos_forja,
    roll_forge_check,
    teto_por_maestria,
    teto_por_material,
)


from .cozinha import (  # noqa: F401
    _apply_cozinha_ops,
    _h_cozinha,
    duracao_segundos,
    roll_cook_check,
)


# --- motor/fogo (spec 053) ---
from .fogo import (  # noqa: F401
    _apply_fogo_ops,
    _h_fogo,
    duracao_fogo_s,
    roll_kindle_check,
)


# --- motor/acougue.py (spec 050) ---
from .acougue import (  # noqa: F401
    _apply_esquartejar_ops,
    _h_esquartejar,
    porcoes_de_carne,
    roll_esquartejar_check,
)


# --- motor/herbario (spec 054) ---
from .herbario import (  # noqa: F401
    _apply_forage_ops,
    _h_forage,
    porcoes_de_erva,
    rebrota_s,
    roll_colher_check,
)


# --- motor/botica (spec 055) ---
from .botica import (  # noqa: F401
    _apply_botica_ops,
    _h_botica,
    duracao_segundos_preparo,
    roll_preparar_check,
)


# --- extraído para motor/fisica.py (spec 021) ---
from .fisica import (  # noqa: F401
    CARRY_KG_PER_STR,
    DEAD,
    DEFAULT_BODY_WEIGHT_KG,
    DEFAULT_WEIGHT_BY_SIZE,
    DOWN_CONDITIONS,
    HAND_SLOT,
    INCAPACITATED,
    PUSH_IMPOSSIBLE_RATIO,
    PUSH_KG_PER_STR,
    PUSH_TRIVIAL_RATIO,
    _CROSSING_BY_SIZE,
    _conditions_of,
    _inside_closed,
    _direct_items,
    _is_wide_open,
    _reachable_item_folder,
    _slot_cap,
    _slot_pega,
    _walk_open_items,
    apply_damage,
    apply_healing,
    finish_rest,
    start_rest,
    apply_speed,
    body_of,
    body_weight_of,
    carried_weight,
    carry_capacity,
    check_carga,
    check_carga_livre,
    check_empurrar,
    check_encaixe,
    check_mao,
    check_slot,
    check_vaga,
    default_hp_max,
    effective_weight,
    ensure_fatigue,
    ensure_hp,
    is_resting,
    fatigue_max,
    porter_of,
    rest_fraction,
    spend_fatigue,
    custo_da_falha,
    CUSTO_TENTATIVA_SOCIAL,
    grasp_slot_of,
    is_closed,
    is_currency,
    is_dead,
    is_down,
    is_for_sale,
    is_negotiable,
    item_own_weight,
    item_size,
    item_slot,
    protection_of,
    push_capacity,
    slot_capacity,
    slots_in_use,
    speed_multiplier_of,
    total_value,
    total_weight_of,
    value_of,
    weapon_of,
)

from . import acougue, ativacao, botica, cozinha, fatos, fogo, herbario, io, memoria, registro, rolagem, tempo  # noqa: F401  (handles de módulo p/ o seam de injeção; tempo=spec 040 registra consultar_momento)
from .registro import ConsultSpec, consult_spec, consult_specs  # noqa: F401  (spec 040: lane de consulta)
from .tempo import current_moment  # noqa: F401  (spec 040)
from .percepcao import recall  # noqa: F401  (spec 040: consultar_memoria; reúso pelo Árbitro em US3)

# Seam de injeção do dado (spec 006/021). A suíte inteira injeta o d20 com um só
# ponto: `motor._roll_d20 = fake`. O Motor virou pacote, e os executores chamam
# `rolagem._roll_d20()` (late-bound, resolvido no ato). Este forwarding faz o
# patch na FACHADA alcançar a definição real em `rolagem`, preservando o único
# seam de teste sem editar as ~21 fases (SC-001).
#
# `_roll_trace_d20` (spec 034) é um SEGUNDO seam, deliberadamente separado do
# primeiro — a marca física rola seu PRÓPRIO dado (research.md da 034), nunca o
# mesmo `_roll_d20` que ações arbitradas usam, porque deslocamento roda
# incondicionalmente (inclusive nos extremos deterministas de `persuade`/
# `carry`, que testes já monkeypatcham para PROIBIR dado). Mesmo forwarding,
# alvo diferente (`memoria`, onde `_leave_trace` de fato lê o nome).
import sys as _sys
import types as _types


class _MotorFacade(_types.ModuleType):
    def __setattr__(self, k, v):
        if k == "_roll_d20":
            rolagem._roll_d20 = v
        elif k == "_roll_trace_d20":
            # item 31 §3: memoria virou pacote — `_leave_trace` chama o
            # `_roll_trace_d20` LOCAL de memoria.primitivas (não o do __init__ do
            # pacote). O seam de teste tem de patchar o submódulo onde ele mora.
            memoria.primitivas._roll_trace_d20 = v
            memoria._roll_trace_d20 = v
        super().__setattr__(k, v)


_sys.modules[__name__].__class__ = _MotorFacade


# --- extraído para motor/rolagem.py (spec 021) ---
from .rolagem import (  # noqa: F401
    IMPROVISED_ATTRIBUTE,
    IMPROVISED_DAMAGE,
    LEARN_ROUTE_DC,
    NEUTRAL_ADVANTAGE,
    _AFETO_DC_TETO,
    _APEGO_DC_TETO,
    _attachment_dc_share,
    _roll_d20,
    attack_tendencia,
    attr_modifier,
    defense_of,
    learn_dc_from,
    persuade_dc,
    persuade_tendencia,
    push_dc,
    resist_dc,
    trade_dc,
)


# --- extraído para motor/io.py (spec 021) ---
from .io import (  # noqa: F401
    ENTITY_FILENAMES,
    MotorError,
    REPO_ROOT,
    ValidationError,
    WORLD_DIR,
    WRITE_LOCK,
    _ENTITY_FILE_BY_KIND,
    _GROUND_WORDS,
    _IMMUTABLE_ROOTS_BY_KIND,
    _MUTABLE_ROOT_BY_KIND,
    _SYSTEM_FIELDS,
    _WHY_BY_REGRA,
    _char_fm,
    _entity_file,
    _fail,
    _is_valid,
    _marca,
    _rejection,
    _sinal,
    _slugify,
    find_character_folder,
    find_entity,
    move_entity,
    name_of,
    descricao_de,
    new_id,
    read_doc,
    write_doc,
)

# Raiz do mundo: <repo>/world  (server/ é irmão de world/)
# NB: este arquivo mora em server/motor/ — sobe TRÊS níveis até a raiz do repo.
# Serializa mutações: um /act por vez (FR-036, atomicidade single-player).
# Reentrante: apply_resolution pode chamar enter_route com o lock já em mãos.
# --------------------------------------------------------------------------- #
# Erros
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# Leitura de entidades
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# Física de itens e do corpo (spec 004) — guichê único de regras
#
# Toda validação de movimentação de item nasce aqui e é REUSADA pela guarda do
# Árbitro (mesmas funções, dados do contexto) e pela aplicação autoritativa
# (dados dos arquivos). Nenhuma tool implementa regra própria (research D3).
# --------------------------------------------------------------------------- #

   # capacidade de carregar = STR × 7 kg (MVP, revisável)
   # capacidade de empurrar = STR × 14 kg (o dobro)
# --- checagens puras (retornam None se ok, ou {"regra", "valores"}) ---------- #

# Teste de força no empurrar (spec 006): zonas determinísticas + rolagem.
# Trivial (≤ 0.5× capacidade) passa sem dado; impossível (> 2×) nega sem dado —
# a sorte não move montanhas. Entre elas rola-se d20 + mod(STR) vs DC.
# --------------------------------------------------------------------------- #
# Combate (spec 008): derrota, equipamento e o teste oposto
# --------------------------------------------------------------------------- #

# Derrota mora em status.conditions, lista que o mundo JÁ publica ao próprio
# (self.status) e aos outros (_character_summary) — nenhuma rota nova.
# Golpe sem arma declarada (mão vazia ou item que não é arma): o corpo, e só.
# Vantagem situacional 0–10 do Árbitro; 5 = combate limpo (modificador zero).
# Peso do corpo de quem não declara (spec 010): adulto típico. Existe para que
# nenhum character.md escrito antes desta spec precise ser editado.
# --------------------------------------------------------------------------- #
# Comércio (spec 011): preço, disponibilidade e o portão
# --------------------------------------------------------------------------- #

    # spec 016: teto do quanto o apego sobe a DC — dificulta, não proíbe
    # spec 016: teto do afeto pelo parceiro (nos dois sentidos)


# --------------------------------------------------------------------------- #
# Proximity context
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# Autoria editorial: validação do mundo na leitura (Phase 4) — FR-010, SC-006
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# Inventário (árvore de pertences aninhados) — FR-034
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# Detalhe diegético de uma entidade (para o painel lateral) — FR-035, Princípio V
# --------------------------------------------------------------------------- #

# Campos de frontmatter que NUNCA vão para a visão diegética (são de sistema).
# --------------------------------------------------------------------------- #
# Tool consultiva: observar uma entidade ao alcance (spec 003, taxonomia de exposição)
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# Escrita atômica (usada nas fases 1+)
# --------------------------------------------------------------------------- #

  # rename atômico no mesmo filesystem


# --------------------------------------------------------------------------- #
# Aplicação de resolução do Árbitro (Phase 1) — FR-014, FR-015, FR-016, FR-036
# --------------------------------------------------------------------------- #

# Raiz mutável por ação, e identidade imutável, variam por tipo de entidade-alvo.
# character: status.* mutável; object/item: state.* mutável (spec 002, FR-014/016).
# Intensidades válidas (espelham o World Validator) — clamp defensivo antes de gravar.
# Classes de memória (spec 013). A ausência do campo significa `acontecimento`:
# é o que mantém válido todo o mundo escrito antes desta spec.
# Prazo por classe. Os números são balanceamento revisável; a ordem de grandeza
# (rota ≫ acontecimento) não é — caminho se esquece devagar, e ainda renova a
# cada uso. O acontecimento escala pela intensidade a partir de uma base bem
# maior que a hora única de antes, que expirava 6 das 9 memórias do mundo.
# Relevância por canal de evento (spec 013, FR-012b). É esta tabela que faz o
# banal sumir sozinho SEM ninguém julgar banalidade no calor da cena — julgar
# erra sempre para menos, e foi o que produziu 9 memórias no mundo inteiro.
# Quem acrescentar um canal novo descobre aqui que precisa declarar o peso dele.
# Sinal por "evento de valência" (spec 016), irmã do _RELEVANCE_BY_EVENT. As
# chaves codificam a PERSPECTIVA, porque a valência é DIRIGIDA e por-lado: a
# vítima pende contra o agressor, mas o agressor não pende contra a vítima (só
# se afirma sinal onde o evento DETERMINA). A magnitude não está aqui — vem de
# `sinal × intensidade` na soma. Ausência de entrada = neutro.
# --------------------------------------------------------------------------- #
# Recordadores por-família (spec 020): cada um deriva as memórias de UMA família
# de op, usando o funil único `record_event`. São o "registrar" dos executores
# de fase única; o `_record_events`-no-fim (driver de lote) apenas os encadeia na
# mesma ordem de antes, então o comportamento do lote é idêntico. Cada um recebe
# o que a família aplicou e devolve a lista de memórias criadas.
# --------------------------------------------------------------------------- #

# Dificuldade FIXA de aprender um caminho lido (spec 014, FR-009). Fixa porque
# aprender um caminho não é mais difícil num material do que noutro — a variação
# vem de QUEM LÊ, não do que se lê. Por isso esta é a única capacidade de
# julgamento do projeto sem régua canônica: não há nota que o Árbitro possa dar.
  # revalida schema + atômico


# --------------------------------------------------------------------------- #
# Abrir/fechar contêiner — lock_ops (spec 005)
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# Vestir/tirar equipamento — equip_ops (spec 004, US1/US3)
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# Posse de item — pegar/dar/saquear (spec 002, FR-010 a FR-013)
# --------------------------------------------------------------------------- #

# Palavras que, na referência de destino do Árbitro, significam "o chão daqui".
# Prosa curta por código de regra — vai no campo `why` legado (devlog e
# inworld_failures); o {regra, valores} estruturado segue junto (FR-011).
# --------------------------------------------------------------------------- #
# Memória e avaliação preguiçosa (stubs — fases 2 e 3)
# --------------------------------------------------------------------------- #

# Janela (em segundos) durante a qual uma memória fica "vívida" (na ponta da mente),
# escalada pela intensidade: quanto mais forte, por mais tempo ela se intromete sozinha.
# Passada a janela, vira "latente": só volta se o contexto a evocar (memória humana).
# Teto de memórias que descem ao client. Rede de segurança contra o volume que a
# criação automática produz — não é o filtro principal, que é a evocação.
# --------------------------------------------------------------------------- #
# Consultas de conhecimento (spec 013) — servem O MUNDO, não o client.
#
# Estas funções enxergam TUDO, inclusive memórias vencidas, porque é a
# diferença entre vencida e viva que separa "reconheço" de "sei". O corte que
# `get_active_memories` faz é de NARRAÇÃO; cortar conhecimento junto quebraria
# a viagem sem que nada acusasse.
# --------------------------------------------------------------------------- #

# Peso por intensidade (spec 013): a tabela ÚNICA que apego e afeto partilham.
# Módulo e sinal são a MESMA leitura em dois eixos (spec 016, FR-011/SC-009).
# Piso de familiaridade abaixo do qual não há vivência que pese (spec 018).
# 0.5 casa com o "desconhecido" do rótulo: um `large` VENCIDO (4×¼=1.0) já é
# reconhecimento VAGO; um `small` vencido (0.25) não — trivial que desbotou.
# Teto de entidades na cor ambiente, para não inflar a narração de todo turno.
# --------------------------------------------------------------------------- #
# Deslocamento por rotas (Phase 2) — FR-018, FR-019, FR-020, FR-021
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# Viagem longa (spec 012) — travessia de lugar, busca de trajeto e plano
# --------------------------------------------------------------------------- #

# Tempo de atravessar um lugar, por degrau da régua. É função APENAS do tamanho
# (SC-012): o mesmo lugar custa o mesmo a qualquer viajante, antes dos
# modificadores pessoais. Números são balanceamento revisável; o que não é
# revisável é que um vale possa custar mais que várias rotas somadas.
# Tipos de prerequisite avaliados como estáticos (antes dos contextuais) — FR-019.
