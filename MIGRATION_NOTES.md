# mAI Gateway migration notes

## What changed

| File | Change |
|---|---|
| `utils/llm.py` | New. OpenAI → Responses API (OpenAI SDK), Gemini → Interactions API (Google GenAI SDK), Claude → Bedrock Converse over `requests`. All send `X-Posit-App-Id` (from `CONNECT_CONTENT_GUID`), `x-source-type: interactive`, `mai-endpoint` query parameter. No API keys. |
| `constants.py` | Model list and `MAI_*` environment variables. |
| `utils/rag.py` | Prompts ported from the Next.js app; calls `generate_answer`. |

Removed from the original app: `ANTHROPIC_API_KEY` / `CLAUDE_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_GENAI_API_KEY`, `MISTRAL_API_KEY`, Supabase keys, `ADMIN_TOKEN`, and the provider SDK calls in `src/lib/llm.ts`.

## Models

| Original | mAI model | Provider |
|---|---|---|
| Claude Sonnet 4.6 / Haiku 4.5 / Opus 4.8 | `claude-haiku-5-5` (only allowed Claude model) | Claude |
| GPT-5.5 / 5.4 Mini / 5.4 Nano | `gpt-6-luna`, `gpt-5.6-luna` | OpenAI |
| Gemini 2.5 Pro / 2.5 Flash | `gemini-3.8-flash`, `gemini-3.7-flash` | Gemini |
| Mistral | not available through mAI — removed | — |

## Posit Connect environment variables

| Variable | QA | Production |
|---|---|---|
| `MAI_BASE_URL` | `https://apiqa2.worldbank.org/posit-mai/conversationalai/` | `https://api.worldbank.org/posit-mai/conversationalai/` |
| `MAI_ENDPOINT_OPENAI` | `https://azapimqa.worldbank.org/maifactory/openai/responses` | `https://azapim.worldbank.org/maifactory/openai/responses` |
| `MAI_ENDPOINT_CLAUDE` | `https://azapimqa.worldbank.org/maifactory/bedrock/model/us.anthropic.claude-haiku-5-5/converse` | `https://azapim.worldbank.org/maifactory/bedrock/model/us.anthropic.claude-haiku-5-5/converse` |
| `MAI_ENDPOINT_GEMINI` | `https://azapimqa.worldbank.org/maifactory/gemini/interactions` | `https://azapim.worldbank.org/maifactory/gemini/interactions` |
| `MAI_MODEL` (optional) | default model id | default model id |

Names `MAI_ENDPOINT_OPENAI/CLAUDE/GEMINI` are this migration's choice (one gateway endpoint per provider). **Integrations: leave empty** — do not attach `mai Integration-QA` or `mai-posit`.

## Flagged items — not documented in the mAI Developer Guide, verify on QA

- System prompt fields (`instructions` for OpenAI, `system_instruction` for Gemini, `system` for Claude). On HTTP 400/422 the app retries once with the system prompt folded into the user message.
- Gemini request path: the Google GenAI SDK calls `<MAI_BASE_URL minus trailing />/v1/interactions`; confirm this path with the platform team if QA returns 404.
- `max_output_tokens` / `maxTokens` / `generation_config` sampling limits.
- Claude endpoint value `…/model/us.anthropic.claude-haiku-5-5/converse` (single `us.anthropic.` prefix): if QA returns 404/403, confirm the exact value.

Unmigrated: embeddings (no longer needed — Databricks AI Search embeds queries and documents), streaming (answers are returned when complete).

## Checks done

`py_compile` on all files; manual review against the rules (no keys/`Authorization` headers set by the app, App ID from `CONNECT_CONTENT_GUID`, URLs from env vars, allowed models only, `mai-endpoint` query parameter on every call); mock-gateway test of all five models including the system-field fallback. `scripts/check_mai_compliance.py` was not available in the skill folder, so the compliance review was manual. No live gateway call was made (gateway accepts Connect apps only).

## First deploy test (QA first)

1. Set the QA variables above and restart the content.
2. `?page=query` → ask one question per model (five total) with "All PIM Documents".
3. A 403 "Model not allowed" means the model id is not enabled; 404 → check `MAI_BASE_URL` (trailing `/`) and the Claude/Gemini paths above; 400 → check the system-field fallback in the app log.
4. Repeat with the Production values after QA passes.
