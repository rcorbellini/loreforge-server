"""World Validator — checagem de schema pura, sem LLM (camada zero).

Princípio VI: toda escrita de `.md` passa por aqui antes de entrar no mundo.
É deliberadamente simples: valida presença de campos obrigatórios do frontmatter
e alguns enums. Não interpreta narrativa nem chama modelo algum.

Retorna uma lista de erros (strings legíveis). Lista vazia = válido.
"""

from __future__ import annotations

# Tipos de entidade do MVP (spec 001, FR-002; object: spec 002, RF-06 v1.1). island/region/
# event: fase posterior. rastro: spec 034 (marca física de deslocamento) —
# mesma classe de extensão que object/intention já estabeleceram.
TRABALHO_BLOCO = "trabalho"

MVP_TYPES = {"location", "character", "route", "memory", "item", "object", "intention",
             "rastro"}

# spec 034: os dois eventos que geram a marca física (partida/chegada).
RASTRO_EVENTOS = {"partida", "chegada"}

INTENSITIES = {"trivial", "small", "medium", "large", "giant"}
# spec 032: "esquecida" é MAIS DEFINITIVA que "expired" — nunca pesa
# fração nenhuma (ao contrário de expired, que pesa ¼) e NUNCA revive
# via `_renew_memory` (ao contrário de expired, que revive por
# proximidade). É o custo de memória de `curar` — arquivo preservado no
# disco (Princípio IV), só deixa de contar para tudo.
MEMORY_STATES = {"active", "expired", "esquecida"}
# Domínio de memória (spec 029, item 9/16/18 do backlog): fechado, ao
# contrário de `evento` (spec 028, campo aberto e sem enum aqui) — o valor
# alimenta o cálculo de proficiência (motor.memoria.proficiencies_for), que
# precisa ser estável entre consultas. Os 5 domínios de fase 1 mais
# "nenhuma" (a resposta explícita para memórias sem prática nenhuma
# associada). "cura" (spec 032) é o primeiro domínio de fase 2 — a tool
# `curar` é a primeira a CONSUMIR proficiencies_for como modificador real.
# spec 052: `ferraria` (arma) e `armaria` (armadura) — DOIS domínios, não um.
# Substituem a reserva de `oficio` que a doc anunciava: manter as três seria uma
# opção morta no manifesto. Praticar um NÃO faz o outro progredir (FR-033).
# spec 057 (revisão): `craft` ganhou domínio PRÓPRIO, `construtor` — não mais
# variável por criação. Pedir ao Árbitro pra escolher entre 8 domínios (e um
# atributo) a cada tentativa é o mesmo erro que `forja` já evitava (spec 052:
# `_DOMINIO`/`_ATRIBUTO` fixos no executor, nunca julgados): um modelo pequeno,
# sem material nenhum apontado, sobra sem grão pra decidir e cola no primeiro
# vocabulário forte que vir no prompt — foi assim que um boneco de cera saiu
# classificado como "herbalismo", puxado da descrição do LUGAR (Boticário da
# Raiz Torta), não da narração. `oficio` fica como resíduo histórico (nenhum
# emissor novo usa), mantido só porque memórias antigas já gravadas com esse
# domain continuam válidas.
DOMAINS = {"combate", "crime", "comercio", "social", "deslocamento", "cura", "cozinha",
          "acougue", "ferraria", "armaria", "fogo", "herbalismo", "botica", "oficio",
          "construtor", "musica", "investigar", "nenhuma"}
# "investigar" (spec 065): a leitura de rastro (item 14-gama) alimenta este dominio pelo
# mesmo mecanismo dinamico que os outros 16 ja usam - proficiencies_for(), sem campo
# estatico. Um valor a mais no conjunto fechado, no molde de botica/herbalismo/construtor.
# spec 026: intenção não tem TTL nem se acumula (ao contrário de memória) — é um
# plano que a própria LLM edita no lugar. Só três estados, sem decaimento por
# relógio; encerrar é decisão explícita (concluída/abandonada), nunca lazy-eval.
INTENTION_STATES = {"ativa", "concluida", "abandonada"}
ATTRIBUTES = ("STR", "DEX", "CON", "INT", "WIS", "CHA")

# Régua de tamanho ordenada e partes canônicas do corpo com multiplicidade.
# Constantes únicas do sistema — o Motor importa daqui.
#
# A régua nasceu para a física de item (spec 004): é ela que decide se a espada
# cabe na mochila. A spec 012 a ESTENDEU com degraus geográficos, para dar conta
# de um vale ou de uma serra como `location.size`. Os degraus novos entram no
# FIM de propósito: SIZE_ORDER é derivado por índice, então toda comparação de
# encaixe que já existia continua valendo intacta.
#
# A régua é compartilhada, e isso é deliberado — duas escalas de tamanho no mesmo
# projeto seriam a duplicação que o Princípio I evita. O efeito colateral aceito
# é que um item PODERIA declarar tamanho de vale; se acontecer, é erro autoral,
# não de schema.
SIZES = ("PP", "P", "M", "G", "XG", "XXG", "XXXG", "XXXXG", "XXXXXG")
SIZE_ORDER = {s: i for i, s in enumerate(SIZES)}
# O CORPO HUMANO PADRÃO (spec 019). Deixou de ser a "lei do corpo" de todo
# personagem: agora é só o corpo que um personagem SEM campo `body` herda. Quem
# declara `body` na ficha tem o próprio corpo (fonte única, no personagem). O
# vocabulário de nomes de slot é ABERTO (FR-009): esta tabela não barra mais
# `wearable.slot`/`state.slot` — ela só dá o default humano. `motor.body_of()` é
# a leitura canônica; ninguém lê SLOTS como a capacidade de um personagem.
SLOTS = {
    "cabeca": 1, "rosto": 1, "pescoco": 1, "torso": 1, "costas": 1,
    "bracos": 1, "mao": 2, "dedo": 10, "cintura": 1, "pernas": 1, "pes": 1,
}

