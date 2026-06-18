# Prompt and Worker Contracts

Phase 1 uses deterministic worker functions, not model prompts.

The contracts still matter because future model workers must preserve the same input/output boundaries.

## Abi Ear worker contracts

### Germ Analyzer

Input:

- germ text

Output:

- word_forces
- future_opened
- risks
- fertility_score

### Variant Generator

Input:

- germ text
- germ analysis

Output:

- ten variants
- short rationale for each
- predicted field shift

### Field Model Builder

Input:

- selected germ
- germ analysis

Output:

- objects
- local laws
- latent oppositions
- negative space
- scale ceiling
- forbidden imports
- possible returns

### Move Composer

Input:

- germ
- field model

Output:

- twenty moves
- parent material
- operation name
- new material
- predicted field delta
- pressure delta
- derivation distance
- return payoff
- risk

### Retrospective Inevitability Judge

Input:

- moves
- field model

Output:

- ranked move sequence
- score for surprise-before / necessity-after
- risks

### Development Composer

Input:

- germ
- field model
- ranked move sequence

Output:

- three short prose inventions
- one refined invention

### Reread Tracer

Input:

- refined invention
- germ
- field model

Output:

- first-read opening interpretation
- second-read opening interpretation
- changed opening words
- supporting lines or passages
- reread gain estimate
- unsupported claims

### Ablation Reporter

Input:

- refined invention
- germ
- selected moves
- reread trace

Output:

- tested removals/replacements
- predicted effect loss
- verdict per ablation

### Gate Evaluator

Input:

- full Abi Ear packet

Output:

- passed
- blocking defects
- gate scores
- summary verdict

## Role separation

Even with deterministic stubs, keep functions separated by role.

Do not create one monolithic function that fabricates the whole packet without preserving intermediate artifacts.
