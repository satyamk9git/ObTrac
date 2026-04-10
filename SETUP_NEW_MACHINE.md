# Setup ObTrac on a New Machine

Step-by-step guide to set up ObTrac (SDK + Backend + Frontend) on a fresh machine.

---

## Prerequisites

Install these first:

| Tool | Version | Download |
|---|---|---|
| **Python** | 3.10+ | https://www.python.org/downloads/ |
| **Node.js** | 18+ | https://nodejs.org/ |
| **Git** | latest | https://git-scm.com/ |

Verify:

```bash
python --version
node --version
npm --version
git --version
```

---

## Step 1: Clone the repository

```bash
git clone https://github.com/<your-username>/ObTrac.git
cd ObTrac
```

---

## Step 2: Install the ObTrac SDK

The SDK is the Python package you'll import in your code.

```bash
pip install -e .
```

This installs `obtrac_sdk` from `pyproject.toml` so any Python script can do:

```python
from obtrac_sdk import obtrac_config, trace, observe
```

Verify:

```bash
python -c "from obtrac_sdk import obtrac_config, trace, observe; print('SDK installed')"
```

---

## Step 3: Install backend dependencies

The backend stores your traces and runs RAGAS evaluation.

```bash
cd backend
pip install -r requirements.txt
cd ..
```

This installs FastAPI, SQLAlchemy, RAGAS, LiteLLM, and dependencies.

---

## Step 4: Install frontend dependencies

The frontend is the dashboard.

```bash
cd frontend
npm install
cd ..
```

---

## Step 5: Configure your LLM credentials

Create a `.env` file in the project root:

```bash
# Windows
copy NUL .env

# Linux/Mac
touch .env
```

Edit `.env` and add your Azure OpenAI credentials:

```env
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_MODEL_NAME=gpt-4o
AZURE_OPENAI_DEPLOYMENT=gpt-4o
AZURE_OPENAI_API_KEY=your-api-key-here
AZURE_OPENAI_API_VERSION=2024-12-01-preview
```

> **Important:** Never commit `.env` to git. It's in `.gitignore` for safety.

For other providers (OpenAI, Anthropic, Gemini), see [README.md](README.md).

---

## Step 6: Start the services (3 terminals)

Open **3 separate terminal windows** in the project root.

### Terminal 1 — Backend (FastAPI on port 8100)

```bash
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8100
```

Wait until you see:
```
INFO:     Application startup complete.
```

### Terminal 2 — Frontend (Next.js on port 3100)

For best performance (production build):

```bash
cd frontend
npm run build
npm start -- --port 3100
```

For development with hot-reload (slower):

```bash
cd frontend
npx next dev --port 3100
```

Wait for `Ready in X.Xs`.

### Terminal 3 — Test App (optional)

Pick any test app to verify everything works:

```bash
streamlit run test_app/app.py --server.port 8501
```

---

## Step 7: Open the dashboard

Open these URLs in your browser:

| URL | What |
|---|---|
| http://localhost:3100 | **Dashboard** |
| http://localhost:8100/docs | API docs (Swagger) |
| http://localhost:8501 | Test app (Streamlit) |

---

## Step 8: Configure auto-evaluation (one-time)

1. Go to http://localhost:3100/llm-config
2. Click **+ Add LLM**
3. Select Provider: **Azure OpenAI**
4. Fill in your credentials (same as `.env`)
5. Set Role: **judge**
6. Check **"Use for Auto-Evaluation"**
7. Click **Save**

Now any pipeline with `auto_eval=True` will be automatically evaluated.

---

## Step 9: Test your setup

Create a file `test.py` in the project root:

```python
from obtrac_sdk import obtrac_config, trace, observe

obtrac_config(
    project="setup-test",
    backend_url="http://localhost:8100",
    user="test-user",
)

@trace(name="hello", span_type="custom")
def hello(name):
    return f"Hello, {name}!"

@observe(name="test_pipeline")
def pipeline(name):
    return hello(name)

if __name__ == "__main__":
    result = pipeline("World")
    print(result)
    print("Check http://localhost:3100 for your trace")
```

Run it:

```bash
python test.py
```

