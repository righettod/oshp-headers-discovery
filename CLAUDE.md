# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

AI agent for the OWASP Secure Headers Project (OSHP) that tries to discover HTTP response security headers that OSHP's list is missing. It cross-references MDN and IANA header data sources, classifies each header (direction + security relevance) using NVIDIA-hosted LLMs via LangChain/LangGraph, and diffs the result against OSHP's known header list.

Single-file project: all logic lives in `main.py`, built as a `langgraph` `StateGraph` (a linear pipeline with one feedback loop, see the diagram in README.md / `diagram.png`). Each run writes three generated artifacts: `state.json` (pipeline state, resumed on the next run), `diagram.png` (graph diagram), and `dashboard.md` (human-facing report of headers OSHP's list appears to be missing).

## Commands

This project uses `uv` for dependency management (Python 3.13, see `.python-version`).

```bash
uv sync                # install dependencies from pyproject.toml / uv.lock
uv run main.py          # run the agent pipeline
bash update-mdn-ref-headers-folder.sh   # fetch MDN header docs into mdn/ (required before running main.py)
bash ci.sh              # full pipeline: fetch MDN data, uv sync, run main.py, clean up mdn/
```

There is no formal test suite (`test.py` is a standalone throwaway script for exploring the IANA XML feed, not run via a test runner, and is git-ignored).

Requires the environment variable `NVIDIA_BUILD_API_KEY` to be set (an NVIDIA Build / NIM API key) — `main.py` reads it at import time and will fail immediately if unset.

Linting/formatting is configured in `.vscode/settings.json` to use `ruff` (format on save, `fixAll` + `organizeImports`) for Python, and `markdownlint` for Markdown. There is no separate `ruff.toml`/`[tool.ruff]` block in `pyproject.toml`, so ruff defaults apply.

## Architecture

`main.py` builds and runs a `langgraph` pipeline (`assemble_agent`) over a shared `PipelineState` dict (`headers_info_collection`, `last_update`, `oshp_headers_missed`, `loop_interation_count`). Each header is tracked as a `HeaderInfo` dataclass with direction (`REQUEST`/`RESPONSE`/`UNKNOWN`), a security flag, and classification bookkeeping (`is_already_classified` short-circuits re-processing already-resolved headers on subsequent runs).

Pipeline nodes, in order:

1. **`gather_http_header_names`** — pulls header names + spec/RFC references from two sources: MDN's `browser-compat-data` (`data.json` + per-header spec JSON) and IANA's `http-fields.xml` registry. Fetches the actual RFC/spec text for each header. Headers in `HTTP_RESPONSE_HEADERS_EXPLICLITY_IGNORED` (deprecated ones like `Public-Key-Pins`) are pre-classified and skipped from further processing.
2. **`identify_http_header_directions_without_model`** — cheap heuristic pass: looks for direction markers in the local `mdn/` clone (glossary link patterns) or in the fetched RFC/spec text (`"<header> response header"` / `"<header> request header"` substrings), before falling back to an LLM. Requires `mdn/content-main/...` to exist (populated by `update-mdn-ref-headers-folder.sh`), else raises.
3. **`identify_http_header_directions_with_model`** — for headers still `UNKNOWN`, asks `meta/llama-3.1-8b-instruct` (structured output via `with_structured_output`) to classify direction from a windowed excerpt of the RFC, then retries with as much of the full RFC as fits in the context window if still unresolved.
4. **`determine_classification_state_for_non_response_header`** — marks `REQUEST` headers as fully classified (out of scope) and drops their RFC content to shrink the saved state; marks `UNKNOWN` headers as not-yet-classified so they get retried next run.
5. **`identify_http_header_security_relation_with_model`** — for `RESPONSE` headers, asks `nvidia/llama-3.3-nemotron-super-49b-v1` (temperature `0.01`) whether the header is security-related, per a fairly detailed rubric in the system prompt (mitigates a specific attack class, enforces transport/isolation/permission policy, protects auth artifacts, or is explicitly framed as security in a "Security Considerations" section).
6. **`validate_classification_state`** — a second LLM call, deliberately using a **different model family** (`mistralai/mistral-medium-3.5-128b`, temperature `0.01`) so the "independent reviewer" isn't just the classifier's own weights re-rolled, acts as an independent reviewer of step 5's verdict; disagreement feeds back as `is_security_classification_validation_explanation` into another pass of step 5. Both classifier and validator run at low temperature specifically to keep verdicts deterministic and avoid decoding-noise-driven disagreement between rounds.
7. **Conditional loop** (`classification_is_over`) — steps 5→6 repeat until all `RESPONSE`+security headers are validated, or `MAX_LOOP_ITERATION_COUNT` (2) is reached. When the iteration budget is exhausted, `validate_classification_state` force-resolves any header still in disagreement by flipping `is_security` to match the validator's implied verdict, marking it `is_already_classified = True`, and prefixing the stored explanation with `"[Forced resolution]"` — this guarantees the loop terminates instead of re-litigating the same disputed headers on every future run.
8. **`identify_headers_missed_by_oshp`** — fetches OSHP's own `headers_add.json` and diffs it against the locally classified security response headers to produce `oshp_headers_missed`.
9. **`create_dashboard`** — renders `dashboard.md` (`DASHBOARD_FILENAME`), a markdown table (HTML built inline, then converted via `markdownify`) listing headers that are both classified as security-related and present in `oshp_headers_missed` — the human-facing view of what this run found. Columns: header name, direction, classification status, classifier/validator explanations, and RFC/spec links.

State is persisted to/from `state.json` (`STATE_FILENAME`) via `DataclassEncoder` (a `json.JSONEncoder` that serializes dataclasses), so re-running `main.py` resumes from prior classification results rather than starting from scratch — `is_already_classified` is the key gate for this incremental behavior. `state.json` is a large generated artifact; treat it as pipeline output, not something to hand-edit.

LLM calls go through `handle_structured_model_call`, which retries up to `LLM_API_MAX_TRY_CALL` times and sleeps `LLM_API_RATE_COOLDOWN_DELAY_IN_SECONDS` on HTTP 429/500 before re-raising other errors — this is the place rate-limit/robustness behavior for NVIDIA NIM calls lives.

`NodeLoggerCallback` is a LangChain callback handler that prints node enter/exit timestamps during `agent.invoke(...)`, keyed off the graph's actual node names.

At the end of a run, `main.py` also regenerates `diagram.png` from the compiled graph (`agent.get_graph(xray=True).draw_mermaid_png()`) — this is the flow diagram embedded in README.md.

## Data flow dependencies

- `mdn/` (git-ignored) must exist before running `main.py` directly — it's produced by `update-mdn-ref-headers-folder.sh`, which downloads and unzips only the `web/http/reference/headers` subtree of the `mdn/content` repo. `ci.sh` handles this automatically and cleans up `mdn/` afterward.
- Network access is required to MDN (`unpkg.com`, raw GitHub), IANA, RFC editor/IETF, OWASP's OSHP repo, and the NVIDIA Build API — there is no offline/mocked mode.