# Nome novo para o mesmo dict, documentando o papel pós-019: o corpo herdado por
# quem não declara `body`. SLOTS permanece como alias por retrocompatibilidade.
DEFAULT_BODY = SLOTS

# Atributos que uma arma pode usar (spec 008): força no corpo a corpo, agilidade
# nas leves e de arremesso.
WEAPON_ATTRIBUTES = ("STR", "DEX")

# As cinco BANDAS de qualidade de equipamento forjado (spec 052), em ordem. É enum
# FECHADO, ao contrário do vocabulário de slot: o valor vira precondição mecânica de
# capacidades futuras (encantamento só sobre certas bandas), e uma precondição que
# dependesse de reler prosa derivaria a cada leitura. `falha` é a única sem bloco
# mecânico nenhum — vale como improvisado pelas regras que já existem.
RARITIES = ("falha", "comum", "incomum", "raro", "lendario")

# Campos obrigatórios de topo por tipo (FR-006, FR-008, FR-009).
REQUIRED_TOP = {
    # `size` é obrigatório desde a spec 012: sem tamanho não há tempo de
    # travessia, e o viajante saltaria de rota em rota sem nunca estar num lugar.
    # Quebra de compatibilidade consciente (FR-010c) — o mundo tinha 7 lugares.
    "location": ["id", "name", "size"],
    # `skills` SAIU dos obrigatórios (spec 058, US6): o campo subia ao contexto
    # do Árbitro (`arbiter.py`, projeção de `self`) e virou uma SEGUNDA via
    # para "quão bom o personagem é" no exato domínio (`musica`) que a spec
    # passou a derivar de memória de verdade (`proficiencies_for`). Um
    # `character.md` legado que ainda declare `skills` continua VÁLIDO — a
    # checagem de TIPO abaixo (`_validate_character`) segue intacta, só a
    # AUSÊNCIA deixou de ser erro.
    "character": ["id", "name", "controlled_by", "attributes", "status"],
    "route": ["id", "name", "from", "to", "travel_time_base", "bidirectional",
              "prerequisites"],
    "memory": ["id", "timestamp_start", "timestamp_end", "intensity", "state"],
    "item": ["id", "name"],
    "object": ["id", "name"],
    "intention": ["id", "status", "created_ts", "updated_ts"],
    # spec 034: marca física de deslocamento — mora no LUGAR, decai por
    # relógio (nunca por uso). `quem`/`direcao` são ground-truth do Motor,
    # secretos até uma futura ação de investigar (item 14-γ) os revelar.
    "rastro": ["id", "quem", "direcao", "evento", "criado_em", "ttl_seconds",
               "intensity"],
}


def validate(frontmatter: dict) -> list[str]:
    """Valida um frontmatter de entidade. Retorna lista de erros (vazia = ok)."""
    errors: list[str] = []

    etype = frontmatter.get("type")
    if not etype:
        errors.append("frontmatter sem campo 'type'.")
        return errors
    if etype not in MVP_TYPES:
        errors.append(
            f"tipo '{etype}' não faz parte do MVP (permitidos: "
            f"{', '.join(sorted(MVP_TYPES))})."
        )
        return errors

    for field in REQUIRED_TOP[etype]:
        if field not in frontmatter or frontmatter.get(field) in ("", None):
            errors.append(f"{etype}: campo obrigatório ausente ou vazio: '{field}'.")

    if etype == "character":
        errors.extend(_validate_character(frontmatter))
    elif etype == "location":
        errors.extend(_validate_location(frontmatter))
    elif etype == "memory":
        errors.extend(_validate_memory(frontmatter))
    elif etype == "route":
        errors.extend(_validate_route(frontmatter))
    elif etype == "object":
        errors.extend(_validate_object(frontmatter))
    elif etype == "item":
        errors.extend(_validate_item(frontmatter))
    elif etype == "intention":
        errors.extend(_validate_intention(frontmatter))
    elif etype == "rastro":
        errors.extend(_validate_rastro(frontmatter))

    return errors


