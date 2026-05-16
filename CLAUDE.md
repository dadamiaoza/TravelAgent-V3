# TravelAgent-V3: AI 旅行规划助手

## Project

- Python FastAPI backend at `src/backend/`
- React Vite frontend at `src/frontend/`
- PostgreSQL 16 via Docker at `src/docker-compose.yml`
- LangChain agents for AI orchestration at `src/backend/app/agents/`
- MiniMax M2.7 as the LLM provider (OpenAI-compatible API)
- Spec documents at `.ad/specs/ai-travel-assistant/`

## Agent skills

### Issue tracker

Issues live as local markdown files under `.scratch/<feature>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Uses the five default labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout: one `CONTEXT.md` + one `docs/adr/` at repo root. See `docs/agents/domain.md`.
