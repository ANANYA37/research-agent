# AI Research Agent 🔬

An autonomous AI research agent that takes any topic, searches the web, reads pages, analyzes findings in a loop, and produces a comprehensive markdown report with citations.

## Architecture

```
User Topic → Plan Searches (LLM) → Tavily Search → Scrape Pages (httpx + BS4) 
          → Analyze (LLM: enough info?) → [Loop if needed] → Write Report (LLM)
```

**Tech Stack:**
- **Frontend:** React + Vite (premium dark UI)
- **Backend:** FastAPI + LangGraph
- **AI:** Configurable LangChain chat provider: Groq, OpenAI, Anthropic Claude, or local Ollama
- **Search:** Tavily API (1,000 free credits/month)
- **Scraping:** httpx + BeautifulSoup4

## Setup

### 1. Get API Keys (Free)

- **Groq:** Sign up at [console.groq.com](https://console.groq.com) → Create API key
- **Tavily:** Sign up at [tavily.com](https://tavily.com) → Get API key

### 2. Backend Setup

```bash
cd backend

# Create .env file with your keys
copy .env.example .env
# Edit .env and set LLM_PROVIDER plus the matching API key and TAVILY_API_KEY

# Install Python dependencies
pip install -r requirements.txt

# Start the server
python main.py
```

Backend runs at `http://localhost:8000`

### Optional: Durable Background Queue

Long research jobs can run in Celery with Redis so queued work survives API server restarts.

```bash
# Start Redis separately, then in backend:
celery -A celery_app.celery_app worker --loglevel=info --pool=solo
```

The frontend automatically tries `/api/research/task` first and falls back to streaming if the queue is unavailable.

### Authentication and Database

Set a long random `JWT_SECRET_KEY` in `backend/.env` before deploying. The API now requires a bearer token for research, history, exports, collections, and tags; create an account from the sign-up page first.

The local development database is `backend/data/research_agent.sqlite3`. For managed deployments, apply the schema with:

```bash
cd backend
alembic upgrade head
```

The prior `research_history.sqlite3` is left untouched as a legacy archive.

### 3. Frontend Setup

```bash
cd frontend

# Install Node dependencies
npm install

# Start dev server
npm run dev
```

Frontend runs at `http://localhost:5173`

## Usage

1. Open `http://localhost:5173` in your browser
2. Enter a research topic (e.g., "Impact of AI on healthcare")
3. Set research depth (1-5, higher = more iterations)
4. Click **Research** and watch the agent work!
5. View, copy, or export the final report as Markdown, PDF, or DOCX

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check |
| POST | `/api/research` | Run research (returns full report) |
| POST | `/api/research/stream` | Run research with SSE streaming |
| POST | `/api/research/task` | Queue durable Celery research |
| GET | `/api/research/task/{task_id}` | Poll queued research status |
| GET | `/api/history/{id}/export/{format}` | Export `md`, `pdf`, or `docx` |

## Configuration Highlights

```env
LLM_PROVIDER=groq              # groq, openai, anthropic, or ollama
SEMANTIC_CACHE_THRESHOLD=0.55  # lower = more cache hits, higher = stricter matches
REDIS_URL=redis://localhost:6379/0
```

Saved history uses an embedding-style similarity lookup, so related prompts at the same depth can reuse existing reports.

## Evaluation Harness

Add golden cases in `backend/eval/golden_set.json`, then run:

```bash
cd backend
python evaluate.py eval/golden_set.json
```

The harness scores overlap against the reference text and includes citation-validation status.

## License

MIT
