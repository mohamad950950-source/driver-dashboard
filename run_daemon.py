"""
Driver Dashboard — Daemon Mode
Runs permanently in background with auto-restart on crash.
"""
import subprocess, sys, time, os

SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SERVER_DIR)

PYTHON = sys.executable  # full path to python.exe
SERVER_SCRIPT = os.path.join(SERVER_DIR, "app.py")
LOG_FILE = os.path.join(SERVER_DIR, "server.log")

def log(msg):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

def run_server():
    for d in ["data", "uploads"]:
        os.makedirs(os.path.join(SERVER_DIR, d), exist_ok=True)
    log("Starting server...")
    proc = subprocess.Popen(
        [PYTHON, SERVER_SCRIPT],
        cwd=SERVER_DIR,
        stdout=open(LOG_FILE, "a", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    return proc

def main():
    log("=" * 50)
    log("Daemon v2.0 — Starting")
    log(f"Python: {PYTHON}")
    log(f"Script: {SERVER_SCRIPT}")
    log(f"Workdir: {SERVER_DIR}")

    proc = None
    delay = 2

    try:
        while True:
            if proc is None or proc.poll() is not None:
                if proc is not None:
                    code = proc.poll()
                    log(f"Crashed (code={code}). Restart in {delay}s...")
                    time.sleep(delay)
                    delay = min(delay * 2, 30)
                else:
                    delay = 2
                proc = run_server()
                log(f"PID: {proc.pid}")
            time.sleep(5)
    except KeyboardInterrupt:
        log("Shutting down...")
        if proc and proc.poll() is None:
            proc.terminate(); proc.wait(5)
        log("Stopped.")
    except Exception as e:
        log(f"Error: {e}")
        if proc and proc.poll() is None:
            proc.terminate()

if __name__ == "__main__":
    main()
