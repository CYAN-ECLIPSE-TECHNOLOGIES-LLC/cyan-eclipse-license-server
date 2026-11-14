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
