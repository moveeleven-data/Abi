# Context Specs

The files in this directory are frozen phase specs, plans, and historical architecture notes.

They are not all current runtime instructions. Earlier phase files often prohibit work that was only out of scope for that specific phase, while later frozen phases deliberately add guarded scaffolds, fake-client paths, or protocol documents.

For current operator usage, read the root `README.md` first. For current handoff and validation status, read:

- `docs/phase14_operator_handoff/operator_handoff.md`
- `docs/phase14_operator_handoff/known_blockers.md`
- `docs/phase15_real_validation_protocol/validation_protocol.md`
- `docs/INDEX.md`

When implementing a requested phase, use the active task prompt plus the matching file under `context/plans/`. Do not delete or rewrite frozen context specs as part of normal repo hygiene.