def _validate_character(fm: dict) -> list[str]:
    errors: list[str] = []
    attrs = fm.get("attributes")
    if isinstance(attrs, dict):
        for a in ATTRIBUTES:
            if a not in attrs:
                errors.append(f"character: atributo obrigatório ausente: '{a}'.")
            elif not isinstance(attrs[a], int):
                errors.append(f"character: atributo '{a}' deve ser inteiro.")
    elif attrs is not None:
        errors.append("character: 'attributes' deve ser um mapa dos 6 atributos.")
    owner = fm.get("owner")
    if owner is not None and owner != "":
        if not isinstance(owner, str) or not owner.startswith("google:"):
            errors.append("character: 'owner' deve ser texto iniciado com 'google:'.")
    image_url = fm.get("image_url")
    if image_url is not None and image_url != "":
        # absoluta (http/https) ou relativa ao server (ex.: /api/character/image
        # — o retrato servido do próprio disco, spec 056: URL de terceiro expira).
        if not isinstance(image_url, str) or not image_url.startswith(("http://", "https://", "/")):
            errors.append("character: 'image_url' deve ser uma URL http(s) ou um caminho começando com '/'.")
    status = fm.get("status")
    if status is not None and not isinstance(status, dict):
        errors.append("character: 'status' deve ser um mapa.")
    elif isinstance(status, dict):
        # spec 030: fadiga numérica é o alvo (campo `fatigue`/`fatigue_max`,
        # nome já estabelecido pelo projeto antes desta spec), mas texto
        # legado (fichas anteriores, ex. "alto") é TOLERADO — a leitura
        # (fisica.ensure_fatigue) já trata isso como 0, compatibilidade
        # deliberada. Só bloqueia tipo genuinamente inválido (lista, mapa).
        for campo in ("fatigue", "fatigue_max"):
            valor = status.get(campo)
            if valor is not None and (
                isinstance(valor, bool) or not isinstance(valor, (int, float, str))
            ):
                errors.append(f"character: 'status.{campo}' deve ser número ou texto.")
        # spec 031: descansando_desde é timestamp (time.time()) — campo NOVO,
        # sem ficha legada a acomodar, então sem tolerância de texto aqui.
        desde = status.get("descansando_desde")
        if desde is not None and (
            isinstance(desde, bool) or not isinstance(desde, (int, float))
        ):
            errors.append("character: 'status.descansando_desde' deve ser número.")
        # spec 049: âncoras de decadência de fome/sede — mesmo molde de
        # descansando_desde (campo novo, sem ficha legada a acomodar).
        # `*_ts` é epoch (time.time()); `*_note` é a nota 0-10 de
        # saciedade/hidratação do ato que gravou a âncora.
        for campo in ("hunger_ts", "hunger_note", "thirst_ts", "thirst_note"):
            valor = status.get(campo)
            if valor is not None and (
                isinstance(valor, bool) or not isinstance(valor, (int, float))
            ):
                errors.append(f"character: 'status.{campo}' deve ser número.")
    skills = fm.get("skills")
    if skills is not None and not isinstance(skills, dict):
        errors.append("character: 'skills' deve ser um mapa.")
    # peso do corpo (spec 010): ausente assume o padrão — mundo antigo intacto
    weight = fm.get("weight_kg")
    if weight is not None and (
        isinstance(weight, bool) or not isinstance(weight, (int, float)) or weight <= 0
    ):
        errors.append("character: 'weight_kg' deve ser número positivo.")
    # corpo (spec 019): ausente = corpo humano padrão (mundo antigo intacto).
    # Presente, valida só a FORMA — mapa de slot->capacidade inteiro >= 0. O NOME
    # do slot é livre (vocabulário aberto, FR-009): não se barra chave alguma.
    body = fm.get("body")
    if body is not None:
        if not isinstance(body, dict):
            errors.append("character: 'body' deve ser um mapa de slot para capacidade.")
        else:
            for slot, val in body.items():
                # spec 019: valor do slot é um inteiro >= 0 (capacidade) OU a forma
                # rica {capacidade: n>=0, pega: bool} — pega marca o slot onde os
                # itens pegos vão (a mão do humano, a boca do cão).
                if isinstance(val, dict):
                    cap = val.get("capacidade")
                    if isinstance(cap, bool) or not isinstance(cap, int) or cap < 0:
                        errors.append(f"character: 'body.{slot}.capacidade' deve ser "
                                      f"inteiro >= 0.")
                    if "pega" in val and not isinstance(val.get("pega"), bool):
                        errors.append(f"character: 'body.{slot}.pega' deve ser booleano.")
                elif isinstance(val, bool) or not isinstance(val, int) or val < 0:
                    errors.append(
                        f"character: 'body.{slot}' deve ser inteiro >= 0 (capacidade) "
                        f"ou um mapa {{capacidade, pega}}."
                    )
    errors.extend(_validate_bonds(fm))
    return errors


