# EX-5 Level 2 Methodology Note

Level 2 "Corrected Precision" = 62.3% (259/416)

Denominator: 416 unique expected actions across AUTO-GENERATED scenarios only
(not all 602 expected actions across manual+auto).

Numerator: 259 of those 416 actions were performed by at least one model
in at least one episode of that scenario.

This measures: "Of the constraints the derivation engine adds,
what fraction are actions that models can actually produce?"

It is NOT the same as global action overlap (227/602 = 37.7%),
which includes manual scenarios where expected actions were
hand-written to match known model capabilities.

The correct interpretation: "62.3% of engine-derived expected actions
are within the action vocabulary of current LLM agents."
