"""Entry points.

  python -m license_server                 MCP server on stdio (default)
  python -m license_server --seed          seed tenant #1 into the runtime DB
  python -m license_server --rotate-key cet-2026-02   (tenant #1 owner act)
  python -m license_server --http 8799     thin HTTP face on localhost ONLY
                                           (bench/tests; not a deployment)

Runtime state defaults to the runtime dir OUTSIDE the repo tree:
  /home/witness/app-family/cyan-eclipse-license-server-runtime/
Override with CETLIC_RUNTIME_DIR / CETLIC_DB / CETLIC_KEY_DIR.
"""
import os, sys
from .core import Core, Caller
from .seed import seed, TENANT_ID, OWNER, DEFAULT_KID

RUNTIME = os.environ.get("CETLIC_RUNTIME_DIR",
                         "/home/witness/app-family/cyan-eclipse-license-server-runtime")

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
