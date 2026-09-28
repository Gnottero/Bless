import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

const sourcePath = (path) => path
  .replace("../app/", "../src/app/")
  .replace("../components/header.tsx", "../src/components/Header.tsx");
const text = (path) => readFile(new URL(sourcePath(path), import.meta.url), "utf8");

test("offers both official decks, multiplayer, Bot and the guided tutorial", async () => {
  const [page, launcher, simulator, header, alias] = await Promise.all([
    text("../app/gioco/page.tsx"),
    text("../src/app/gioco/PlayLauncher.tsx"),
    text("../src/lib/simulator.ts"),
    text("../components/header.tsx"),
    text("../app/play/page.tsx"),
  ]);
  const gameEntry = `${page}\n${launcher}\n${simulator}`;

  assert.match(gameEntry, /Luce-Ombra/);
  assert.match(gameEntry, /TuonoSabbia/);
  assert.match(gameEntry, /Gioca contro il Bot/);
  assert.match(gameEntry, /Invita un giocatore/);
  assert.match(gameEntry, /Gioca il tutorial/);
  assert.match(gameEntry, /Fai una prova guidata/);
  assert.match(gameEntry, /\/gioco\/bot\?tutorial=1&mazzo=Luce-Ombra/);
  assert.match(gameEntry, /Crea link d(?:.invito|&apos;invito)/);
  assert.match(gameEntry, /\/gioco\/bot\?mazzo=/);
  assert.match(gameEntry, /\/gioco\/stanza\//);
  assert.match(header, /href="\/gioco"/);
  assert.match(alias, /redirect\("\/gioco"\)/);
});

test("ships a deterministic guided Luce Ombra match on the real table", async () => {
  const [botPage, manual, styles] = await Promise.all([
    text("../app/gioco/bot/page.tsx"),
    text("../public/python/bless_sim/manual.py"),
    text("../app/gioco/bot/play.css"),
  ]);

  assert.match(botPage, /function TutorialCoach/);
  assert.match(botPage, /TutorialCoach[\s\S]*useDraggablePanel\("tutorial-coach"\)/);
  assert.match(botPage, /tutorial-coach \$\{drag\.panelClassName\}/);
  assert.match(botPage, /<PanelDragHandle handleProps=\{drag\.handleProps\}/);
  assert.match(botPage, /function TutorialIntro/);
  assert.match(botPage, /TUTORIAL_CARD_PARTS/);
  assert.match(botPage, /\/cards\/23\.jpg/);
  assert.match(botPage, /tutorial: override\?\.tutorial/);
  assert.match(botPage, /tutorialLockedUids/);
  assert.match(botPage, /tutorialFocusUids/);
  assert.match(botPage, /tutorialCoachMinimized/);
  assert.match(botPage, /moveLesson/);
  assert.match(botPage, /Turni, Azioni e fine della partita/);
  assert.match(botPage, /quinta carta nel proprio Altare/);
  assert.match(botPage, /tutorial-coach-navigation/);
  assert.match(botPage, /Spiegazione precedente/);
  assert.match(botPage, /Spiegazione successiva/);
  assert.match(botPage, /Invocare un Eco significa usare di nuovo il suo effetto/);
  assert.doesNotMatch(botPage, /Clicca a sinistra per tornare indietro o a destra per avanzare/);
  assert.match(manual, /def _prepare_tutorial_opening/);
  assert.match(manual, /def _tutorial_opponent_action/);
  assert.match(manual, /TUTORIAL_FIRST_CURSE = 23/);
  assert.match(manual, /TUTORIAL_BOND = 25/);
  assert.match(manual, /TUTORIAL_OPPONENT_PRAYER/);
  assert.match(manual, /"Tutorial completato"/);
  assert.match(styles, /\.tutorial-coach/);
  assert.match(styles, /\.tutorial-card-lesson/);
  assert.match(styles, /\.tutorial-coach-minimized/);
  assert.match(styles, /\.play-card\.is-tutorial-focus/);
});

test("ships the complete in-browser Bot engine and both card sets", async () => {
  const [worker, bridge, manual, botPage, cardBack] = await Promise.all([
    text("../public/manual-worker.mjs"),
    text("../public/python/manual_bridge.py"),
    text("../public/python/bless_sim/manual.py"),
    text("../app/gioco/bot/page.tsx"),
    readFile(new URL("../public/cards/back.png", import.meta.url)),
  ]);

  assert.match(worker, /loadPyodide/);
  assert.match(worker, /manual_bridge\.py/);
  assert.match(worker, /bless_sim\/engine\.py/);
  assert.match(bridge, /start_manual_game/);
  assert.match(bridge, /manual_command/);
  assert.match(manual, /class HumanDecisionBot/);
  assert.match(manual, /can_charge_during_mulligan/);
  assert.match(botPage, /Gioca senza conoscere la tua mano/);
  assert.match(botPage, /firstPlayer: "random"/);
  assert.ok(cardBack.byteLength > 1_000);

  await Promise.all(Array.from({ length: 62 }, (_, index) => (
    access(new URL(`../public/cards/${index + 1}.jpg`, import.meta.url))
  )));
  await Promise.all(Array.from({ length: 62 }, (_, index) => (
    access(new URL(`../public/cards/tuono-sabbia/ThunderSand_${String(index + 1).padStart(2, "0")}.png`, import.meta.url))
  )));
});

test("keeps room identity locally and supports invite, polling and reconnection", async () => {
  const [roomApi, roomPage] = await Promise.all([
    text("../app/gioco/room-api.ts"),
    text("../app/gioco/stanza/[code]/page.tsx"),
  ]);

  assert.match(roomApi, /bless-room-/);
  assert.match(roomApi, /window\.localStorage\.setItem/);
  assert.match(roomApi, /Authorization.*Bearer/);
  assert.match(roomApi, /operation: "create"/);
  assert.match(roomApi, /operation: "join"/);
  assert.match(roomApi, /operation: "ready"/);
  assert.match(roomApi, /operation: "rematch"/);
  assert.match(roomPage, /window\.setInterval\([^]*1400\)/);
  assert.match(roomPage, /next\.version === current\.version/);
  assert.match(roomPage, /presenceChanged/);
  assert.match(roomPage, /refreshInFlightRef\.current/);
  assert.match(roomPage, /navigator\.clipboard\.writeText/);
  assert.match(roomPage, /\/gioco\/stanza\/\$\{roomCode\}/);
  assert.match(roomPage, /expected_version/);
  assert.match(roomPage, /deckMismatch/);
  assert.match(roomPage, /Abbandona partita/);
  assert.match(roomPage, /Chiedi la rivincita/);
  assert.match(roomPage, /Connessione interrotta/);
  assert.doesNotMatch(roomPage, /score-side score-side-bot">Bot/);
});

test("enforces an authoritative server and filters private game information", async () => {
  const [api, multiplayer, deployment] = await Promise.all([
    text("../api/game.py"),
    text("../api/bless_server/multiplayer.py"),
    text("../vercel.json"),
  ]);

  assert.match(api, /BLESS_GAME_STATE_SECRET/);
  assert.match(api, /hmac\.compare_digest/);
  assert.match(api, /token_hash/);
  assert.match(api, /decks\[0\].*decks\[1\]/s);
  assert.match(api, /all\(item and item\.get\("ready"\)/);
  assert.match(api, /expected_version/);
  assert.match(api, /def rematch_room/);
  assert.match(api, /MultiplayerGameSession/);
  assert.match(multiplayer, /from api\._engine\.bless_sim\.engine import/);
  assert.match(multiplayer, /def forfeit/);
  assert.match(multiplayer, /hidden = player != viewer/);
  assert.match(multiplayer, /engine\.active_player != viewer/);
  assert.match(multiplayer, /if engine\.game_over.*result\["replay"\]/s);
  assert.match(multiplayer, /request = dict\(self\.pending_request\) if owner == viewer else None/);
  assert.match(deployment, /api\/_engine\/\*\*/);
});

test("keeps ability help above the table and uses a compact victory difference", async () => {
  const [abilityTerm, botPage, roomPage, tableStyles] = await Promise.all([
    text("../app/gioco/ability-term.tsx"),
    text("../app/gioco/bot/page.tsx"),
    text("../app/gioco/stanza/[code]/page.tsx"),
    text("../app/gioco/bot/play.css"),
  ]);

  assert.match(abilityTerm, /createPortal/);
  assert.match(abilityTerm, /getBoundingClientRect/);
  assert.match(abilityTerm, /document\.fullscreenElement \?\? document\.body/);
  assert.match(abilityTerm, /addEventListener\("fullscreenchange", updatePortalTarget\)/);
  assert.match(abilityTerm, /removeEventListener\("fullscreenchange", updatePortalTarget\)/);
  assert.match(botPage, /<AbilityTerm/);
  assert.match(roomPage, /<AbilityTerm/);
  assert.match(tableStyles, /\.ability-tooltip[^}]*position:\s*fixed/s);
  for (const page of [botPage, roomPage]) {
    assert.match(page, /className="score-marker"[^]*Math\.abs\(difference\)/);
    assert.doesNotMatch(page, /score-side score-side-(?:bot|human)/);
    assert.match(page, /className="score-track"/);
  }
  assert.match(tableStyles, /\.score-meter \.score-marker\s*{[^}]*border-radius:\s*50%/s);
  assert.match(tableStyles, /\.score-meter \.score-track\s*{[^}]*position:\s*absolute[^}]*top:\s*22px[^}]*bottom:\s*22px/s);
});