# Vocabulário que o vínculo NÃO pode expressar (spec 066, FR-006). Não é polícia de
# estilo: as três relações abaixo JÁ TÊM RESPOSTA no mundo, por outra via —
#
#   posse            -> `dono()`, que é CRENÇA por observador, derivada de memória
#   autoria de craft -> memória com `evento: craft`
#   dívida           -> promessa (spec 027): memória nos dois lados + intenção em quem deve
#
# Deixar o vínculo declarar qualquer uma delas criaria a SEGUNDA VERDADE que o
# Invariante 10/17 proíbe: duas fontes para a mesma pergunta, uma declarada e uma
# derivada, discordando em silêncio — e a declarada venceria por ser mais barata de ler.
# A comparação é por PALAVRA INTEIRA, não por substring — a primeira versão casava
# substring e recusava "dona de casa", que é rótulo perfeitamente legítimo. Um rótulo
# bom recusado é pior que um ruim aceito: o autor não entende por que o mundo não
# aceita a palavra dele, e não tem como descobrir.
_BONDS_PROIBIDOS = frozenset((
    "dono", "dona", "donos", "donas", "proprietario", "proprietaria",
    "meu", "minha", "meus", "minhas", "pertence",
    "forjei", "criador", "criadora",
    "devedor", "devedora", "credor", "credora", "divida", "dividas",
))

# Rótulos que CONTÊM uma palavra da lista acima mas são legítimos, porque a palavra
# ali não afirma posse — é título ou ofício. Sem esta porta, a regra do FR-006 vira
# uma armadilha para quem escreve o mundo.
_BONDS_PERMITIDOS = frozenset((
    "dona de casa", "dono de casa", "senhora do moinho", "senhor do moinho",
))


def _normaliza_rotulo(texto: str) -> str:
    """Minúsculas, sem acento, pontuação virando espaço — para comparar PALAVRAS."""
    import unicodedata
    sem_acento = "".join(c for c in unicodedata.normalize("NFD", texto.lower())
                         if unicodedata.category(c) != "Mn")
    return "".join(c if c.isalnum() else " " for c in sem_acento)


def _validate_bonds(fm: dict) -> list[str]:
    """O bloco `bonds` (spec 066) — a CAMADA 2, fato declarado.

    OPCIONAL por desenho, e ausente em 100% do mundo no dia em que nasceu: quem cria um
    personagem sem saber que ele existe segue criando como sempre (Princípio XI, o
    critério do criador).

    O `target` inexistente é REPORTADO, não bloqueante — `write_doc` valida a cada
    escrita de personagem, e um alvo que ainda não existe (ou que foi removido) não pode
    impedir o mundo de girar. Mesmo espírito de `name_of`/`dono`, que já tratam aresta
    pendente como ausência, não como erro.
    """
    bonds = fm.get("bonds")
    if bonds is None:
        return []
    if not isinstance(bonds, list):
        return ["character: 'bonds' deve ser uma lista."]
    errors: list[str] = []
    proprio = fm.get("id")
    vistos = set()
    for i, b in enumerate(bonds):
        onde = f"bonds[{i}]"
        if not isinstance(b, dict):
            errors.append(f"character: '{onde}' deve ser um mapa {{target, label}}.")
            continue
        alvo = b.get("target")
        rotulo = b.get("label")
        if not isinstance(alvo, str) or not alvo.strip():
            errors.append(f"character: '{onde}.target' deve ser o id de uma entidade.")
        elif alvo == proprio:
            errors.append(f"character: '{onde}.target' não pode ser o próprio personagem.")
        elif alvo in vistos:
            errors.append(f"character: '{onde}.target' repetido: '{alvo}'.")
        else:
            vistos.add(alvo)
        if not isinstance(rotulo, str) or not rotulo.strip():
            # Um vínculo sem palavra não diz nada a quem lê: a aresta existiria e a face
            # não teria o que mostrar.
            errors.append(f"character: '{onde}.label' não pode ser vazio.")
        elif any(ord(c) < 32 for c in rotulo):
            # O rótulo é PROSA QUE DESCE PARA O PROMPT d'A Mente (o trecho social do
            # conector). Um `\n` ou `\t` no meio dele parte a frase que ela lê e, pior,
            # é vetor de injeção de instrução: quem escreve o mundo passaria a poder
            # escrever no prompt. Achado do exploratório da 066 — passava antes.
            errors.append(
                f"character: '{onde}.label' não pode conter quebra de linha nem "
                f"caractere de controle — ele desce como prosa para A Mente."
            )
        elif (_normaliza_rotulo(rotulo).strip() not in
              {_normaliza_rotulo(p).strip() for p in _BONDS_PERMITIDOS}
              and set(_normaliza_rotulo(rotulo).split()) & _BONDS_PROIBIDOS):
            errors.append(
                f"character: '{onde}.label' não pode expressar posse, autoria de craft "
                f"nem dívida ('{rotulo}') — o mundo já responde a isso por dono(), "
                f"memória de craft e promessa (spec 066, FR-006)."
            )
    return errors


MEMORY_KINDS = ("acontecimento", "rota")


def _validate_location(fm: dict) -> list[str]:
    """Tamanho do lugar (spec 012): é dele que sai o tempo de atravessar."""
    errors: list[str] = []
    size = fm.get("size")
    if size is not None and size not in SIZES:
        errors.append(
            f"location: 'size' inválido: '{size}' (permitidos: {', '.join(SIZES)})."
        )
    # spec 057: location passou a poder carregar um bloco `trabalho` (craft pode
    # deixar um lugar em CONSTRUÇÃO — uma casa não nasce pronta de um ato só).
    # Mesmo buraco que a 053 fechou para `object`: sem isto, um bloco malformado
    # passaria sem erro nenhum.
    errors.extend(_validate_trabalho(fm, "location"))
    return errors


