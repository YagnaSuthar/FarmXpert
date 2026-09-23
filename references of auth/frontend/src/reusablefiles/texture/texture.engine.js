// ============================================================
// FILE: src/reusablefiles/texture/texture.engine.js
//
// Generative curve-field painter for the dark dashboard surfaces
// (time tracker, highlight stat card, sidebar promo panel).
//
// Every curve is a Catmull-Rom spline threaded through a randomised
// turning walk — many SHORT steps with a gentle turn rate, which is
// what produces real curvature. Few long steps with a wild turn rate
// only ever looks like a zigzag.
//
// COLOR RULE: this file contains no literal colors. It reads the
// `--tex-*` RGB channels from :root (globals.css) at paint time, the
// same pattern the hero canvas already uses, so the texture always
// tracks the Frozen Lake palette.
// ============================================================

/** Density / composition presets. Seeds are fixed so a repaint is stable. */
export const TEXTURE_PRESETS = {
  stat: { seed: 0x5bf03d17, tangle: 190, bundles: 16, sweeps: 14, accents: 12, lift: 0.55 },
  tracker: { seed: 0x2c9a71e3, tangle: 230, bundles: 20, sweeps: 16, accents: 14, lift: 0.6 },
  promo: { seed: 0x71d4b2af, tangle: 150, bundles: 12, sweeps: 12, accents: 10, lift: 0.45 },
  panel: { seed: 0x1f77b4c9, tangle: 120, bundles: 10, sweeps: 10, accents: 8, lift: 0.4 },
};

const FALLBACK = {
  line: [173, 216, 230],
  accent: [226, 242, 250],
  glow: [61, 100, 154],
  core: [0, 0, 128],
  deep: [0, 5, 22],
};

/** Read one `--name-r/g/b` triplet off the computed style. */
function channels(style, name, fallback) {
  const read = (suffix, i) => {
    const raw = style.getPropertyValue(`--${name}-${suffix}`).trim();
    const n = Number.parseInt(raw, 10);
    return Number.isFinite(n) ? n : fallback[i];
  };
  return [read('r', 0), read('g', 1), read('b', 2)];
}

/**
 * Resolve the texture palette from CSS custom properties.
 * @param {Element} [el] element to compute against (defaults to :root)
 */
export function readTexturePalette(el) {
  if (typeof window === 'undefined') return FALLBACK;
  try {
    const style = getComputedStyle(el || document.documentElement);
    return {
      line: channels(style, 'tex-line', FALLBACK.line),
      accent: channels(style, 'tex-accent', FALLBACK.accent),
      glow: channels(style, 'tex-glow', FALLBACK.glow),
      core: channels(style, 'tex-core', FALLBACK.core),
      deep: channels(style, 'tex-deep', FALLBACK.deep),
    };
  } catch {
    return FALLBACK;
  }
}

const rgba = ([r, g, b], a) => `rgba(${r},${g},${b},${Number(a).toFixed(4)})`;

/**
 * Paint one texture onto a canvas.
 *
 * @param {HTMLCanvasElement} cv
 * @param {object} cfg   a TEXTURE_PRESETS entry
 * @param {object} pal   palette from readTexturePalette()
 */
