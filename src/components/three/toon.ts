/*
 * Toon shader for the 3D card: cel shading in a few hard bands plus an
 * ink outline.
 *
 * We don't use any of three's built-in materials. Lighting is done by hand
 * and snapped to a handful of bands so it looks drawn rather than rendered.
 * Each Form gets its own theme: Luce is lit from above and calm, Ombra is
 * lit from below and a bit creepy, Duale is somewhere in between.
 *
 * Light never tints the artwork, it only makes it brighter or darker. The
 * colour comes from the foil, which shifts as the card turns and looks
 * different for each Form.
 */

import type { Form } from "@/data/cards";

/** Where the light comes from and how strong the light/shade bands are. */
export type SideTheme = {
  /** Multiplier for the brightest band. 1 leaves the artwork as is. */
  light: number;
  /** Multiplier for the darkest band. Only scales brightness, never hue. */
  shade: number;
  /** Light direction, in world space. */
  dir: [number, number, number];
};

/** Holographic foil settings. */
export type FoilTheme = {
  /** Overall foil intensity. 0 turns it off. */
  strength: number;
  /** How tightly the rainbow repeats across the card. */
  scale: number;
  /** Higher = thinner shiny stripe. */
  band: number;
  /** Hue offset for the rainbow. */
  spectrum: number;
  /** Number of steps. Low looks like printed foil, high looks liquid. */
  steps: number;
};

export type ToonTheme = {
  side: SideTheme;
  /** Number of shading bands. Fewer = harsher. */
  bands: number;
  foil: FoilTheme;
  /** Rim light colour and strength. */
  rim: string;
  rimStrength: number;
  /** Ink outline: colour, width, and how much it wobbles. */
  ink: string;
  thickness: number;
  tremor: number;
  /** Fallback colour for the back until the texture loads. */
  back: string;
  /** How much the artwork ripples. 0 = not at all, 1 = full Ombra weirdness. */
  grotesque: number;
  /** Idle sway settings. */
  motion: { amplitude: number; speed: number; jitter: number };
};

const LIGHT_SIDE: SideTheme = {
  light: 1.1,
  shade: 0.72,
  dir: [-0.38, 0.86, 0.62],
};

const DUAL_SIDE: SideTheme = {
  // Warm light, almost head-on, with slightly harsher bands.
  light: 1.12,
  shade: 0.66,
  dir: [-0.18, 0.5, 0.85],
};

const SHADOW_SIDE: SideTheme = {
  // Lit from below, like holding a torch under your chin.
  light: 1.16,
  // Don't go too dark, the artwork still has to be readable in shadow.
  shade: 0.55,
  dir: [0.46, -0.72, 0.52],
};

export const THEMES: Record<Form, ToonTheme> = {
  Luce: {
    side: LIGHT_SIDE,
    bands: 4,
    // Gold-ish foil: wide, slow, few steps.
    foil: { strength: 0.5, scale: 1.5, band: 0.46, spectrum: 0.08, steps: 4 },
    // Keep the rim soft here: the page behind is already light and a
    // strong glow would wash out the outline.
    rim: "#ffe9a8",
    rimStrength: 0.4,
    ink: "#2a1e12",
    thickness: 1.05,
    tremor: 0,
    back: "#efdfb0",
    grotesque: 0,
    motion: { amplitude: 1, speed: 0.62, jitter: 0 },
  },
  Ombra: {
    side: SHADOW_SIDE,
    bands: 3,
    // Cold and twitchy: thin stripes, dense rainbow, hard steps.
    foil: { strength: 0.62, scale: 3.4, band: 0.68, spectrum: 0.62, steps: 3 },
    rim: "#b9a4e8",
    rimStrength: 0.5,
    ink: "#07050b",
    thickness: 2.15,
    tremor: 0.65,
    back: "#241a33",
    grotesque: 1,
    motion: { amplitude: 1.35, speed: 0.95, jitter: 1 },
  },
  Duale: {
    side: DUAL_SIDE,
    bands: 3.5,
    // Middle ground: full rainbow, medium stripe.
    foil: { strength: 0.56, scale: 2.3, band: 0.56, spectrum: 0.33, steps: 5 },
    rim: "#f0a48d",
    rimStrength: 0.46,
    ink: "#170f22",
    thickness: 1.5,
    tremor: 0.28,
    back: "#3a2b3f",
    grotesque: 0.45,
    motion: { amplitude: 1.15, speed: 0.78, jitter: 0.45 },
  },
};

