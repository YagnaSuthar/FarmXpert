// ============================================================
// FILE: src/components/ui/icons.jsx
//
// The FarmXpert icon set, drawn for this product - no icon library.
//
// One grammar for every icon:
//   - 24px grid, 1.6 stroke, round caps and joins, currentColor
//   - a soft "tint" layer (the same colour at 14%) that gives each
//     icon a second tone, so they read richer than plain line icons
//   - farm-specific motifs where the meaning allows: the home is a
//     barn, soil shows its layers and a root, water has a ripple,
//     the market is a stall with an awning, usage bars end in leaves
//
// Components keep familiar names, so swapping them in is an import
// change. Every icon accepts className, strokeWidth and any SVG prop.
// ============================================================

import { forwardRef } from 'react';

const TINT = { fill: 'currentColor', fillOpacity: 0.14, stroke: 'none' };
const DOT = { fill: 'currentColor', stroke: 'none' };

function make(name, draw) {
  const Icon = forwardRef(function Icon({ className, strokeWidth = 1.6, size, ...props }, ref) {
    return (
      <svg ref={ref} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth}
        strokeLinecap="round" strokeLinejoin="round" width={size ?? '1em'} height={size ?? '1em'}
        className={className ? `fx-icon ${className}` : 'fx-icon size-5'} aria-hidden={props['aria-label'] ? undefined : true}
        focusable="false" {...props}>
        {draw}
      </svg>
    );
  });
  Icon.displayName = name;
  return Icon;
}

// ── navigation: the farm ──────────────────────────────────────────────────

/** Today: a barn with a gambrel roof, hay-loft window and cross-braced door. */
export const House = make('House', <>
  <path d="M3.5 10.5 7 5.5h10l3.5 5v9.5h-17z" style={TINT} />
  <path d="M3.5 10.5 7 5.5h10l3.5 5M3.5 10.5V20h17v-9.5" />
  <path d="M9.5 20v-5.5h5V20M9.5 14.5l5 5.5M14.5 14.5l-5 5.5" />
  <path d="M11 9h2" />
</>);

/** Ask: a speech bubble with a leaf growing inside - advice that grows. */
export const MessagesSquare = make('MessagesSquare', <>
  <path d="M4 6.5A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5v7a2.5 2.5 0 0 1-2.5 2.5H11l-4.5 4v-4A2.5 2.5 0 0 1 4 13.5z" style={TINT} />
  <path d="M4 6.5A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5v7a2.5 2.5 0 0 1-2.5 2.5H11l-4.5 4v-4A2.5 2.5 0 0 1 4 13.5z" />
  <path d="M9 12.5c0-2.6 2-4.3 6-4.5-.2 3.6-2.2 5.3-6 4.5zM9 12.5l3-2.5" />
</>);
export const MessageCircle = MessagesSquare;

/** Tasks: a clipboard whose ticks are sprouting seedlings. */
export const ListChecks = make('ListChecks', <>
  <rect x="5" y="4.5" width="14" height="16" rx="2.5" style={TINT} />
  <path d="M9 4.5H7.5A2.5 2.5 0 0 0 5 7v11a2.5 2.5 0 0 0 2.5 2.5h9A2.5 2.5 0 0 0 19 18V7a2.5 2.5 0 0 0-2.5-2.5H15" />
  <rect x="9" y="3" width="6" height="3" rx="1" />
  <path d="m8 11 1.3 1.3L11.5 10M8 16l1.3 1.3 2.2-2.3M13.5 11.5H16M13.5 16.5H16" />
</>);

/** Water: a drop with an inner highlight and a ripple where it lands. */
export const Droplets = make('Droplets', <>
  <path d="M12 3.5c3 3.6 5 6.4 5 9a5 5 0 0 1-10 0c0-2.6 2-5.4 5-9z" style={TINT} />
  <path d="M12 3.5c3 3.6 5 6.4 5 9a5 5 0 0 1-10 0c0-2.6 2-5.4 5-9z" />
  <path d="M10 13.5a2.2 2.2 0 0 0 2 2" />
  <path d="M4 20.5c1.3-.7 2.7-.7 4 0M16 20.5c1.3-.7 2.7-.7 4 0" />
</>);

