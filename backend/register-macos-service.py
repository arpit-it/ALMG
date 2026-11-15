"""Register the local ALMG backend for the current macOS login session."""
import os
import plistlib
import subprocess
import sys
from pathlib import Path

LABEL = "local.almg.backend"

if __name__ == "__main__":
    if sys.platform != "darwin":
        sys.exit("This service uses macOS launchd.")
    root = Path(__file__).resolve().parents[1]
    python = root / ".venv/bin/python"
    if not python.is_file():
        sys.exit("Set up the project's Python environment first.")
    domain = f"gui/{os.getuid()}"
    service = f"{domain}/{LABEL}"
    if subprocess.run(["launchctl", "print", service], capture_output=True).returncode == 0:
        sys.exit("ALMG backend service is already registered for this login.")
    runs = root / "backend/runs"
    runs.mkdir(exist_ok=True)
    config = runs / f"{LABEL}.plist"
    config.write_bytes(plistlib.dumps({
        "Label": LABEL,
        "ProgramArguments": [str(python), str(root / "backend/studio.py"), "--launchd"],
        "WorkingDirectory": str(root),
        "StandardOutPath": str(runs / "backend.log"),
        "StandardErrorPath": str(runs / "backend.log"),
        "Sockets": {"Backend": {"SockNodeName": "127.0.0.1",
                                "SockServiceName": "8766", "SockFamily": "IPv4"}},
    }))
    subprocess.run(["launchctl", "bootstrap", domain, str(config)], check=True)
