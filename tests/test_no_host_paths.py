"""ETO-93 regression battery — the PLU-17 host-path class.

Two legs:
  * ShippedArtefactHostPathTest ASSEMBLES the shipped artefact
    (the license_server package + the distribution metadata the
    Dockerfile / pip build actually ship) into a zip and scans
    the ARTEFACT's bytes, member by member, for host paths,
    internal addresses and internal hostnames — not a source grep.
  * RuntimeResolutionMechanismsTest proves the runtime dir now
    resolves through proper mechanisms only (env override ->
    per-user state root), hermetically and in a fresh process,
    and that a seeded runtime lands under the override, never at
    a host-specific default.
  * RepoTreeHostPathTest (WS-11b addendum, ETO-93 G-2) scans the
    WHOLE repo tree — not just the shipped artefact — for the
    same pattern class, so a non-shipped member (admin/, client/,
    tests/) cannot carry the class silently. Exclusions, named:
    .git/, __pycache__/, this test file itself (the fence), and
    BENCH-REQUEST-*.md repo records, which quote the cured literal
    as historical bench evidence (WS-11 G-3: naming the build home
    is a record's function; records are not code defaults).
  * AdminClientResolutionTest proves admin/mcp_client.py resolves
    its runtime dir through the SAME default_runtime_dir()
    mechanism (env override first, else the per-user state root),
    closing the G-2 instance WS-11 enumerated but did not cure.

The pattern literals below are the fence itself; this file is a
test, not an artefact member.
"""
import io
import os
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
sys.path.insert(0, SRC)

try:
    from license_server.__main__ import default_runtime_dir  # noqa: E402
except ImportError:  # pre-cure tree: the artefact-scan leg must still run
    default_runtime_dir = None

ARTEFACT_MEMBERS = (
    [os.path.join("src", "license_server", n)
     for n in sorted(os.listdir(os.path.join(SRC, "license_server")))
     if n.endswith(".py")]
    + ["pyproject.toml", "README.md", "LICENSE", "Dockerfile", "glama.json"]
)

HOST_PATTERNS = [
    rb"/home/[^/\s\"']+/",          # any user's home path (the ETO-93 literal class)
    rb"/root/",
    rb"/var/lib/",
    rb"/var/tmp/",
    rb"/Users/",
    rb"[A-Za-z]:\\Users\\",
    rb"\b64\.23\.\d{1,3}\.\d{1,3}\b",      # firm droplet addresses
    rb"\b146\.190\.\d{1,3}\.\d{1,3}\b",
    rb"\b10\.124\.\d{1,3}\.\d{1,3}\b",     # VPC addresses
    rb"[A-Za-z0-9-]+\.internal\b",          # internal hostnames
    rb"cetech-witness",
]


