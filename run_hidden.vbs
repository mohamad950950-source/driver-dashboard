Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "uv run python run_daemon.py", 0, False
