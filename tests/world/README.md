# Fixture de mundo (imutável, só para testes)

Mundo-semente fixo usado pelos `selftest*.py`. É **independente** do `world/` que você joga —
por isso jogar (mover personagens, criar memórias) não quebra os testes.

Não edite para "continuar uma partida"; edite só se um teste passar a exigir outro estado
inicial. Os testes que mutam copiam este fixture para um diretório temporário.