test("uses one unified table surface and keeps resources in their game zones", async () => {
  const [botPage, roomPage, tableStyles] = await Promise.all([
    text("../app/gioco/bot/page.tsx"),
    text("../app/gioco/stanza/[code]/page.tsx"),
    text("../app/gioco/bot/play.css"),
  ]);

  for (const page of [botPage, roomPage]) {
    assert.match(page, /className="table-brand"/);
    assert.match(page, /<AltarDisplay count=\{player\.altar_count\}/);
    assert.doesNotMatch(page, /opponent-charge-count/);
    assert.match(page, /card\.uid === firstGlyphUid/);
    assert.match(page, /kind === "prayer" && card\.open != null/);
    assert.match(page, /card\.zone === "maledizione"/);
    assert.match(page, /ordered[^]*onInspect=\{previewCard\}/);
  }
  assert.match(tableStyles, /grid-template-columns:\s*repeat\(var\(--hand-count\)/);
  assert.match(tableStyles, /\.battle-board\s*{[^}]*border:\s*0[^}]*box-shadow:\s*none/s);
  assert.match(tableStyles, /\.bot-field \.prayer-zone\s*{[^}]*grid-row:\s*1/s);
  assert.match(tableStyles, /\.bot-field \.malediction-zone\s*{[^}]*grid-row:\s*2/s);
  assert.match(tableStyles, /\.zone-list-position b/);
});

