# Fixture Evidence Safety Report

Last realigned: 2026-06-19

Fixture and fake-client outputs are engineering artifacts. They can exercise artifact registration, model-call recording, packet assembly, and fail-closed controller behavior. They do not satisfy autonomous creative-candidate gates by themselves.

## Active Rule

The `autonomous_creative_candidate` profile requires `no_fixture_only_core_evidence`. Do not mark that gate passed unless the corresponding internal artifacts are non-fixture and operator-reviewed.

## Legacy Rule

The legacy `final_artifact` profile still rejects fixture evidence. That profile is retained for external validation policy only and is not the active development path.

## Private Source Safety

Runtime and private material must remain in ignored locations:

- `runs/`
- `outputs/`
- `db/*.sqlite`
- `inputs/private/`

Tracked docs must not copy private source contents.
