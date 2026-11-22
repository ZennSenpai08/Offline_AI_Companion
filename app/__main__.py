import time
import sys

STARTED_AT = time.perf_counter()

if __name__ == "__main__":
    if not (3, 10) <= sys.version_info[:2] < (3, 15):
        raise SystemExit("Use Python 3.10–3.14 x64; Python 3.12 is the recommended baseline.")
    try:
        from app.main import main
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.split('.')[0] in {"PySide6", "shiboken6", "psutil"}:
            raise SystemExit("Missing desktop dependency. Run scripts/setup.ps1, then use .venv/Scripts/python.exe -m app.") from exc
        raise
    raise SystemExit(main(started_at=STARTED_AT))