Open http://localhost:3100 → click `setup-test` project → see your trace.

---

## Project Structure

```
ObTrac/
├── obtrac_sdk/                  # Python SDK (pip installable)
│   ├── __init__.py
│   ├── decorators.py            # @trace, @observe
│   ├── context.py
│   ├── config.py
│   ├── models.py
│   ├── llm_gateway.py
│   ├── mlflow_logger.py
│   └── evaluator.py
│
├── backend/                     # FastAPI server
│   ├── app/
│   │   ├── main.py
│   │   ├── api/                 # REST endpoints
│   │   ├── db/                  # SQLAlchemy models
│   │   ├── core/                # Settings
│   │   └── services/
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/                    # Next.js dashboard
│   ├── src/
│   │   ├── app/                 # Pages
│   │   └── components/
│   ├── package.json
│   └── Dockerfile
│
├── test_app/                    # Streamlit test apps
│   ├── app.py                   # Simple RAG
│   ├── agent_app.py             # Multi-agent
│   ├── langchain_app.py         # LangChain example
│   ├── langgraph_app.py         # LangGraph example
│   └── google_adk_app.py        # Google ADK example
│
├── pyproject.toml               # SDK pip install metadata
├── README.md                    # Main docs
├── EXAMPLES.md                  # Code examples & edge cases
├── SETUP_NEW_MACHINE.md         # This file
├── .env.example                 # Template for credentials
└── .gitignore
```

---

## Files NOT in Git (sensitive or large)

These are excluded by `.gitignore`:

- `.env` — Your API keys (NEVER commit this)
- `backend/data/` — SQLite database with traces
- `node_modules/` — Frontend dependencies (re-installed by `npm install`)
- `__pycache__/` — Python bytecode
- `*.egg-info/` — Python package build artifacts
- `.next/` — Next.js build output
- `dist/`, `build/` — Build artifacts

---

## Common Issues

### "ModuleNotFoundError: No module named 'obtrac_sdk'"

Run `pip install -e .` from the project root.

### "Port 8100 already in use"

Another process is using the port. Either:
- Kill it: `taskkill //PID <pid> //F` (Windows) or `kill -9 <pid>` (Linux/Mac)
- Or use a different port: `--port 8101` and update `backend_url` accordingly

### "Cannot connect to backend"

Make sure the backend (Terminal 1) is running before starting the frontend or any test app.

### Frontend pages are slow

Use production build instead of dev:
```bash
cd frontend
npm run build
npm start -- --port 3100
```

### Auto-eval not working

1. Check **LLM Config** has at least one LLM with **Use for Auto-Evaluation** enabled
2. Make sure your code has `auto_eval=True` in `obtrac_config()`
3. The `@observe` decorator must have `metrics=[...]`

For more issues, see [README.md#troubleshooting](README.md#troubleshooting).

---

## Migrating Existing Data

If you have existing traces from another machine:

```bash
# On old machine — copy the database
cp backend/data/obtrac.db backup.db

# Transfer backup.db to new machine, then
cp backup.db ObTrac/backend/data/obtrac.db
```

---

## Production Deployment

For running ObTrac in production:

1. **Use PostgreSQL** instead of SQLite
   - Edit `backend/app/db/database.py`:
     ```python
     DATABASE_URL = "postgresql://user:pass@host:5432/obtrac"
     ```

2. **Run backend with Gunicorn**
   ```bash
   pip install gunicorn
   gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8100
   ```

3. **Build frontend for production**
   ```bash
   cd frontend
   npm run build
   ```

4. **Use Nginx as reverse proxy** for both backend (port 8100) and frontend (port 3100)

5. **Use Docker Compose** (provided in `docker-compose.yml`):
   ```bash
   docker-compose up --build
   ```

---

## Next Steps

- Read [README.md](README.md) for full feature documentation
- Read [EXAMPLES.md](EXAMPLES.md) for code examples and edge cases
- Try the test apps in `test_app/` to see ObTrac in action
- Build your own pipeline using the SDK!

---

## Need Help?

- Check [README.md](README.md) Troubleshooting section
- Open an issue on GitHub
- Read the source code — it's well-commented