/** Soil: a cross-section - topsoil, subsoil and a root reaching down. */
export const FlaskConical = make('FlaskConical', <>
  <path d="M3.5 10.5h17v9a1 1 0 0 1-1 1h-15a1 1 0 0 1-1-1z" style={TINT} />
  <path d="M3.5 10.5h17v9a1 1 0 0 1-1 1h-15a1 1 0 0 1-1-1z" />
  <path d="M3.5 14.5c2.8.9 5.6.9 8.5 0s5.7-.9 8.5 0" />
  <path d="M12 10.5V6M12 6c0-1.8 1.3-3 3.5-3-.1 2-1.4 3-3.5 3zM12 7.5c0-1.4-1-2.3-2.7-2.3.1 1.5 1 2.3 2.7 2.3z" />
  <path d="M12 10.5v3.3c0 1.2-1 1.6-1 2.8M12 13.8c.9.4 1.4 1 1.4 2" />
  <circle cx="6.5" cy="17.5" r=".6" style={DOT} /><circle cx="17" cy="18" r=".6" style={DOT} />
</>);

/** Mandi: a market stall with a scalloped awning and a weighing scale. */
export const Store = make('Store', <>
  <path d="M4 9.5h16v11H4z" style={TINT} />
  <path d="M3 9.5 4.5 4h15L21 9.5" />
  <path d="M3 9.5a2.25 2.25 0 0 0 4.5 0 2.25 2.25 0 0 0 4.5 0 2.25 2.25 0 0 0 4.5 0 2.25 2.25 0 0 0 4.5 0" />
  <path d="M4.5 11.5v9h15v-9" />
  <path d="M12 13.5v4M9 15l3-1.5 3 1.5M8 15l-1 2.2h2zM16 15l-1 2.2h2z" />
</>);

/** Usage: three bars growing like stalks, the tallest crowned with a leaf. */
export const ChartNoAxesColumn = make('ChartNoAxesColumn', <>
  <rect x="4.5" y="13" width="3.5" height="7.5" rx="1" style={TINT} />
  <rect x="10.25" y="9.5" width="3.5" height="11" rx="1" style={TINT} />
  <rect x="16" y="11.5" width="3.5" height="9" rx="1" style={TINT} />
  <path d="M6.25 20.5V13M12 20.5V9.5M17.75 20.5V11.5M3.5 20.5h17" />
  <path d="M12 9.5c0-2.8 1.8-4.7 5-5-.2 3.2-2 5-5 5zM12 9.5c0-2-1.3-3.3-3.6-3.5.1 2.3 1.4 3.5 3.6 3.5z" />
</>);
export const BarChart3 = ChartNoAxesColumn;

/** Settings: three sliders whose knobs are seeds. */
export const Settings2 = make('Settings2', <>
  <path d="M4 6.5h9M18 6.5h2M4 12h3M12 12h8M4 17.5h11M20 17.5h0" />
  <path d="M15.5 4.3c1.5.6 1.5 3.8 0 4.4-1.5-.6-1.5-3.8 0-4.4z" style={TINT} />
  <path d="M15.5 4.3c1.5.6 1.5 3.8 0 4.4-1.5-.6-1.5-3.8 0-4.4z" />
  <path d="M9.5 9.8c1.5.6 1.5 3.8 0 4.4-1.5-.6-1.5-3.8 0-4.4z" style={TINT} />
  <path d="M9.5 9.8c1.5.6 1.5 3.8 0 4.4-1.5-.6-1.5-3.8 0-4.4z" />
  <path d="M17.5 15.3c1.5.6 1.5 3.8 0 4.4-1.5-.6-1.5-3.8 0-4.4z" style={TINT} />
  <path d="M17.5 15.3c1.5.6 1.5 3.8 0 4.4-1.5-.6-1.5-3.8 0-4.4z" />
</>);