/**
 * The two effect boxes on the card face, measured by hand on the artwork
 * (all 62 cards share the same frame). UV coords, origin bottom-left:
 * x0, y0, x1, y1.
 */
export const CARD_ZONES = {
  curse: [0.045, 0.2, 0.955, 0.323] as const,
  prayer: [0.045, 0.035, 0.955, 0.18] as const,
};

export type CardZone = keyof typeof CARD_ZONES;

/**
 * Passes along the world normal (lighting), the object normal (to tell
 * front/back/edge apart) and the world position (specular and rim).
 */
export const CARD_VERT = /* glsl */ `
  varying vec3 vNormalW;
  varying vec3 vNormalO;
  varying vec3 vPosW;
  varying vec2 vUv;

  void main() {
    vUv = uv;
    vNormalO = normal;
    vec4 pw = modelMatrix * vec4(position, 1.0);
    vPosW = pw.xyz;
    vNormalW = normalize(mat3(modelMatrix) * normal);
    gl_Position = projectionMatrix * viewMatrix * pw;
  }
`;

/**
 * N·L gets snapped into `bands` steps instead of a smooth falloff. The
 * specular is a hard-edged spot and the rim light has just two levels.
 */
export const CARD_FRAG = /* glsl */ `
  uniform sampler2D cardMap;
  uniform float lightStrength;
  uniform float shadeStrength;
  uniform vec3 dir;
  uniform vec3 rimColor;
  // Foil params, see FoilTheme.
  uniform float foilStrength;
  uniform float foilScale;
  uniform float foilBand;
  uniform float foilSpectrum;
  uniform float foilSteps;
  // Card back texture. Until it's loaded (or if it fails) we use the
  // theme's flat colour instead.
  uniform sampler2D backMap;
  uniform float backReady;
  uniform vec3 backColor;
  uniform vec3 edgeColor;
  uniform float bands;
  uniform float rimStrength;
  uniform float grotesque;
  uniform float time;
  uniform float appear;
  // Effect box to spotlight (x0, y0, x1, y1 in UV), so you can see which
  // of the two effects is being talked about.
  uniform vec4 zone;
  uniform float zoneStrength;

  varying vec3 vNormalW;
  varying vec3 vNormalO;
  varying vec3 vPosW;
  varying vec2 vUv;

  // Snap to n steps, with a tiny bit of smoothing on each edge so the
  // bands don't look aliased.
  float quantize(float x, float n) {
    float s = clamp(x, 0.0, 1.0) * n;
    float i = floor(s);
    float f = fract(s);
    return (i + smoothstep(0.90, 1.0, f)) / n;
  }

  // Cheap rainbow: maps 0..1 to a full loop around the hue wheel.
  vec3 iridescence(float h) {
    return 0.5 + 0.5 * cos(6.2831853 * (h + vec3(0.0, 0.3333, 0.6667)));
  }

  float luma(vec3 c) {
    return dot(c, vec3(0.2126, 0.7152, 0.0722));
  }

  void main() {
    float front = step(0.5, vNormalO.z);
    float back = step(vNormalO.z, -0.5);
    float edge = 1.0 - front - back;

    // Ombra cards wobble a little, just enough to feel slightly off.
    vec2 uvWave = vUv + grotesque * vec2(
      sin(vUv.y * 30.0 + time * 1.25) * 0.0032,
      cos(vUv.x * 24.0 - time * 0.9) * 0.0026
    );

    vec3 albedo = texture2D(cardMap, clamp(uvWave, 0.001, 0.999)).rgb;

    // The back shares the front's UVs but we're looking at it from behind,
    // so x has to be flipped (otherwise sun and moon swap sides). No texture
    // yet? Flat colour with a soft glow in the middle.
    vec3 backCol = backReady > 0.5
      ? texture2D(backMap, clamp(vec2(1.0 - vUv.x, vUv.y), 0.001, 0.999)).rgb
      : backColor * (0.72 + 0.4 * smoothstep(0.55, 0.0, length(vUv - 0.5)));

    vec3 base = albedo * front + backCol * back + edgeColor * edge;

    vec3 N = normalize(vNormalW);
    vec3 V = normalize(cameraPosition - vPosW);

    // Half-Lambert so the shadow side doesn't go black.
    float ndl = dot(N, dir) * 0.5 + 0.5;
    float t = quantize(ndl, bands);
    vec3 col = base * mix(vec3(shadeStrength), vec3(lightStrength), t);

    // Hard specular spot, no gradient.
    vec3 H = normalize(dir + V);
    float spec = pow(max(dot(N, H), 0.0), 64.0);
    col += vec3(1.0) * step(0.5, spec) * 0.22 * (front + edge);

    // Foil: a diagonal rainbow stripe that slides with the viewing angle,
    // so it only moves when the card does. It's stepped like the rest of the
    // shading, and it mostly shows on the lighter parts of the art (foil
    // doesn't really show up over black ink).
    if (foilStrength > 0.001 && front > 0.5) {
      float view = dot(N, V);
      float wave = (vUv.x * 0.7 - vUv.y * 1.3) * foilScale + view * 2.6;

      vec3 tint = iridescence(fract(wave * 0.5 + foilSpectrum));
      tint = mix(vec3(luma(tint)), tint, 0.85);

      // Turn the wave into a thin stepped stripe.
      float crest = sin(wave * 3.1415926) * 0.5 + 0.5;
      crest = pow(crest, mix(1.0, 5.0, foilBand));
      float foil = quantize(crest, foilSteps);

      // A bit more foil around the border, like on real cards.
      float border = 0.75 + 0.55 * smoothstep(0.34, 0.5, max(
        abs(vUv.x - 0.5), abs(vUv.y - 0.5)
      ));

      float grip = 0.18 + 0.82 * smoothstep(0.12, 0.72, luma(albedo));
      col += tint * foil * grip * border * foilStrength;
    }

    // Rim light, two steps.
    float rim = smoothstep(0.52, 1.0, 1.0 - max(dot(N, V), 0.0));
    col += rimColor * quantize(rim, 2.0) * rimStrength;

    // Effect spotlight: dim everything outside the box and draw a thin
    // glowing line around it. No flipping needed, Maledizione and Preghiera
    // are both on the front.
    if (zoneStrength > 0.001 && front > 0.5) {
      vec2 d0 = vUv - zone.xy;
      vec2 d1 = zone.zw - vUv;
      float inside = smoothstep(0.0, 0.006, min(min(d0.x, d0.y), min(d1.x, d1.y)));
      col = mix(col, col * vec3(0.34, 0.33, 0.31), (1.0 - inside) * zoneStrength);

      // Glowing outline.
      float border = min(min(abs(d0.x), abs(d0.y)), min(abs(d1.x), abs(d1.y)));
      float insideHard = step(zone.x, vUv.x) * step(vUv.x, zone.z) *
        step(zone.y, vUv.y) * step(vUv.y, zone.w);
      col += rimColor * smoothstep(0.0075, 0.0, border) * insideHard * zoneStrength * 0.9;
    }

    gl_FragColor = vec4(col, appear);
    #include <colorspace_fragment>
  }
`;

/**
 * Classic inverted-hull outline: same mesh pushed out along the normals and
 * rendered back-faces only. Scaled by depth so the line width stays the same
 * on screen.
 */
export const OUTLINE_VERT = /* glsl */ `
  uniform float thickness;
  uniform float tremor;
  uniform float time;

  void main() {
    vec3 n = normalize(normalMatrix * normal);
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    float t = 1.0 + tremor * sin(position.y * 8.0 + time * 5.5) * 0.55;
    mv.xyz += n * (thickness * t * 0.018 * -mv.z);
    gl_Position = projectionMatrix * mv;
  }
`;

export const OUTLINE_FRAG = /* glsl */ `
  uniform vec3 color;
  uniform float appear;

  void main() {
    gl_FragColor = vec4(color, appear);
    #include <colorspace_fragment>
  }
`;
