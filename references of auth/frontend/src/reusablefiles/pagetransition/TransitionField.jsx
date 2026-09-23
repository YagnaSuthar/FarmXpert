'use client';

// ============================================================
// FILE: src/reusablefiles/pagetransition/TransitionField.jsx
//
// The full-screen stage behind the transition.
//
// It carries no information on purpose. A loading moment that asks to be
// read feels long; one that is simply nice to look at feels short. So
// there are no labels, no readouts, no symbols — only light:
//
//   aurora   heavily blurred colour drifting behind everything, so the
//            ground is never flat navy
//   ribbons  long S-curves entering off one edge and leaving off another,
//            stroked with a gradient that fades at both ends so they have
//            no visible start or stop
//   motes    points of light rising at three depths
//   rings    bloom expanding out of the centre, past the frame
//
// The aurora is DOM (a blurred div outperforms an SVG filter of the same
// size by a wide margin); everything else is SVG. All motion is transform
// and opacity only, so it stays on the compositor.
//
// viewBox is 1600x900 with `slice`, so the stage fills any aspect ratio.
// ============================================================

import React from 'react';
import { AURORA, STAGE_CENTER } from './transition.config';
import { CENTER, MOTES, RIBBONS, RINGS, STAGE_H, STAGE_W } from './field.geometry';

const W = STAGE_W;
const H = STAGE_H;

export default function TransitionField() {
  return (
    <div className="field-layer-loading" aria-hidden="true">
      {/* --- aurora: blurred colour drifting behind everything --- */}
      <div className="aurora-wrap-loading">
        {AURORA.map((a, i) => (
          <span
            key={i}
            className="aurora-blob-loading"
            style={{
              left: `${a.x}%`,
              top: `${a.y}%`,
              width: `${a.size}vmax`,
              height: `${a.size}vmax`,
              // falls off to the element's own edge — a hard stop at 68% would
              // show a rim now that there is no blur to hide it
              background: `radial-gradient(circle at 50% 50%, ${a.color} 0%, ${a.color} 14%, transparent 100%)`,
              opacity: a.alpha,
              animationDuration: `${a.dur}s`,
              animationDelay: `${a.delay}s`,
            }}
          />
        ))}
      </div>

      <svg
        className="field-svg-loading"
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="xMidYMid slice"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          {/* a ribbon fades in and out along its own length, so it reads
              as passing through the frame rather than ending in it */}
          <linearGradient id="ribbonGradLoading" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="var(--tr-cyan)" stopOpacity="0" />
            <stop offset="26%" stopColor="var(--tr-ice)" stopOpacity="0.7" />
            <stop offset="52%" stopColor="var(--tr-white)" stopOpacity="1" />
            <stop offset="76%" stopColor="var(--tr-cyan)" stopOpacity="0.7" />
            <stop offset="100%" stopColor="var(--tr-cyan)" stopOpacity="0" />
          </linearGradient>

          {/* a soft well so the title is never fighting a ribbon */}
          <radialGradient id="wellGradLoading" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="var(--tr-deep)" stopOpacity="0.82" />
            <stop offset="55%" stopColor="var(--tr-deep)" stopOpacity="0.4" />
            <stop offset="100%" stopColor="var(--tr-deep)" stopOpacity="0" />
          </radialGradient>

          <radialGradient id="bloomGradLoading" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="var(--tr-white)" stopOpacity="0.5" />
            <stop offset="34%" stopColor="var(--tr-cyan)" stopOpacity="0.22" />
            <stop offset="100%" stopColor="var(--tr-core)" stopOpacity="0" />
          </radialGradient>

        </defs>

        {/* --- ribbons, soft pass underneath then crisp pass on top --- */}
        {/* the glow pass: no filter, just a much wider and fainter stroke */}
        <g className="ribbons-soft-loading">
          {RIBBONS.map((r, i) => (
            <path
              key={`s-${i}`}
              className="ribbon-loading"
              d={r.d}
              stroke="url(#ribbonGradLoading)"
              strokeWidth={r.width * 6}
              strokeOpacity={r.opacity * 0.22}
              fill="none"
              strokeLinecap="round"
              pathLength="1"
              style={{ animationDelay: `${r.delay}ms`, animationDuration: `${r.dur}ms` }}
            />
          ))}
        </g>

        <g className="ribbons-crisp-loading">
          {RIBBONS.map((r, i) => (
            <path
              key={`c-${i}`}
              className="ribbon-loading"
              d={r.d}
              stroke="url(#ribbonGradLoading)"
              strokeWidth={r.width}
              strokeOpacity={r.opacity}
              fill="none"
              strokeLinecap="round"
              pathLength="1"
              style={{ animationDelay: `${r.delay}ms`, animationDuration: `${r.dur}ms` }}
            />
          ))}
        </g>

        {/* --- rings blooming out past the frame --- */}
        <g className="bloom-rings-loading">
          {RINGS.map((r) => (
            <circle
              key={r.key}
              className="bloom-ring-loading"
              cx={CENTER.x}
              cy={CENTER.y}
              r="120"
              fill="none"
              stroke="var(--tr-cyan)"
              strokeWidth="1.4"
              style={{
                animationDelay: `${r.delay}s`,
                animationDuration: `${r.dur}s`,
                transformOrigin: `${CENTER.x}px ${CENTER.y}px`,
              }}
            />
          ))}
        </g>

        {/* --- motes rising at three depths --- */}
        <g className="motes-loading">
          {MOTES.map((m) => (
            <circle
              key={m.key}
              className="mote-loading"
              cx={m.x.toFixed(1)}
              cy={m.y.toFixed(1)}
              r={m.r.toFixed(2)}
              fill="var(--tr-ice)"
              style={{
                '--rise': `${-m.rise}px`,
                opacity: m.opacity,
                animationDuration: `${m.dur}s, ${m.twinkleDur}s`,
                animationDelay: `${m.delay}s, ${m.delay}s`,
              }}
            />
          ))}
        </g>

        {/* --- reading well: sits over the ribbons, under the bloom --- */}
        <ellipse
          className="center-well-loading"
          cx={STAGE_CENTER.x}
          cy={STAGE_CENTER.y + 40}
          rx="560"
          ry="300"
          fill="url(#wellGradLoading)"
        />

        {/* --- the centre bloom the mark sits inside --- */}
        <circle
          className="center-bloom-loading"
          cx={STAGE_CENTER.x}
          cy={STAGE_CENTER.y}
          r="430"
          fill="url(#bloomGradLoading)"
          style={{ transformOrigin: `${STAGE_CENTER.x}px ${STAGE_CENTER.y}px` }}
        />
      </svg>
    </div>
  );
}
