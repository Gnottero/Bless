from __future__ import annotations

import importlib.util
from pathlib import Path


TEST_DIR = Path(__file__).resolve().parent


def main() -> None:
    executed = 0
    for path in sorted(TEST_DIR.glob("test_*.py")):
        spec = importlib.util.spec_from_file_location(path.stem, path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Impossibile caricare {path.name}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for name in sorted(dir(module)):
            candidate = getattr(module, name)
            if name.startswith("test_") and callable(candidate):
                candidate()
                executed += 1
                print(f"PASS {path.name}::{name}")
    print(f"{executed} test Python completati")


if __name__ == "__main__":
    main()
