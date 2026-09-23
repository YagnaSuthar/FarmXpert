'use client';

// ============================================================
// FILE: src/reusablefiles/pagetransition/TransitionLoader.jsx
//
// The centre stage of the page transition.
//
// This builds on the existing mark rather than replacing it — the corner
// brackets, the counter-rotating dashed diamond and hexagon, the cardinal
// conduits and the faceted star core all stay. What is new is the depth
// around them:
//
//   · a tick ruler ring that reads as a calibrated instrument
//   · a determinate progress arc that sweeps once over the enter duration
//   · an orbit carrying three satellite nodes at three radii
//   · a scan bar that passes across the core
//   · a deeper facet break-up on the star, with a specular edge
//
// Colors come from the `--tr-*` tokens in globals.css. SVG gradients
// cannot read a CSS variable through `stopColor` in every engine, so the
// stops are set from the tokens via inline `style` — which does resolve.
//
// Every class keeps the project's '-loading' suffix convention.
// ============================================================

import React from 'react';

const stop = (token, opacity) => ({ stopColor: `var(${token})`, stopOpacity: opacity });

/** 48 ticks around the ruler ring, every 6th one long. */
const TICKS = Array.from({ length: 48 }, (_, i) => {
  const angle = (360 / 48) * i;
  const long = i % 6 === 0;
  return { angle, len: long ? 7 : 3.5, opacity: long ? 0.9 : 0.4 };
});

/** Three satellites, each on its own radius and phase. */
const SATELLITES = [
  { r: 74, from: 0, dur: '5.5s', size: 2.6 },
  { r: 74, from: 140, dur: '5.5s', size: 1.8 },
  { r: 58, from: 250, dur: '4s', size: 2.2 },
];

