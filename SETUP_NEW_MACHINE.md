# Setup ObTrac on a New Machine

The fastest way to get ObTrac running — works for both **fresh installs** and **updating an existing install**.

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

## Install (or upgrade) — 2 commands

```bash
pip install --upgrade --force-reinstall "obtrac[all] @ git+https://github.com/satyamk9git/ObTrac.git"
obtrac install
```

That's it. These two commands work for **every** scenario:

| Scenario | What happens |
|---|---|
| **First time on this machine** | pip installs the SDK + all deps. `obtrac install` clones the repo to `~/.obtrac`, runs `npm install`, builds the frontend. |
| **Upgrading an existing install** | pip force-reinstalls the SDK to the latest version. `obtrac install` detects `~/.obtrac` is a git repo, runs `git fetch + reset --hard origin/main`, then re-runs `npm install` and rebuilds. **Your `.env` and SQLite database are preserved.** |
| **Old non-git folder at `~/.obtrac`** | `obtrac install` automatically backs up `.env` and `obtrac.db` to `~/.obtrac_backup/`, wipes the folder, re-clones fresh, and restores both files. |

> **No manual uninstall needed.** Re-running these two commands always brings you to the latest version while keeping your data.

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
```

Open the dashboard:
```bash
obtrac open
```

---

## First-time only — configure LLM credentials

After `obtrac install`, create a `.env` file at `~/.obtrac/.env`:

```env
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_MODEL_NAME=gpt-4o
AZURE_OPENAI_DEPLOYMENT=gpt-4o
AZURE_OPENAI_API_KEY=your-api-key-here
AZURE_OPENAI_API_VERSION=2024-12-01-preview
```

Or skip the `.env` and add LLMs through the dashboard at **Settings → LLM Config** after starting.

> **On upgrades:** your existing `.env` is preserved automatically — you don't need to redo this step.

---

## If `obtrac` command isn't recognized

Python's Scripts folder isn't on your PATH. Use the module form instead — it always works:

```bash
python -m obtrac_sdk.cli install
python -m obtrac_sdk.cli start
python -m obtrac_sdk.cli stop
python -m obtrac_sdk.cli status
python -m obtrac_sdk.cli open
```

### Permanent fix on Windows

Find your Scripts folder:
```powershell
python -c "import sys, os; print(os.path.join(sys.prefix, 'Scripts'))"
```

Add it to PATH:
1. `Win + R` → `sysdm.cpl` → Enter
2. **Advanced** → **Environment Variables**
3. Under "User variables", select **Path** → **Edit** → **New** → paste the Scripts path
4. OK → restart your terminal

### On Mac/Linux

Add to `~/.bashrc` or `~/.zshrc`:
```bash
export PATH="$HOME/.local/bin:$PATH"
```
Then `source ~/.bashrc`.

---

## CLI Commands

| Command | Or use | What it does |
|---|---|---|
| `obtrac install` | `python -m obtrac_sdk.cli install` | Install / update project files + frontend |
| `obtrac start` | `python -m obtrac_sdk.cli start` | Start backend + frontend |
| `obtrac stop` | `python -m obtrac_sdk.cli stop` | Stop running services |
| `obtrac status` | `python -m obtrac_sdk.cli status` | Check service status |
| `obtrac open` | `python -m obtrac_sdk.cli open` | Open dashboard in browser |

---

## Test your install

Create `test.py`:

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

Open http://localhost:3100 → see your trace under the `setup-test` project.

---

## Where things live

| What | Path |
|---|---|
| Project files | `~/.obtrac/` |
| `.env` | `~/.obtrac/.env` |
| SQLite database | `~/.obtrac/backend/data/obtrac.db` |
| Frontend build | `~/.obtrac/frontend/.next/` |
| Backups (auto) | `~/.obtrac_backup/` |
| PID file | `~/.obtrac_pids.json` |

---

## Alternative: Clone first (for code modifications)

If you want to edit ObTrac itself:

```bash
git clone https://github.com/satyamk9git/ObTrac.git
cd ObTrac
pip install -e ".[all]"
obtrac install
```

In this mode, `obtrac install` skips the clone/update logic and uses your local checkout — you manage updates with `git pull` yourself.

---

## Troubleshooting

### `npm install` fails
- Ensure Node.js 18+: `node --version`
- Clear cache: `npm cache clean --force`
- Delete `~/.obtrac/frontend/node_modules` and re-run `obtrac install`

### Port 8100 / 3100 already in use
```bash
obtrac stop
```
Then start again. If that doesn't help, kill manually:
```bash
# Windows
netstat -ano | findstr :8100
taskkill /PID <pid> /F
```

### `.env` not loading
Make sure it lives at `~/.obtrac/.env` (project root), **not** inside `backend/` or `test_app/`.

### Auto-eval not working
1. Open http://localhost:3100/llm-config
2. Add an LLM with **Use for Auto-Evaluation** checked
3. In your code: `obtrac_config(..., auto_eval=True)`

---

## Optional extras

The `[all]` extra in the pip command above already pulls in everything:
RAGAS, MLflow, Streamlit, FAISS, sentence-transformers, LangGraph, LangChain.

If you want a leaner install, swap `[all]` for one of:
- `[ragas]` — RAGAS evaluation only
- `[ui]` — Streamlit + FAISS + sentence-transformers (test apps)
- `[agents]` — LangGraph + LangChain
- (no extra) — SDK + backend only

---

## Next steps

- [README.md](README.md) — full feature documentation
- [EXAMPLES.md](EXAMPLES.md) — code patterns and edge cases
- `~/.obtrac/test_app/` — Streamlit examples (RAG, agents, LangChain, LangGraph)
