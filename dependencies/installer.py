from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path
from typing import List

REQUIREMENTS_FILE = Path(__file__).resolve().parents[1] / "requirements.txt"


def _normalize_package_name(package: str) -> str:
    return package.replace("-", "_")


def _iter_required_imports(requirements_path: Path) -> List[str]:
    imports: List[str] = []
    if not requirements_path.exists():
        return imports

    for line in requirements_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        pkg = stripped.split(";")[0].strip()
        if not pkg:
            continue
        # Remove version specifiers (==, >=, <=, etc.)
        for token in ("==", ">=", "<=", "~=", "!=", ">", "<"):
            if token in pkg:
                pkg = pkg.split(token, 1)[0]
                break
        imports.append(_normalize_package_name(pkg))
    return imports


def find_missing_packages(requirements_path: Path | None = None) -> List[str]:
    requirements_path = requirements_path or REQUIREMENTS_FILE
    missing: List[str] = []
    for module_name in _iter_required_imports(requirements_path):
        try:
            importlib.import_module(module_name)
        except ImportError:
            missing.append(module_name)
    return missing


def install_requirements(requirements_path: Path | None = None) -> bool:
    requirements_path = requirements_path or REQUIREMENTS_FILE
    if not requirements_path.exists():
        print(f"Requirements file not found: {requirements_path}")
        return False

    command = [sys.executable, "-m", "pip", "install", "-r", str(requirements_path)]
    print("Running:", " ".join(command))
    result = subprocess.run(command)
    if result.returncode == 0:
        print("Dependencies installed successfully.")
        return True

    print("Dependency installation failed. See output above.")
    return False


def run() -> bool:
    missing = find_missing_packages()
    if not missing:
        print("All dependencies are already installed.")
        return True

    print("Missing dependencies detected:", ", ".join(missing))
    choice = input("Install now? [Y/N]: ").strip().lower()
    if choice != "y":
        print("Skipping installation. Exiting application.")
        return False

    return install_requirements()
