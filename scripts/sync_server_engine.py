from __future__ import annotations

import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "public" / "python"
TARGET_ROOT = PROJECT_ROOT / "api" / "_engine"


def main() -> None:
    source_files = [
        *sorted((SOURCE_ROOT / "bless_sim").glob("*.py")),
        SOURCE_ROOT / "data" / "luce_ombra.json",
        SOURCE_ROOT / "data" / "tuono_sabbia.json",
    ]
    for source in source_files:
        relative = source.relative_to(SOURCE_ROOT)
        target = TARGET_ROOT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    print(f"Sincronizzati {len(source_files)} file del motore server.")


if __name__ == "__main__":
    main()
