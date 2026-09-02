"""Versão do server, em SemVer — a única fonte da verdade.

Por que existe: o devlog é a ferramenta de diagnóstico do projeto, e ler um log
sem saber que código o produziu já custou caro. Um turno foi jogado por uma hora
e meia contra um server que não tinha as tools da spec recém-implementada, e o
log não dizia nada a respeito — a única pista foi comparar o horário do processo
com o do commit. Com a versão carimbada em cada entrada, isso se vê de imediato.

Como versionar:
  MAJOR  quebra de contrato do mundo (schema obrigatório novo, campo removido
         que o save usa, endpoint mudando de forma)
  MINOR  capacidade nova (tool, canal de evento, consulta) — normalmente uma spec
  PATCH  correção de comportamento sem superfície nova

O MINOR acompanha a spec que introduziu a capacidade, quando há uma: a 014 leva
o server a 0.14.0. A 020 leva a 1.0.0 (MAJOR): reescreveu o motor de turno para
fase única e retirou o suporte a runtimes sem tool-calling — quebra de contrato de
runtime. 1.0.0 marca o motor de turno estabilizado; daqui em diante MAJOR é quebra
de contrato do mundo ou do runtime.
"""

from __future__ import annotations

__version__ = "2.27.3"

# Marco de cada MINOR/MAJOR, para quem for ler um log antigo saber o que existia.
# PATCHes (correções sem superfície nova) não ganham linha; ficam no git.
# (2.27.0 — spec 061: a intenção na mão do JOGADOR. Três portas de escrita
#  (`/api/intention/create|update|close`) para o DONO criar, corrigir e ABANDONAR
#  os compromissos do personagem dele, com ZERO LLM no caminho — nem Árbitro, nem
#  Mente, nem juízo, nem rolagem. É a metade que se sabia resolver do item 53.3: o
#  Torvin carregou dois dias a promessa de buscar cravos que estavam na mão de
#  quem estava ao lado dele (27 tentativas legítimas esgotadas), e a Elga ficou
#  parada com um compromisso com alguém que ela viu partir. Em nenhum dos dois o
#  personagem errou — o jogo é que não tinha porta de saída. O Princípio III
#  sobrevive porque quem escreve continua sendo o Motor: o que muda é de onde vem
#  o gatilho, e o item 40 já previu isto por nome ("front-face self-action"). Não
#  há juízo sendo contornado porque intenção NUNCA teve régua, não tem TTL e a
#  própria Mente já a reescreve no lugar. ZERO campo novo, ZERO primitiva nova, e
#  o `validator.py` intocado: `create_intention`/`update_intention`/
#  `close_intention` já existiam. "Abandonar" marca `status`, não apaga
#  (Princípio IV) — e a tela diz ABANDONAR, porque dizer "excluir" e não excluir
#  seria o jogo mentindo. Autorização no molde de `claim-character` (spec 056),
#  com a MESMA resposta para "não é seu" e "não existe", para a recusa não virar
#  oráculo de existência. Escrita REJEITA durante turno em voo, preservando o
#  invariante de que um turno não vê o mundo mudar debaixo dele.)
# (2.26.0 — spec 060: a cadeia que completa, e o pedido que emagrece. Quatro
#  etapas, todas medidas antes de aplicadas. (US1) O TURNO CONTINUA NO SUCESSO:
#  `_porPropostas` só chamava `continuar()` na RECUSA, então o passo que dava
#  certo encerrava a vez e A Mente nunca era perguntada "e agora?" — um sussurro
#  de dois passos rendia um (medido: 1.0 chamada por rodada em 35 rodadas, e o
#  controle de duas tools INDEPENDENTES falhava igual, então não era encadear).
#  Continuar é 44% mais barato que recomeçar: 4 chamadas e 36.863 tokens viram 3
#  e 20.726, porque o prefixo fica no cache. (US2) O ID NÃO CHEGA MAIS À MENTE:
#  ela aponta pelo NOME e o conector resolve — o enum não era imposto pelo
#  runtime (id fora dele saía 4/5), paralisava no ambíguo (mudo 5/5) e SUBSTITUÍA
#  em silêncio no ausente (examinou o fogão para quem pediu o destilador, 5/5).
#  Id inventado deixa de ser possível: ela nunca vê um. (US3) A cena desce em
#  PROSA — o formato mais barato E mais certeiro dos cinco medidos (20/20 contra
#  19/20 do JSON). (US4) As descrições passam pela RÉGUA DA RELEVÂNCIA: toda
#  frase responde "o que isto faz na situação?" ou "como eu chamo?"; a que
#  responde "como o sistema funciona por trás" sai, porque quem lê é A Mente e
#  para ela não existe Motor nem Árbitro. Onze descrições limpas, com lint
#  próprio no `selftest_phase44` — de que o anti-vazamento vira caso particular.
#  REVOGADO por medição: "o schema é IMPOSTO pelo runtime de tool-calling"
#  (spec 043 / item 52.5) é FALSO para Ollama + llama3.1:8b.)
# (2.25.0 — EMPUNHAR o que já se carrega, e o LAYOUT dos registros no mundo.
#  (a) `itens.bring_to_hand`, o espelho do `_accommodate` do item 44: o instrumento
#  de `write`/`sing` deixa de precisar estar JÁ na mão — basta que o personagem o
#  CARREGUE, e o Motor o traz, abrindo vaga na pega (guardando o que estava lá) se
#  preciso; sem saída, a recusa `maos_ocupadas` segue valendo, agora honesta.
#  Vestido nunca sobe sozinho (isso é `unequip`, decisão do personagem), e o gesto
#  é NARRADO (Princípio X). Custava um turno de `take` para pegar o que já se tinha
#  no bolso. (b) RASTRO vira registro, não entidade: `<lugar>/rastros/<id>.md`, o
#  mesmo desenho de `memories/`/`intentions/`, em vez de uma PASTA por marca —
#  eram 235 diretórios dentro dos lugares (67 só na praça). (c) toda ROTA passa a
#  morar na menor estrutura que contém as duas pontas, em vez de num `routes/` na
#  raiz do mundo; nenhum código dependia disso (`find_route` faz rglob), e o
#  caminho de runtime do `craft` já gravava assim. Migradores:
#  `migra_rastros.py` e `migra_rotas.py`.)
# (2.24.0 — spec 059: `write` — escrever num documento. Dois modos: ANCORADO
#  (`memoria_id`, transcrição verbatim do `conteudo` da memória, sem distorção —
#  o inverso exato do boato) e LIVRE (`texto`, VOZ sem ancoragem). Dois gates de
#  admissão lidos de prosa (superfície aceita escrita? instrumento na mão serve
#  pra escrever?), nenhuma rolagem depois deles. Zero primitiva nova: reusa
#  `read_doc`/`rewrite_description` (`eat` já as usa). `own_memories()` ganha
#  `require_sobre=False` para incluir memórias sem outro envolvido — o caso do
#  boticário sozinho, que `sing_memorias` excluiria.)
# (2.22.1 — spec 057, quatro consertos da exploração pós-implementação de craft.
#  (a) `REGUA_CRAFT` reforçada: banda `falha` precisa comunicar DEFEITO concreto na
#  `descricao_baixa` (o modelo real deixava fracasso quase indistinguível de sucesso).
#  (b) `craftable_entities` (`percepcao/consultas.py`) — TERCEIRO predicado de posse,
#  nem `alcançável` (`steal`, sem checagem) nem `disponível` (`comercio`, exige posse
#  comprovada — bloquearia material livre): passa por posse livre e própria, para em
#  posse RECONHECIDA de outro. Aplicado aos 5 enum_sources de material de trabalho
#  (`craft_materiais`/`forge_materiais`/`cook_ingredientes`/`brew_ingredientes`/
#  `kindle_materiais`) — antes, dava pra consumir o que outro personagem presente
#  segurava na mão. (c) `peca_ja_concluida`, recusa nova (forja E craft): "sem bloco
#  de trabalho" quase sempre é "já terminou", não "é de outra capacidade" — as duas
#  causas estavam conflated numa frase só. (d) craft agora GERA uma `route` ao
#  concluir uma `location` — achado sério: confirmado que aninhamento de pasta
#  sozinho NUNCA bastou pra alcançar um lugar (o único mecanismo é `enter_route`,
#  enum de destinos só vem de `route` declarada); sem isto a location criada nascia
#  ilhada. Testado de ponta a ponta: `enter_route` de verdade move um personagem pra
#  dentro da location criada e volta (bidirecional). Nenhuma superfície de tool nova
#  — por isso PATCH, não MINOR.)
# (1.1.1 — spec 025, 021 Fase C: refactor do fluxo de turno sem superfície nova.
#  Executores auto-suficientes (leem a própria cena, aplicam-e-registram), o funil
#  apply_resolution desidratado a sequenciador fino + _finalize_turn, os dois band-aids
#  de "cena congelada" removidos, crash do furto-duplo/transfer+steal impossível.
#  Comportamento-preservante — por isso PATCH, sem HISTORY própria.)
# (2.27.3 — spec 063, O ÍNDICE DE ARESTAS. Nenhuma superfície de mundo nova, nenhum campo
#  de schema, nenhuma tool — por isso PATCH, e o precedente é a 2.4.3 logo abaixo.
#  `motor/indice.py` (nível 0) torna o grafo que o mundo JÁ é (≈7 000 arestas em
#  `involved`/`about`/`from`/`to` + a contenção das pastas) atravessável nos DOIS sentidos,
#  em memória, nunca persistido. Sete consumidores migraram (`find_character_folder`,
#  `find_entity`, `dono`, `remembered_about`, `familiarity_with`/`sentiment_toward`,
#  `knows_route`/`recognizes_route`, `offered_by`, `scene_candidates`). Montar a face saiu de
#  80,9 s para 994 ms no pior caso (81×), e o mundo passou a caber em UM núcleo: 0,207 s de
#  CPU por segundo de relógio para os 38 personagens em cadência de 45 s, contra ~34.
#  Comportamento-preservante, e provado como tal: resposta de `/api/context` + `capacidades`
#  BYTE-IDÊNTICA nos 5 personagens medidos, e a suíte verde nos DOIS modos (61/61 com índice
#  e 61/61 com `LOREFORGE_SEM_INDICE=1`). Fase 62 nova: lê o fonte e reprova varredura
#  mundial nova, importação indevida no índice e gravação de relação derivada.)
# (2.4.3 — spec 043, fases A e B. Nenhuma superfície de mundo nova (a face exposta e o
#  endpoint de proposta ainda não existem), por isso PATCH. (a) `arbiter.build_ctx` extraído
#  de `resolve_with_tools`: a montagem da cena vira função PURA, reusável sem laço de LLM —
#  comportamento-preservante, provado por suíte idêntica + golden byte-equivalente. (b) a
#  TENTATIVA FRACASSADA passa a cobrar fadiga, um degrau abaixo do sucesso (primitiva nova
#  `fisica.custo_da_falha`): attack/carry/expulsar eram GRÁTIS na falha e agora cobram
#  `medio`; steal/heal cobravam o CHEIO e agora cobram um degrau abaixo. Capacidades SOCIAIS
#  não mudam — fadiga é de quem age fisicamente (spec 030, FR-003).)
# (2.4.2 — apoio à spec 042 (prompt de autonomia), sem superfície de mundo nova: (a) livro
#  de regras passa a repassar o NOME da tool por regra (`rulebook.to_groups` inclui `tool`, do
#  `key` já existente) — ancoragem determinística das `acoes` da Mente; a tela do jogador ignora
#  (prosa-só, IX). (b) recência da memória mais fina ("agora mesmo"/"há pouco" em vez de "há
#  instantes" <1h) — para a Mente ordenar atos e a GUI mostrar linha do tempo. PATCH.)
# (2.4.1 — sem superfície de mundo nova: (a) memória de transferência agora grava o
#  VERBO — "Peguei X" / "Larguei X" (antes "Passou por minhas mãos", ambíguo), pra o
#  recall responder com verbo+alvo; (b) MODO SOMBRA: o interpret do client passa a
#  devolver, no MESMO JSON, um `plano` (ações-do-livro ordenadas + narrativa) que sobe
#  ao /api/act e o server SÓ LOGA — telemetria, nunca à arbitragem. Investigação da
#  execução de intenção, fatia C do item 38. PATCH.)
# (2.17.1 — spec 051, sem superfície nova (nenhuma tool, campo ou endpoint), por isso
#  PATCH: a proficiência em `crime` passa a DECIDIR o furto. Desde a spec 029 todo furto
#  carimbava `domain: "crime"` nas memórias que gera, e desde então esse acúmulo não era
#  lido por ninguém — `crime` era a única proficiência do jogo que crescia e nunca era
#  consultada, e um gatuno de cem furtos rolava idêntico a quem nunca roubou.
#  `roll_steal_check` ganha `nivel_crime`, somado DIRETO no total (`d20 + mod(DEX) +
#  nivel_crime` vs `persuade_dc(exposição)`) — mesmo papel que `nivel_cozinha` em `cook`
#  e `nivel_acougue` em `butcher`, divergência deliberada de `cura` (lá a proficiência só
#  ajusta magnitude depois do desfecho). Os extremos deterministas (exposição 0/10)
#  continuam sem dado, fora do alcance da perícia. Quarto consumidor real da spec 029,
#  zero arquivo novo.)
HISTORY = {
    "2.23.0": "spec 058 — CANTAR. Tool nova `sing`: canta uma lembrança VIVA "
             "própria para quem estiver presente — SEM régua de admissão, SEM "
             "gate, SEM recusa de mérito (\"cantar não é cozinhar\": o "
             "personagem abre a boca e canta, sempre; a única negativa é o "
             "portão de estado, dormindo). Propagação reusa a PRIMITIVA de "
             "boato da spec 017 (`_record_hearsay`, estendida com `degraus` e "
             "`about` — renovação, nunca inflar arquivo por reprise), nunca "
             "chama `ask_about`. Rolagem `d20+mod(CHA)+nivel_musica+bonus` vs "
             "DC FIXA (não `persuade_dc` — medido que a LLM inverte a ordem "
             "dos feitos ao tentar julgar tamanho de episódio; o teto do "
             "reconto vem de `intensity`, campo já gravado). Régua de "
             "instrumento lida da PROSA do item na mão (medida "
             "determinística: 2/0/10). Cantar sozinho é permitido e conta "
             "como prática. Domínio `musica` (11º de fase 2). CONSERTO em "
             "`motor/juizo.py`: uma resposta com quebra de linha crua dentro "
             "de string JSON era perdida em silêncio — saneada agora para "
             "TODA capacidade julgada. CONSERTO em `_record_witness`: o ramo "
             "recorrente do leque de testemunha não propagava `valence` "
             "(byte-idêntico para o único usuário anterior, `witness_accuse`, "
             "que sempre tinha valência nula). REVOGADO `character.skills` — "
             "saiu dos obrigatórios e da projeção de `self` ao Árbitro (era a "
             "segunda via para \"quão bom ele é\" no domínio que esta spec "
             "passa a derivar de memória de verdade); `.md` legado com o "
             "campo continua válido, só ignorado.",
    "2.22.0": "spec 057 — CRAFT GENÉRICO + retrofit de testemunha. Tool nova "
              "`craft`: narração livre + `materiais` (param explícito, mesmo "
              "padrão de forge/cook/brew) cria item, object OU location numa "
              "chamada só — o Árbitro classifica TIPO, domínio, atributo e "
              "duração junto da nota de VIABILIDADE; o Motor escolhe "
              "item.md/object.md/location.md sem a Mente saber disso de "
              "antemão. Três caminhos no executor, não dois: síncrono (conclui "
              "no ato, molde forage/esquartejar), assíncrono (peça em processo "
              "no relógio de ESFORÇO, molde forja — primeira chamada nunca "
              "conclui), retomada (zero LLM). `trabalho.py` generalizado para "
              "`location.md` (terceiro tipo de arquivo com bloco `trabalho`) — "
              "`criar_peca` ganha `filename`/`extra_fm`. `posicao` (US5): item "
              "nasce solto ou com o personagem por julgamento; object sempre "
              "fixo na location; location sempre subpasta NOVA da location "
              "atual, nunca gera `route`; item assíncrono só migra pro autor "
              "na CONCLUSÃO (a peça em processo mora na location o tempo "
              "todo — é uma COISA no mundo, sobrevive a expulsão/ausência). "
              "Domínio `oficio` REINTRODUZIDO com sentido novo — residual, "
              "não a reserva que 052 substituiu (ver seção Domínios). "
              "RETROFIT (US4, achado real da Fase 0 do plano): os seis "
              "ofícios legados (forja/cozinha/botica/forage/esquartejar/"
              "fogo) nunca alimentavam o leque de testemunha — trabalhar em "
              "público não deixava rastro em quem via. Dois mecanismos, não "
              "um: Mecanismo A (`_WITNESS_CANAIS`/`_witness_facts`, pipeline "
              "de `Fato`) cobre abertura de todos + conclusão de "
              "ESFORÇO/síncronos; Mecanismo B (`trabalho."
              "_testemunhar_conclusao_prazo`, hook NOVO em `resolver_vencidas`) "
              "cobre a conclusão de PRAZO (cozinha/botica), que resolve "
              "preguiçosamente dentro de uma CONSULTA (`get_context`) e nunca "
              "passa pelo pipeline de mutação. `witness_forja` carrega domínio "
              "POR-INSTÂNCIA (ferraria/armaria — `_record_witness` ganha "
              "override `domain=fato.get(\"dominio\")`, `_write_memory` já "
              "aceitava). Posse (`dono()`, spec 036) por cinco dos sete "
              "eventos — `witness_forage`/`witness_fogo` ficam de fora "
              "(FR-020/021). Nenhum campo `owner` em entidade nenhuma.",
    "2.21.0": "spec 055 — PREPARAR. Tool nova `brew`: combina N ingredientes sobre um "
              "recipiente (`object` ou o LUGAR), molde EXATO de `cook` — não uma tool "
              "nova em espécie, `cook` com vocabulário de botica. Duas réguas de gate "
              "(RECIPIENTE_ADEQUADO + PREPARABILIDADE, mesmo argumento de calibração "
              "ambígua que separa fonte_de_calor/cozinhabilidade em cook), oito chaves "
              "na chamada — cópia estrutural de REGUA_COZINHAR. Domínio de "
              "proficiência novo (`botica`, INT — mesma razão de cook: dose, ordem, "
              "técnica; distinto de `herbalismo`/WIS, que `forage` já usa para "
              "perceber o terreno). O recipiente NUNCA é escrito nem trava — "
              "divergência deliberada de `forage` (que reescreve um object colhido "
              "porque há prosa autoral a proteger; aqui não há nada do tipo, e `cook` "
              "já decidiu que exclusividade de equipamento não vale o mecanismo: um "
              "fogão serve várias panelas ao mesmo tempo). Terceiro consumidor do "
              "relógio de PRAZO genérico (`trabalho.criar_peca` + "
              "`resolver_vencidas()`, specs 052/053) — código novo na trilha de "
              "materialização: uma linha em `_FATO_POR_TOOL`. `motor/juizo.py` sem "
              "extensão nenhuma. `character.skills.herbalismo`/`alquimia` seguem "
              "mortos, mesma decisão que `forage` já tomou.",
    "2.20.0": "spec 054 — COLHER. Tool nova `forage`: lê a prosa de um alvo — o "
              "LUGAR atual ou um `object` presente — e extrai matéria vegetal dele, "
              "duas réguas (HERBABILIDADE categórica, RIQUEZA rolada) + TRÊS pares "
              "nome/description (divergência deliberada de `butcher`: aqui a banda "
              "decide O QUE se trouxe, não só quanto). Domínio de proficiência novo "
              "(`herbalismo`, WIS — perceber o terreno, não força nem precisão de "
              "faca nem conhecimento de bancada); `skills.herbalismo` da ficha da "
              "Nerissa segue MORTO, de propósito. Síncrono como `butcher` (sem "
              "peça em processo): N ≥ 1 porções nascem no mesmo turno. O "
              "ESGOTAMENTO é ASSIMÉTRICO por tipo de alvo, e é a decisão central "
              "da spec: um `object` colhido tem o corpo REESCRITO para o estado "
              "colhido e ganha um bloco `trabalho` de PRAZO cujo `resultado` "
              "guarda o NOME e o CORPO ANTIGOS — sentido invertido do que "
              "`cook`/`forge_*` fazem —, e a rebrota é inteiramente "
              "`trabalho.resolver_vencidas()` (uma linha nova: a frase em "
              "`_FATO_POR_TOOL`); uma `location` NUNCA é tocada — nem campo, nem "
              "prazo, porque um ato de um personagem não pode reescrever o palco "
              "onde os outros estão. Nenhuma extensão de `io._MUTABLE_ROOT_BY_KIND` "
              "nem de `trabalho._ARQUIVOS` foi necessária: a arquitetura já tratava "
              "`location` como intocável. `forage_onde` é cópia literal de "
              "`cook_fonte`/`forge_fonte` (objects + o lugar), com objects "
              "`em_trabalho` excluídos do enum — o que dá a recusa por cooldown "
              "ZERO chamadas ao Árbitro sem nenhum código de guarda extra, mesmo "
              "molde que `kindle_materiais`/`forge_materiais` já usam para peça em "
              "processo. Único campo de schema novo: o valor `herbalismo` "
              "acrescido a `DOMAINS`.",
    "2.19.0": "spec 053 — ACENDER FOGO, e a primeira coisa do projeto que SE TRANSFORMA "
              "NO TEMPO SEM SER PORTÁTIL. `kindle_fire` cria uma fonte de fogo como "
              "`object` cujo significado inteiro vive na PROSA: nenhum campo diz que "
              "aquilo é fogo, esquenta 7 ou serve para forja — `cook` e `forge_*` leem a "
              "MESMA descrição e chegam às próprias conclusões, e a integração saiu de "
              "graça porque os enums de fonte de calor já são `objects + place`. Três "
              "réguas, não as quatro de `cook` (acender tem um universo só); o meio de "
              "ignição NÃO é gate, porque fogo por atrito existe — a falta de pederneira "
              "é difícil, não impossível, e entra na favorabilidade, que lê o que o ator "
              "carrega num bloco `em_maos` separado dos materiais. Falha PRESERVA o "
              "material (diverge de `cook`, onde os ingredientes somem no ato porque "
              "sempre nasce um prato). Domínio de proficiência novo (`fogo`, DEX). "
              "TRÊS mudanças em código compartilhado, cada uma consertando um defeito "
              "que já existia: (a) `trabalho` ficou CEGO AO TIPO e `prato` virou "
              "`resultado` — e `cozinha._resolve_pratos` foi removida porque iterava "
              "TODAS as peças de prazo do mundo lendo `bloco[\"prato\"]`, então a "
              "primeira peça de outro domínio a usar o mesmo relógio viraria \"Prato\" "
              "em silêncio; (b) `description` de object passou a descer no bundle — sem "
              "isso A Mente via só o NOME de uma entidade cujo sentido é a prosa; (c) "
              "`proficiencies_for` passou a contar `vezes`, corrigindo 479 práticas de "
              "`social` que o merge de memória recorrente tornara invisíveis (64 pares "
              "personagem×domínio subiram, retroativo, nenhum acima do teto). O fogo se "
              "apaga por prazo e NÃO é deletado: vira cinzas, ganha `state.extinto_em` e "
              "sai de cena por filtro em três pontos — Princípio IV inteiro, e o "
              "vestígio fica datado para uma investigação futura achar.",
    "2.18.0": "spec 052 — FORJAR EQUIPAMENTO, e o primeiro ato do projeto que ATRAVESSA "
              "O TEMPO E PODE SER RETOMADO. Duas tools novas (`forge_weapon`, "
              "`forge_armor`) com DUAS declarações e UM corpo — desvio declarado do "
              "Princípio XII item 2, pelo motivo certo: as réguas nunca chegam à face "
              "(os params de juízo somem do manifest), então duas tools não enxugam "
              "prompt nenhum; o que elas fazem é mover a escolha entre arma e armadura "
              "de um VALOR DE ENUM para o NOME DA TOOL, que modelos fracos erram muito "
              "menos. QUATRO mecanismos novos: (1) a PEÇA EM PROCESSO é uma ENTIDADE "
              "(`motor/trabalho.py`), não um campo no personagem — nasce na cena, "
              "qualquer um a vê, pega, rouba ou termina, e ninguém é dono dela; (2) o "
              "JULGAMENTO É CONGELADO — o Árbitro é consultado UMA vez, na abertura, e "
              "toda retomada é aritmética pura, ZERO LLM, quantas forem; (3) DOIS "
              "RELÓGIOS nomeados e distintos, compartilhando a mesma entidade: ESFORÇO "
              "(`forge_*`, só avança com alguém presente, crédito por sessão com clamp "
              "em min(decorrido, o que faltava), conclui num ATO) e PRAZO (`cook`, o "
              "fogo trabalha sozinho, resolve na consulta ao mundo) — unificá-los "
              "tornaria cozinhar interrompível e forjar passivo; (4) BANDA DE RARIDADE "
              "com CATRACA DE MÃO ÚNICA: cinco bandas, rolada uma vez, só desce quando "
              "alguém sem maestria põe a mão nela, e o EXTREMO natural do dado fica "
              "congelado AO LADO da banda para ser pago só na conclusão — é o que torna "
              "a obra excepcional imune à interrupção sem nenhuma exceção no "
              "rebaixamento. A banda máxima exige TRÊS condições independentes "
              "(material que permita, maestria que sustente, crítico), e `lendario` não "
              "é alcançável por margem nenhuma. Banda `falha` nasce SEM bloco mecânico "
              "e vale como improvisado por `fisica.weapon_of` — nenhum número novo foi "
              "inventado para punir. DOIS domínios de proficiência (`ferraria`, "
              "`armaria`, substituindo a reserva de `oficio`) e o TERCEIRO papel que a "
              "proficiência cumpre no projeto: TETO, não modificador. O FERRAMENTAL não "
              "tem parâmetro — a régua lê os objetos presentes E A DESCRIÇÃO DO LUGAR, "
              "porque numa oficina escrita no idioma deste projeto a bigorna está na "
              "prosa do ambiente (a Forja de Ferro de Porto Negro não tem NENHUM "
              "object): um desenho que só olhasse entidades recusaria forjar exatamente "
              "onde se forja. TRÊS RETROFITS no mesmo escopo: (a) `app.fate_twists` "
              "ganhou ramo de BANDA e passou a narrar `cozinha`/`cura`/`acougue`, que "
              "calculavam virada/crítico desde que nasceram e morriam em silêncio (o "
              "crítico era descartado pelo guard, e a virada saía como frase de FORÇA "
              "com id vazio — Princípio X violado em produção); (b) `cook` migrou para "
              "a peça em processo, `status.cozinhando`/`fisica.is_cooking` MORRERAM, os "
              "19 call sites passaram a `trabalho.is_busy(actor_folder)` e `get_context` "
              "deriva `self.ocupado` sem persistir nada — o prato agora nasce ONDE A "
              "PANELA ESTIVER; (c) `cook_fonte` passou a aceitar o LUGAR além dos "
              "objects, para que a mesma prosa não sirva para forjar e deixe de servir "
              "para cozinhar. MINOR: duas tools novas. Ver specs/052-forge-equipment/",
    "2.17.0": "spec 050 — ESQUARTEJAR. Tool nova `butcher`: extrai uma ou mais porções "
              "de carne crua de um corpo QUE JÁ ESTÁ MORTO. Nasceu de uma sondagem real "
              "nesta sessão — um coelho morto criado no mundo confirmou que NENHUMA tool "
              "de item enxergava um `character.md`, mesmo morto (`take`/`cook` recusavam "
              "estruturalmente, zero LLM). DUAS réguas numa chamada só — "
              "ESQUARTEJABILIDADE (categórica: este corpo é feito de carne? golem/"
              "esqueleto/construto pontuam 0, SEM TESTE) antes de RENDIMENTO (quanto "
              "daquela carne está aproveitável, rolada com `d20 + mod(DEX) + "
              "nivel_acougue`) — divididas de propósito, no molde de "
              "`fonte_de_calor`/`cozinhabilidade` em `cook`, pra que uma calibração "
              "ambígua do Árbitro nunca deixe passar carne de quem não é carne. O "
              "resultado é N ITENS (nunca um único item com campo de quantidade): a LLM "
              "escreve nome/description UMA vez, o Motor deriva quantas porções e o "
              "peso de cada uma deterministicamente do peso do corpo e da banda — mesmo "
              "padrão de item fungível que as moedas do mundo já usam, sem estender o "
              "parser de julgamento (`motor/juizo.py`) pra arrays. O corpo NUNCA é "
              "apagado nem reescrito (`character` é exceção-zero ao Princípio IV, ao "
              "contrário do ingrediente que `cook` consome) — só ganha "
              "`status.esquartejado: true`, marcador permanente que impede uma segunda "
              "extração. Proficiência em `\"acougue\"` (3º consumidor de "
              "`proficiencies_for`, mesmo mecanismo assintótico de `cozinha`/`cura`) "
              "soma DIRETO na rolagem. TRÊS simplificações deliberadas vs. `cook`: sem "
              "materialização preguiçosa (esquartejar não tem tempo de preparo real — "
              "YAGNI), sem gate de exclusividade próprio, e o `enum_source` de "
              "personagens mortos (`butcher_alvo`) é UMA linha em "
              "`arbiter.py::_verb_candidates`, copiando o padrão que `heal` já usa pra "
              "`incapacitado` — a hipótese inicial de que a percepção filtrava mortos "
              "era falsa (bug de schema no fixture de teste, não comportamento do "
              "Motor). MINOR: tool nova. Ver specs/050-butcher-corpse/",
    "2.16.0": "spec 049 — FOME E SEDE COM O TEMPO REAL. `eat`/`drink` passam a "
              "gravar, além do rótulo já existente, uma âncora interna por régua "
              "(`status.hunger_ts`+`hunger_note`, `status.thirst_ts`+`thirst_note` "
              "— epoch do ato + a nota 0-10 de saciedade/hidratação daquele ato, "
              "segredo do server). `hunger_label`/`thirst_label` "
              "(`motor/fisica/primitivas.py`), lidas por `get_context`, passam a "
              "DERIVAR o rótulo do tempo real decorrido desde a âncora contra "
              "dois limiares lineares por nota (nota mais alta segura mais "
              "tempo; sede sempre aperta antes de fome na mesma nota) — puro "
              "cálculo na lane de consulta, sem escrita, mesmo molde de "
              "`tempo.py::current_moment()`. Personagem sem âncora (nunca comeu/"
              "bebeu via tool, ou ficção autorada à mão) mantém o comportamento "
              "de sempre, sem decadência. Consulta enriquecida com mecânica "
              "nova — MINOR.",
    "2.15.0": "spec 048 — COZINHAR. Tool nova `cook`: combina N ingredientes (em "
              "qualquer lugar ao alcance) sobre uma fonte de calor presente, julgada "
              "por QUATRO réguas (fonte de calor, cozinhabilidade, favorabilidade, "
              "duração) numa chamada só. Três primeiras estreias do projeto de uma "
              "vez: (1) `io.create_entity`, primeira primitiva que INSTANCIA entidade "
              "nova em vez de mover/consumir/reescrever — simétrica a "
              "`io.remove_entity` (spec 046); (2) materialização PREGUIÇOSA — os "
              "ingredientes somem no ATO, mas o prato só existe quando o tempo real "
              "de preparo se cumpre, resolvido em `get_context` no MESMO mecanismo "
              "que já resolve chegada de rota (`deslocamento._resolve_arrivals`), "
              "segunda família a usá-lo; (3) `fisica.is_cooking`, molde exato de "
              "`is_resting` — enquanto um prato está pendente, nenhuma outra tool do "
              "ator é aceita, e o manifest do turno some de mutação (mesmo gate "
              "cosmético do descanso, generalizado). Banda RUIM nunca é falha total: "
              "sempre nasce um prato, comprometido — a punição é inteiramente "
              "deferida para quando `eat`/`drink` julgar essa description depois "
              "(medido por sondagem real: toxicidade 6–9 em 9/9 tentativas sobre "
              "descriptions de banda ruim, 0/0/0 na banda ótima da mesma cena). "
              "Porque a banda só existe DEPOIS da rolagem, a mesma chamada pede TRÊS "
              "descriptions candidatas (uma por banda) — achado de sequência que não "
              "tinha precedente em `eat`/`drink` (cuja prosa nunca dependia de dado). "
              "RETROFIT que atravessa a fronteira da spec: `memoria.proficiencies_for` "
              "deixou de devolver um NÍVEL INTEIRO 0–5 com teto duro (peso≥64) e "
              "passou a devolver um FATOR contínuo, assintótico, sem teto de peso "
              "acumulado (`TETO·peso/(peso+K)`) — pedido do mantenedor para valer "
              "em QUALQUER proficiência; `cura` (spec 032) não precisou de nenhuma "
              "linha de código alterada (os dois pontos onde consome o valor já "
              "grampeavam o resultado). A proficiência em `cozinha` soma DIRETO no "
              "total da rolagem de favorabilidade — decide a própria banda —, "
              "divergência DELIBERADA do papel que a mesma proficiência cumpre em "
              "`cura` (lá só ajusta magnitude depois da banda decidida): o projeto "
              "não impõe um único papel para \"como perícia entra\", cada capacidade "
              "escolhe o que faz sentido pro que está em jogo. `julgamento()` "
              "generalizado de um texto único pra VÁRIOS textos candidatos na mesma "
              "resposta (`eat`/`drink` migrados no mesmo passo, byte-equivalentes).",
    "2.14.0": "spec 047 — BEBER. Tool nova `drink`: bebe de um item (cantil, copo, "
              "garrafa) OU direto de uma FONTE AMBIENTAL presente (`object` como um "
              "rio/poço, inesgotável) — julgada por até CINCO réguas (bebibilidade, "
              "hidratação, embriaguez, toxicidade, consumo — a última só para item). "
              "Revisão por casos de uso REAIS antes do plano (rio na descrição da "
              "location; cantil ambíguo; copo; garrafa no chão) achou dois buracos "
              "no desenho inicial e os fechou na própria spec: (1) o alvo pode ser "
              "um `item` finito OU um `object` ambiental — a MESMA régua de "
              "bebibilidade decide os dois, sem nenhum campo novo em nenhum schema; "
              "(2) `drink` NUNCA chama `io.remove_entity` — mesmo em consumo 0, "
              "SEMPRE reescreve a descrição para um estado vazio, porque bebida "
              "quase sempre tem um RECIPIENTE reutilizável que a exceção do "
              "Princípio IV (aberta por `eat`) nunca foi desenhada para proteger. "
              "Embriaguez é eixo PRÓPRIO, independente de toxicidade — o mesmo gole "
              "pode falhar nos dois testes e aplicar `bêbado` E `doente` juntos, "
              "numa ÚNICA memória combinada (nunca duas do mesmo ato). "
              "`status.thirst` é campo NOVO (ao contrário de `status.hunger`, que "
              "já existia morto antes de `eat`) e sobe ao contexto da Mente em "
              "`self.necessidade.sede`, ao lado de `fome`/`cansaco` — sem isso "
              "repetiria o bug que o item 51 já corrigiu (campo que muda mas "
              "ninguém sabe que sente). ZERO extensão de arquitetura: `ToolSpec."
              "juizo` multi-par e `react_actor_memory` em `rejected` já existiam, "
              "prontos, desde `eat` — `drink` só consome infraestrutura genérica. "
              "MINOR: tool nova. Ver specs/047-drink-item/",
    "2.13.0": "spec 046 — COMER. Tool nova `eat`: consome um item comestível julgado "
              "por QUATRO réguas dedicadas (comestibilidade, saciedade, toxicidade, "
              "consumo) — a primeira capacidade a pedir mais de uma nota, o que "
              "estendeu `ToolSpec.juizo` de par único para tupla de pares (migrando as "
              "8 tools que já usavam a forma antiga, no mesmo passo — nenhuma convive "
              "em duas formas). Comestibilidade preenche a lacuna que o Motor "
              "estruturalmente não valida sozinho (ele sabe presença/alcance; não sabe "
              "que uma bota não é comida); nota 0 recusa SEM gastar as outras três. "
              "Saciedade escreve `status.hunger` em RÓTULO pela primeira vez (o campo "
              "já existia, mas nenhuma tool o escrevia). Toxicidade separa o RISCO que "
              "o Árbitro julga do TESTE que o Motor resolve (`toxin_dc`, curva nova — "
              "inclinação inversa de `persuade_dc`, porque nota alta aqui significa "
              "mais perigoso, não mais fácil). Consumo decide entre marcar "
              "`state.consumido: true` (o item some do jogo, mas o ARQUIVO NUNCA é "
              "deletado — Princípio IV) ou reescrever a `description` em lugar. "
              "Correção do mantenedor durante o planejamento: uma recusa de MÉRITO "
              "(comestibilidade 0) também vira memória — não é caso especial, é a "
              "regra geral (o que só sai em narração efêmera some do que o personagem "
              "'sabe' no próximo tick), o que abriu `react_actor_memory` para também "
              "ler `op[\"memory\"]` em fatos `rejected`, não só `applied` — peça "
              "reusável para a próxima tool. MINOR: tool nova.",
    "2.12.0": "item 51, fatia 1 — A NECESSIDADE CHEGA À MENTE, em RÓTULO. A segunda "
              "bússola do tick autônomo estava desligada: o prompt de autonomia lia "
              "`status_sobrevivencia` numa 'escala de 0 a 10' e o conector a "
              "alimentava com `status.survival_level || 0` — campo que NUNCA existiu "
              "em lugar nenhum do mundo, logo constante ZERO para todo personagem "
              "desde sempre. E o modelo lia o zero como urgência ('com o status de "
              "sobrevivência em 0, ele está focado em resolver problemas imediatos, "
              "como encontrar comida'), o que explica retroativamente o Draven e o "
              "Doncel interrogando um cão sobre comida com `hunger: saciado`. Pior: "
              "`hunger`/`fatigue` não chegavam à Mente por NENHUMA outra via — o "
              "payload dela não trazia status —, então o personagem não tinha como "
              "SABER que estava com fome, e seis do mundo estavam. "
              "SUPERFÍCIE NOVA: `self.necessidade` no contexto ({fome, cansaco}), "
              "derivada por `fisica.hunger_label`/`fatigue_label`. RÓTULO e não "
              "escala, porque pedir 0-10 já era o erro: a regra do projeto é 'fato "
              "vai em rótulo, não número — o número é segredo do mundo'. Um "
              "personagem sabe que está faminto, não que está em 7 de 10, e rótulo "
              "não permite a inversão que o modelo fez com o zero. A normalização do "
              "vocabulário livre do mundo (saciado/satisfeita/faminto/extremo/'com "
              "fome') mora na LEITURA, não numa migração de fichas — mesmo princípio "
              "de `ensure_fatigue`. O cansaço é faixa do PRÓPRIO teto, porque 70 num "
              "teto de 100 e num de 120 são coisas diferentes. `status` cru segue no "
              "contexto ao lado: a régua do Motor precisa do número. E a seção 2 do "
              "prompt de autonomia raciocina sobre o rótulo, sem escala e sem exemplo. "
              "MINOR: campo novo no contexto.",
    "2.11.0": "itens 53.4/53.5/53.6 — a rodada que saiu de ver o Irmão Tobias passar "
              "TRÊS HORAS pedindo à Nerissa um caminho que ele já sabia. "
              "(a) 53.4 — A MEMÓRIA REPETIDA VIRA UMA SÓ. Cada pergunta gravava um "
              "arquivo, e ele chegou a 35 das 40 memórias VIVAS sendo a MESMA recusa: "
              "a vida dele soterrada, o contexto dobrado (9.128 → 20.631 tokens), o "
              "turno de 68s a 260s com timeout em 34% das vezes — e, o pior, virou "
              "COMBUSTÍVEL: sem intenção e sem urgência biológica a memória era a única "
              "bússola do tick, e apontava 35 vezes para o assunto malresolvido. Ele "
              "perguntava porque lembrava de ter perguntado. `_remember_recurring` "
              "generaliza o `criar OU renovar, nunca duplicar` que só a memória de rota "
              "tinha (spec 013); a fusão é por ASSUNTO e o texto adensa sem número no "
              "corpo (Princípio V). "
              "(b) 53.5 — RECUSA GRATUITA: se todo caminho que o informante ensinaria já "
              "está vivo na memória de quem ia perguntar, `ask_directions` recusa com "
              "frase de mundo, sem cobrar fadiga e sem pedir juízo ao Árbitro — a "
              "decisão é anterior à conversa. Não é o mundo barrando, é o personagem "
              "lembrando. "
              "(c) 53.6 — O RAMO DE CRIAR INTENÇÃO ESTAVA MORTO. O tick autônomo bifurca "
              "(quem tem compromisso age por ele; quem não tem para e faz um), e o `if` "
              "que fazia isso foi apagado num refactor de prompts em 06/08, deixando "
              "`REFLECT_COMMAND` órfão por uma semana. Falhava em SILÊNCIO — um "
              "personagem sem intenção nunca fazia nenhuma, e isso parece apatia. "
              "Religado, com o texto reescrito para o formato de hoje (o antigo mandava "
              "descrever a `action`, campo que o tool-calling aposentou) e `refletir` "
              "virou rotina editável no painel. Nada do Motor mudou em (c). MINOR pela "
              "recusa nova de `ask_directions`.",
    "2.10.0": "itens 44/45 — A TRAVA DAS MÃOS. `maos_ocupadas` era a recusa mais "
              "frequente do jogo e quase sempre injusta: a regra estava certa e o "
              "resultado era que NINGUÉM de mãos cheias recebia nada, nem uma moeda — "
              "o gesto social mais comum virando turno perdido. Medido: o Torvin passou "
              "dois dias tentando entregar uma moeda ao Obadiah, que estava de mãos "
              "cheias justamente com o feixe de cravos que o Torvin queria. "
              "`transfer_item` passa a ACOMODAR antes de recusar, nos DOIS lados "
              "(decisão do mantenedor: simetria), em duas saídas — (1) o que chega vai "
              "para um contêiner aberto de quem recebe, sem mexer em mão nenhuma; "
              "(2) só se não couber, libera uma vaga da pega guardando o que já estava "
              "lá, nunca o item da própria ação. Nunca o chão: perder item sem perceber "
              "é pior que a recusa que isto evita. Sem saída, `maos_ocupadas` segue "
              "valendo, agora honesta. O desvio é DECLARADO (`applied.acomodou`) e "
              "narrado na mesma frase — Princípio X não admite o mundo guardar algo de "
              "alguém em silêncio. `fisica.open_container_for` é a primitiva, promovida "
              "do comércio (que já fazia isto para permitir pagar com três moedas) — "
              "tool não chama tool, o reuso mora na primitiva (Princípio XII). "
              "SUPERFÍCIE NOVA: `stow` aceita `container` OPCIONAL e acha sozinho a "
              "primeira bolsa aberta com espaço — guardar é o gesto com que se libera a "
              "mão, e exigir que A Mente escolha o contêiner é cobrar dela uma decisão "
              "que o corpo toma sozinho (3 das 9 chamadas de `stow` do jogo morreram "
              "por não nomear destino). Por isso MINOR. "
              "Item 53.2 (A RAJADA) foi MEDIDO nesta versão, mas o conserto ficou em "
              "aberto no servidor — nada do Motor mudou por ele; o conserto é todo do "
              "CONECTOR. O modelo devolve VÁRIAS tool "
              "calls numa resposta só e o conector despacha todas, uma ida ao mundo por "
              "item. Medido em 869 propostas: cadeia de 1 recusa 29%, de 2 recusa 27%, "
              "de 3+ recusa 42% (e só 8% delas têm sequer um alvo em comum); dentro das "
              "longas a recusa vai de 20% na 1ª a 62% da 6ª em diante. Um teto de duas "
              "foi tentado e REVERTIDO a pedido do mantenedor: teto trata sintoma, e o "
              "que se quer é que A Mente PLANEJE uma sequência deliberada de qualquer "
              "tamanho. O conserto que ficou é outro: a recusa MATA O RESTO DA FILA e o "
              "turno REPLANEJA — uma sequência é encadeada, e os passos de trás "
              "pressupõem os da frente. Isso virou uma decisão anterior deliberada (as "
              "propostas seguintes valiam mesmo depois de uma recusa). O que já foi ao "
              "mundo não volta no replano; MAX_REPLANOS fecha o turno para que uma "
              "recusa teimosa não pense para sempre. E o prompt foi reescrito em forma "
              "procedural, sem exemplo ancorado neste mundo (exemplo induz o modelo a "
              "repetir a sequência do exemplo). A medição DESMENTE o rótulo do 52.5: 54% das "
              "recusas de alvo fantasma nasciam em rajada — contra 2% das recusas "
              "in-world legítimas, o controle que prova que o sinal não é artefato.",
    "2.9.0": "item 52 — a rodada que saiu de VER a Nerissa jogar 11 horas (391 turnos, "
             "84% sem efeito no mundo). Todo o lote 52.x saiu carimbado 2.8.0 por "
             "esquecimento meu; esta linha cobre o lote inteiro, e quem ler um log "
             "entre 2.8.0 e 2.9.0 deve suspeitar da versão, não do log. "
             "(a) 52.3 — O MATERIAL DA CONSULTA CHEGA À MENTE. Dos cinco canais de "
             "`arbiter._MATERIAL_CH`, o `tools/call` encaminhava só `reconhecimentos` e "
             "`informes`; `lido`, `wares` e `falas` morriam no servidor. Eram 197 dos "
             "391 turnos dela em capacidades cujo RESULTADO ela nunca recebia — olhou a "
             "mesma bolsa 40 vezes porque olhar não devolvia nada. O stdio segue "
             "descartando `_narrativa` de propósito (host externo recebe só a frase de "
             "mundo); o material é do caminho HTTP, por onde A Mente fala. "
             "(b) 52.1 — A PANE DO JUÍZO VIROU ALTA: o Árbitro caía por cota e 8 "
             "capacidades julgadas degradavam em silêncio (189 falhas, 148 numa "
             "madrugada). `build_ask` coleta as falhas, o outcome sobe "
             "`juizo_indisponivel` e o MCP manda em `_sistema` — FORA do `_narrativa`, "
             "senão A Mente teceria pane como fato do mundo. "
             "(c) 52.2/52.5 — A PERGUNTA QUE NÃO RENDEU deixa de ser muda: `ask_about` "
             "sobre o que o informante não conhece recusa com `nada_a_contar` (regra que "
             "a spec 017 já tinha), e a recusa registra memória NOS DOIS LADOS. "
             "(d) O RECONTO VIROU UM Z: as lembranças vivas sobre o assunto são "
             "sanitizadas e o mundo escreve UM texto pela LLM, na voz de quem conta — "
             "uma memória de cada lado (\"H me contou Z\" / \"contei a A, Z\") em vez de "
             "18 arquivos por turno. A distorção do reconto é FEATURE, não defeito. "
             "(e) 52.6 — sono, despertar e intenção passam a derivar memória `mutate` "
             "de vida curta e sem renovação, e o `evento` gravado vem da tool de origem. "
             "MINOR: canais de material e de sistema novos descendo à Mente.",
    "2.8.0": "SUPERFÍCIE NOVA PARA A MENTE, em três frentes. (a) spec 040 finalmente "
             "CHEGA à Mente: `consultar_memoria` e `consultar_momento` existiam no "
             "Motor e eram servidas por `/api/consult`, mas `face.build` iterava só "
             "`registro.specs()` (mutação) e nunca `consult_specs()` — a consulta era "
             "código morto do ponto de vista do jogo. Descem marcadas com "
             "`annotations.readOnlyHint`, sem `prosa` obrigatória, fora do manifesto "
             "de ativação, e o conector consulta-e-CONTINUA pensando na mesma vez. "
             "(b) item 50 — `sleep` era um ALTERNADOR que decidia deitar×acordar pelo "
             "estado do arquivo, em silêncio; virou `sleep` + `wake_up`, dois corpos, "
             "com recusa própria (`ja_dormindo`, `nao_esta_dormindo`) em vez de virar "
             "a ação oposta à pedida. `ToolSpec.only_while_resting` novo: o gate de "
             "descanso deixou de escrever a face à mão no `build_tools`. "
             "(c) a face não desce mais a quem CAIU — morto vê nada, incapacitado vê "
             "só a lane de consulta (o servidor já recusava tudo; agora também não "
             "oferece, e a vez não queima uma chamada de modelo à toa). "
             "A bancada acompanha: `/api/spec` passa a declarar as consultas "
             "(`x-consulta`) e o `spec.html` ganhou filtro por personagem, que mostra "
             "a face de quem você escolher.",
    "2.7.0": "spec 044 (continuação) — O PAINEL DO CONECTOR e a rodada de defeitos "
             "achados jogando. Sem superfície de mundo nova: tudo do lado do "
             "conector e da tela. O conector passa a servir a própria página de "
             "configuração em `/` (mundo, personagem com troca AO VIVO, modelo, "
             "laço automático, os 4 prompts, inventário de extensões) — prompt "
             "virou TEXTO e não `.js`, e escrita só de 127.0.0.1. Do lado da "
             "tela: todo evento do conector passa a dizer DE QUEM é (era a raiz de "
             "cinco defeitos, entre eles a resposta aparecer no personagem errado), "
             "a trava do botão virou local e imediata, o rascunho da ação voltou a "
             "aparecer palavra a palavra, e a reconexão parou de inundar a "
             "interface. MINOR: nada do Motor, do Árbitro ou das capacidades mudou.",
    "2.6.0": "spec 044 — A CISÃO DO CLIENT. A Mente saiu do navegador: `connector/` "
             "é um processo que o jogador baixa e roda na PRÓPRIA máquina, com o "
             "próprio modelo e a própria chave — que agora nem poderia estar numa "
             "página servida pelo projeto. O laço do turno (interpretar → propor → "
             "narrar) mudou de dono: era `client/app.js`, agora é `connector/laco.js`, "
             "e por isso o personagem deixou de depender de uma aba aberta (headless "
             "é modo nativo). MUDANÇA DE CONTRATO DA TELA: `client/` não chama modelo "
             "nenhum, perdeu o formulário de modelo/chave, e passa a receber beats e "
             "prosa do conector por SSE. Superfície nova no mundo: `POST /api/registro` "
             "(o racional da Mente, canal PRÓPRIO fora do caminho da proposta) e a "
             "captura do turno em `resolver_proposta` — gravados em `registro/`, "
             "WRITE-ONLY PARA O JOGO: nenhum caminho de leitura do jogo os alcança, e "
             "`selftest_phase47` afirma isso estruturalmente. `/api/mcp` ganha "
             "`turno_id` na query, que costura as duas metades do registro. MINOR: "
             "nada do Motor, do Árbitro ou das capacidades mudou.",
    "2.5.0": "spec 043 — AS CAPACIDADES DESCEM À MENTE. Superfície nova: `GET "
             "/api/context` devolve `capacidades` (a face da cena, com os alvos "
             "vivos); `POST /api/tools/<nome>` é a via de PROPOSTA (uma rota por "
             "capacidade, cada chamada um turno); `GET /api/spec` gera OpenAPI 3.1 "
             "do registro; `mcp_server.py` expõe o mesmo por Model Context Protocol "
             "(stdio), como CLIENTE do REST — nunca 2º escritor. A FRONTEIRA: o "
             "parâmetro de JUÍZO (a nota de régua) some da face e a capacidade pede "
             "a nota ao mundo por `ctx.ask` + a régua co-locada (`juizo=(param, "
             "REGUA)` no ToolSpec); nota vinda de fora é descartada. As 8 réguas "
             "saíram de arbiter.py (system prompt: 15.164 -> 7.151 chars). Exige "
             "constituição v2.0.0 (Princípio IX redefinido: ESCOLHA x JUÍZO). "
             "Portal APOSENTADO (a `description` da declaração virou o texto "
             "player-facing, fonte única). Fadiga passa a ser cobrada na tentativa "
             "FRACASSADA (um degrau abaixo do sucesso; social cobra de quem tentou, "
             "superando a spec 030 FR-003). Client: `consulteRules()` removido, A "
             "Mente ancora na face real e propõe por capacidade; narração e "
             "intenção STREAMAM; o beat in-world pinta o fato na hora.",
    "2.4.0": "spec 041 — Expulsar (pôr um personagem para fora à força). Tool de "
             "MUTAÇÃO do Árbitro (@tool_spec interno, como attack) na família de "
             "deslocamento — por isso MINOR. COMPÕE primitivas existentes (zero "
             "rolagem nova): resolução do levar-à-força (roll_resist_check de pé / "
             "roll_push_check caído) + move SÓ o alvo (_enter_route_locked no alvo) — "
             "o ATOR FICA (a diferença vs carry). Memória: rancor `large` no EXPULSO "
             "(gated por percepção; dispara trauma) + o modo NOVO `depende_observador` "
             "nas testemunhas (a valência sobre o expulsor é DERIVADA por observador do "
             "sentiment_toward pelo expulso — mágoa→+, estima→−, neutro→neutro; dente "
             "mecânico na reputação). Manifest interno; prosa própria no portal. Aditivo "
             "ao molde 038 (nada do caminho de mutação muda). Ver specs/041-expel-character/",

    "2.3.0": "spec 040 — Tools de Consulta da Mente (memória e momento). Capacidade "
             "NOVA (um CANAL de consulta que a Mente PUXA) — por isso MINOR. Nasceu uma "
             "LANE PARALELA e aditiva no registro (`ConsultSpec`/`consult_spec`/"
             "`consult_specs` em `motor/registro.py`) — o caminho de MUTAÇÃO "
             "(`ToolSpec`/`@handler`/`apply_op`/FACE) fica INTOCADO (restrição "
             "não-negociável). `consultar_memoria` (corpo `recall` em `percepcao/"
             "consultas.py`, reusa `memory_involved`/saliência; filtro sujeito+tema, "
             "prosa, ausência honesta, perspectiva) e `consultar_momento` (`motor/"
             "tempo.py`, relógio real→prosa). Despacho GENÉRICO `GET /api/consult` "
             "(app.py, molde /api/observe). No client (`mente.js`): tabela "
             "`CONSULT_TOOLS[]`, `consultar_regras` da 039 MIGRADO, `deriveWhisper` "
             "agora AGÊNTICA. Portal decisão B (as duas player-facing, dois gatilhos "
             "como `examine`); `portal/sync.py` descobre `consult_specs()`. Read-only: "
             "consultar não muta, escrita segue no Árbitro (Princípio III). Fases "
             "núcleo + `selftest_phase42` + `selftest_portal` (31) verdes. Ver "
             "specs/040-consult-memory-time/",
    "2.2.0": "spec 039 — Livro de Regras para A Mente. Capacidade NOVA no PROJETO "
             "(um portal INDEPENDENTE em portal/ — processo próprio stdlib — serve o "
             "repertório player-facing em prosa; a Mente o consulta via Tool agêntica "
             "de LEITURA em client/mente.js) — por isso MINOR. IMPORTANTE: o runtime do "
             "GAME server (motor, arbiter, /api/act e demais rotas) fica INALTERADO — "
             "portal/sync.py só LÊ nomes de @tool_spec em build; a única mudança em "
             "server/ é o encadeamento de portal/selftest_portal.py no selftest. Um log "
             "carimbado 2.2.0 tem o MESMO comportamento de turno que 2.1.0.",
    "2.1.0": "spec 038 — Tool como plugin auto-declarado. Capacidade NOVA de engine "
             "(uma tool passa a tocar UM lugar), sem quebra de CONTRATO do mundo "
             "(schemas/endpoints/`motor.X` inalterados; o `world.md` de ativação é "
             "OPCIONAL — ausência = todas as tools ativas) — por isso MINOR. As 32 "
             "tools viraram DECLARAÇÕES `@tool_spec` co-localizadas no Motor "
             "(`motor/<dom>/declaracao.py`); `arbiter_tools/<dom>.py` foi DELETADO "
             "(sobra `base.py` com o builder de FACE genérico `build_face` + "
             "`_arb_deny`). Nasceu o BARRAMENTO DE FATOS (`motor/fatos.py`): cada op "
             "é publicada por-op em `turno.apply_op` e as consequências transversais "
             "viraram REAÇÕES (`react_actor_memory` genérico via contrato no "
             "`applied[\"memory\"]`, `react_witness`, `react_interrupt_travel`). "
             "MORRERAM `_TURN_STEPS`, `_finalize_turn` (FR-014 virou pós-condição), as "
             "tabelas `_VALENCE_BY_EVENT`/`_RELEVANCE_BY_EVENT` (a nota viaja com o "
             "ato), e as listas à mão do Árbitro (`_MUT_CH`/`_ACC_CH`/`_BEAT_CH`/"
             "`queue`/`resultado` derivam de `registro._HANDLERS`; `inworld_effects` "
             "de `@registro.inworld`). ATIVAÇÃO por mundo (`motor/ativacao.py`, "
             "`world.md`); doc GERADA (`server/tools_doc.py` → `docs/tools.generated.md`). "
             "Comportamento-preservante: golden byte-equivalente a v2.0.0 + as fases "
             "(41, incl. 40=US2 ativação, 41=Observer + caminho genérico de memória). "
             "Fronteira Árbitro×Motor intacta. Ver specs/038-tool-plugin-autodeclarada/",
    "2.0.0": "item 31 — refactor da arquitetura Árbitro×Motor. Sem quebra de "
             "CONTRATO do mundo (schemas, endpoints e a fachada `motor.X`/"
             "`import arbiter_tools` inalterados) — MAJOR pela virada ESTRUTURAL "
             "e pela mudança na fronteira de recusa que o modelo lê. Três frentes: "
             "(FACE) `build_tools` deixou de ser monolito — cada tool tem seu "
             "`manifest_X` co-localizado com o handler, via registro MANIFESTS. "
             "(§2, guarda×executor) a REGRA virou autoridade ÚNICA do executor: "
             "posse/slot/vestir/soltura (itens) e o VEREDITO+ROLAGEM (persuade/"
             "persuade_give/steal/attack/buy/trade) saíram do pré-voo da tool. "
             "Recusa CORRIGÍVEL leva os `validos` (o modelo se corrige sem pré-"
             "voo); o DADO virou segredo do modelo — recusa de rolagem volta "
             "NEUTRO ao Árbitro (só o veredito determinístico sobe), e as viradas "
             "de uma tentativa que FALHA seguem narrando pelo client (Princípio "
             "IX/X). (§3, DDD) o Motor e o `arbiter_tools` viraram PACOTES por "
             "domínio: `motor/<dom>/{primitivas,executores}.py` e `arbiter_tools/"
             "<dom>.py` + base — acrescentar tool = 1 arquivo por lado da "
             "fronteira. Kernel (io/rolagem/validador/registro/turno) fica módulo. "
             "39 fases verdes a cada lote; comportamento-preservante salvo o "
             "enquadramento de recusa acima.",
    "1.9.0": "spec 036 — Pertencimento por Memória: dono deixa de ser campo "
             "(nunca existiu `owner` em item.md) e vira RELAÇÃO lida de "
             "memória (`memoria.dono`) — sem memória contrária, quem "
             "possui fisicamente (`fisica.carried_item_ids`) vale como dono, de "
             "propósito, sem verdade global a sincronizar. Seis primitivos "
             "novos em `percepcao.py`/`fisica.py`/`memoria.py` (`carried_item_ids`, "
             "`is_blocked`, `reachable_entities`, `visible_entities`, `dono`, `offerable_entities`) "
             "substituem três varreduras ad-hoc que `_find_item_folder_in_"
             "scene`/`_visible_item_refs`/`_character_summary` faziam cada "
             "uma à sua moda. `give` ganha `emprestimo: true` — o único "
             "caminho MECÂNICO de emprestar (posse muda, dono não); "
             "`comercio.py` passa a oferecer o que `offerable_entities` alcança, "
             "não só a pasta do vendedor (mercador vendendo da própria "
             "banca). Contestação no INSTANTE em que alguém pega um item: "
             "todo presente com memória contrária sobre aquele item específico "
             "registra furto nele mesmo, mesmo fora da tool `steal` — extensão "
             "do leque de testemunha (spec 024/028) por conhecimento PRÉVIO, "
             "não percepção do ato; o Motor nunca planta intenção de denunciar "
             "(`[[server-never-owns-character-agency]]`). Reconciliação: "
             "`prometer` (spec 027) perde de vez a capacidade de mover item "
             "— vira puramente verbal/social, e compõe com `give+emprestimo` "
             "em chamadas separadas, nunca sobrepondo responsabilidade. "
             "`steal`/`item_transfers` alcançam mais longe de propósito "
             "(`reachable_entities` atravessa conteúdo aberto de terceiro na cena) "
             "— mudança de comportamento deliberada, não efeito colateral. "
             "Ver specs/036-pertencimento-por-memoria/",
    "1.8.0": "spec 034 — Presença no mundo: deslocamento (partida/chegada) "
             "passa a ser TESTEMUNHÁVEL, mesmo piso de saliência de golpe/"
             "furto/etc — código PRÓPRIO de `deslocamento.py` "
             "(`_enter_route_locked`/`_resolve_arrivals`), nunca uma entrada "
             "no dispatcher transversal `_witness_facts`/`_record_witness` "
             "(revisão do mantenedor: tool atômica vale em nível 0 e 1 "
             "igualmente — a capacidade de UMA família não deve vazar pro "
             "mecanismo genérico de fim-de-turno). `ask_about` generaliza "
             "`sobre` para LUGAR (item 20 do backlog, a peça que faltava ao "
             "rastreador, item 14-γ) e, junto com `ask_directions`, passa a "
             "resolver PERGUNTA + REGISTRO numa chamada só — `hear_about` e "
             "o ramo `fonte` de `learn_routes` saem do manifest (o mesmo "
             "padrão de duas chamadas já medido frágil, 1/6 turnos, na "
             "sondagem que motivou `prometer`/spec 027). Toda partida/"
             "chegada também grava uma marca FÍSICA (`rastro`, tipo novo em "
             "`validator.MVP_TYPES`) no lugar — ground-truth de quem passou "
             "e a direção, decaimento por RELÓGIO (≤48h, nunca por uso), "
             "dado PRÓPRIO (`memoria._roll_trace_d20`, seam de injeção "
             "separado de `_roll_d20` — a marca roda incondicionalmente em "
             "TODO deslocamento, inclusive nos extremos deterministas de "
             "`persuade`/`carry` que testes já proíbem dado). Nenhuma tool "
             "lê o rastro ainda — insumo para uma spec futura de investigar "
             "(item 14-γ). Ver specs/034-ask-about-place/",
    "1.7.0": "spec 032 — Cura e Socorro: tool nova `curar` reergue um "
             "`incapacitado` (nunca `morto`) — ação arbitrada de TRÊS "
             "bandas por margem de rolagem (baixa/média/alta, mesmo molde "
             "de `roll_steal_check`), `d20 + mod(WIS)` vs a régua "
             "narrativa de favorabilidade da cena. Sucesso remove a "
             "condição e recupera fração de HP (nunca ao máximo, "
             "escalada pela proficiência do socorrista no domínio NOVO "
             "`cura` — 1º consumidor real de `proficiencies_for`, spec "
             "029). Custo: uma porcentagem das memórias mais vívidas do "
             "curado vira `esquecida` — estado NOVO, mais definitivo que "
             "`expired` (peso zero em vez de ¼, nunca revive por "
             "proximidade — `_is_alive`/`_weigh_memories`/"
             "`proficiencies_for`/`_renew_memory` foram ensinados a "
             "tratar os dois estados de forma diferente). Memória nova "
             "nos dois lados + leque de testemunha (spec 024); NENHUMA "
             "intenção de dívida é criada pelo servidor "
             "(`[[server-never-owns-character-agency]]`) — o gancho é só "
             "a memória, e quem decide declarar dívida é a própria Mente "
             "do curado (`deriveWhisper`, spec 026). Toda tentativa "
             "(mesmo a que falha) cobra fadiga; a falha nunca é "
             "silenciosa. Atomicidade garantida por desenho: o executor "
             "valida alvo/condição/descanso com os PRÓPRIOS meios, "
             "provado chamando-o direto, sem `arbiter.py` nem "
             "`turno.apply_op`. Ver specs/032-cura-e-socorro/",
    "1.6.0": "spec 031 — Duração real de dormir/descansar: `dormir` vira "
             "alternador — a 1ª chamada INICIA (grava `status."
             "descansando_desde`, fadiga intacta); a seguinte ACORDA e "
             "recupera fadiga PROPORCIONAL ao tempo real decorrido (teto de "
             "recuperação plena: 8h reais). Enquanto descansando, qualquer "
             "outra tool do próprio ator é recusada — não por um guard "
             "central (duas versões assim foram descartadas em planejamento "
             "por quebrarem a auto-suficiência da tool, spec 025), mas por "
             "CADA um dos 10 executores mutadores validando com os próprios "
             "meios (`fisica.is_resting`, mesmo molde de "
             "`spend_fatigue`). Intensificar compromisso pendente (Frente D, "
             "spec 030) migrou pro acordar, só se ≥50% da fadiga foi "
             "recuperada (\"sono de qualidade\"). Confirmado ao vivo contra "
             "OpenRouter/OpenCode Zen: recuperação proporcional bateu exata "
             "(1h de 8h = 1/8 da fadiga), o manifest restringiu a só "
             "`dormir` durante o sono, e uma narração sem lastro (item "
             "nunca movido no disco) foi corretamente rejeitada em vez de "
             "aceita. Ver specs/031-sleep-real-duration/",
    "1.5.0": "specs 029/030 — Domínio da Memória + Fadiga como recurso. 029: "
             "`domain` fechado (5 domínios de fase 1 + \"nenhuma\"), carimbado "
             "por construção via `_DOMAIN_BY_EVENT` em `_write_memory` (zero "
             "LLM extra) e obrigatório em `create_memory`; `proficiencies_for` "
             "deriva nível por domínio, exposto via `/api/proficiencies`. 030: "
             "`fisica.spend_fatigue` — capacidade nível 0 chamada de DENTRO de "
             "cada executor (não um hook central: a 1ª versão do plano violava "
             "a tool auto-contida da spec 025, corrigida ainda em planejamento) "
             "— custo sempre de quem fisicamente age, nunca de quem persuade; "
             "três rolagens existentes (aprender, testemunha, resistência à "
             "persuasão) passam a ler fadiga como modificador; `_renew_memory` "
             "generaliza a renovação que só rota tinha; `dormir` intensifica "
             "compromisso pendente (`prometer`), um degrau por noite, teto "
             "`giant`. Bump recuperado nesta entrada — o commit original "
             "(76fa26f) shippou as duas specs sem versionar.",
    "1.4.0": "spec 028 — Acusar: primeira tool que toma uma memória como "
             "OBJETO (item 20 do backlog). Determinística (sem régua/rolagem "
             "— a reação de quem é acusado fica pra ações separadas e já "
             "existentes). Numa chamada só: memória em quem acusa, memória "
             "em quem é acusado, e leque de testemunha (spec 024, entrada "
             "nova em `_witness_facts`) pros demais presentes, zero LLM por "
             "testemunha. Grounding via `remembered_about` (já existia, "
             "spec 015) exposto como enum — uma acusação sem memória real "
             "por trás é estruturalmente impossível de expressar. Junto: "
             "`evento` (item 19 do backlog), campo aberto novo em TODA "
             "memória — o rótulo que já calibrava intensidade/valência na "
             "escrita passou a ser também persistido, com retrofit "
             "disciplinado em todos os call sites existentes, não só nos "
             "novos. Confirmado com sondagem ao vivo: 3/3 (100%) contra 1/3 "
             "medido sem a tool. Ver specs/028-witness-accusation/",
    "1.3.0": "spec 027 — Compromisso Lembrado: tool nova `prometer` (empréstimo "
             "com item, ou juramento puramente verbal sem item) que, numa chamada "
             "só, registra memória fatual nos dois lados (spec 013) e cria intenção "
             "ATIVA só em quem promete (spec 026, FR-008 — nunca na conta do "
             "alvo). Nenhuma entidade nova, nenhum campo de schema novo: o "
             "'compromisso' é a orquestração de duas peças que já existiam. "
             "`give`/`trade` ganham `intention_id` opcional — fecham a PRÓPRIA "
             "intenção de quem cumpre na mesma chamada, sem exigir nada de quem "
             "nunca rastreou nada; inválido/alheio nunca desfaz a transferência "
             "(as duas coisas não são atômicas entre si de propósito). Motivado "
             "por sondagem empírica: sem tool dedicada, o Árbitro só encadeava "
             "give+set_intention corretamente em ~1 de 6 turnos (esquecia o "
             "segundo passo). Achado e corrigido junto: `resolve_with_tools` "
             "nunca expunha `intentions_applied` no outcome desde a 026 (a "
             "escrita sempre funcionou; só a observabilidade do turno faltava). "
             "Ver specs/027-promise-debt-orchestration/",
    "1.2.0": "spec 026 — Intenções Persistentes: personagem guarda o que "
             "PRETENDE (não o que viveu) em entidade própria (intentions/<id>.md, "
             "handler auto-contido registro.handler('intentions'), spec 025); tool "
             "set_intention (só o próprio ator, v1); get_context ganha 'intentions'. "
             "Do lado do client, a Mente ganha deriveWhisper(context): decide SE "
             "há algo a fazer sem sussurro e devolve TEXTO livre, que reentra no "
             "MESMO interpret() de sempre — nenhum intent estruturado paralelo. "
             "Gatilho autônomo em dois pontos (chegada de viagem já resolvida "
             "preguiçosamente, spec 012; poll ocioso no client) convergindo na "
             "mesma rotina; trava desde o INÍCIO da avaliação, não só da ação "
             "(FR-010). Origem do turno (manual/autônoma) chega ao devlog só para "
             "observabilidade — nunca ao Árbitro (FR-015). Sem processo novo no "
             "servidor (Princípio VII): a autonomia mora inteira no client.",
    "1.1.0": "spec 024 — memória de TESTEMUNHA: a cena tem plateia. Um ato "
             "(furto/golpe/compra/doação) pinga memória factual de primeira mão nos "
             "presentes que PERCEBEM, determinístico no Motor (d20+WIS vs. exposição "
             "do furto ou ruído público), zero LLM por testemunha; intensidade "
             "modulada por afeto (piso de saliência), valência− leve ABAIXO do portão "
             "de trauma; o relato é assíncrono, do lado da testemunha. Sem tool nova, "
             "sem campo. US3 (deslocamento) deferido. Ver specs/024-witness-memory/",
    "1.0.0": "spec 020 — turno de FASE ÚNICA: cada tool aplica-e-registra "
             "atomicamente na ordem em que o Árbitro a chama; a ordem das chamadas "
             "é a sequência do mundo; portões duros conferem o estado atual; "
             "runtime sem tool-calling deixa de ser suportado (quebra → MAJOR)",
    "0.19.0": "spec 019 — corpo por personagem: a capacidade de slot mora na ficha "
              "(campo body), corpo humano padrão na ausência; vocabulário de slot "
              "aberto (validator.SLOTS rebaixada a default); recusa corpo_sem_slot; "
              "slot de PEGA por corpo (body {capacidade, pega}) — a mão do humano, "
              "a boca do cão: onde os itens pegos vão, não mais fixo em 'mao'",
    "0.18.0": "spec 018 — reconhecer: a observação (olho + tool recognize) leva em "
              "conta a vivência; recognition_of compõe prosa + familiaridade/afeto "
              "(rótulo) + memórias vivas; A Mente interpreta, o Árbitro só dispara",
    "0.17.0": "spec 017 — boato e reputação: contar o que se lembra (ask_about/"
              "hear_about); memória de reconto com grau (1º/2º/3º), peso decaído; "
              "'ouvido_de' é o 3º nível de sigilo (secreto até do Árbitro)",
    "0.16.0": "spec 016 — memória ligada a tudo (pessoa/item/lugar) com apego "
              "(familiarity_with) e afeto (sentiment_toward, valência dirigida); "
              "apego e afeto do parceiro no trade_dc, afeto por lugar no persuade, "
              "saldo pré-computado na disposição",
    "0.15.0": "spec 015 — perguntar o caminho a outro personagem (ask_directions); "
              "learn_routes ganha fonte/disposicao/atitude e o portão de disposição",
    "0.14.0": "spec 014 — prosa alcança o Árbitro (examine) e aprender caminhos "
              "pela leitura (learn_routes); item.teaches removido do schema",
    "0.13.0": "spec 013 — memória com classes; o mundo passa a registrar sozinho",
    "0.12.0": "spec 012 — viagem longa por caminho conhecido; location.size",
    "0.11.0": "spec 011 — troca e compra entre personagens",
}
