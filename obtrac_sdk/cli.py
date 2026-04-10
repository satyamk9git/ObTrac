"""
ObTrac CLI — install, start, stop, status

Usage:
    obtrac install     # Install frontend dependencies (npm install + build)
    obtrac start       # Start backend + frontend
    obtrac stop        # Stop running services
    obtrac status      # Check status of services
    obtrac open        # Open dashboard in browser
"""

import os
import sys
import subprocess
import time
import argparse
from pathlib import Path

# Find project root (where pyproject.toml lives)
def find_project_root():
    current = Path(__file__).parent
    for _ in range(5):
        if (current / "pyproject.toml").exists():
            return current
        current = current.parent
    return None


PROJECT_ROOT = find_project_root()
BACKEND_DIR = PROJECT_ROOT / "backend" if PROJECT_ROOT else None
FRONTEND_DIR = PROJECT_ROOT / "frontend" if PROJECT_ROOT else None
PID_FILE = Path.home() / ".obtrac_pids.json"

BACKEND_PORT = 8100
FRONTEND_PORT = 3100


def _print_banner():
    print()
    print("  ===================================")
    print("    ObTrac - RAG Observability")
    print("  ===================================")
    print()


def _check_node():
    try:
        subprocess.run(["node", "--version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def cmd_install():
    """Install frontend dependencies and build for production."""
    _print_banner()

    if not PROJECT_ROOT:
        print("Error: Could not find project root. Are you in the ObTrac directory?")
        sys.exit(1)

    if not _check_node():
        print("Error: Node.js not found. Install from https://nodejs.org/")
        sys.exit(1)

    print(f"Project root: {PROJECT_ROOT}")
    print()

    # Install frontend dependencies
    if FRONTEND_DIR.exists():
        print("Installing frontend dependencies (this may take a few minutes)...")
        try:
            subprocess.run(
                ["npm", "install"],
                cwd=str(FRONTEND_DIR),
                check=True,
                shell=(os.name == "nt"),
            )
            print("Frontend dependencies installed.")
        except subprocess.CalledProcessError:
            print("npm install failed.")
            sys.exit(1)

        print()
        print("Building frontend for production (one-time)...")
        try:
            subprocess.run(
                ["npx", "next", "build"],
                cwd=str(FRONTEND_DIR),
                check=True,
                shell=(os.name == "nt"),
            )
            print("Frontend built.")
        except subprocess.CalledProcessError:
            print("Frontend build failed.")
            sys.exit(1)

    # Initialize backend data dir
    data_dir = BACKEND_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    print()
    print("Installation complete!")
    print()
    print("Next steps:")
    print("  1. Create a .env file with your LLM credentials (see .env.example)")
    print("  2. Run: obtrac start")
    print()


def cmd_start():
    """Start backend + frontend in the background."""
    _print_banner()

    if not PROJECT_ROOT:
        print("Error: Could not find project root.")
        sys.exit(1)

    # Check if .env exists
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        print("Warning: .env file not found.")
        print(f"Create one at: {env_file}")
        print("See .env.example for the template.")
        print()

    # Check if frontend is built
    if not (FRONTEND_DIR / ".next").exists():
        print("Frontend not built. Running 'obtrac install' first...")
        cmd_install()

    print(f"Starting backend on port {BACKEND_PORT}...")
    backend_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(BACKEND_PORT)],
        cwd=str(BACKEND_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    print(f"Starting frontend on port {FRONTEND_PORT}...")
    frontend_proc = subprocess.Popen(
        ["npx", "next", "start", "--port", str(FRONTEND_PORT)],
        cwd=str(FRONTEND_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        shell=(os.name == "nt"),
    )

    # Save PIDs
    import json
    with open(PID_FILE, "w") as f:
        json.dump({"backend": backend_proc.pid, "frontend": frontend_proc.pid}, f)

    # Wait for services to be ready
    print()
    print("Waiting for services to start...")
    time.sleep(8)

    print()
    print("ObTrac is running!")
    print()
    print(f"  Dashboard:   http://localhost:{FRONTEND_PORT}")
    print(f"  Backend API: http://localhost:{BACKEND_PORT}/docs")
    print()
    print("To stop:    obtrac stop")
    print("To check:   obtrac status")
    print("To open:    obtrac open")
    print()


def cmd_stop():
    """Stop running backend + frontend."""
    _print_banner()

    import json
    if not PID_FILE.exists():
        print("No running services found.")
        return

    with open(PID_FILE) as f:
        pids = json.load(f)

    for name, pid in pids.items():
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"], capture_output=True)
            else:
                os.kill(pid, 9)
            print(f"Stopped {name} (PID {pid})")
        except (ProcessLookupError, OSError):
            print(f"{name} (PID {pid}) was not running")

    PID_FILE.unlink()
    print()
    print("All services stopped.")


def cmd_status():
    """Check status of services."""
    _print_banner()

    import requests

    def _check(url, name):
        try:
            r = requests.get(url, timeout=2)
            return r.status_code < 500
        except Exception:
            return False

    backend_ok = _check(f"http://localhost:{BACKEND_PORT}/health", "backend")
    frontend_ok = _check(f"http://localhost:{FRONTEND_PORT}/", "frontend")

    print(f"  Backend  ({BACKEND_PORT}):  {'RUNNING' if backend_ok else 'STOPPED'}")
    print(f"  Frontend ({FRONTEND_PORT}):  {'RUNNING' if frontend_ok else 'STOPPED'}")
    print()

    if backend_ok and frontend_ok:
        print(f"  Open: http://localhost:{FRONTEND_PORT}")


def cmd_open():
    """Open the dashboard in the default browser."""
    import webbrowser
    url = f"http://localhost:{FRONTEND_PORT}"
    print(f"Opening {url}...")
    webbrowser.open(url)


def main():
    parser = argparse.ArgumentParser(
        prog="obtrac",
        description="ObTrac - RAG Observability & Evaluation Framework",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    subparsers.add_parser("install", help="Install frontend dependencies + build")
    subparsers.add_parser("start", help="Start backend + frontend")
    subparsers.add_parser("stop", help="Stop running services")
    subparsers.add_parser("status", help="Check service status")
    subparsers.add_parser("open", help="Open dashboard in browser")

    args = parser.parse_args()

    if args.command == "install":
        cmd_install()
    elif args.command == "start":
        cmd_start()
    elif args.command == "stop":
        cmd_stop()
    elif args.command == "status":
        cmd_status()
    elif args.command == "open":
        cmd_open()
    else:
        parser.print_help()
        print()
        print("Quick start:")
        print("  obtrac install   # Install frontend deps")
        print("  obtrac start     # Start backend + dashboard")
        print("  obtrac open      # Open dashboard in browser")


if __name__ == "__main__":
    main()