// ── crops and field ───────────────────────────────────────────────────────

/** A seedling: two cotyledons opening above a soil line with a seed. */
export const Sprout = make('Sprout', <>
  <path d="M12 12c-.2-3.4-2.3-5.4-6.5-5.5.1 3.6 2.4 5.5 6.5 5.5zM12 10.5c.3-3.7 2.7-5.8 7-6-.2 4-2.7 6-7 6z" style={TINT} />
  <path d="M12 12c-.2-3.4-2.3-5.4-6.5-5.5.1 3.6 2.4 5.5 6.5 5.5zM12 10.5c.3-3.7 2.7-5.8 7-6-.2 4-2.7 6-7 6z" />
  <path d="M12 19.5v-9M8.5 12 12 15.5M4 19.5h16" />
  <ellipse cx="12" cy="20.8" rx="1.4" ry=".7" style={DOT} />
</>);

/** A grain ear: paired kernels up a curved stalk, with an awn at the tip. */
export const Wheat = make('Wheat', <>
  <path d="M12 21c0-5 .5-9 2-13" />
  <path d="M14 8c-2 0-3.3-1.2-3.4-3.2 2 0 3.3 1.2 3.4 3.2zM14 8c.3-1.9 1.8-3 3.8-2.9-.3 2-1.8 3-3.8 2.9z" style={TINT} />
  <path d="M14 8c-2 0-3.3-1.2-3.4-3.2 2 0 3.3 1.2 3.4 3.2zM14 8c.3-1.9 1.8-3 3.8-2.9-.3 2-1.8 3-3.8 2.9z" />
  <path d="M13.2 11.6c-2 0-3.4-1.2-3.5-3.2 2 0 3.4 1.2 3.5 3.2zM13.2 11.6c.4-1.9 1.9-2.9 3.9-2.8-.4 2-1.9 3-3.9 2.8z" />
  <path d="M12.6 15.2c-2 0-3.4-1.2-3.5-3.2 2 0 3.4 1.2 3.5 3.2zM12.6 15.2c.4-1.9 1.9-2.9 3.9-2.8-.4 2-1.9 3-3.9 2.8z" />
  <path d="M15 5.2 16.8 2.5" />
</>);

/** A tractor: big rear wheel, small front wheel, cab and exhaust. */
export const Tractor = make('Tractor', <>
  <circle cx="7.5" cy="16" r="4" style={TINT} />
  <circle cx="7.5" cy="16" r="4" /><circle cx="7.5" cy="16" r="1.2" />
  <circle cx="18" cy="17.5" r="2.5" />
  <path d="M5 12V5.5h5l1.5 6.5M11.5 12h6.5l1.5 3M15.5 12V8.5M11.5 16h4" />
</>);

/** Weather: a sun half behind a cloud, with one falling drop. */
export const CloudSun = make('CloudSun', <>
  <path d="M8 7.5a3.5 3.5 0 0 1 6.2-1.3" />
  <path d="M8.5 2.5v1.5M3.5 7.5H5M4.8 3.8l1 1M12.2 3.8l-1 1" />
  <path d="M7 18.5a3.5 3.5 0 0 1-.4-7 5 5 0 0 1 9.7-1.4A3.9 3.9 0 0 1 17 18.5z" style={TINT} />
  <path d="M7 18.5a3.5 3.5 0 0 1-.4-7 5 5 0 0 1 9.7-1.4A3.9 3.9 0 0 1 17 18.5z" />
  <path d="M11 21.5l.5-1" />
</>);

/** Microscope, drawn as a hand lens over a leaf - close inspection. */
export const Microscope = make('Microscope', <>
  <circle cx="10" cy="10" r="6" style={TINT} />
  <circle cx="10" cy="10" r="6" />
  <path d="m14.5 14.5 5.5 5.5" strokeWidth="2.4" />
  <path d="M7.5 12.5c0-3 1.8-4.8 5-5-.2 3.1-2 5-5 5zM7.5 12.5l2.6-2.6" />
</>);

