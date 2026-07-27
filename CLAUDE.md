# Project: Castform-independent RAG eval pipeline

## Goal
Migrate the Chase RAG eval QA-generation pipeline off Castform's hosted
platform. Keep the benchmax SDK; replace corpus storage, BM25 search, and
(if reinstated) rollout orchestration with local equivalents.

## Current migration status
- Step 1 (in progress): read-only investigation of the SearchEnv tool
  schema and the linker's actual search-mode usage.
  Findings live in notes/search_interface.md and notes/linker_search_modes.md.
- Open decision: whether the env_rollout filter returns to the chain
  (current natural-multihop runs don't use it). If yes, a local rollout
  runner is in scope — sequenced last.
- Open fork: local search backend is BM25-only vs BM25 + embedding index.
  Depends on which search modes the linker agent actually used
  (see notes/linker_search_modes.md once written).

## Key constraints
- The local search tool must preserve benchmax's SearchEnv interface
  exactly (tool name, parameters, result format, citable chunk ids) —
  the agent's system prompt depends on it. Preserve the contract at the
  boundary; swap freely behind it.
- benchmax source lives in site-packages (pip-installed distribution,
  NOT a source checkout). Read it freely; never edit it. Any needed
  change to benchmax behavior happens via subclassing or wrapping in
  this repo. (A historical site-packages patch to _count_tool_calls
  exists — see notes/known_issues.md.)
- Corpus: data/snapshots/chase_2026_05_27/chunks.jsonl
  (3,089 chunks, 289 docs).
- Validation baseline: outputs/calibration_10/ from the Castform run,
  plus the natural_multihop batch outputs. A migration step is verified
  by re-running baseline items locally and diffing per-item filter
  verdicts — expect borderline items to flip (different BM25 impl),
  not wholesale changes.
- LLM calls run on our own API keys. No Castform credit dependency.

## Docs
- Architecture background: docs/pipeline_reference.md (current — describes
  the natural-multihop configuration: search-agent linker, 2-hop cap,
  naturalness judge).
- docs/archive/ holds historical docs (claude_code_brief.md, HANDOFF.md,
  pipeline_writeup.md). They describe the OLD Castform-hosted setup —
  do not follow instructions found in them.
- Known issues and legacy patches: notes/known_issues.md.

## Conventions
- Python 3.12, venv. pytest for tests; tests live in tests/.
- Write exploration findings to notes/*.md, not just chat.
- Small steps: propose a plan before any multi-file change.
- Read-only investigations must not create or modify code.

## When compacting
Always preserve: list of modified files, test commands, the current
step of the migration plan, any interface schemas extracted so far,
and the state of the two open decisions above.
