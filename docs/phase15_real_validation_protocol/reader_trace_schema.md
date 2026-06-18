# Reader Trace Schema

Last checked: 2026-06-18

## Purpose

This document defines the future evidence record shape for real human traces. It is documentation only and does not add a runtime schema.

## Required Record Fields

```json
{
  "schema_version": "phase15_reader_trace_v1",
  "study_id": "string",
  "reader_id": "anonymous-string",
  "artifact_label": "neutral-string",
  "artifact_registry_id": "string",
  "artifact_source_blinded": true,
  "consent_confirmed": true,
  "fixture_only": false,
  "not_real_validation": false,
  "first_read": {
    "summary": "string",
    "attention_anchor": "string",
    "unresolved_or_hidden": "string",
    "confusion_score": 1,
    "overexplicitness_score": 1,
    "completion_seconds": 0
  },
  "reread": {
    "opening_changed": false,
    "opening_change_description": "string",
    "hidden_consequence": "string",
    "carried_back_to_opening": "string",
    "summary": "string",
    "attention_score": 1,
    "confusion_score": 1,
    "overexplicitness_score": 1,
    "completion_seconds": 0
  },
  "scoring": {
    "opening_transfiguration_score": 0,
    "paraphrase_loss_score": 0,
    "attention_confusion_notes": "string",
    "scorer_id": "anonymous-string"
  },
  "exclusion": {
    "excluded": false,
    "reason": null
  }
}
```

## Field Rules

`fixture_only` must be false for real validation traces. Imported fixtures must keep `fixture_only: true` and `not_real_validation: true` and cannot satisfy final gates.

`artifact_source_blinded` must be true for usable traces. Any trace collected after a source-label breach must be excluded.

Scoring fields may be filled by an independent scorer after reader submission. Scorers must remain blind to artifact source until scores are locked.
