# FarmXpert

Multi-agent farm advisory: a farmer asks a question, the right agents (weather, soil,
irrigation, crop choice, task planning, market) run, and one plain answer comes back.

```
Frontend/     Next.js app                        :3000
Backend/      Node.js + Express API, owns the database and every write    :4000
AI_Backend/   FastAPI, the agents and the orchestrator (stateless)        :8000
```

```
browser ──► Backend (Node) ──► PostgreSQL + PostGIS + pgvector
               │   ▲
               ▼   │ farm context in, answer out
           AI_Backend (FastAPI) ──► weather / LLM / data.gov.in
```

- **Node owns the data.** Farms, fields, soil readings, conversations, agent outputs,
  plans and mandi prices: all tables, all migrations, all writes.
- **The AI backend is stateless.** Node sends it what it needs (location, latest soil
  reading, crop, the last turns of the conversation); it never looks a farm up. Its only
  database use is the knowledge index (`knowledge_chunks`), which it reads and rebuilds.
- **Answer first, record after.** A chat turn is persisted after the farmer has the
  answer, in one idempotent transaction; a database fault costs history, never an answer.

## Run locally

Needs Node 22.9+, Python 3.11+, PostgreSQL 14+ with the PostGIS and pgvector extensions.

```bash
cd Backend && npm install && cp .env.example .env
```

```bash
npm run migrate
```

```bash
npm run dev
```

```bash
cd AI_Backend && pip install -r requirements.txt && cp .env.example .env
```

```bash
cd .. && uvicorn AI_Backend.main:app --port 8000
```

```bash
cd Frontend && npm install && npm run dev
```

Set the same `INTERNAL_API_KEY` in `Backend/.env` and `AI_Backend/.env` so only the Node
backend can call the AI service.

## Tests

```bash
cd Backend && npm test
```

```bash
python -m pytest AI_Backend/tests -q
```

See [Backend/README.md](Backend/README.md) for the API and the database design.
