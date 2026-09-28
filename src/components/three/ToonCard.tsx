"use client";

import { useEffect, useRef, useState } from "react";
import { CARD_BACK, CARD_HEIGHT, CARD_WIDTH, type Form } from "@/data/cards";
import {
  CARD_FRAG,
  CARD_VERT,
  CARD_ZONES,
  OUTLINE_FRAG,
  OUTLINE_VERT,
  THEMES,
  type CardZone,
} from "./toon";
import styles from "./ToonCard.module.css";

type Props = {
  /** Card artwork, from /public/cards. */
  src: string;
  form: Form;
  name: string;
  /** Set to false to hide the "Gira" button when the page controls the card. */
  showFlip?: boolean;
  /**
   * Highlights one of the two effect boxes. The card doesn't flip for this,
   * both effects are on the front.
   */
  zone?: CardZone | null;
  /** Plain <Image> fallback. Always rendered, for SEO, screen readers and no-JS. */
  children: React.ReactNode;
};

// Same aspect ratio as the printed card.
const WIDTH = 2.1;
const HEIGHT = WIDTH * (CARD_HEIGHT / CARD_WIDTH);
const DEPTH = 0.07;
const FOV = 30;

/** Rounded rectangle centred on the origin. */
function roundedRect(THREE: typeof import("three"), r: number) {
  const s = new THREE.Shape();
  const w = WIDTH / 2;
  const h = HEIGHT / 2;
  s.moveTo(-w + r, -h);
  s.lineTo(w - r, -h);
  s.quadraticCurveTo(w, -h, w, -h + r);
  s.lineTo(w, h - r);
  s.quadraticCurveTo(w, h, w - r, h);
  s.lineTo(-w + r, h);
  s.quadraticCurveTo(-w, h, -w, h - r);
  s.lineTo(-w, -h + r);
  s.quadraticCurveTo(-w, -h, -w + r, -h);
  return s;
}

/**
 * 3D version of a card with a toon shader (see toon.ts for the look of each
 * Form).
 *
 * The regular image is always underneath the canvas, so if WebGL isn't
 * available nothing breaks. With reduced motion we just render a single
 * static pose.
 */
