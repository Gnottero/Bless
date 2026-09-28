import type { PrayerType } from "@/data/cards";

/**
 * Icon for each Prayer type: a spark for Impulso (one-off), a wave for Eco
 * (repeats), a chain link for Legame (ties two cards together).
 * Decorative only, the type name is always next to it.
 */
export default function PrayerTypeIcon({
  type,
  size = 22,
}: {
  type: PrayerType;
  size?: number;
}) {
  const common = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.6,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true as const,
    focusable: "false" as const,
  };

  if (type === "Impulso") {
    return (
      <svg {...common}>
        <path d="M13 2 4.5 13.5H11l-1 8.5 9-11.5h-6.5L13 2Z" />
      </svg>
    );
  }

  if (type === "Eco") {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="2.2" />
        <path d="M7.4 7.4a6.5 6.5 0 0 0 0 9.2M16.6 16.6a6.5 6.5 0 0 0 0-9.2" />
        <path d="M4.2 4.2a11 11 0 0 0 0 15.6M19.8 19.8a11 11 0 0 0 0-15.6" opacity="0.5" />
      </svg>
    );
  }

  return (
    <svg {...common}>
      <path d="M9.5 14.5 7 17a3.5 3.5 0 0 1-5-5l2.5-2.5a3.5 3.5 0 0 1 5 0" />
      <path d="M14.5 9.5 17 7a3.5 3.5 0 0 1 5 5l-2.5 2.5a3.5 3.5 0 0 1-5 0" />
      <path d="m9.8 14.2 4.4-4.4" />
    </svg>
  );
}
