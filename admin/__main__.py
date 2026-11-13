"""Run the web admin: python3 -m admin (binds 127.0.0.1:8798)."""
from .app import main

if __name__ == "__main__":
    raise SystemExit(main())