class ShippedArtefactHostPathTest(unittest.TestCase):
    def test_assembled_artefact_carries_no_host_paths(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for member in ARTEFACT_MEMBERS:
                z.write(os.path.join(REPO, member), member)
        hits = []
        with zipfile.ZipFile(io.BytesIO(buf.getvalue())) as z:
            for info in z.infolist():
                data = z.read(info.filename)
                for pat in HOST_PATTERNS:
                    for m in re.finditer(pat, data):
                        hits.append("%s: %r matched %s"
                                    % (info.filename, pat, m.group()[:60]))
        self.assertEqual([], hits)


class RuntimeResolutionMechanismsTest(unittest.TestCase):
    def setUp(self):
        if default_runtime_dir is None:
            self.fail("default_runtime_dir is not defined: the runtime "
                      "dir still resolves through a hardcoded default")

    def test_env_override_wins_on_every_platform(self):
        env = {"CETLIC_RUNTIME_DIR": "/srv/cetlic-runtime"}
        for platform in ("linux", "darwin", "win32"):
            self.assertEqual("/srv/cetlic-runtime",
                             default_runtime_dir(env, platform, "/home/u"))

    def test_linux_xdg_state_home(self):
        env = {"XDG_STATE_HOME": "/home/u/.state"}
        self.assertEqual("/home/u/.state/cyan-eclipse-license-server",
                         default_runtime_dir(env, "linux", "/home/u"))

    def test_linux_fallback_is_per_user_state_root(self):
        self.assertEqual("/home/u/.local/state/cyan-eclipse-license-server",
                         default_runtime_dir({}, "linux", "/home/u"))

    def test_win32_localappdata(self):
        env = {"LOCALAPPDATA": r"C:\Users\u\AppData\Local"}
        got = default_runtime_dir(env, "win32", r"C:\Users\u")
        self.assertTrue(got.endswith("CyanEclipseLicenseServer"), got)
        self.assertIn("AppData", got)

    def test_win32_fallback_under_home(self):
        got = default_runtime_dir({}, "win32", "/home/u")
        self.assertTrue(got.endswith(
            os.path.join("AppData", "Local", "CyanEclipseLicenseServer")), got)

    def test_darwin_application_support(self):
        got = default_runtime_dir({}, "darwin", "/home/u")
        self.assertEqual("/home/u/Library/Application Support/"
                         "CyanEclipseLicenseServer", got)

    def test_default_is_never_a_host_specific_path(self):
        for platform in ("linux", "darwin", "win32"):
            got = default_runtime_dir({}, platform, "/home/u")
            self.assertNotIn("witness", got)
            self.assertFalse(got.startswith(REPO), got)
            self.assertTrue(got.startswith("/home/u"), got)


# Repo records that quote the cured literal as bench evidence
# (WS-11 G-3 class); they are records, not code defaults.
REPO_TREE_EXCLUDED_BASENAMES = ("BENCH-REQUEST-",)


class RepoTreeHostPathTest(unittest.TestCase):
    def test_whole_repo_tree_carries_no_host_paths(self):
        hits = []
        for root, dirs, files in os.walk(REPO):
            dirs[:] = [d for d in dirs
                       if d not in (".git", "__pycache__")]
            for name in files:
                path = os.path.join(root, name)
                if os.path.abspath(path) == os.path.abspath(__file__):
                    continue  # this file is the fence itself
                if name.startswith(REPO_TREE_EXCLUDED_BASENAMES):
                    continue  # bench records quoting the literal
                with open(path, "rb") as fh:
                    data = fh.read()
                for pat in HOST_PATTERNS:
                    for m in re.finditer(pat, data):
                        hits.append("%s: %r matched %s"
                                    % (os.path.relpath(path, REPO),
                                       pat, m.group()[:60]))
        self.assertEqual([], hits)


class AdminClientResolutionTest(unittest.TestCase):
    """admin/mcp_client.py (ETO-93 G-2): reuse, not a fork."""

    def _client(self):
        if REPO not in sys.path:
            sys.path.insert(0, REPO)
        from admin.mcp_client import McpClient
        return McpClient()

    def test_admin_env_override_wins(self):
        with mock.patch.dict(os.environ,
                             {"CETLIC_RUNTIME_DIR": "/srv/cetlic-runtime"}):
            self.assertEqual("/srv/cetlic-runtime",
                             self._client().runtime_dir)

    def test_admin_default_matches_server_mechanism(self):
        if default_runtime_dir is None:
            self.fail("default_runtime_dir is not defined")
        with tempfile.TemporaryDirectory() as tmp:
            env = {"XDG_STATE_HOME": tmp, "HOME": tmp}
            with mock.patch.dict(os.environ, env):
                os.environ.pop("CETLIC_RUNTIME_DIR", None)
                got = self._client().runtime_dir
                self.assertEqual(default_runtime_dir(), got)
                self.assertEqual(
                    os.path.join(tmp, "cyan-eclipse-license-server")
                    if sys.platform.startswith("linux") else got, got)
                self.assertNotIn("witness", got)


class FreshProcessResolutionTest(unittest.TestCase):
    def _run(self, extra_env, *args):
        env = dict(os.environ)
        for k in ("CETLIC_RUNTIME_DIR", "CETLIC_DB", "CETLIC_KEY_DIR",
                  "XDG_STATE_HOME"):
            env.pop(k, None)
        env.update(extra_env)
        env["PYTHONPATH"] = SRC
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run(
            [sys.executable, "-m", "license_server", *args],
            capture_output=True, text=True, env=env, timeout=60)

    def test_fresh_process_default_uses_xdg_state_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ)
            for k in ("CETLIC_RUNTIME_DIR", "CETLIC_DB", "CETLIC_KEY_DIR"):
                env.pop(k, None)
            env.update({"XDG_STATE_HOME": tmp, "HOME": tmp,
                        "PYTHONPATH": SRC, "PYTHONDONTWRITEBYTECODE": "1"})
            proc = subprocess.run(
                [sys.executable, "-c",
                 "from license_server.__main__ import RUNTIME; print(RUNTIME)"],
                capture_output=True, text=True, env=env, timeout=60)
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertEqual(
                os.path.join(tmp, "cyan-eclipse-license-server"),
                proc.stdout.strip())

    def test_seed_lands_under_env_override_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = os.path.join(tmp, "runtime")
            proc = self._run({"CETLIC_RUNTIME_DIR": runtime,
                              "HOME": tmp, "XDG_STATE_HOME": tmp},
                             "--seed")
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertTrue(os.path.isfile(os.path.join(runtime, "state.db")))
            self.assertFalse(os.path.exists(
                os.path.join(tmp, "cyan-eclipse-license-server", "state.db")))


if __name__ == "__main__":
    unittest.main()