def _validate_intention(fm: dict) -> list[str]:
    """Intenção (spec 026): compromisso/plano de médio-longo prazo, mutável no
    lugar. Só `status` é campo estruturado (Princípio XI) — o resto é prosa
    livre no corpo, nunca validada aqui."""
    errors: list[str] = []
    status = fm.get("status")
    if status is not None and status not in INTENTION_STATES:
        errors.append(
            f"intention: 'status' inválido: '{status}' "
            f"(permitidos: {', '.join(sorted(INTENTION_STATES))})."
        )
    for campo in ("created_ts", "updated_ts"):
        val = fm.get(campo)
        if val is not None and (isinstance(val, bool) or not isinstance(val, int)):
            errors.append(f"intention: '{campo}' deve ser inteiro (timestamp).")
    # spec 030: referência opcional à memória do compromisso que a originou
    # (prometer) — identidade por id, mesmo padrão de intention_id em outras
    # tools; nunca interpretação.
    memoria_id = fm.get("memoria_id")
    if memoria_id is not None and not isinstance(memoria_id, str):
        errors.append("intention: 'memoria_id' deve ser o id de uma memória.")
    return errors


def _validate_memory(fm: dict) -> list[str]:
    errors: list[str] = []
    # spec 013: kind/involved/about são opcionais — a AUSÊNCIA tem significado
    # (acontecimento, lista vazia, sem referente) e é o que mantém o mundo antigo
    # válido. Presentes, porém, o tipo é estrito.
    kind = fm.get("kind")
    if kind is not None and kind not in MEMORY_KINDS:
        errors.append(
            f"memory: 'kind' inválido: '{kind}' "
            f"(permitidos: {', '.join(MEMORY_KINDS)})."
        )
    if kind == "rota" and not isinstance(fm.get("about"), str):
        errors.append("memory: 'kind: rota' exige 'about' com o id da rota.")
    involved = fm.get("involved")
    if involved is not None and (
        not isinstance(involved, list)
        or not all(isinstance(x, str) for x in involved)
    ):
        # spec 016: `involved` passa a aceitar ids de ITEM e LUGAR, não só de
        # personagem — o vínculo que sustenta apego e afeto. Continua sendo lista
        # de ids; o tipo do id não se valida aqui.
        errors.append("memory: 'involved' deve ser lista de ids.")
    # spec 016: valência DIRIGIDA, opcional e derivada pelo Motor. Mapa id→sinal.
    # Ausência = memória neutra (o mundo antigo continua válido).
    valence = fm.get("valence")
    if valence is not None and (
        not isinstance(valence, dict)
        or not all(isinstance(k, str) and v in ("positiva", "negativa")
                   for k, v in valence.items())
    ):
        errors.append("memory: 'valence' deve ser mapa de id para "
                      "'positiva'/'negativa'.")
    # spec 017: proveniência de boato, opcional, escrita pelo Motor. Id do
    # narrador imediato. Ausência = 1º grau (vivido). SECRETO — nunca surfaçado.
    ouvido_de = fm.get("ouvido_de")
    if ouvido_de is not None and not isinstance(ouvido_de, str):
        errors.append("memory: 'ouvido_de' deve ser o id de quem contou.")
    about = fm.get("about")
    if about is not None and not isinstance(about, str):
        errors.append("memory: 'about' deve ser o id da entidade lembrada.")
    intensity = fm.get("intensity")
    if intensity is not None and intensity not in INTENSITIES:
        errors.append(
            f"memory: 'intensity' inválida: '{intensity}' "
            f"(permitidos: {', '.join(sorted(INTENSITIES))})."
        )
    state = fm.get("state")
    if state is not None and state not in MEMORY_STATES:
        errors.append(
            f"memory: 'state' inválido: '{state}' "
            f"(permitidos: {', '.join(sorted(MEMORY_STATES))})."
        )
    # spec 029: domínio de memória, fechado (ao contrário de 'evento').
    # Opcional na leitura (memórias antigas sem o campo continuam válidas).
    domain = fm.get("domain")
    if domain is not None and domain not in DOMAINS:
        errors.append(
            f"memory: 'domain' inválido: '{domain}' "
            f"(permitidos: {', '.join(sorted(DOMAINS))})."
        )
    return errors


def _validate_interactions(fm: dict) -> list[str]:
    """Checagem leve e comum a item/object: 'interactions' é opcional e consultivo (spec 002,
    RF-06 v1.1) — se presente, deve ser uma lista de mapas com 'action'. Não valida
    'requires'/'check' em profundidade: é contexto para o Árbitro, não regra de schema.
    """
    errors: list[str] = []
    interactions = fm.get("interactions")
    if interactions is None:
        return errors
    etype = fm.get("type")
    if not isinstance(interactions, list):
        errors.append(f"{etype}: 'interactions' deve ser uma lista.")
        return errors
    for i, entry in enumerate(interactions):
        if not isinstance(entry, dict):
            errors.append(f"{etype}: interactions[{i}] deve ser um mapa.")
            continue
        if not entry.get("action"):
            errors.append(f"{etype}: interactions[{i}] sem 'action' obrigatório.")
    return errors