/** Soil probe / sensor: a stake in the ground sending a signal. */
export const Radio = make('Radio', <>
  <path d="M12 21V9" strokeWidth="2" />
  <path d="M9.5 21h5" />
  <circle cx="12" cy="7.5" r="1.6" style={TINT} /><circle cx="12" cy="7.5" r="1.6" />
  <path d="M8.5 4.5a4.5 4.5 0 0 0 0 6M15.5 4.5a4.5 4.5 0 0 1 0 6M6 2.5a7.5 7.5 0 0 0 0 10M18 2.5a7.5 7.5 0 0 1 0 10" />
</>);
export const Wifi = make('Wifi', <>
  <path d="M3 9.5a13 13 0 0 1 18 0M6 13a8.5 8.5 0 0 1 12 0M9 16.5a4 4 0 0 1 6 0" />
  <circle cx="12" cy="19.5" r="1.3" style={DOT} />
</>);

/** Satellite: body with two solar wings and a dish looking down at the field. */
export const Satellite = make('Satellite', <>
  <rect x="9" y="9" width="6" height="6" rx="1" transform="rotate(45 12 12)" style={TINT} />
  <rect x="9" y="9" width="6" height="6" rx="1" transform="rotate(45 12 12)" />
  <path d="m4 8 4-4 3 3-4 4zM20 16l-4 4-3-3 4-4z" />
  <path d="M16 3.5a4.5 4.5 0 0 1 4.5 4.5M16 6a2 2 0 0 1 2 2" />
</>);

// ── assistant ─────────────────────────────────────────────────────────────

/** AI: a four-point star with a smaller companion - FarmXpert thinking. */
export const Sparkles = make('Sparkles', <>
  <path d="M10 3.5c.6 3.8 2.7 5.9 6.5 6.5-3.8.6-5.9 2.7-6.5 6.5-.6-3.8-2.7-5.9-6.5-6.5 3.8-.6 5.9-2.7 6.5-6.5z" style={TINT} />
  <path d="M10 3.5c.6 3.8 2.7 5.9 6.5 6.5-3.8.6-5.9 2.7-6.5 6.5-.6-3.8-2.7-5.9-6.5-6.5 3.8-.6 5.9-2.7 6.5-6.5z" />
  <path d="M18 14.5c.3 1.9 1.1 2.7 3 3-1.9.3-2.7 1.1-3 3-.3-1.9-1.1-2.7-3-3 1.9-.3 2.7-1.1 3-3z" />
</>);
export const Brain = Sparkles;
export const Cpu = make('Cpu', <>
  <rect x="6" y="6" width="12" height="12" rx="2.5" style={TINT} />
  <rect x="6" y="6" width="12" height="12" rx="2.5" />
  <path d="M9.5 3v3M14.5 3v3M9.5 18v3M14.5 18v3M3 9.5h3M3 14.5h3M18 9.5h3M18 14.5h3" />
  <path d="M10 14c0-2.3 1.4-3.7 4-4-.2 2.6-1.6 4-4 4z" />
</>);
export const Mic = make('Mic', <>
  <rect x="9" y="3" width="6" height="11" rx="3" style={TINT} />
  <rect x="9" y="3" width="6" height="11" rx="3" />
  <path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M9 21h6M11 6.5h2M11 9h2" />
</>);
/** Voice mode: sound bars of a spoken reply, tallest in the middle. */
export const AudioLines = make('AudioLines', <>
  <path d="M4 10v4M8 7v10M12 4v16M16 7v10M20 10v4" />
</>);
export const Volume2 = make('Volume2', <>
  <path d="M4 9.5h3l4.5-4v13L7 14.5H4z" style={TINT} />
  <path d="M4 9.5h3l4.5-4v13L7 14.5H4z" />
  <path d="M15 9a4 4 0 0 1 0 6M17.5 6.5a7.5 7.5 0 0 1 0 11" />
</>);
export const Square = make('Square', <rect x="6" y="6" width="12" height="12" rx="2.5" />);
export const BookOpen = make('BookOpen', <>
  <path d="M12 6.5C10 5 7 4.5 3.5 5v13c3.5-.5 6.5 0 8.5 1.5 2-1.5 5-2 8.5-1.5V5C17 4.5 14 5 12 6.5z" style={TINT} />
  <path d="M12 6.5C10 5 7 4.5 3.5 5v13c3.5-.5 6.5 0 8.5 1.5 2-1.5 5-2 8.5-1.5V5C17 4.5 14 5 12 6.5zM12 6.5v13" />
  <path d="M15 11c0-1.8 1.2-3 3-3.1-.1 1.9-1.2 3-3 3.1z" />
</>);
export const Handshake = make('Handshake', <>
  <path d="m3 11 4-4 3 1 2-1 3.5 3.5a1.4 1.4 0 0 1-2 2L12 11" />
  <path d="M21 11l-4-4-2.5 1M5 13l4.5 4.5a1.4 1.4 0 0 0 2-2M8 12.5l4 4a1.4 1.4 0 0 0 2-2l-1-1M14.5 13.5l1 1a1.4 1.4 0 0 0 2-2L19 11" />
  <path d="M7 7 12 11" style={{ opacity: 0.4 }} />
</>);

