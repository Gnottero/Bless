import type { Form } from "@/data/cards";

/**
 * Form symbol, traced from the one at the bottom of the cards:
 *
 *  - Luce:  eight-pointed sun with a ring in the middle
 *  - Ombra: crescent moon facing up-left, with two sparkles
 *  - Duale: the same crescent with the sun inside it (one symbol, not two
 *           next to each other)
 *
 * Purely decorative, the Form name is always shown next to it.
 */
export default function FormEmblem({
  form,
  size = 24,
}: {
  form: Form;
  size?: number;
}) {
  const common = {
    width: size,
    height: size,
    viewBox: "0 0 32 32",
    "aria-hidden": true as const,
    focusable: "false" as const,
  };

  /* Eight-pointed sun, with a ring and a filled dot in the middle. */
  const sun = (cx: number, cy: number, r: number) => {
    const points: string[] = [];
    for (let k = 0; k < 16; k += 1) {
      const a = ((-90 + k * 22.5) * Math.PI) / 180;
      const rr = k % 2 === 0 ? r : r * 0.44;
      points.push(
        `${(cx + rr * Math.cos(a)).toFixed(2)} ${(cy + rr * Math.sin(a)).toFixed(2)}`,
      );
    }
    return (
      <>
        <path d={`M${points.join("L")}Z`} fill="currentColor" />
        <circle
          cx={cx}
          cy={cy}
          r={r * 0.3}
          fill="var(--emblem-paper, #fbf5e7)"
        />
        <circle cx={cx} cy={cy} r={r * 0.15} fill="currentColor" />
      </>
    );
  };

  /* Crescent: a circle with another circle cut out of the top left, so the
     tips point the same way as on the cards. */
  const crescent = (cx: number, cy: number, r: number, id: string) => (
    <>
      <mask id={id}>
        <rect x="0" y="0" width="32" height="32" fill="#000" />
        <circle cx={cx} cy={cy} r={r} fill="#fff" />
        <circle
          cx={cx - r * 0.42}
          cy={cy - r * 0.34}
          r={r * 0.86}
          fill="#000"
        />
      </mask>
      <circle cx={cx} cy={cy} r={r} fill="currentColor" mask={`url(#${id})`} />
    </>
  );

  /* Four-pointed sparkle with curved-in sides. */
  const sparkle = (cx: number, cy: number, r: number) => {
    const m = r * 0.16;
    return (
      <path
        d={[
          `M${cx} ${cy - r}`,
          `Q${cx + m} ${cy - m} ${cx + r} ${cy}`,
          `Q${cx + m} ${cy + m} ${cx} ${cy + r}`,
          `Q${cx - m} ${cy + m} ${cx - r} ${cy}`,
          `Q${cx - m} ${cy - m} ${cx} ${cy - r}`,
          "Z",
        ].join("")}
        fill="currentColor"
      />
    );
  };

  if (form === "Luce") {
    return <svg {...common}>{sun(16, 16, 13.5)}</svg>;
  }

  if (form === "Ombra") {
    return (
      <svg {...common}>
        {crescent(18.5, 16.5, 11.5, "bless-crescent-shadow")}
        {sparkle(9, 17.5, 6.2)}
        {sparkle(14, 7, 3.6)}
      </svg>
    );
  }

  return (
    <svg {...common}>
      {crescent(19.5, 17, 11, "bless-crescent-dual")}
      {sun(12.2, 12.8, 8.2)}
    </svg>
  );
}