LOCK_TYPES = {"item"}


def _validate_locks(fm: dict) -> list[str]:
    """Fecho e travas (spec 005): `state.fechado` bool e bloco `locks` com listas
    open/close de travas em conjunção. Comum a item e object."""
    errors: list[str] = []
    etype = fm.get("type")
    state = fm.get("state")
    if isinstance(state, dict) and "fechado" in state \
            and not isinstance(state.get("fechado"), bool):
        errors.append(f"{etype}: 'state.fechado' deve ser booleano.")

    locks = fm.get("locks")
    if locks is None:
        return errors
    if not isinstance(locks, dict) or not ({"open", "close"} & set(locks)):
        errors.append(f"{etype}: 'locks' deve ser um mapa com listas 'open' e/ou "
                      "'close'.")
        return errors
    if etype == "item" and not isinstance(fm.get("container"), dict):
        errors.append("item: 'locks' exige o bloco 'container' (sem contenção não "
                      "há o que trancar).")
    for lista in ("open", "close"):
        entries = locks.get(lista)
        if entries is None:
            continue
        if not isinstance(entries, list):
            errors.append(f"{etype}: 'locks.{lista}' deve ser uma lista.")
            continue
        for i, entry in enumerate(entries):
            if not isinstance(entry, dict) or entry.get("type") not in LOCK_TYPES:
                errors.append(
                    f"{etype}: locks.{lista}[{i}]: tipo de trava desconhecido "
                    f"(permitidos: {', '.join(sorted(LOCK_TYPES))})."
                )
                continue
            if entry["type"] == "item" and not (
                isinstance(entry.get("required"), str) and entry["required"].strip()
            ):
                errors.append(
                    f"{etype}: locks.{lista}[{i}]: trava de item exige 'required'."
                )
    return errors


def _validate_object(fm: dict) -> list[str]:
    errors: list[str] = []
    state = fm.get("state")
    if state is not None and not isinstance(state, dict):
        errors.append("object: 'state' deve ser um mapa.")
    errors.extend(_validate_interactions(fm))
    errors.extend(_validate_locks(fm))
    # spec 053: object passou a poder carregar um bloco `trabalho` (a fonte de fogo
    # tem prazo). Antes disto, um object com bloco malformado passava SEM ERRO
    # NENHUM — toda a validação vivia em `_validate_item_trabalho`, que só rodava
    # para item. O buraco existia desde a 052; foi fechado aqui.
    errors.extend(_validate_trabalho(fm, "object"))
    if isinstance(state, dict):
        extinto = state.get("extinto_em")
        if extinto is not None and (isinstance(extinto, bool)
                                    or not isinstance(extinto, (int, float))):
            errors.append("object: 'state.extinto_em' deve ser numérico (epoch).")
    return errors


def _validate_item(fm: dict) -> list[str]:
    errors: list[str] = []
    state = fm.get("state")
    if state is not None and not isinstance(state, dict):
        errors.append("item: 'state' deve ser um mapa.")
    errors.extend(_validate_interactions(fm))
    errors.extend(_validate_item_physics(fm))
    errors.extend(_validate_locks(fm))
    errors.extend(_validate_item_trabalho(fm))
    return errors


def _validate_trabalho(fm: dict, kind: str) -> list[str]:
    """O bloco `trabalho` — comum a item e object desde a spec 053.

    Extraído de `_validate_item_trabalho` quando a fonte de fogo passou a usar o
    mesmo relógio de prazo sendo um `object`. O que sobrou lá é só o que é DE ITEM
    (banda, teto de material, e a proibição de arma/armadura em peça em processo).
    """
    errors: list[str] = []
    bloco = fm.get(TRABALHO_BLOCO)
    if bloco is None:
        return errors
    if not isinstance(bloco, dict):
        errors.append(f"{kind}: 'trabalho' deve ser um mapa.")
        return errors
    if not isinstance(bloco.get("tool"), str) or not bloco.get("tool"):
        errors.append(f"{kind}: 'trabalho.tool' ausente (qual capacidade criou a peça).")

    por_prazo = "pronto_ts" in bloco
    por_esforco = "tempo_necessario_s" in bloco
    if por_prazo == por_esforco:
        # O CAMPO PRESENTE é o que diz qual relógio vale — sem enum de modo e sem
        # máquina de estados. Ter os dois (ou nenhum) é peça sem relógio nenhum.
        errors.append(f"{kind}: 'trabalho' precisa de EXATAMENTE um relógio — "
                      "'pronto_ts' (prazo) ou 'tempo_necessario_s' (esforço).")
    for campo in ("pronto_ts", "tempo_necessario_s", "tempo_trabalhado_s",
                  "trabalhando_desde"):
        valor = bloco.get(campo)
        if valor is not None and (isinstance(valor, bool)
                                  or not isinstance(valor, (int, float))):
            errors.append(f"{kind}: 'trabalho.{campo}' deve ser numérico (segundos).")

    # spec 053: `prato` virou `resultado` — genérico, com uma marca opcional. A
    # transformação acontece nos dois casos; `extinto` decide só se a coisa continua
    # VISÍVEL, não se continua existindo.
    resultado = bloco.get("resultado")
    if resultado is not None:
        if not isinstance(resultado, dict):
            errors.append(f"{kind}: 'trabalho.resultado' deve ser um mapa.")
        else:
            if not isinstance(resultado.get("nome"), str) or not resultado.get("nome"):
                errors.append(f"{kind}: 'trabalho.resultado.nome' ausente.")
            extinto = resultado.get("extinto")
            if extinto is not None and not isinstance(extinto, bool):
                errors.append(f"{kind}: 'trabalho.resultado.extinto' deve ser booleano.")
    return errors


