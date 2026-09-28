import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import vm from "node:vm";
import test from "node:test";
import ts from "typescript";

const sourcePath = (path) => path.replace("../app/", "../src/app/");

async function loadModule(path, globals = {}) {
  const source = await readFile(new URL(sourcePath(path), import.meta.url), "utf8");
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  });
  const context = vm.createContext({ exports: {}, process: { env: {} }, Headers,
    AbortController, setTimeout, clearTimeout, ...globals });
  vm.runInContext(outputText, context, { filename: path });
  return context.exports;
}

const room = () => ({ code: "ABC123", status: "waiting", version: 1,
  player_slot: 0, agreed_deck: null,
  players: [{ slot: 0, name: "Test", ready: false, connected: true, deck: null, rematch: false }, null] });
const blocked = () => { throw new Error("SecurityError"); };

test("replay reading tolerates denied storage and corrupted saved data", async () => {
  const saved = await loadModule("../app/saved-replays.ts", {
    window: { get localStorage() { return blocked(); } },
  });
  assert.equal(saved.readSavedReplays().length, 0);
  for (const raw of ["{broken", "null", "{}", "[null,1,{}]"]) {
    assert.equal(saved.parseSavedReplays(raw).length, 0);
  }
  const record = { id: "one", saved_at: "today", title: "Test", replay: { actions: [] } };
  assert.equal(saved.parseSavedReplays(JSON.stringify([record]))[0].id, "one");
});

test("room access falls back to session storage without crashing on denied reads", async () => {
  const memory = new Map();
  const api = await loadModule("../app/gioco/room-api.ts", { window: {
    get localStorage() { return blocked(); },
    sessionStorage: { setItem: (key, value) => memory.set(key, value), getItem: (key) => memory.get(key) ?? null },
  } });
  api.rememberRoomAccess("abc123", "test-token");
  assert.equal(api.readRoomAccess("ABC123"), "test-token");
  const denied = await loadModule("../app/gioco/room-api.ts", { window: {
    get localStorage() { return blocked(); }, get sessionStorage() { return blocked(); },
  } });
  assert.equal(denied.readRoomAccess("ABC123"), null);
  assert.throws(() => denied.rememberRoomAccess("ABC123", "test-token"), /Abilita la memoria/);
});

test("online API rejects invalid successful responses instead of corrupting the table", async () => {
  for (const payload of [null, {}, [], { ...room(), players: null }, { ...room(), players: [{}] },
    { code: "ABC123", room: room() }, { code: "DIFFERENT", token: "test-token", room: room() }]) {
    const api = await loadModule("../app/gioco/room-api.ts", {
      fetch: async () => ({ ok: true, json: async () => payload }),
    });
    await assert.rejects(api.getRoom("ABC123", "test-token"), /Risposta della stanza non valida/);
  }
  const api = await loadModule("../app/gioco/room-api.ts", {
    fetch: async () => ({ ok: true, json: async () => { throw new SyntaxError("HTML instead of JSON"); } }),
  });
  await assert.rejects(api.getRoom("ABC123", "test-token"), /Risposta della stanza non valida/);
});

test("online API preserves authorization and accepts valid room and access responses", async () => {
  let calls = 0;
  const api = await loadModule("../app/gioco/room-api.ts", { fetch: async (_url, init) => {
    calls += 1;
    if (calls === 1) {
      assert.equal(init.headers.get("Authorization"), "Bearer test-token");
      return { ok: true, json: async () => room() };
    }
    return { ok: true, json: async () => ({ code: "ABC123", token: "new-token", room: room() }) };
  } });
  assert.equal((await api.getRoom("ABC123", "test-token")).code, "ABC123");
  assert.equal((await api.createRoom("Test")).token, "new-token");
});

test("a hung request times out, frees its timer and never repeats a game command", async () => {
  let expire;
  let calls = 0;
  let cleared = 0;
  const api = await loadModule("../app/gioco/room-api.ts", {
    setTimeout: (callback, delay) => { assert.equal(delay, 35000); expire = callback; return 1; },
    clearTimeout: () => { cleared += 1; },
    fetch: (_url, init) => new Promise((_resolve, reject) => {
      calls += 1;
      init.signal.addEventListener("abort", () => reject(new Error("aborted")));
    }),
  });
  const pending = api.sendRoomCommand("ABC123", "test-token", { type: "action" });
  expire();
  await assert.rejects(pending, /La stanza non risponde/);
  assert.equal(calls, 1);
  assert.equal(cleared, 1);
});

test("server error messages remain readable and request timers are cleaned up", async () => {
  let cleared = 0;
  const api = await loadModule("../app/gioco/room-api.ts", {
    setTimeout: () => 1, clearTimeout: () => { cleared += 1; },
    fetch: async () => ({ ok: false, json: async () => ({ error: "Stanza scaduta" }) }),
  });
  await assert.rejects(api.getRoom("ABC123", "test-token"), /Stanza scaduta/);
  assert.equal(cleared, 1);
});

test("the game worker serializes rapid commands and continues after a command failure", async () => {
  const source = (await readFile(new URL("../public/manual-worker.mjs", import.meta.url), "utf8"))
    .replace(/^import .*loadPyodide.*;\r?\n/, "");
  const globals = new Map();
  const output = [];
  const executed = [];
  let active = 0;
  let maxActive = 0;
  const runtime = { FS: { mkdirTree() {}, writeFile() {} }, runPython() {},
    globals: { set: (key, value) => globals.set(key, value) },
    async runPythonAsync() {
      active += 1;
      maxActive = Math.max(maxActive, active);
      try {
        await new Promise((resolve) => setTimeout(resolve, 5));
        const command = JSON.parse(globals.get("manual_command_json"));
        executed.push(command.type);
        if (command.type === "invalid") throw new Error("Test command rejected");
        return JSON.stringify({ command: command.type });
      } finally { active -= 1; }
    },
  };
  const context = vm.createContext({
    loadPyodide: async () => runtime,
    fetch: async () => ({ ok: true, text: async () => "# test source" }),
    self: { postMessage: (message) => output.push(message) },
  });
  vm.runInContext(source, context);
  for (const type of ["first", "invalid", "last"]) context.self.onmessage({ data: { type } });
  await vm.runInContext("commandQueue", context);
  assert.equal(maxActive, 1);
  assert.deepEqual(executed, ["first", "invalid", "last"]);
  assert.deepEqual(output.map((message) => message.type), ["state", "error", "state"]);
});

test("card drag uses the fullscreen layer and cancels cleanly on fullscreen changes", async () => {
  const source = await readFile(new URL(sourcePath("../app/gioco/card-drag.tsx"), import.meta.url), "utf8");
  assert.match(source, /\(document\.fullscreenElement \?\? document\.body\)\.appendChild\(ghost\)/);
  assert.match(source, /addEventListener\("fullscreenchange", onWindowInterruption\)/);
  assert.match(source, /removeEventListener\("fullscreenchange", onWindowInterruption\)/);
});
