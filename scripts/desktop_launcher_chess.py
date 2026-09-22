"""
Chess Speak Out Loud (Analysis App) — Desktop App Wrapper.

Launches the FastAPI backend and Vite frontend in background, opens a dedicated
standalone desktop window (Chromium/Edge App Mode), and cleanly terminates all
processes when the user closes the window.
"""
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_DIR / "frontend"
PYTHON_EXE = r"C:\Users\Admin\miniconda3\envs\cszero\python.exe"


def is_ready(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=1) as resp:
            return resp.status == 200
    except Exception:
        return False


def find_browser_app_executable() -> str | None:
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def main():
    CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

    # 1. Start FastAPI backend (port 8000)
    backend_proc = subprocess.Popen(
        [PYTHON_EXE, "-m", "uvicorn", "backend.app:app", "--port", "8000"],
        cwd=str(PROJECT_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=CREATE_NO_WINDOW,
    )

    # 2. Start Vite frontend dev server (port 5173)
    frontend_proc = subprocess.Popen(
        ["cmd", "/c", "npm", "run", "dev"],
        cwd=str(FRONTEND_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=CREATE_NO_WINDOW,
    )

    # 3. Wait until both are ready
    for _ in range(50):
        if is_ready("http://127.0.0.1:8000/api/health") and is_ready("http://localhost:5173/"):
            break
        time.sleep(0.2)

    # 4. Open standalone desktop window
    browser_exe = find_browser_app_executable()
    temp_profile = os.path.join(os.environ.get("TEMP", "."), "chess_analysis_app_profile")

    try:
        if browser_exe:
            subprocess.run(
                [
                    browser_exe,
                    "--app=http://localhost:5173/",
                    f"--user-data-dir={temp_profile}",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--window-size=1280,900",
                ],
                check=False,
            )
        else:
            import webbrowser
            webbrowser.open("http://localhost:5173/")
            backend_proc.wait()
    finally:
        # 5. Clean shutdown
        for p in [backend_proc, frontend_proc]:
            try:
                p.terminate()
            except Exception:
                pass
        # Kill any orphaned lc0 or node instances spawned by this run
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                "Get-Process -Name lc0 -ErrorAction SilentlyContinue | Stop-Process -Force; "
                "Get-Process -Name node -ErrorAction SilentlyContinue | Where-Object { $_.Path -like '*frontend*' -or $_.CommandLine -like '*vite*' } | Stop-Process -Force",
            ],
            creationflags=CREATE_NO_WINDOW,
            check=False,
        )


if __name__ == "__main__":
    main()