def _validate_item_trabalho(fm: dict) -> list[str]:
    """A PEÇA EM PROCESSO e a BANDA de qualidade (spec 052).

    Nenhum dos dois é campo de autor: `trabalho` só existe em peça que o Motor
    criou, e `rarity` só nasce ao concluir uma forja. Quem escreve um mundo à mão
    nunca digita nem um nem outro — é a resposta ao portão do Princípio XI ("o
    criador precisaria conhecer o schema?": não).

    A regra que vale a pena ler duas vezes: peça EM PROCESSO não tem banda nem bloco
    mecânico. Enquanto está na bigorna ela não é arma nem armadura, e empunhá-la vale
    como improvisado — sem nenhuma regra nova para isso.
    """
    errors: list[str] = []
    rarity = fm.get("rarity")
    if rarity is not None and rarity not in RARITIES:
        errors.append(f"item: 'rarity' inválida: '{rarity}' "
                      f"(permitidas: {', '.join(RARITIES)}).")

    errors.extend(_validate_trabalho(fm, "item"))   # spec 053: a parte comum
    bloco = fm.get(TRABALHO_BLOCO)
    if not isinstance(bloco, dict):
        return errors
    for campo in ("banda", "teto_material"):
        valor = bloco.get(campo)
        if valor is not None and valor not in RARITIES:
            errors.append(f"item: 'trabalho.{campo}' inválida: '{valor}' "
                          f"(permitidas: {', '.join(RARITIES)}).")
    extremo = bloco.get("extremo")
    if extremo is not None and extremo not in ("sucesso", "falha"):
        errors.append("item: 'trabalho.extremo' só pode ser 'sucesso' ou 'falha'.")
    for campo in ("weapon", "armor", "rarity"):
        if fm.get(campo) is not None:
            errors.append(f"item: peça em processo não pode ter '{campo}' — "
                          "ela ainda não é o que vai ser.")
    return errors


def _validate_item_physics(fm: dict) -> list[str]:
    """Física do item (spec 004): size/weight_kg/wearable/container/state.slot.

    Todos opcionais no topo (mundo legado continua válido), mas estritos quando
    presentes — declaração parcial de `container` é inválida (FR-006/FR-012).
    """
    errors: list[str] = []
    size = fm.get("size")
    if size is not None and size not in SIZES:
        errors.append(
            f"item: 'size' inválido: '{size}' (permitidos: {', '.join(SIZES)})."
        )
    weight = fm.get("weight_kg")
    if weight is not None and (
        isinstance(weight, bool) or not isinstance(weight, (int, float)) or weight <= 0
    ):
        errors.append("item: 'weight_kg' deve ser número positivo.")

    wearable = fm.get("wearable")
    if wearable is not None:
        # spec 019: o NOME do slot é livre (vocabulário aberto). Exige-se só que
        # `wearable.slot` seja uma string não-vazia — "cabe neste corpo?" deixa de
        # ser questão de schema e passa a ser resolvida na hora de vestir, contra o
        # corpo do alvo (motor.body_of).
        slot = wearable.get("slot") if isinstance(wearable, dict) else None
        if not isinstance(wearable, dict) or not isinstance(slot, str) or not slot:
            errors.append(
                "item: 'wearable.slot' ausente ou vazio (deve nomear um slot de corpo)."
            )
        elif "speed_multiplier" in wearable:
            # spec 009: acelera a viagem enquanto vestido. Aceita ≤ 1 (é número
            # legítimo); o cálculo o neutraliza — só o que não é número positivo
            # é erro de schema.
            mult = wearable.get("speed_multiplier")
            if isinstance(mult, bool) or not isinstance(mult, (int, float)) \
                    or mult <= 0:
                errors.append(
                    "item: 'wearable.speed_multiplier' deve ser número positivo."
                )

    container = fm.get("container")
    if container is not None:
        if not isinstance(container, dict) or \
                "max_size" not in container or "max_items" not in container:
            errors.append(
                "item: 'container' exige 'max_size' e 'max_items' "
                "(declaração parcial é inválida)."
            )
        else:
            max_size = container.get("max_size")
            max_items = container.get("max_items")
            if max_size not in SIZES:
                errors.append(
                    f"item: 'container.max_size' inválido: '{max_size}' "
                    f"(permitidos: {', '.join(SIZES)})."
                )
            if isinstance(max_items, bool) or not isinstance(max_items, int) \
                    or max_items < 1:
                errors.append("item: 'container.max_items' deve ser inteiro >= 1.")
            # realismo: nada entra maior que o próprio recipiente (spec FR-006)
            own = size if size in SIZES else "P"
            if max_size in SIZES and SIZE_ORDER[max_size] > SIZE_ORDER[own]:
                errors.append(
                    "item: 'container.max_size' não pode exceder o 'size' do "
                    "próprio contêiner (nada entra maior que o recipiente)."
                )

    errors.extend(_validate_item_combat(fm))
    errors.extend(_validate_item_commerce(fm))

    state = fm.get("state")
    if isinstance(state, dict) and state.get("slot") is not None \
            and not (isinstance(state.get("slot"), str) and state.get("slot")):
        # spec 019: nome de slot livre; exige-se só que, se presente, seja string
        # não-vazia (o Motor grava aqui o slot onde a peça está acoplada).
        errors.append("item: 'state.slot' deve ser uma string não-vazia quando presente.")
    return errors


