import fs from "node:fs";
import path from "node:path";
import xlsx from "xlsx";

const INPUT = process.argv[2] || "data/cards.xlsx";
const OUTPUT = process.argv[3] || "src/data/cards.ts";
const DEFAULT_DECK = "Bless";

function norm(s) {
  return String(s ?? "")
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, "");
}

function slugify(s) {
  return (
    String(s ?? "")
      .trim()
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/(^-|-$)/g, "") || "carta"
  );
}

function toInt(v, fallback = 0) {
  if (v === null || v === undefined || v === "") return fallback;
  const n = Number(v);
  return Number.isFinite(n) ? Math.trunc(n) : fallback;
}

const MAP = {
  id: "id",
  name: "name",
  sight: "sight",
  karma: "karma",
  form: "form",
  effcurse: "effCurse",
  gracetype: "effType",
  effgrace: "effGrace",
};

console.log("🔎 INPUT =", INPUT);
console.log("📝 OUTPUT =", OUTPUT);

try {
  // controlli file
  if (!fs.existsSync(INPUT)) {
    throw new Error(`File Excel non trovato: ${INPUT}`);
  }

  const wb = xlsx.readFile(INPUT);
  console.log("📄 Sheets:", wb.SheetNames);

  const ws = wb.Sheets[wb.SheetNames[0]];
  const rows = xlsx.utils.sheet_to_json(ws, { defval: "" });
  console.log("📦 Righe lette:", rows.length);

  const cards = rows
    .map((row) => {
      const rec = {};
      for (const [k, v] of Object.entries(row)) {
        const key = MAP[norm(k)] || norm(k);
        rec[key] = v;
      }

      const id = toInt(rec.id, 0);
      if (!id) return null;

      const name = String(rec.name ?? "").trim();

      return {
        id,
        slug: slugify(name),
        name,
        deck: DEFAULT_DECK,
        form: String(rec.form ?? "").trim(),
        sight: toInt(rec.sight, 0),
        karma: toInt(rec.karma, 0),
        effCurse: String(rec.effCurse ?? "").trim(),
        effType: String(rec.effType ?? "").trim(),
        effGrace: String(rec.effGrace ?? "").trim(),
      };
    })
    .filter(Boolean)
    .sort((a, b) => a.id - b.id);

  const out = `// AUTO-GENERATO da ${path.basename(INPUT)}. Non modificare a mano.
// Rigenera con: node scripts/gen_cards_ts.mjs ${INPUT}

export type Card = {
  id: number;
  slug: string;
  name: string;
  deck: string;
  form: string;
  sight: number;
  karma: number;
  effCurse: string;
  effType: string;
  effGrace: string;
};

export const cards: Card[] = ${JSON.stringify(cards, null, 2)};

export function getCardById(id: number): Card | undefined {
  return cards.find((c) => c.id === id);
}

export function getCardBySlug(slug: string): Card | undefined {
  return cards.find((c) => c.slug === slug);
}
`;

  fs.mkdirSync(path.dirname(OUTPUT), { recursive: true });
  fs.writeFileSync(OUTPUT, out, "utf8");

  console.log(`✅ Creato ${OUTPUT} con ${cards.length} carte`);
} catch (err) {
  console.error("❌ Errore:", err);
  process.exit(1);
}
