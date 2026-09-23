/**
 * PageTransition Configuration & Timing Constants
 * Single source of truth for all transition durations, delays, and curves.
 */

export const TRANSITION_CONFIG = {
  // Duration for the panels to glide down and cover the viewport (ms)
  enterDuration: 2600,

  // Stagger delays for panels during entry (ms)
  enterStagger: {
    center: 0,
    right: 200,
    left: 400,
  },

  // Minimal buffer once fully covered to ensure destination route DOM is rendered underneath (ms)
  loadingDuration: 350,

  // Duration for the panels to glide up and reveal the destination (ms)
  exitDuration: 2600,

  // Stagger delays for panels during exit (ms)
  exitStagger: {
    center: 0,
    left: 200,
    right: 380,
  },

  // Default title and subtitle text shown during the transition
  defaultTitle: 'Preparing your experience',
  defaultSubtitle: 'Synchronizing multi-agent intelligence',

  // Easing curve constants
  easeOutCubic: 'cubic-bezier(0.22, 1, 0.36, 1)',
  easeInOutCubic: 'cubic-bezier(0.65, 0, 0.35, 1)',
  easeInCubic: 'cubic-bezier(0.32, 0, 0.67, 0)',
};

/* ------------------------------------------------------------------
 * STAGE
 *
 * The transition is atmosphere, not information. There are no labels,
 * readouts or symbols in it — a loading moment that asks to be read is a
 * loading moment that feels long. What carries it is light: drifting
 * aurora, long ribbons of it, motes rising, and rings blooming out of
 * the centre.
 *
 * Coordinates are in the stage's 1600x900 viewBox.
 * ------------------------------------------------------------------ */

/** Where the brand mark sits — everything blooms from here. */
export const STAGE_CENTER = { x: 800, y: 450 };

/**
 * Aurora blobs, in percentages of the viewport. Heavily blurred and
 * slowly drifting, they are what stops the background reading as flat
 * navy. Each carries its own drift duration so they never resynchronise.
 */
export const AURORA = [
  { x: 26, y: 30, size: 62, color: 'var(--tr-mid)',   alpha: 0.5,  dur: 19, delay: 0 },
  { x: 74, y: 26, size: 54, color: 'var(--tr-cyan)',  alpha: 0.24, dur: 23, delay: -6 },
  { x: 18, y: 76, size: 58, color: 'var(--tr-core)',  alpha: 0.6,  dur: 27, delay: -12 },
  { x: 82, y: 72, size: 66, color: 'var(--tr-mid)',   alpha: 0.36, dur: 21, delay: -3 },
  { x: 50, y: 50, size: 46, color: 'var(--tr-cyan)',  alpha: 0.2,  dur: 17, delay: -9 },
];
