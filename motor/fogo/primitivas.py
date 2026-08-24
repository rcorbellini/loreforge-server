"""O Motor / fogo — PRIMITIVAS (item 31 §3: DDD por domínio; spec 053).

Funções puras: a rolagem de ignição e a conversão da nota de duração em tempo real.
A resolução do prazo NÃO mora aqui — é `trabalho.resolver_vencidas`, genérica para
todo domínio de prazo. Sem turno/LLM. Ver executores.py.
"""
from __future__ import annotations

from .. import rolagem


def roll_kindle_check(actor_fm: dict, nota: int, nivel_fogo: float = 0.0,
                      rolls: list | None = None) -> tuple[bool, dict]:
    """Devolve (pegou, roll_info). Desfecho BINÁRIO, não em bandas.

    Divergência deliberada de `cook`, que precisa de três bandas porque a qualidade
    do prato varia: a chama pegou ou não pegou. Uma "fogueira média" não é um
    resultado diferente — é a mesma fogueira, e o que varia (porte, brasa, duração)
    já vem da prosa e da nota de DURAÇÃO, não da sorte.

    Extremos deterministas, mesmo molde de `roll_cook_check`/`roll_cura_check`:
    nota<=0 -> não pega, sem dado; nota>=10 -> pega, sem dado. Entre 1-9:
    `d20 + mod(DEX) + nivel_fogo` vs `persuade_dc(nota)` — MESMA curva que
    `cook`/`cura`/persuadir já usam (favorabilidade alta = DC baixa).

    DEX no lugar do INT de `cook`, e a escolha é do domínio: acender é mão, não
    cabeça. A proficiência soma DIRETO no total (como em `cook`, não como em `cura`)
    — a prática decide o próprio desfecho.

    Nota e DC nunca saem do `roll_info` (segredo do mundo, Princípio IX)."""
    nota = max(0, min(10, int(nota)))
    if nota <= 0:
        info = {"tipo": "fogo", "resultado": "falha", "virada": False,
                "critico": None, "rolagem": None}
        if rolls is not None:
            rolls.append(info)
        return False, info
    if nota >= 10:
        info = {"tipo": "fogo", "resultado": "sucesso", "virada": False,
                "critico": None, "rolagem": None}
        if rolls is not None:
            rolls.append(info)
        return True, info
    d20 = rolagem._roll_d20()
    mod = rolagem.attr_modifier((actor_fm.get("attributes") or {}).get("DEX", 10))
    dc = rolagem.persuade_dc(nota)
    total = d20 + mod + float(nivel_fogo)
    pegou = total >= dc
    info = {
        "tipo": "fogo", "resultado": "sucesso" if pegou else "falha",
        # virada: a cena dizia fácil e não pegou, ou dizia difícil e pegou
        "virada": (nota >= 6 and not pegou) or (nota <= 4 and pegou),
        "critico": (d20 == 20) or (d20 == 1) or None,
        "rolagem": {"d20": d20, "mod": mod, "nivel_fogo": round(float(nivel_fogo), 2),
                    "total": total, "dc": dc},
    }
    if rolls is not None:
        rolls.append(info)
    return pegou, info


def duracao_fogo_s(nota: int) -> int:
    """Converte a nota 0-10 de DURAÇÃO em tempo real de queima.

    Mesmo PAPEL que `cozinha.duracao_segundos`, uma década acima: 10 a 110 minutos,
    contra 1 a 11 do preparo. A razão é dura — a fonte precisa SOBREVIVER a um
    preparo. Com a escala de `cook`, uma fogueira de nota baixa morreria antes do
    ensopado ficar pronto, e como `cook` julga a fonte uma única vez, na abertura, o
    prato sairia mesmo assim: o mundo diria uma coisa e o mecanismo, outra.

    Piso de 10 min cobre quase todo preparo; teto de ~1h50 sustenta uma noite de
    acampamento sem virar fogo eterno. CALIBRÁVEL — o número saiu do raciocínio,
    não de medição no jogo (spec 053, research R4). Nunca julgado pelo Árbitro."""
    return 600 + 600 * max(0, min(10, int(nota)))
