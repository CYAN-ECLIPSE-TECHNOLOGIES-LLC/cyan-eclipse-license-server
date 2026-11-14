"""Entry points.

  python -m license_server                 MCP server on stdio (default)
  python -m license_server --seed          seed tenant #1 into the runtime DB
  python -m license_server --rotate-key cet-2026-02   (tenant #1 owner act)
  python -m license_server --http 8799     thin HTTP face on localhost ONLY
                                           (bench/tests; not a deployment)

Runtime state defaults to a runtime dir OUTSIDE the repo tree,
resolved by default_runtime_dir() through proper mechanisms only:

  1. CETLIC_RUNTIME_DIR env var — explicit deployment config (the
     systemd unit and the Dockerfile both set it);
  2. the per-user state root of the account running the server:
       Windows  %LOCALAPPDATA%\CyanEclipseLicenseServer
       macOS    ~/Library/Application Support/CyanEclipseLicenseServer
       Linux    $XDG_STATE_HOME/cyan-eclipse-license-server
                (fallback ~/.local/state/cyan-eclipse-license-server)

No host-specific absolute path is ever a default (ETO-93).
CETLIC_DB / CETLIC_KEY_DIR override the DB / key locations
individually, wherever the runtime dir resolves.
"""
import os, sys
from .core import Core, Caller
from .seed import seed, TENANT_ID, OWNER, DEFAULT_KID

def default_runtime_dir(environ=None, platform=None, home=None):
    """Resolve the runtime state dir; see the module docstring."""
    environ = os.environ if environ is None else environ
    override = environ.get("CETLIC_RUNTIME_DIR")
    if override:
        return override
    platform = sys.platform if platform is None else platform
    home = os.path.expanduser("~") if home is None else home
    if platform.startswith("win"):
        base = environ.get("LOCALAPPDATA") or os.path.join(
            home, "AppData", "Local")
        return os.path.join(base, "CyanEclipseLicenseServer")
    if platform == "darwin":
        return os.path.join(home, "Library", "Application Support",
                            "CyanEclipseLicenseServer")
    base = environ.get("XDG_STATE_HOME") or os.path.join(
        home, ".local", "state")
    return os.path.join(base, "cyan-eclipse-license-server")

RUNTIME = default_runtime_dir()

def build_core():
    db = os.environ.get("CETLIC_DB", os.path.join(RUNTIME, "state.db"))
    keys = os.environ.get("CETLIC_KEY_DIR", os.path.join(RUNTIME, "keys"))
    os.makedirs(os.path.dirname(db), exist_ok=True)
    core = Core(db, key_dir=keys, current_kids={TENANT_ID: DEFAULT_KID})
    return core

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    core = build_core()
    if "--seed" in argv:
        print(seed(core))
        return 0
    if "--rotate-key" in argv:
        kid = argv[argv.index("--rotate-key") + 1]
        seed(core)
        print(core.rotate_key(Caller(TENANT_ID, OWNER), kid))
        return 0
    if "--http" in argv:
        port = int(argv[argv.index("--http") + 1])
        from .http_face import serve
        httpd = serve(core, "127.0.0.1", port)
        print(f"http face on 127.0.0.1:{port} (localhost bench only)", file=sys.stderr)
        httpd.serve_forever()
        return 0
    from .mcp_server import serve_stdio
    serve_stdio(core)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