// ── theme ─────────────────────────────────────────────────────────────────

/** Sun: a disc with eight tapered rays, alternating long and short. */
export const Sun = make('Sun', <>
  <circle cx="12" cy="12" r="4" style={TINT} />
  <circle cx="12" cy="12" r="4" />
  <path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M5.6 5.6l1.3 1.3M17.1 17.1l1.3 1.3M5.6 18.4l1.3-1.3M17.1 6.9l1.3-1.3" />
</>);
/** Moon: a crescent with a small star beside it. */
export const Moon = make('Moon', <>
  <path d="M19.5 14.5A8 8 0 1 1 9.5 4.5a6.5 6.5 0 0 0 10 10z" style={TINT} />
  <path d="M19.5 14.5A8 8 0 1 1 9.5 4.5a6.5 6.5 0 0 0 10 10z" />
  <path d="M17 3.5c.2 1.3.9 2 2.2 2.2-1.3.2-2 .9-2.2 2.2-.2-1.3-.9-2-2.2-2.2 1.3-.2 2-.9 2.2-2.2z" />
</>);
/** Languages: two overlapping bubbles, a Latin A and a Devanagari-style headline. */
export const Languages = make('Languages', <>
  <rect x="3" y="4" width="11" height="9" rx="2.5" style={TINT} />
  <rect x="3" y="4" width="11" height="9" rx="2.5" />
  <path d="m6.5 11 2-5 2 5M7.2 9.5h2.6" />
  <path d="M14 9.5h4.5A2.5 2.5 0 0 1 21 12v5a2.5 2.5 0 0 1-2.5 2.5H18v2l-2.5-2h-3A2.5 2.5 0 0 1 10 17v-1" />
  <path d="M13.5 13.5h5M16 13.5v4M16 15.5c-1.2 0-2 .6-2 1.5" />
</>);

// ── arrows and actions ────────────────────────────────────────────────────

