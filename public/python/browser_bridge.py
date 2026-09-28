from __future__ import annotations

import base64
import json
import pickle
import tempfile
from pathlib import Path

from bless_sim.simulation import (
    SimulationConfig,
    _aggregate,
    _jobs,
    _play_job,
    _play_replay_job,
    export_report_bundle,
)

try:
    from js import reportProgress  # type: ignore[import-not-found]
except ImportError:  # Permette di verificare il ponte anche con Python nativo.
    reportProgress = None


def _config(raw: str) -> SimulationConfig:
    payload = json.loads(raw)
    config = SimulationConfig(**payload)
    config.validate()
    return config


def run_chunk(config_json: str, start: int, stop: int, worker_id: int) -> str:
    """Gioca una porzione deterministica del campione e la rende trasferibile."""
    config = _config(config_json)
    jobs = _jobs(config)
    start = max(0, int(start))
    stop = min(len(jobs), int(stop))
    total = max(0, stop - start)
    notify_every = max(1, total // 100)
    indexed_results = []

    for completed, index in enumerate(range(start, stop), start=1):
        result = _play_replay_job(jobs[index]) if index == 0 else _play_job(jobs[index])
        indexed_results.append((index, result))
        if reportProgress is not None and (completed == total or completed % notify_every == 0):
            reportProgress(int(worker_id), completed, total)

    encoded = pickle.dumps(indexed_results, protocol=pickle.HIGHEST_PROTOCOL)
    return base64.b64encode(encoded).decode("ascii")


def aggregate_chunks(config_json: str, chunks_json: str) -> str:
    """Riunisce i risultati, crea il report e prepara lo ZIP scaricabile."""
    config = _config(config_json)
    indexed_results = []
    for encoded in json.loads(chunks_json):
        indexed_results.extend(pickle.loads(base64.b64decode(encoded)))

    indexed_results.sort(key=lambda item: item[0])
    if len(indexed_results) != config.games:
        raise RuntimeError(
            f"Campione incompleto: {len(indexed_results)} risultati su {config.games}."
        )

    report = _aggregate(config, [result for _, result in indexed_results])
    export_dir = Path(tempfile.gettempdir()) / "bless_exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    bundle = export_report_bundle(report, export_dir)
    bundle_base64 = base64.b64encode(bundle.read_bytes()).decode("ascii")

    return json.dumps(
        {
            "report": report.to_dict(),
            "bundle_base64": bundle_base64,
            "bundle_name": bundle.name,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
