# Strongest-Rival Protocol

Last checked: 2026-06-18

## Definition

The strongest rival is the best available non-Abi artifact produced under comparable source, length, and time constraints. It may be human-written, model-written, or hybrid, but it must not use Abi internals, Abi packet outputs, hidden Abi annotations, or Abi scoring feedback.

## Selection Rules

Before reader data is collected, an independent selector should choose the strongest rival from a documented candidate pool. The selector must not know which future reader label will correspond to Abi.

The candidate pool and selection rationale must be stored. Rejected rivals should remain visible in the audit trail.

## Constraints

The strongest rival must:

- Use the same source material available to Abi.
- Target the same reader effect category.
- Stay within the same length band.
- Avoid direct access to Abi-generated candidate text.
- Avoid post-hoc editing after seeing Abi output, unless the same editing opportunity is available to all arms and preregistered.

## Passing Evidence

Future evidence may support `strongest_rival_comparison_passed` only if the Abi candidate beats or matches the strongest rival on the preregistered primary endpoint and has no worse blocking defect on confusion, overexplicitness, or hostile-audit criteria.

Protocol definition alone does not pass the gate.