export const ArrowRight = make('ArrowRight', <path d="M4.5 12h15M14 6.5l5.5 5.5-5.5 5.5" />);
export const ArrowLeft = make('ArrowLeft', <path d="M19.5 12h-15M10 6.5 4.5 12l5.5 5.5" />);
export const ArrowUp = make('ArrowUp', <path d="M12 19.5v-15M6.5 10 12 4.5l5.5 5.5" />);
export const ArrowUpRight = make('ArrowUpRight', <path d="M7 17 17 7M8.5 7H17v8.5" />);
export const ChevronsUpDown = make('ChevronsUpDown', <path d="m8 9.5 4-4 4 4M8 14.5l4 4 4-4" />);
export const Plus = make('Plus', <path d="M12 5v14M5 12h14" />);
export const Minus = make('Minus', <path d="M5 12h14" />);
export const Check = make('Check', <path d="m5 12.5 4.5 4.5L19 7.5" />);
export const CheckCircle2 = make('CheckCircle2', <>
  <circle cx="12" cy="12" r="8.5" style={TINT} />
  <circle cx="12" cy="12" r="8.5" />
  <path d="m8.3 12.3 2.5 2.5 5-5.3" />
</>);
export const Circle = make('Circle', <circle cx="12" cy="12" r="8.5" />);
export const Info = make('Info', <>
  <circle cx="12" cy="12" r="8.5" style={TINT} /><circle cx="12" cy="12" r="8.5" />
  <path d="M12 11v5.5" /><circle cx="12" cy="7.8" r="1" style={DOT} />
</>);
export const AlertCircle = make('AlertCircle', <>
  <path d="M10.3 4.3a2 2 0 0 1 3.4 0l7 12.2a2 2 0 0 1-1.7 3H5a2 2 0 0 1-1.7-3z" style={TINT} />
  <path d="M10.3 4.3a2 2 0 0 1 3.4 0l7 12.2a2 2 0 0 1-1.7 3H5a2 2 0 0 1-1.7-3z" />
  <path d="M12 9v4.5" /><circle cx="12" cy="16.5" r="1" style={DOT} />
</>);
/** Loading: three arcs of decreasing weight - spun by an animate-spin class. */
export const Loader2 = make('Loader2', <>
  <path d="M12 3.5a8.5 8.5 0 0 1 8.5 8.5" />
  <path d="M20.5 12a8.5 8.5 0 0 1-8.5 8.5" style={{ opacity: 0.45 }} />
  <path d="M12 20.5A8.5 8.5 0 0 1 3.5 12" style={{ opacity: 0.2 }} />
</>);
export const RefreshCw = make('RefreshCw', <>
  <path d="M19.5 8.5A8 8 0 0 0 5 7.5M4.5 15.5A8 8 0 0 0 19 16.5" />
  <path d="M19.5 4v4.5H15M4.5 20v-4.5H9" />
</>);
export const Search = make('Search', <>
  <circle cx="10.5" cy="10.5" r="6.5" style={TINT} /><circle cx="10.5" cy="10.5" r="6.5" />
  <path d="m15.5 15.5 5 5" />
</>);
export const Eye = make('Eye', <>
  <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" style={TINT} />
  <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" />
  <circle cx="12" cy="12" r="3" />
</>);
export const EyeOff = make('EyeOff', <>
  <path d="M9.9 5.8A9 9 0 0 1 12 5.5c6 0 9.5 6.5 9.5 6.5a16 16 0 0 1-2.4 3.2M6.3 7.3A16.5 16.5 0 0 0 2.5 12S6 18.5 12 18.5a9.2 9.2 0 0 0 4.2-1" />
  <path d="M9.9 9.9a3 3 0 0 0 4.2 4.2M3.5 3.5l17 17" />
</>);
export const Trash2 = make('Trash2', <>
  <path d="M6 7h12l-1 12.5a1.5 1.5 0 0 1-1.5 1.5h-7A1.5 1.5 0 0 1 7 19.5z" style={TINT} />
  <path d="M4 7h16M9.5 7V4.5h5V7M6 7l1 12.5a1.5 1.5 0 0 0 1.5 1.5h7a1.5 1.5 0 0 0 1.5-1.5L18 7M10 11v6M14 11v6" />
</>);
/** Log out: a door ajar with the arrow stepping through it. */
export const LogOut = make('LogOut', <>
  <path d="M13 3.5H6.5a1.5 1.5 0 0 0-1.5 1.5v14a1.5 1.5 0 0 0 1.5 1.5H13" />
  <path d="M5 4 11 6v13l-6 1.5z" style={TINT} />
  <path d="M15 8l4 4-4 4M19 12h-8.5" />
</>);

// ── people, places, time ─────────────────────────────────────────────────

