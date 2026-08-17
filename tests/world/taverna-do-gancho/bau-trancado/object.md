---
type: object
id: bau-trancado
name: Baú de ferro trancado
state:
  trancado: true
interactions:
  - action: inspect
  - action: arrombar
    requires: { skill: arrombamento, min_level: 1 }
    check: { attribute: DEX, dc: 14 }
    hint: "a fechadura é antiga, mas resistente"
origin: editorial
---

Um baú de ferro enferrujado, encostado na parede perto do balcão. A fechadura parece
antiga, mas segue firme.
