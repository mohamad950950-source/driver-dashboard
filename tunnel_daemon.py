"""
Driver Dashboard — Online Tunnel Daemon
Keeps Serveo tunnel alive in background with auto-restart.
"""
import subprocess, sys, time, os, json, urllib.request

SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(SERVER_DIR, "tunnel.log")
URL_FILE = os.path.join(SERVER_DIR, "public_url.txt")

def log(msg):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

def get_public_url():
    """Try to extract the public URL from Serveo output."""
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if "serveousercontent.com" in line:
                    # Extract URL
                    import re
                    m = re.search(r'https://[a-z0-9-]+\.serveousercontent\.com', line)
                    if m:
                        url = m.group(0)
                        with open(URL_FILE, "w") as uf:
                            uf.write(url)
                        return url
    except:
        pass
    return None

def run_tunnel():
    log("Starting Serveo tunnel...")
    proc = subprocess.Popen(
        ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ServerAliveInterval=30",
         "-o", "ExitOnForwardFailure=yes", "-R", "80:localhost:8000", "serveo.net"],
        cwd=SERVER_DIR,
        stdout=open(LOG_FILE, "a", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    return proc

def main():
    log("=" * 50)
    log("Tunnel Daemon v1.0 — Starting")
    log(f"Workdir: {SERVER_DIR}")

    proc = None
    restart_delay = 5

    try:
        while True:
            if proc is None or proc.poll() is not None:
                if proc is not None:
                    exit_code = proc.poll()
                    log(f"Tunnel exited (code={exit_code}). Restarting in {restart_delay}s...")
                    time.sleep(restart_delay)
                    restart_delay = min(restart_delay * 2, 60)
                else:
                    restart_delay = 5

                proc = run_tunnel()
                log(f"Tunnel PID: {proc.pid}")

                # Wait a bit then check URL
                time.sleep(5)
                url = get_public_url()
                if url:
                    log(f"🌐 PUBLIC URL: {url}")
                    print(f"\n🌐 PUBLIC URL: {url}\n")
                else:
                    log("Still waiting for tunnel URL...")

            time.sleep(10)

    except KeyboardInterrupt:
        log("Shutting down tunnel daemon...")
        if proc and proc.poll() is None:
            proc.terminate()

if __name__ == "__main__":
    main()
