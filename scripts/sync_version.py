#!/usr/bin/env python3
"""Keep the Python (``pyproject.toml``) version in lock-step with npm (``package.json``).

The release flow keys off ``$npm_package_version`` (see ``package.json`` ``publish:pypi`` /
``release:create``), so ``package.json`` is the source of truth. This script copies that
version into ``pyproject.toml`` (and ``package-lock.json``) so a release can never ship a
mismatched PyPI/npm version — the exact drift that happens when only one side is bumped.

It is wired into the npm ``version`` lifecycle (``package.json``), so ``npm version <x>``
syncs ``pyproject.toml`` automatically. It can also be run directly:

    python scripts/sync_version.py            # set pyproject.toml to package.json's version
    python scripts/sync_version.py 0.5.0      # set package.json + lock + pyproject to 0.5.0
    python scripts/sync_version.py --check    # exit non-zero if versions drift (CI guard)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
PACKAGE_JSON = ROOT / "package.json"
PACKAGE_LOCK = ROOT / "package-lock.json"
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+.][0-9A-Za-z.-]+)?$")
_PYPROJECT_VERSION = re.compile(r'(?m)^(version\s*=\s*)"([^"]*)"')


def read_pyproject_version() -> str:
    m = _PYPROJECT_VERSION.search(PYPROJECT.read_text(encoding="utf-8"))
    if not m:
        sys.exit("error: no `version = \"...\"` line found in pyproject.toml")
    return m.group(2)


def read_json_version(path: Path) -> str:
    return json.loads(path.read_text(encoding="utf-8"))["version"]


def set_pyproject_version(version: str) -> bool:
    text = PYPROJECT.read_text(encoding="utf-8")
    new, n = _PYPROJECT_VERSION.subn(rf'\g<1>"{version}"', text, count=1)
    if n != 1:
        sys.exit(f"error: expected exactly one version line in pyproject.toml, matched {n}")
    if new != text:
        PYPROJECT.write_text(new, encoding="utf-8")
        return True
    return False


def set_json_version(path: Path, version: str) -> bool:
    """Set a package's own version in package.json / package-lock.json (not dep versions)."""
    if not path.exists():
        return False
    data = json.loads(path.read_text(encoding="utf-8"))
    changed = False
    if data.get("version") and data["version"] != version:
        data["version"] = version
        changed = True
    # package-lock.json also records the root package's version under packages[""].
    root_pkg = data.get("packages", {}).get("") if isinstance(data.get("packages"), dict) else None
    if isinstance(root_pkg, dict) and root_pkg.get("version") not in (None, version):
        root_pkg["version"] = version
        changed = True
    if changed:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return changed


def main() -> None:
    args = sys.argv[1:]
    check = "--check" in args
    positional = [a for a in args if not a.startswith("--")]
    explicit = positional[0].lstrip("v") if positional else None

    if explicit and not SEMVER.match(explicit):
        sys.exit(f"error: invalid version {explicit!r} (expected e.g. 0.4.0)")

    npm_version = read_json_version(PACKAGE_JSON)
    target = explicit or npm_version
    if not SEMVER.match(target):
        sys.exit(f"error: package.json version {target!r} is not valid semver")

    if check:
        py = read_pyproject_version()
        if py != npm_version:
            sys.exit(f"version drift: pyproject.toml={py} != package.json={npm_version}")
        print(f"versions in sync: {py}")
        return

    changed = []
    if explicit:
        if set_json_version(PACKAGE_JSON, target):
            changed.append("package.json")
        if set_json_version(PACKAGE_LOCK, target):
            changed.append("package-lock.json")
    if set_pyproject_version(target):
        changed.append("pyproject.toml")

    if changed:
        print(f"set version {target} in: {', '.join(changed)}")
    else:
        print(f"already at {target} — nothing to change")


if __name__ == "__main__":
    main()
