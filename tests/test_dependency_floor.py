"""Dependency floor guard (cryptography currency cure round 2, 2026-11-14).

The License Server signs licences with Ed25519 (keys.py) — the
licence-signing path of the universal sales mechanism. Both the
server (--http 8799) and the admin face ran /usr/bin/python3 and
imported the system python's cryptography 41.0.7, which carries
the 2026 CVE batch (fixes up to 48.0.1 / 50.0.0; RockEm
manifest-mode sweep, 2026-11-14; Shard E runtime census ETO-95,
2026-11-14). pyproject declared only cryptography>=41 — no pin,
no floor at the fixed level. This test is the regression guard:
it fails if the recorded pin OR the actually installed runtime
drops below the fixed floor (48.0.1, the highest fix version in
the 41.0.7 batch). The suite is expected to run under the
deployment venv built from requirements.txt.
"""
import re
import unittest
from pathlib import Path

import cryptography

FLOOR = (48, 0, 1)


def _parse(v: str):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


class DependencyFloor(unittest.TestCase):
    def test_pin_at_or_above_fixed_floor(self):
        req = (Path(__file__).resolve().parent.parent
               / "requirements.txt").read_text()
        m = re.search(r"^cryptography==([0-9.]+)", req, re.M)
        self.assertIsNotNone(m, "requirements.txt must pin cryptography")
        self.assertGreaterEqual(
            _parse(m.group(1)), FLOOR,
            f"cryptography pin {m.group(1)} is below the fixed floor "
            f"{'.'.join(map(str, FLOOR))} (CVE set re-opens)")

    def test_pyproject_floor_at_or_above_fixed_floor(self):
        pp = (Path(__file__).resolve().parent.parent
              / "pyproject.toml").read_text()
        m = re.search(r"cryptography>=([0-9.]+)", pp)
        self.assertIsNotNone(m, "pyproject must declare a cryptography floor")
        self.assertGreaterEqual(
            _parse(m.group(1)), FLOOR,
            f"pyproject cryptography floor {m.group(1)} is below the "
            f"fixed floor {'.'.join(map(str, FLOOR))}")

    def test_installed_at_or_above_fixed_floor(self):
        self.assertGreaterEqual(
            _parse(cryptography.__version__), FLOOR,
            f"installed cryptography {cryptography.__version__} is "
            f"below the fixed floor {'.'.join(map(str, FLOOR))}; "
            "run the suite under the deployment venv")


if __name__ == "__main__":
    unittest.main()