test("pins inspected cards and explains stats, prayer types and transferred Bonds", async () => {
  const [botPage, roomPage, tableStyles] = await Promise.all([
    text("../src/app/gioco/bot/page.tsx"),
    text("../src/app/gioco/stanza/[code]/page.tsx"),
    text("../src/app/gioco/bot/play.css"),
  ]);

  for (const page of [botPage, roomPage]) {
    assert.match(page, /inspectorLockedUid/);
    assert.match(page, /const previewCard/);
    assert.match(page, /const pinCard/);
    assert.match(page, /name="Occhio"/);
    assert.match(page, /name="Karma"/);
    assert.match(page, /PRAYER_TYPE_HELP/);
    assert.match(page, /Effetto Preghiera trasferito/);
    assert.match(page, /card\.attached_to === inspectedLive\.uid/);
  }
  assert.match(tableStyles, /\.inspector-lock-button/);
  assert.match(tableStyles, /\.linked-prayer-effect/);
  assert.match(tableStyles, /\.side-hand-section \.modern-hand[^}]*min-height:\s*210px/s);
});

test("uses a real pointer-driven card drag and keeps the Void readable and playable", async () => {
  const [botPage, roomPage, cardDrag, engine, tableStyles] = await Promise.all([
    text("../app/gioco/bot/page.tsx"),
    text("../app/gioco/stanza/[code]/page.tsx"),
    text("../app/gioco/card-drag.tsx"),
    text("../public/python/bless_sim/engine.py"),
    text("../app/gioco/bot/play.css"),
  ]);

  for (const page of [botPage, roomPage]) {
    assert.match(page, /useCardDrag\(handleDrop/);
    assert.match(page, /dragProps=\{cardDrag\.bindCard/);
    assert.match(page, /data-card-drop-mode=\{isHuman/);
    assert.doesNotMatch(page, /DragEvent|dataTransfer/);
    assert.match(page, /className="zone-dialog-reader"/);
    assert.match(page, /className="zone-list-play"/);
    assert.match(page, /onPlay=\{\(card\) =>/);
  }
  assert.match(cardDrag, /setPointerCapture/);
  assert.match(cardDrag, /cloneNode\(true\)/);
  assert.match(cardDrag, /document\.elementFromPoint/);
  assert.match(cardDrag, /onPointerCancel/);
  assert.match(cardDrag, /CardDragAccessibility/);
  assert.match(engine, /playable_from_void/);
  assert.match(engine, /dalla cima del Vuoto/);
  assert.match(tableStyles, /\.card-drag-ghost\s*{[^}]*position:\s*fixed[^}]*z-index:\s*10000/s);
  assert.match(tableStyles, /\.zone-dialog-content\.is-ordered/);
  assert.match(tableStyles, /overflow-wrap:\s*anywhere/);
});

test("keeps corrupted marked cards compact and uses Boato's removed-mark choice", async () => {
  const [manual, engine, tableStyles] = await Promise.all([
    text("../public/python/bless_sim/manual.py"),
    text("../public/python/bless_sim/engine.py"),
    text("../app/gioco/bot/play.css"),
  ]);

  assert.match(manual, /non viene scartata nel Vuoto/);
  assert.match(manual, /take_removed_mark/);
  assert.match(engine, /taken_by.*Boato del Marchio/s);
  assert.match(tableStyles, /\.play-card\.is-corrupted\.card-malediction\s*{[^}]*1\.14[^}]*\.82/s);
  assert.match(tableStyles, /\.play-card\.is-corrupted\.is-marked \.card-mark-back\s*{[^}]*68%/s);
});

test("stages Impulses, supports movable choices and ships the mobile themed table", async () => {
  const [botPage, roomPage, sharedUi, engine, manual, multiplayer, tableStyles] = await Promise.all([
    text("../app/gioco/bot/page.tsx"),
    text("../app/gioco/stanza/[code]/page.tsx"),
    text("../app/gioco/table-ui.tsx"),
    text("../public/python/bless_sim/engine.py"),
    text("../public/python/bless_sim/manual.py"),
    text("../api/bless_server/multiplayer.py"),
    text("../app/gioco/bot/play.css"),
  ]);

  for (const page of [botPage, roomPage]) {
    assert.match(page, /last_impulse: ImpulseStageEvent<GameCard>/);
    assert.match(page, /<ImpulseStage/);
    assert.match(page, /useDraggablePanel/);
    assert.match(page, /turn-control-stack/);
    assert.match(page, /deck-thunder-sand/);
  }
  assert.match(sharedUi, /setPointerCapture/);
  assert.match(sharedUi, /Sposta questa finestra/);
  assert.match(engine, /self\.last_impulse/);
  assert.match(manual, /engine\.is_thunder_sand and definition_id == 29/);
  assert.match(multiplayer, /"last_impulse": last_impulse/);
  assert.match(tableStyles, /\.deck-thunder-sand \.battle-board/);
  assert.match(tableStyles, /@media \(max-width: 760px\)[^]*\.side-hand-section \.modern-hand[^]*repeat\(var\(--hand-count\)/);
  assert.match(tableStyles, /@keyframes impulse-resolve/);
});

test("ships flat inspectable zones and a landscape-only phone table", async () => {
  const [botPage, roomPage, sharedUi, tableStyles] = await Promise.all([
    text("../app/gioco/bot/page.tsx"),
    text("../app/gioco/stanza/[code]/page.tsx"),
    text("../app/gioco/table-ui.tsx"),
    text("../app/gioco/bot/play.css"),
  ]);

  for (const page of [botPage, roomPage]) {
    assert.match(page, /<InspectCue label="Guarda"/);
    assert.match(page, /<OrientationGate \/>/);
    assert.match(page, /compact-log-summary/);
    assert.match(page, /className="table-effects-layer"/);
  }
  assert.match(sharedUi, /className="inspect-cue"/);
  assert.match(sharedUi, /Il tavolo di Bless si gioca in orizzontale/);
  assert.match(tableStyles, /\.right-rail > \.card-inspector,[^}]*border:\s*0/s);
  assert.match(tableStyles, /@media \(max-width: 760px\) and \(orientation: portrait\)[^]*\.orientation-gate[^]*position:\s*fixed/s);
  assert.match(tableStyles, /@media \(max-height: 520px\) and \(orientation: landscape\)[^]*\.manual-table[^]*height:\s*100svh/s);
  assert.match(tableStyles, /@media \(max-height: 520px\) and \(orientation: landscape\)[^]*\.manual-table \.battle-board\s*{[^}]*64px/s);
  assert.match(tableStyles, /\.void-rail-panel\s*{[^}]*translateX\(-27px\)/s);
  assert.match(tableStyles, /\.table-effects-layer\s*{[^}]*z-index:\s*120/s);
});

test("keeps replay data available internally without exposing downloads in the game UI", async () => {
  const [savedReplays, gameHome, botPage, roomPage, replay, manualWorker, documentation] = await Promise.all([
    text("../app/saved-replays.ts"),
    text("../src/app/gioco/PlayLauncher.tsx"),
    text("../src/app/gioco/bot/page.tsx"),
    text("../src/app/gioco/stanza/[code]/page.tsx"),
    text("../public/python/bless_sim/replay.py"),
    text("../public/manual-worker.mjs"),
    text("../docs/sync-engine-and-replays.md"),
  ]);

  assert.match(savedReplays, /bless\.replay\.archive/);
  assert.match(savedReplays, /downloadSavedReplayArchive/);
  assert.match(savedReplays, /bless-partite-/);
  for (const page of [gameHome, botPage, roomPage]) {
    assert.doesNotMatch(page, /Scarica dati per Sim\. Bless/);
  }
  assert.match(replay, /engine_version/);
  assert.match(manualWorker, /bless_sim\/version\.py/);
  assert.match(documentation, /Bless-cardgame\/Bless-core/);
});
