from __future__ import annotations

import hashlib
import json
import re
import subprocess
import zipfile
from datetime import UTC, datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = PROJECT_ROOT / "artifacts"


def _git_revision() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _engine_version() -> str:
    version_file = PROJECT_ROOT / "public" / "python" / "bless_sim" / "version.py"
    match = re.search(
        r'^ENGINE_VERSION\s*=\s*["\']([^"\']+)["\']',
        version_file.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
    if match is None:
        raise RuntimeError("ENGINE_VERSION non trovato.")
    return match.group(1)


def _source_files() -> list[Path]:
    patterns = (
        "public/python/bless_sim/*.py",
        "public/python/data/*.json",
        "public/python/manual_bridge.py",
        "public/python/browser_bridge.py",
        "public/manual-worker.mjs",
        "tests/game-engine/*.py",
        "api/bless_server/*.py",
        "api/game.py",
        "src/app/gioco/**/*.ts",
        "src/app/gioco/**/*.tsx",
        "src/app/gioco/**/*.css",
        "src/app/saved-replays.ts",
        "docs/sync-engine-and-replays.md",
        "scripts/sync_server_engine.py",
    )
    files = {
        path
        for pattern in patterns
        for path in PROJECT_ROOT.glob(pattern)
        if path.is_file()
    }
    return sorted(files, key=lambda path: path.as_posix().lower())


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    engine_version = _engine_version()
    revision = _git_revision()
    exported_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    files = _source_files()
    entries: list[dict[str, object]] = []
    payloads: dict[str, bytes] = {}

    for path in files:
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        data = path.read_bytes()
        payloads[relative] = data
        entries.append(
            {
                "path": relative,
                "bytes": len(data),
                "sha256": _sha256(data),
            }
        )

    manifest = {
        "format": "bless.game-system.bundle",
        "schema_version": 1,
        "engine_version": engine_version,
        "replay_schema_version": 1,
        "git_revision": revision,
        "exported_at": exported_at,
        "canonical_engine": "public/python/bless_sim",
        "canonical_card_data": "public/python/data",
        "generated_server_mirror_omitted": "api/_engine",
        "files": entries,
    }
    instructions = f"""# Importazione in Sim. Bless

Pacchetto motore: {engine_version}
Revisione sorgente: {revision}

1. Considera `public/python/bless_sim` e `public/python/data` la sorgente canonica.
2. Conserva le funzioni specifiche del simulatore (analisi, campioni e UI) fuori dal motore.
3. Sostituisci le vecchie copie del motore con questi file, senza fondere regole a mano.
4. Esegui tutti i file in `tests/game-engine` prima di aggiornare il sito del simulatore.
5. Verifica che replay e archivi richiedano `engine_version={engine_version}`.
6. Le cartelle `src/app/gioco` e `api/bless_server` sono riferimenti per tavolo e multiplayer;
   non devono sostituire automaticamente la UI o gli strumenti di analisi di Sim. Bless.

Le immagini delle carte non sono duplicate: usa gli asset gia' presenti nel simulatore.
"""

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    archive = OUTPUT_ROOT / f"bless-game-system-{engine_version}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        bundle.writestr("IMPORTA_IN_SIM_BLESS.md", instructions)
        for relative, data in payloads.items():
            bundle.writestr(relative, data)

    print(archive)
    print(f"{len(files)} file, SHA-256 archivio: {_sha256(archive.read_bytes())}")


if __name__ == "__main__":
    main()
