# Setup ObTrac on a New Machine

The fastest way to get ObTrac running on a fresh machine.

---

## Prerequisites

| Tool | Version | Download |
|---|---|---|
| **Python** | 3.10+ | https://www.python.org/downloads/ |
| **Node.js** | 18+ | https://nodejs.org/ |
| **Git** | latest | https://git-scm.com/ |

Verify:
```bash
python --version
node --version
git --version
```

---

## Installation (3 commands)

### Step 1: Clone the repo

```bash
git clone https://github.com/satyamk9git/ObTrac.git
cd ObTrac
```

### Step 2: Install ObTrac (Python deps + CLI command)

```bash
pip install -e .
```

This installs:
- The `obtrac_sdk` Python package (use in your code)
- All backend dependencies (FastAPI, SQLAlchemy, RAGAS, LiteLLM, etc.)
- The `obtrac` CLI command (start, stop, status, install)

### Step 3: Install frontend + build

```bash
obtrac install
```

This runs `npm install` and `npm run build` for the dashboard.

> **One-time only.** Takes ~2 minutes.

---

## Configure your LLM credentials

Create a `.env` file in the project root:

```bash
# Windows
copy .env.example .env

# Linux/Mac
cp .env.example .env
```

Edit `.env` with your Azure OpenAI credentials:

```env
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_MODEL_NAME=gpt-4o
AZURE_OPENAI_DEPLOYMENT=gpt-4o
AZURE_OPENAI_API_KEY=your-api-key-here
AZURE_OPENAI_API_VERSION=2024-12-01-preview
```

---

## Start ObTrac

```bash
obtrac start
```

Output:
```
ObTrac is running!

  Dashboard:   http://localhost:3100
  Backend API: http://localhost:8100/docs

To stop:    obtrac stop
To check:   obtrac status
To open:    obtrac open
```

Open the dashboard:
```bash
obtrac open
```

---

## CLI Commands

| Command | What it does |
|---|---|
| `obtrac install` | Install frontend deps + build (one-time) |
| `obtrac start` | Start backend + frontend in background |
| `obtrac stop` | Stop running services |
| `obtrac status` | Check if services are running |
| `obtrac open` | Open dashboard in browser |
| `obtrac --help` | Show help |

---

## Test it works

Create a file `test.py`:

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
    print(pipeline("World"))
    print("Check http://localhost:3100 for your trace")
```

Run it:
```bash
python test.py
```

Open http://localhost:3100 → see your trace under `setup-test` project.

---

## Optional Features

Install extra dependencies on demand:

```bash
# RAGAS evaluation support
pip install -e ".[ragas]"

# Streamlit test apps (FAISS, sentence-transformers, etc.)
pip install -e ".[ui]"

# LangGraph + LangChain agents
pip install -e ".[agents]"

# Everything
pip install -e ".[all]"
```

---

## Run Test Apps

After `pip install -e ".[ui]"`:

```bash
# Simple RAG (FAISS + Azure OpenAI)
streamlit run test_app/app.py --server.port 8501

# Multi-agent
streamlit run test_app/agent_app.py --server.port 8502

# LangChain
streamlit run test_app/langchain_app.py --server.port 8503

# LangGraph
streamlit run test_app/langgraph_app.py --server.port 8504

# Google ADK style
streamlit run test_app/google_adk_app.py --server.port 8505
```

---

## Project Structure

```
ObTrac/
├── obtrac_sdk/                  # Python SDK + CLI
│   ├── __init__.py
│   ├── cli.py                   # obtrac command
│   ├── decorators.py            # @trace, @observe
│   ├── config.py
│   └── ...
│
├── backend/                     # FastAPI server
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   ├── db/
│   │   └── core/
│   └── data/                    # SQLite (gitignored)
│
├── frontend/                    # Next.js dashboard
│   ├── src/
│   │   ├── app/
│   │   └── components/
│   └── package.json
│
├── test_app/                    # Streamlit examples
│   ├── app.py
│   ├── agent_app.py
│   ├── langchain_app.py
│   ├── langgraph_app.py
│   └── google_adk_app.py
│
├── examples/                    # Code samples
│   └── quickstart.py
│
├── pyproject.toml               # pip install config
├── README.md
├── EXAMPLES.md
├── SETUP_NEW_MACHINE.md         # This file
├── .env.example
└── .gitignore
```

---

## Troubleshooting

### `obtrac: command not found`

Make sure pip's bin directory is in your PATH. On Windows, restart your terminal after `pip install -e .`.

Check installation:
```bash
pip show obtrac
```

### `npm install` fails

- Make sure Node.js 18+ is installed: `node --version`
- Try clearing the cache: `npm cache clean --force`
- Delete `frontend/node_modules` and `frontend/package-lock.json`, then `obtrac install` again

### `Port 8100 already in use`

Stop any existing ObTrac process:
```bash
obtrac stop
```

Or kill manually (Windows):
```bash
taskkill /F /IM python.exe
```

### `.env not loading`

Make sure `.env` is in the **project root** (same folder as `pyproject.toml`), not inside `backend/` or `test_app/`.

### Auto-eval not working

1. Open http://localhost:3100/llm-config
2. Add an LLM with **Use for Auto-Evaluation** checked
3. In your code, set `auto_eval=True` in `obtrac_config()`

---

## Migrating Existing Data

Copy the SQLite database from your old machine:

```bash
# Old machine
cp backend/data/obtrac.db ~/obtrac_backup.db

# Transfer to new machine, then
mkdir -p ObTrac/backend/data
cp ~/obtrac_backup.db ObTrac/backend/data/obtrac.db
```

Restart:
```bash
obtrac stop
obtrac start
```

---

## Production Deployment

For running ObTrac in production:

1. **PostgreSQL** instead of SQLite — edit `backend/app/db/database.py`
2. **Gunicorn** for the backend
3. **Nginx** as reverse proxy
4. **Docker Compose** — `docker-compose up --build`

See [README.md](README.md#production-deployment) for details.

---

## Next Steps

- Read [README.md](README.md) for full feature documentation
- Read [EXAMPLES.md](EXAMPLES.md) for code examples and edge cases
- Try the test apps in `test_app/` to see ObTrac in action
- Build your own pipeline using the SDK!