def _validate_item_commerce(fm: dict) -> list[str]:
    """Preço e disponibilidade do item (spec 011): value/for_sale/negotiable/currency.

    Todos opcionais. A ausência NÃO é omissão a corrigir: significa que o item não
    entra naquele tipo de negócio. Um mundo sem marcas não comercia, e isso é o
    comportamento desejado.
    """
    errors: list[str] = []
    value = fm.get("value")
    if value is not None and (
        isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0
    ):
        errors.append("item: 'value' deve ser número >= 0.")
    for campo in ("for_sale", "negotiable", "currency"):
        marca = fm.get(campo)
        if marca is not None and not isinstance(marca, bool):
            errors.append(f"item: '{campo}' deve ser booleano.")
    return errors


def _validate_item_combat(fm: dict) -> list[str]:
    """Arma e armadura do item (spec 008): weapon/armor.

    Ambos opcionais (item sem `weapon` vale como improvisado; sem `armor` não
    protege), estritos quando presentes. `armor` exige `wearable` no mesmo item —
    o que não se veste não protege (espelho de `locks` exigindo `container`).
    """
    errors: list[str] = []
    weapon = fm.get("weapon")
    if weapon is not None:
        if not isinstance(weapon, dict) or \
                "damage" not in weapon or "attribute" not in weapon:
            errors.append(
                "item: 'weapon' exige 'damage' e 'attribute' "
                "(declaração parcial é inválida)."
            )
        else:
            damage = weapon.get("damage")
            if isinstance(damage, bool) or not isinstance(damage, int) or damage < 1:
                errors.append("item: 'weapon.damage' deve ser inteiro >= 1.")
            if weapon.get("attribute") not in WEAPON_ATTRIBUTES:
                errors.append(
                    f"item: 'weapon.attribute' inválido: '{weapon.get('attribute')}' "
                    f"(permitidos: {', '.join(sorted(WEAPON_ATTRIBUTES))})."
                )

    armor = fm.get("armor")
    if armor is not None:
        if not isinstance(armor, dict) or "protection" not in armor:
            errors.append("item: 'armor' exige 'protection'.")
        else:
            protection = armor.get("protection")
            if isinstance(protection, bool) or not isinstance(protection, int) \
                    or protection < 0:
                errors.append("item: 'armor.protection' deve ser inteiro >= 0.")
        if fm.get("wearable") is None:
            errors.append("item: 'armor' exige 'wearable' (o que não se veste não "
                          "protege).")
    return errors


def _validate_rastro(fm: dict) -> list[str]:
    """Marca física de deslocamento (spec 034). Física/identidade pura —
    `quem`/`direcao` não se interpretam aqui, só se confere a FORMA."""
    errors: list[str] = []
    evento = fm.get("evento")
    if evento is not None and evento not in RASTRO_EVENTOS:
        errors.append(
            f"rastro: 'evento' inválido: '{evento}' "
            f"(permitidos: {', '.join(sorted(RASTRO_EVENTOS))})."
        )
    intensity = fm.get("intensity")
    if intensity is not None and intensity not in INTENSITIES:
        errors.append(
            f"rastro: 'intensity' inválida: '{intensity}' "
            f"(permitidos: {', '.join(sorted(INTENSITIES))})."
        )
    ttl = fm.get("ttl_seconds")
    if ttl is not None and (
        isinstance(ttl, bool) or not isinstance(ttl, int) or ttl <= 0 or ttl > 172800
    ):
        errors.append("rastro: 'ttl_seconds' deve ser inteiro entre 1 e 172800 (48h).")
    criado_em = fm.get("criado_em")
    if criado_em is not None and (
        isinstance(criado_em, bool) or not isinstance(criado_em, (int, float))
    ):
        errors.append("rastro: 'criado_em' deve ser numérico (timestamp).")
    return errors


def _validate_route(fm: dict) -> list[str]:
    errors: list[str] = []
    prereqs = fm.get("prerequisites")
    if prereqs is not None and not isinstance(prereqs, list):
        errors.append("route: 'prerequisites' deve ser uma lista.")
    if isinstance(fm.get("bidirectional"), (int, float)) and not isinstance(
        fm.get("bidirectional"), bool
    ):
        errors.append("route: 'bidirectional' deve ser booleano.")
    return errors


def type_of(frontmatter: dict) -> str | None:
    return frontmatter.get("type")