export function paintTexture(cv, cfg, pal) {
  if (!cv || typeof window === 'undefined') return;

  const rect = cv.getBoundingClientRect();
  const W = Math.max(80, Math.round(rect.width));
  const H = Math.max(80, Math.round(rect.height));
  const SS = Math.min(2, window.devicePixelRatio || 1) * 1.6;

  cv.width = Math.round(W * SS);
  cv.height = Math.round(H * SS);

  const g = cv.getContext('2d');
  if (!g) return;
  g.setTransform(SS, 0, 0, SS, 0, 0);
  g.clearRect(0, 0, W, H);

  /* deterministic PRNG so the same card always paints the same field */
  let s = cfg.seed | 0;
  const rnd = () => {
    s |= 0;
    s = (s + 0x6d2b79f5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };

  /* value noise + fBm, used only by the long sweeps */
  const perm = new Uint8Array(512);
  (() => {
    const p = new Uint8Array(256);
    for (let i = 0; i < 256; i++) p[i] = i;
    for (let i = 255; i > 0; i--) {
      const j = (rnd() * (i + 1)) | 0;
      const t = p[i]; p[i] = p[j]; p[j] = t;
    }
    for (let i = 0; i < 512; i++) perm[i] = p[i & 255];
  })();

  const fade = (t) => t * t * t * (t * (t * 6 - 15) + 10);
  const lerp = (a, b, t) => a + (b - a) * t;
  const grd = (h, x, y) => ((h & 1) ? x : -x) + ((h & 2) ? y : -y);
  function noise(x, y) {
    const X = Math.floor(x) & 255;
    const Y = Math.floor(y) & 255;
    const fx = x - Math.floor(x);
    const fy = y - Math.floor(y);
    const u = fade(fx);
    const v = fade(fy);
    const aa = perm[X + perm[Y]];
    const ba = perm[X + 1 + perm[Y]];
    const ab = perm[X + perm[Y + 1]];
    const bb = perm[X + 1 + perm[Y + 1]];
    return lerp(
      lerp(grd(aa, fx, fy), grd(ba, fx - 1, fy), u),
      lerp(grd(ab, fx, fy - 1), grd(bb, fx - 1, fy - 1), u),
      v,
    );
  }
  const fbm = (x, y, o) => {
    let a = 1, f = 1, acc = 0, n = 0;
    for (let i = 0; i < o; i++) { acc += a * noise(x * f, y * f); n += a; a *= 0.5; f *= 2; }
    return acc / n;
  };

  /** Falls off toward the corners so density concentrates off-centre. */
  const mask = (x, y) => {
    const dx = (x - W * 0.44) / (W * 0.7);
    const dy = (y - H * 0.42) / (H * 0.68);
    return Math.max(0, 1 - Math.sqrt(dx * dx + dy * dy));
  };

  /* --- light pools ------------------------------------------------ */
  const pool = (cx, cy, rad, stops) => {
    const gr = g.createRadialGradient(cx, cy, 0, cx, cy, rad);
    stops.forEach(([at, color]) => gr.addColorStop(at, color));
    g.fillStyle = gr;
    g.fillRect(0, 0, W, H);
  };

  const lift = cfg.lift ?? 0.5;
  pool(W * 0.43, H * 0.36, W * 0.8, [
    [0, rgba(pal.core, 0.55 * (0.6 + lift))],
    [0.44, rgba(pal.glow, 0.26)],
    [1, rgba(pal.deep, 0)],
  ]);
  pool(W * 0.82, H * 0.76, W * 0.68, [
    [0, rgba(pal.glow, 0.24)],
    [1, rgba(pal.deep, 0)],
  ]);
  pool(W * 0.12, H * 0.92, W * 0.72, [
    [0, rgba(pal.deep, 0.6)],
    [1, rgba(pal.deep, 0)],
  ]);

  g.lineCap = 'round';
  g.lineJoin = 'round';

  /* Catmull-Rom emitted as real cubic beziers, so curves stay smooth
     instead of faceting at high supersample. */
  function spline(pts) {
    if (pts.length < 2) return;
    g.moveTo(pts[0][0], pts[0][1]);
    for (let i = 0; i < pts.length - 1; i++) {
      const p0 = pts[i - 1] || pts[i];
      const p1 = pts[i];
      const p2 = pts[i + 1];
      const p3 = pts[i + 2] || pts[i + 1];
      g.bezierCurveTo(
        p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6,
        p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6,
        p2[0], p2[1],
      );
    }
  }

  function walk(x0, y0, ang0, segs, l0, l1, turn) {
    let x = x0, y = y0, ang = ang0;
    const pts = [[x, y]];
    for (let i = 0; i < segs; i++) {
      ang += (rnd() - 0.5) * turn;
      const L = l0 + rnd() * (l1 - l0);
      x += Math.cos(ang) * L;
      y += Math.sin(ang) * L;
      pts.push([x, y]);
    }
    return pts;
  }

  const SC = Math.sqrt(W * H) / 500; // keeps density size-independent

  /* --- curve tangle ----------------------------------------------- */
  for (let n = 0; n < cfg.tangle; n++) {
    const x = rnd() * (W + 160) - 80;
    const y = rnd() * (H + 160) - 80;
    const m = mask(x, y);
    if (rnd() > 0.2 + m * 0.92) continue;
    g.beginPath();
    spline(walk(x, y, rnd() * Math.PI * 2, 7 + ((rnd() * 13) | 0), 14 * SC, 54 * SC, 1.15));
    g.strokeStyle = rgba(pal.line, (0.04 + rnd() * 0.095) * (0.35 + 0.65 * m));
    g.lineWidth = 0.45 + rnd() * 1.0;
    g.stroke();
  }

  /* --- bundles: offset copies along the path normal ---------------- */
  for (let n = 0; n < cfg.bundles; n++) {
    const bx = rnd() * (W + 120) - 60;
    const by = rnd() * (H + 120) - 60;
    const m = mask(bx, by);
    if (rnd() > 0.25 + m * 0.85) continue;
    const base = walk(bx, by, rnd() * Math.PI * 2, 7 + ((rnd() * 8) | 0), 28 * SC, 84 * SC, 0.95);
    const count = 4 + ((rnd() * 5) | 0);
    const gap = (2.4 + rnd() * 4.4) * SC;
    for (let k = 0; k < count; k++) {
      const off = (k - count / 2) * gap;
      const shifted = base.map((p, i) => {
        const q = base[Math.min(i + 1, base.length - 1)];
        const r2 = base[Math.max(i - 1, 0)];
        const dx = q[0] - r2[0];
        const dy = q[1] - r2[1];
        const L = Math.hypot(dx, dy) || 1;
        return [p[0] - (dy / L) * off, p[1] + (dx / L) * off];
      });
      g.beginPath();
      spline(shifted);
      g.strokeStyle = rgba(pal.line, (0.038 + rnd() * 0.065) * (0.35 + 0.65 * m));
      g.lineWidth = 0.42 + rnd() * 0.75;
      g.stroke();
    }
  }

  /* --- long sweeps tying the composition together ------------------ */
  for (let n = 0; n < cfg.sweeps; n++) {
    const y0 = -60 + (H + 120) * rnd();
    const amp = (26 + rnd() * 80) * SC;
    const lane = rnd() * 70;
    const pts = [];
    for (let x = -90; x <= W + 90; x += (46 + rnd() * 40) * SC) {
      pts.push([x, y0 + fbm((x * 0.0022) / SC, lane, 3) * amp]);
    }
    g.beginPath();
    spline(pts);
    g.strokeStyle = rgba(pal.accent, 0.045 + rnd() * 0.08);
    g.lineWidth = 0.5 + rnd() * 1.0;
    g.stroke();
  }

  /* --- bright accents so the tangle has a foreground --------------- */
  g.globalCompositeOperation = 'lighter';
  for (let n = 0; n < cfg.accents; n++) {
    const x = rnd() * (W + 100) - 50;
    const y = rnd() * (H + 100) - 50;
    const m = mask(x, y);
    if (rnd() > 0.16 + m * 0.88) continue;
    g.beginPath();
    spline(walk(x, y, rnd() * Math.PI * 2, 9 + ((rnd() * 12) | 0), 18 * SC, 66 * SC, 1.0));
    g.strokeStyle = rgba(pal.accent, (0.07 + rnd() * 0.095) * (0.4 + 0.6 * m));
    g.lineWidth = 0.7 + rnd() * 1.05;
    g.stroke();
  }
  g.globalCompositeOperation = 'source-over';

  /* --- vignette sinks the curves into the corners ------------------ */
  const vg = g.createRadialGradient(
    W * 0.46, H * 0.44, Math.min(W, H) * 0.2,
    W * 0.46, H * 0.44, Math.max(W, H) * 0.78,
  );
  vg.addColorStop(0, rgba(pal.deep, 0));
  vg.addColorStop(1, rgba(pal.deep, 0.55));
  g.fillStyle = vg;
  g.fillRect(0, 0, W, H);
}