export const User = make('User', <>
  <circle cx="12" cy="8" r="4" style={TINT} /><circle cx="12" cy="8" r="4" />
  <path d="M4.5 20.5a7.5 7.5 0 0 1 15 0" />
</>);
export const KeyRound = make('KeyRound', <>
  <circle cx="8.5" cy="15.5" r="4.5" style={TINT} /><circle cx="8.5" cy="15.5" r="4.5" />
  <path d="m11.7 12.3 8.3-8.3M16.5 7.5l2.5 2.5M14.5 9.5l2 2" />
  <circle cx="7.5" cy="16.5" r="1" style={DOT} />
</>);
/** Place: a map pin holding a leaf. */
export const MapPin = make('MapPin', <>
  <path d="M12 21.5s-7-6-7-11.5a7 7 0 0 1 14 0c0 5.5-7 11.5-7 11.5z" style={TINT} />
  <path d="M12 21.5s-7-6-7-11.5a7 7 0 0 1 14 0c0 5.5-7 11.5-7 11.5z" />
  <path d="M9.8 12c0-2.4 1.5-3.9 4.3-4-.2 2.6-1.7 4-4.3 4zM9.8 12l2.2-2.2" />
</>);
export const LocateFixed = make('LocateFixed', <>
  <circle cx="12" cy="12" r="6.5" style={TINT} /><circle cx="12" cy="12" r="6.5" />
  <path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3" />
  <circle cx="12" cy="12" r="2" style={DOT} />
</>);
export const CalendarDays = make('CalendarDays', <>
  <rect x="3.5" y="5" width="17" height="15.5" rx="2.5" style={TINT} />
  <rect x="3.5" y="5" width="17" height="15.5" rx="2.5" />
  <path d="M3.5 10h17M8 3v4M16 3v4" />
  <circle cx="8" cy="14" r=".9" style={DOT} /><circle cx="12" cy="14" r=".9" style={DOT} /><circle cx="16" cy="14" r=".9" style={DOT} />
  <circle cx="8" cy="17.3" r=".9" style={DOT} /><circle cx="12" cy="17.3" r=".9" style={DOT} />
</>);
export const CalendarCheck = make('CalendarCheck', <>
  <rect x="3.5" y="5" width="17" height="15.5" rx="2.5" style={TINT} />
  <rect x="3.5" y="5" width="17" height="15.5" rx="2.5" />
  <path d="M3.5 10h17M8 3v4M16 3v4M9 15l2 2 4-4" />
</>);
export const CalendarClock = make('CalendarClock', <>
  <path d="M20.5 11V7.5A2.5 2.5 0 0 0 18 5H6a2.5 2.5 0 0 0-2.5 2.5V18A2.5 2.5 0 0 0 6 20.5h5M3.5 10h17M8 3v4M16 3v4" />
  <circle cx="17" cy="17" r="4.5" style={TINT} /><circle cx="17" cy="17" r="4.5" />
  <path d="M17 15v2l1.4 1" />
</>);

// ── measures ──────────────────────────────────────────────────────────────

export const Gauge = make('Gauge', <>
  <path d="M3.5 16a8.5 8.5 0 0 1 17 0z" style={TINT} />
  <path d="M3.5 16a8.5 8.5 0 0 1 17 0M12 16l4-5.5" />
  <circle cx="12" cy="16" r="1.4" style={DOT} />
  <path d="M6 12.5l1 .6M12 7.5v1.2M18 12.5l-1 .6" />
</>);
export const TrendingUp = make('TrendingUp', <>
  <path d="M3 17.5 9 11.5l4 4 7.5-8" />
  <path d="M15.5 7.5h5v5" />
  <path d="M3 20.5h18" style={{ opacity: 0.35 }} />
</>);
export const Zap = make('Zap', <>
  <path d="M13.5 2.5 5 13.5h6l-1 8 8.5-11h-6z" style={TINT} />
  <path d="M13.5 2.5 5 13.5h6l-1 8 8.5-11h-6z" />
</>);
