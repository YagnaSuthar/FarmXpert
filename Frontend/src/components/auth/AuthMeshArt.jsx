'use client';

// ============================================================
// FILE: src/components/auth/AuthMeshArt.jsx
//
// Procedural low-poly mesh for the auth card's diagonal art panel.
// Same algorithm as the reference (seeded 10x10 jittered grid split
// into triangles, hover lift, pointer parallax), recoloured to the
// Aaurawell palette: deep forest to leaf green, with a few gold
// facets catching the light. The seed is fixed, so the art is the
// same on every visit and between server and client.
// ============================================================

import { useEffect, useRef } from 'react';

function mulberry32(seed) {
  return function next() {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const lerp = (a, b, t) => a + (b - a) * t;
const clamp = (v, min, max) => Math.max(min, Math.min(max, v));

export default function AuthMeshArt() {
  const host = useRef(null);

  useEffect(() => {
    const el = host.current;
    if (!el) return undefined;
    el.innerHTML = '';
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const rand = mulberry32(2026);

    function facetColor(cx, cy, w, h) {
      const t = clamp((cx / w) * 0.55 + (cy / h) * 0.75, 0, 1);
      // Forest (hue 152) to leaf (hue 118), darker at the top left.
      let hue = lerp(152, 118, t);
      let sat = lerp(52, 44, t);
      let light = lerp(12, 34, t);
      light = clamp(light + (rand() - 0.5) * 9, 7, 46);
      hue += (rand() - 0.5) * 4;
      const roll = rand();
      if (roll > 0.972) {
        // A gold facet: the Aaurawell accent, used sparingly.
        return `hsl(${lerp(38, 44, rand()).toFixed(1)} ${lerp(48, 60, rand()).toFixed(0)}% ${lerp(42, 56, rand()).toFixed(0)}%)`;
      }
      if (roll > 0.94) light = clamp(light + 14, 0, 52);
      else if (roll < 0.04) light = clamp(light - 8, 5, 100);
      return `hsl(${hue.toFixed(1)} ${sat.toFixed(0)}% ${light.toFixed(0)}%)`;
    }

    const W = 1000;
    const H = 1000;
    const cols = 10;
    const rows = 10;
    const cellW = W / cols;
    const cellH = H / rows;
    const jitter = Math.min(cellW, cellH) * 0.3;

    const pts = [];
    for (let r = 0; r <= rows; r += 1) {
      pts[r] = [];
      for (let c = 0; c <= cols; c += 1) {
        const edge = r === 0 || r === rows || c === 0 || c === cols;
        pts[r][c] = [c * cellW + (edge ? 0 : (rand() - 0.5) * jitter), r * cellH + (edge ? 0 : (rand() - 0.5) * jitter)];
      }
    }

    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    svg.setAttribute('preserveAspectRatio', 'xMidYMid slice');
    const frag = document.createDocumentFragment();

    for (let ri = 0; ri < rows; ri += 1) {
      for (let ci = 0; ci < cols; ci += 1) {
        const a = pts[ri][ci];
        const b = pts[ri][ci + 1];
        const d = pts[ri + 1][ci];
        const e = pts[ri + 1][ci + 1];
        const flip = rand() > 0.5;
        for (const tri of flip ? [[a, b, d], [b, e, d]] : [[a, b, e], [a, e, d]]) {
          const cx = (tri[0][0] + tri[1][0] + tri[2][0]) / 3;
          const cy = (tri[0][1] + tri[1][1] + tri[2][1]) / 3;
          const poly = document.createElementNS(ns, 'polygon');
          poly.setAttribute('points', tri.map((p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' '));
          poly.setAttribute('fill', facetColor(cx, cy, W, H));
          poly.classList.add('facet-poly-auth');
          if (!reduceMotion) poly.style.animationDelay = `${(rand() * 0.5).toFixed(2)}s`;
          // Drop the entrance animation once it has played: a live animation
          // would restart when the facet is re-appended on hover (the old
          // first-hover stutter) and would pin its transform.
          poly.addEventListener('animationend', () => { poly.style.animation = 'none'; }, { once: true });
          poly.addEventListener('mouseenter', () => {
            if (svg.lastChild !== poly) svg.appendChild(poly);   // lift above its neighbours
            poly.classList.add('poly-hovered-auth');
          });
          poly.addEventListener('mouseleave', () => poly.classList.remove('poly-hovered-auth'));
          frag.appendChild(poly);
        }
      }
    }
    svg.appendChild(frag);
    el.appendChild(svg);

    // Gentle parallax with the pointer.
    const panel = el.closest('.panel-art-auth');
    let raf = 0;
    const move = (ev) => {
      const rect = panel.getBoundingClientRect();
      const nx = (ev.clientX - rect.left) / rect.width - 0.5;
      const ny = (ev.clientY - rect.top) / rect.height - 0.5;
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        svg.style.transform = `translate(${(nx * -14).toFixed(1)}px, ${(ny * -10).toFixed(1)}px) scale(1.03)`;
      });
    };
    const leave = () => { svg.style.transform = 'translate(0,0) scale(1)'; };
    const fine = window.matchMedia('(pointer: fine)').matches;
    if (panel && !reduceMotion && fine) {
      panel.addEventListener('mousemove', move);
      panel.addEventListener('mouseleave', leave);
    }
    return () => {
      cancelAnimationFrame(raf);
      if (panel) {
        panel.removeEventListener('mousemove', move);
        panel.removeEventListener('mouseleave', leave);
      }
    };
  }, []);

  return (
    <>
      <div className="art-mesh-auth" ref={host} />
      <div className="art-shade-auth" />
    </>
  );
}
