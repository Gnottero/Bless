import { loadPyodide } from "https://cdn.jsdelivr.net/pyodide/v314.0.2/full/pyodide.mjs";

const PYODIDE_INDEX = "https://cdn.jsdelivr.net/pyodide/v314.0.2/full/";
const ROOT = "/bless_manual";
const SOURCE_FILES = [
  "bless_sim/__init__.py",
  "bless_sim/model.py",
  "bless_sim/cards.py",
  "bless_sim/bots.py",
  "bless_sim/engine.py",
  "bless_sim/version.py",
  "bless_sim/replay.py",
  "bless_sim/manual.py",
  "data/luce_ombra.json",
  "data/tuono_sabbia.json",
  "manual_bridge.py",
];

let runtimePromise;

async function prepareRuntime() {
  if (!runtimePromise) {
    runtimePromise = (async () => {
      const runtime = await loadPyodide({ indexURL: PYODIDE_INDEX });
      runtime.FS.mkdirTree(`${ROOT}/bless_sim`);
      runtime.FS.mkdirTree(`${ROOT}/data`);
      await Promise.all(
        SOURCE_FILES.map(async (relativePath) => {
          const response = await fetch(`/python/${relativePath}`);
          if (!response.ok) throw new Error(`Risorsa di gioco non disponibile: ${relativePath}`);
          runtime.FS.writeFile(`${ROOT}/${relativePath}`, await response.text(), { encoding: "utf8" });
        }),
      );
      runtime.runPython(`
import os
import sys
os.chdir("${ROOT}")
if "${ROOT}" not in sys.path:
    sys.path.insert(0, "${ROOT}")
from manual_bridge import manual_command, start_manual_game
`);
      return runtime;
    })();
  }
  return runtimePromise;
}

function asString(value) {
  const result = String(value);
  if (value && typeof value.destroy === "function") value.destroy();
  return result;
}

async function handleMessage(message) {
  try {
    const runtime = await prepareRuntime();
    if (message.type === "init") {
      self.postMessage({ type: "ready" });
      return;
    }
    let output;
    if (message.type === "start") {
      runtime.globals.set("manual_config_json", JSON.stringify(message.config));
      output = await runtime.runPythonAsync("start_manual_game(manual_config_json)");
    } else {
      runtime.globals.set("manual_command_json", JSON.stringify(message));
      output = await runtime.runPythonAsync("manual_command(manual_command_json)");
    }
    self.postMessage({ type: "state", payload: asString(output) });
  } catch (error) {
    self.postMessage({
      type: "error",
      message: error instanceof Error ? error.message : String(error),
      details: error instanceof Error ? error.stack : "",
    });
  }
}

// Pyodide condivide i globali Python: due comandi concorrenti potrebbero
// sovrascriversi mentre runPythonAsync e' in attesa.
let commandQueue = Promise.resolve();
self.onmessage = (event) => {
  commandQueue = commandQueue.then(() => handleMessage(event.data));
};
