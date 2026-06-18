# Live Model Guardrail Report

Last checked: 2026-06-18

## Guardrails

Live OpenAI paths are guarded by two conditions:

- The operator must pass `--allow-live-model`.
- The environment must contain `OPENAI_API_KEY`.

The documented model configuration uses `ABI_OPENAI_MODEL` when set, with a code-defined default otherwise.

## Fake Paths

Fake-client paths require no API key and are used by tests and local verification. They exercise schema validation, model-call recording, validation-failure handling, and client-failure handling without network access.

## Isolation

The OpenAI adapter is isolated in `src/abi/openai_adapter.py`. Core controller, registry, gate, and deterministic scaffold modules do not need an API key.

## Test Safety

The test suite passes without API keys. Tests use fake or stub adapters for live-model behavior and assert that guarded commands refuse before a client call when opt-in or environment requirements are missing.

## Audit Conclusion

No real OpenAI call was made during this audit. Live model use remains explicit, opt-in, and guarded.
