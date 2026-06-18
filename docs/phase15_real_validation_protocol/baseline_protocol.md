# Baseline Protocol

Last checked: 2026-06-18

## Purpose

Baselines define what Abi must beat before any stronger claim can be considered. A weak or cherry-picked baseline is a hostile-audit failure.

## Baseline Set

Future validation must include:

- Direct-prompt baseline.
- Raw-model baseline.
- Strongest-rival baseline.

Each baseline must use the same source constraints, target length band, and output format as the Abi candidate unless a deviation is preregistered.

## Generation Rules

Baseline prompts must be frozen before outputs are generated. The operator must store prompt text, model/provider configuration where applicable, randomization seed if applicable, generation time, and model-call records.

No baseline may be edited after viewing reader results. Any selection among multiple baseline candidates must follow a preregistered rule and must be recorded.

## Comparison Ordering

Reader presentation order must be randomized or balanced. If a reader sees multiple artifacts, use a Latin-square or equivalent counterbalance so source class does not correlate with position.

Artifact labels must remain neutral. Do not reveal that one output is Abi, raw model, direct prompt, or strongest rival.

## Success Boundary

Beating a baseline in a pilot does not satisfy final gates. Baseline evidence can only support future gate review after a full preregistered validation run with usable traces and locked scoring.