export default function ToonCard({
  src,
  form,
  name,
  showFlip = true,
  zone = null,
  children,
}: Props) {
  const root = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const controls = useRef<{ flip: () => void; redraw: () => void }>({
    flip: () => {},
    redraw: () => {},
  });
  const zoneRef = useRef<CardZone | null>(zone);
  zoneRef.current = zone;

  // If the render loop isn't running (reduced motion, or on mobile where the
  // card has usually scrolled off screen by the time you tap the tabs) the
  // zone change has to be drawn manually or you'd never see it.
  useEffect(() => {
    controls.current.redraw();
  }, [zone]);
  const [ready, setReady] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    const el = root.current;
    const canvas = canvasRef.current;
    if (!el || !canvas) return;

    const lessMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    setReducedMotion(lessMotion);

    let cancelled = false;
    let cleanup: (() => void) | undefined;

    const build = async () => {
      const THREE = await import("three");
      if (cancelled || !root.current) return;

      let renderer: import("three").WebGLRenderer;
      try {
        renderer = new THREE.WebGLRenderer({
          canvas,
          alpha: true,
          antialias: true,
          powerPreference: "low-power",
          // The spotlight outline is only a few thousandths of a UV wide and
          // disappears in mediump, which some mobile GPUs default to.
          precision: "highp",
        });
      } catch {
        return; // no WebGL, keep the fallback image
      }

      const theme = THEMES[form];
      const scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera(FOV, 1, 0.1, 100);
      const group = new THREE.Group();
      scene.add(group);

      renderer.setClearColor(0x000000, 0);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

      // Geometry: a thin rounded slab with a small bevel.
      const uvFromShape = {
        generateTopUV(
          _g: import("three").ExtrudeGeometry,
          v: number[],
          a: number,
          b: number,
          c: number
        ) {
          return [a, b, c].map(
            (i) => new THREE.Vector2(v[i * 3] / WIDTH + 0.5, v[i * 3 + 1] / HEIGHT + 0.5)
          );
        },
        generateSideWallUV() {
          return [
            new THREE.Vector2(0, 0),
            new THREE.Vector2(0, 0),
            new THREE.Vector2(0, 0),
            new THREE.Vector2(0, 0),
          ];
        },
      };

      const geo = new THREE.ExtrudeGeometry(roundedRect(THREE, 0.1), {
        depth: DEPTH,
        bevelEnabled: true,
        bevelThickness: 0.014,
        bevelSize: 0.014,
        bevelSegments: 2,
        curveSegments: 10,
        UVGenerator: uvFromShape,
      });
      geo.translate(0, 0, -DEPTH / 2);

      // Load front and back textures at the same time.
      const load = (url: string) =>
        new Promise<import("three").Texture | null>((resolve) => {
          new THREE.TextureLoader().load(url, resolve, undefined, () => resolve(null));
        });
      const [texture, backTexture] = await Promise.all([load(src), load(CARD_BACK)]);
      if (cancelled || !root.current) {
        geo.dispose();
        texture?.dispose();
        backTexture?.dispose();
        renderer.dispose();
        return;
      }
      for (const t of [texture, backTexture]) {
        if (!t) continue;
        t.colorSpace = THREE.SRGBColorSpace;
        t.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
        t.needsUpdate = true;
      }

      const color = (c: string) => new THREE.Color(c);
      const cardUniforms = {
        cardMap: { value: texture },
        lightStrength: { value: theme.side.light },
        shadeStrength: { value: theme.side.shade },
        dir: { value: new THREE.Vector3(...theme.side.dir).normalize() },
        foilStrength: { value: theme.foil.strength },
        foilScale: { value: theme.foil.scale },
        foilBand: { value: theme.foil.band },
        foilSpectrum: { value: theme.foil.spectrum },
        foilSteps: { value: theme.foil.steps },
        rimColor: { value: color(theme.rim) },
        backMap: { value: backTexture },
        backReady: { value: backTexture ? 1 : 0 },
        backColor: { value: color(theme.back) },
        edgeColor: { value: color(theme.ink).lerp(color(theme.back), 0.45) },
        bands: { value: theme.bands },
        rimStrength: { value: theme.rimStrength },
        grotesque: { value: theme.grotesque },
        time: { value: 0 },
        appear: { value: lessMotion ? 1 : 0 },
        zone: { value: new THREE.Vector4(0, 0, 1, 1) },
        zoneStrength: { value: 0 },
      };

      const cardMaterial = new THREE.ShaderMaterial({
        uniforms: cardUniforms,
        vertexShader: CARD_VERT,
        fragmentShader: CARD_FRAG,
        transparent: true,
      });

      const outlineUniforms = {
        color: { value: color(theme.ink) },
        thickness: { value: theme.thickness },
        tremor: { value: lessMotion ? 0 : theme.tremor },
        time: { value: 0 },
        appear: { value: lessMotion ? 1 : 0 },
      };

      const outlineMaterial = new THREE.ShaderMaterial({
        uniforms: outlineUniforms,
        vertexShader: OUTLINE_VERT,
        fragmentShader: OUTLINE_FRAG,
        side: THREE.BackSide,
        transparent: true,
      });

      group.add(new THREE.Mesh(geo, cardMaterial));
      group.add(new THREE.Mesh(geo, outlineMaterial));

      // Fit the card inside the container with a bit of margin.
      const margin = 1.16;
      const frame = () => {
        const w = el.clientWidth || 1;
        const h = el.clientHeight || 1;
        renderer.setSize(w, h, false);
        camera.aspect = w / h;
        const halfFov = THREE.MathUtils.degToRad(FOV) / 2;
        const byHeight = (HEIGHT * margin) / 2 / Math.tan(halfFov);
        const byWidth = (WIDTH * margin) / 2 / (Math.tan(halfFov) * camera.aspect);
        camera.position.set(0, 0, Math.max(byHeight, byWidth));
        camera.updateProjectionMatrix();
      };
      frame();

      const ro = new ResizeObserver(frame);
      ro.observe(el);

            const motion = theme.motion;
      let pointerX = 0;
      let pointerY = 0;
      let rotX = 0;
      let rotY = 0;
      let flipTarget = 0;
      let flip = 0;

      controls.current.flip = () => {
        flipTarget += Math.PI;
      };

      // The spotlight eases between boxes instead of jumping, so switching
      // zones looks like a pan.
      const rectCurrent = new THREE.Vector4(0, 0, 1, 1);
      const rectTarget = new THREE.Vector4(0, 0, 1, 1);

      const spotlight = () => {
        const key = zoneRef.current;
        if (key) {
          const [x0, y0, x1, y1] = CARD_ZONES[key];
          if (cardUniforms.zoneStrength.value < 0.001) rectCurrent.set(x0, y0, x1, y1);
          rectTarget.set(x0, y0, x1, y1);
        }
        rectCurrent.lerp(rectTarget, 0.16);
        cardUniforms.zone.value.copy(rectCurrent);
        cardUniforms.zoneStrength.value +=
          ((key ? 1 : 0) - cardUniforms.zoneStrength.value) * 0.12;
      };

      const pose = (t: number) => {
        // Idle sway. Slow and smooth for Luce, twitchy for Ombra.
        const waveY =
          Math.sin(t * 0.62 * motion.speed) * 0.11 * motion.amplitude +
          Math.sin(t * 7.3) * 0.012 * motion.jitter;
        const waveX =
          Math.sin(t * 0.47 * motion.speed + 1.1) * 0.06 * motion.amplitude +
          Math.sin(t * 9.1 + 0.6) * 0.008 * motion.jitter;

        rotY += (pointerX * 0.55 + waveY - rotY) * 0.08;
        rotX += (-pointerY * 0.34 + waveX - rotX) * 0.08;
        flip += (flipTarget - flip) * 0.12;

        group.rotation.set(rotX, rotY + flip, Math.sin(t * 0.4) * 0.02 * motion.amplitude);
        group.position.y = Math.sin(t * 0.8 * motion.speed) * 0.045 * motion.amplitude;
      };

      const onMove = (e: PointerEvent) => {
        const r = el.getBoundingClientRect();
        pointerX = (e.clientX - r.left) / r.width - 0.5;
        pointerY = (e.clientY - r.top) / r.height - 0.5;
      };
      const onLeave = () => {
        pointerX = 0;
        pointerY = 0;
      };

      if (!lessMotion && window.matchMedia("(pointer: fine)").matches) {
        el.addEventListener("pointermove", onMove);
        el.addEventListener("pointerleave", onLeave);
      }

            let rafId = 0;
      let inView = true;
      const born = performance.now();

      const draw = () => {
        const t = (performance.now() - born) / 1000;
        const entry = Math.min(1, t / 1.15);
        const eased = 1 - Math.pow(1 - entry, 3);

        cardUniforms.time.value = t;
        outlineUniforms.time.value = t;
        cardUniforms.appear.value = eased;
        outlineUniforms.appear.value = eased;

        spotlight();
        pose(t);
        // Intro: the card comes in face down and flips over.
        group.rotation.y += (1 - eased) * Math.PI;
        group.scale.setScalar(0.92 + 0.08 * eased);

        renderer.render(scene, camera);
        rafId = requestAnimationFrame(draw);
      };

      // Renders a single frame when the loop is stopped. When it's running,
      // spotlight() already animates the zone, so this does nothing. When
      // it's not (reduced motion, or the card is off screen, which on phones
      // is pretty much always the case since the tabs are below it) we just
      // snap the zone into place.
      controls.current.redraw = () => {
        if (rafId) return;
        const key = zoneRef.current;
        if (key) {
          const [x0, y0, x1, y1] = CARD_ZONES[key];
          rectCurrent.set(x0, y0, x1, y1);
          rectTarget.set(x0, y0, x1, y1);
          cardUniforms.zone.value.set(x0, y0, x1, y1);
        }
        cardUniforms.zoneStrength.value = key ? 1 : 0;
        renderer.render(scene, camera);
      };

      if (lessMotion) {
        group.scale.setScalar(1);
        group.rotation.set(-0.05, 0.22, 0);
        controls.current.redraw();
      } else {
        rafId = requestAnimationFrame(draw);
      }

      // Pause while off screen or in a background tab.
      const setRunning = (running: boolean) => {
        if (lessMotion) return;
        if (running && !rafId) rafId = requestAnimationFrame(draw);
        if (!running && rafId) {
          cancelAnimationFrame(rafId);
          rafId = 0;
        }
      };
      const io = new IntersectionObserver(
        ([v]) => {
          inView = v.isIntersecting;
          setRunning(inView && !document.hidden);
        },
        { rootMargin: "240px" }
      );
      io.observe(el);
      const onVisibility = () => setRunning(inView && !document.hidden);
      document.addEventListener("visibilitychange", onVisibility);

      setReady(true);

      cleanup = () => {
        controls.current.redraw = () => {};
        if (rafId) cancelAnimationFrame(rafId);
        io.disconnect();
        ro.disconnect();
        document.removeEventListener("visibilitychange", onVisibility);
        el.removeEventListener("pointermove", onMove);
        el.removeEventListener("pointerleave", onLeave);
        geo.dispose();
        cardMaterial.dispose();
        outlineMaterial.dispose();
        texture?.dispose();
        backTexture?.dispose();
        renderer.dispose();
      };
    };

    // three is about as heavy as the rest of the page combined, so only
    // import it once the card is getting close to the viewport.
    const waitForView = new IntersectionObserver(
      ([v]) => {
        if (!v.isIntersecting) return;
        waitForView.disconnect();
        void build();
      },
      { rootMargin: "600px" }
    );
    waitForView.observe(el);

    return () => {
      cancelled = true;
      waitForView.disconnect();
      cleanup?.();
    };
  }, [src, form]);

  return (
    <div className={styles.block}>
      <div
        className={styles.stage}
        ref={root}
        data-form={form}
        data-ready={ready ? "1" : "0"}
      >
        <div className={styles.flat}>{children}</div>
        <canvas ref={canvasRef} className={styles.canvas} aria-hidden="true" />
      </div>

      {ready && !reducedMotion && showFlip && (
        <button
          type="button"
          className={styles.flip}
          onClick={() => controls.current.flip()}
        >
          Gira {name}
        </button>
      )}
    </div>
  );
}