export default function TransitionLoader() {
  return (
    <div className="loader-container-loading" aria-label="Loading animation">
      <div className="loader-core-wrap-loading">
        {/* Soft ambient radial glow */}
        <div className="loader-aura-glow-loading" />

        <svg
          className="loader-svg-loading"
          viewBox="0 0 200 200"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          <defs>
            <linearGradient id="facetGradPrimaryLoading" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" style={stop('--tr-core', 0.95)} />
              <stop offset="50%" style={stop('--tr-mid', 0.9)} />
              <stop offset="100%" style={stop('--tr-cyan', 1)} />
            </linearGradient>

            <linearGradient id="facetGradAccentLoading" x1="100%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" style={stop('--tr-cyan', 1)} />
              <stop offset="60%" style={stop('--tr-slate', 0.8)} />
              <stop offset="100%" style={stop('--tr-deep', 0.95)} />
            </linearGradient>

            <linearGradient id="laserGradLoading" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" style={stop('--tr-core', 0.2)} />
              <stop offset="50%" style={stop('--tr-cyan', 1)} />
              <stop offset="100%" style={stop('--tr-ice', 0.2)} />
            </linearGradient>

            {/* progress arc runs cool at the tail, bright at the head */}
            <linearGradient id="progressGradLoading" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" style={stop('--tr-core', 0.15)} />
              <stop offset="55%" style={stop('--tr-mid', 0.85)} />
              <stop offset="100%" style={stop('--tr-cyan', 1)} />
            </linearGradient>

            {/* the scan bar is a soft band, not a hard line */}
            <linearGradient id="scanGradLoading" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" style={stop('--tr-cyan', 0)} />
              <stop offset="50%" style={stop('--tr-cyan', 0.85)} />
              <stop offset="100%" style={stop('--tr-cyan', 0)} />
            </linearGradient>

            <radialGradient id="coreSpecularLoading" cx="38%" cy="30%" r="70%">
              <stop offset="0%" style={stop('--tr-white', 0.95)} />
              <stop offset="45%" style={stop('--tr-ice', 0.35)} />
              <stop offset="100%" style={stop('--tr-core', 0)} />
            </radialGradient>

            <filter id="neuralGlowLoading" x="-40%" y="-40%" width="180%" height="180%">
              <feGaussianBlur stdDeviation="3.5" result="blur" />
              <feComposite in="SourceGraphic" in2="blur" operator="over" />
            </filter>

            <filter id="softGlowLoading" x="-60%" y="-60%" width="220%" height="220%">
              <feGaussianBlur stdDeviation="1.6" />
            </filter>

            {/* keeps the scan bar inside the core's footprint */}
            <clipPath id="coreClipLoading">
              <circle cx="100" cy="100" r="46" />
            </clipPath>
          </defs>

          {/* 1. Calibrated tick ruler — the outermost instrument ring */}
          <g className="ruler-ring-loading">
            {TICKS.map((t, i) => (
              <line
                key={i}
                x1="100"
                y1={8}
                x2="100"
                y2={8 + t.len}
                stroke="var(--tr-tick)"
                strokeWidth="1.1"
                strokeLinecap="round"
                opacity={t.opacity}
                transform={`rotate(${t.angle} 100 100)`}
              />
            ))}
          </g>

          {/* 2. Determinate progress arc — one sweep per transition */}
          <circle
            cx="100" cy="100" r="88"
            stroke="var(--tr-track)"
            strokeWidth="1.6"
            fill="none"
          />
          <circle
            className="progress-arc-loading"
            cx="100" cy="100" r="88"
            stroke="url(#progressGradLoading)"
            strokeWidth="2.4"
            strokeLinecap="round"
            fill="none"
            pathLength="1"
            transform="rotate(-90 100 100)"
          />

          {/* 3. Precision tech corner brackets */}
          <g
            className="tech-brackets-group-loading"
            stroke="var(--tr-cyan)"
            strokeWidth="1.8"
            opacity="0.85"
          >
            <path d="M 24,44 L 24,24 L 44,24" fill="none" />
            <path d="M 156,24 L 176,24 L 176,44" fill="none" />
            <path d="M 176,156 L 176,176 L 156,176" fill="none" />
            <path d="M 44,176 L 24,176 L 24,156" fill="none" />
          </g>

          {/* 4. Outer diamond substrate frame */}
          <polygon
            points="100,16 184,100 100,184 16,100"
            stroke="url(#facetGradAccentLoading)"
            strokeWidth="1.5"
            fill="none"
            strokeDasharray="30 12 60 12"
            className="diamond-frame-outer-loading"
          />

          {/* 5. Counter-rotating hexagonal matrix */}
          <polygon
            points="100,36 155,68 155,132 100,164 45,132 45,68"
            stroke="url(#facetGradPrimaryLoading)"
            strokeWidth="1.8"
            fill="none"
            strokeDasharray="24 16"
            className="hexagon-matrix-mid-loading"
          />

          {/* 6. Orbit path with satellites */}
          <g className="orbit-group-loading">
            <circle
              cx="100" cy="100" r="74"
              stroke="var(--tr-track)"
              strokeWidth="1"
              fill="none"
              strokeDasharray="2 7"
            />
            {SATELLITES.map((s, i) => (
              <g
                key={i}
                className="satellite-orbit-loading"
                style={{ animationDuration: s.dur, animationDelay: `${i * -0.9}s` }}
              >
                <circle
                  cx={100 + s.r}
                  cy="100"
                  r={s.size}
                  fill="var(--tr-cyan)"
                  filter="url(#softGlowLoading)"
                  transform={`rotate(${s.from} 100 100)`}
                />
              </g>
            ))}
          </g>

          {/* 7. Cardinal laser conduits */}
          <g
            stroke="url(#laserGradLoading)"
            strokeWidth="1.5"
            className="cardinal-lasers-loading"
          >
            <line x1="100" y1="24" x2="100" y2="176" strokeDasharray="8 8" className="laser-vertical-loading" />
            <line x1="24" y1="100" x2="176" y2="100" strokeDasharray="8 8" className="laser-horizontal-loading" />
          </g>

          {/* 8. Faceted multi-agent polyhedron core */}
          <g className="polyhedron-core-group-loading" filter="url(#neuralGlowLoading)">
            <polygon points="100,60 134,100 100,100 66,100" fill="url(#facetGradAccentLoading)" opacity="0.9" />
            <polygon points="100,60 134,100 100,140" fill="url(#facetGradPrimaryLoading)" opacity="0.8" />
            <polygon points="100,140 134,100 100,100 66,100" fill="var(--tr-core)" stroke="var(--tr-cyan)" strokeWidth="1" opacity="0.9" />
            <polygon points="100,60 66,100 100,140" fill="url(#facetGradAccentLoading)" opacity="0.7" />

            {/* added facet breaks — the star reads as cut, not flat */}
            <polygon points="100,60 117,80 100,100 83,80" fill="var(--tr-white)" opacity="0.14" />
            <polygon points="100,100 117,120 100,140 83,120" fill="var(--tr-deep)" opacity="0.28" />
            <path d="M100,60 L100,140 M66,100 L134,100" stroke="var(--tr-cyan)" strokeWidth="0.6" opacity="0.5" />

            {/* specular bloom on the upper-left facet */}
            <polygon points="100,60 134,100 100,140 66,100" fill="url(#coreSpecularLoading)" opacity="0.75" />

            {/* the bright four-point spark at the centre */}
            <polygon
              className="core-spark-loading"
              points="100,86 105,95 114,100 105,105 100,114 95,105 86,100 95,95"
              fill="var(--tr-white)"
            />
          </g>

          {/* 9. Scan bar sweeping across the core */}
          <g clipPath="url(#coreClipLoading)">
            <rect
              className="core-scan-loading"
              x="54" y="-14" width="92" height="14"
              fill="url(#scanGradLoading)"
            />
          </g>

          {/* 10. Corner data node pins */}
          <g className="corner-nodes-loading">
            <rect x="21" y="21" width="6" height="6" fill="var(--tr-cyan)" />
            <rect x="173" y="21" width="6" height="6" fill="var(--tr-cyan)" />
            <rect x="173" y="173" width="6" height="6" fill="var(--tr-cyan)" />
            <rect x="21" y="173" width="6" height="6" fill="var(--tr-cyan)" />
          </g>
        </svg>

        {/* Crystalline tech pulse frame */}
        <div className="tech-pulse-frame-loading" />
      </div>
    </div>
  );
}
