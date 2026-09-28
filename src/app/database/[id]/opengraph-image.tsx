import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { ImageResponse } from "next/og";
import sharp from "sharp";
import { CARDS, CARD_HEIGHT, CARD_WIDTH, FORM_THEME, cardById, cardImage } from "@/data/cards";
import { OG_IMAGE, SITE } from "@/lib/site";

/*
 * 1200x630 social preview for each card. Just using the card image didn't
 * work, it's portrait and X/Facebook/WhatsApp cropped it into a thin strip.
 * So the full card goes on the left over its Form colour, with the name and
 * stats next to it.
 *
 * `next/og` can't read WebP, so the artwork goes through sharp first. We
 * also use sharp to turn the final PNG into a JPEG, about 5x smaller.
 *
 * Font is EB Garamond like the rest of the site, but `next/og` needs static
 * TTFs (not the variable WOFF2 from `next/font`), hence `src/fonts/`.
 */

export const alt = `Carta di ${SITE.name}`;
export const size = { width: OG_IMAGE.width, height: OG_IMAGE.height };
export const contentType = "image/jpeg";

export function generateStaticParams() {
  return CARDS.map((c) => ({ id: String(c.id) }));
}

/** Card height in the image. Width is derived from the aspect ratio. */
const IMG_CARD_HEIGHT = 540;
const IMG_CARD_WIDTH = Math.round((IMG_CARD_HEIGHT * CARD_WIDTH) / CARD_HEIGHT);

const readFont = (file: string) => readFile(join(process.cwd(), "src/fonts", file));

export default async function CardPreview({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const card = cardById(Number(id));
  if (!card) throw new Error(`Card ${id} does not exist`);
  const theme = FORM_THEME[card.form];

  const illustration = await sharp(join(process.cwd(), "public", cardImage(card.id)))
    .resize({ height: IMG_CARD_HEIGHT * 2 })
    .jpeg({ quality: 88 })
    .toBuffer();

  const [regular, semibold] = await Promise.all([
    readFont("EBGaramond-Regular.ttf"),
    readFont("EBGaramond-SemiBold.ttf"),
  ]);

  const png = new ImageResponse(
    (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          width: "100%",
          height: "100%",
          padding: "0 72px 0 64px",
          background: theme.background,
          color: theme.text,
          fontFamily: "Garamond",
          border: `12px solid ${theme.line}`,
        }}
      >
        <img
          src={`data:image/jpeg;base64,${illustration.toString("base64")}`}
          width={IMG_CARD_WIDTH}
          height={IMG_CARD_HEIGHT}
          style={{ borderRadius: 18, boxShadow: `0 16px 40px ${theme.text}55` }}
        />

        <div style={{ display: "flex", flexDirection: "column", marginLeft: 64, flex: 1 }}>
          <div
            style={{
              fontSize: 27,
              letterSpacing: "0.18em",
              textTransform: "uppercase",
              color: theme.accent,
            }}
          >
            {`Forma ${card.form} · ${String(card.id).padStart(2, "0")} / ${CARDS.length}`}
          </div>

          <div style={{ fontSize: 88, fontWeight: 600, lineHeight: 1, marginTop: 14 }}>
            {card.name}
          </div>

          <div style={{ display: "flex", gap: 20, marginTop: 36 }}>
            {[
              ["Occhio", card.eye],
              ["Karma", card.karma],
            ].map(([label, value]) => (
              <div
                key={label}
                style={{
                  display: "flex",
                  alignItems: "baseline",
                  gap: 12,
                  padding: "10px 22px",
                  border: `3px solid ${theme.line}`,
                  borderRadius: 999,
                  fontSize: 32,
                }}
              >
                <span style={{ fontSize: 50, fontWeight: 600, color: theme.accent }}>{value}</span>
                {label}
              </div>
            ))}
          </div>

          <div style={{ fontSize: 30, marginTop: 56, opacity: 0.75 }}>
            {`${SITE.name} · ${new URL(SITE.url).host}`}
          </div>
        </div>
      </div>
    ),
    {
      ...size,
      fonts: [
        { name: "Garamond", data: regular, weight: 400, style: "normal" },
        { name: "Garamond", data: semibold, weight: 600, style: "normal" },
      ],
    },
  );

  const jpeg = await sharp(Buffer.from(await png.arrayBuffer()))
    .jpeg({ quality: 85, mozjpeg: true })
    .toBuffer();

  return new Response(new Uint8Array(jpeg), {
    headers: { "Content-Type": contentType },
  });
}
