'use client';

import React from 'react';

/**
 * TransitionLayer - Staggered non-uniform geometric panels
 * - 3 vertical panels (Center, Left, Right) with distinct organic angled clip-paths
 * - Staggered entrance (Center -> Right -> Left) and exit (Center -> Left -> Right)
 * Every CSS class strictly adheres to the '-loading' suffix rule.
 */
export default function TransitionLayer({ status }) {
  const isEntering = status === 'ENTERING';
  const isCovered = status === 'COVERED';
  const isExiting = status === 'EXITING';

  let stageClass = 'stage-idle-loading';
  if (isEntering) stageClass = 'stage-entering-loading';
  else if (isCovered) stageClass = 'stage-covered-loading';
  else if (isExiting) stageClass = 'stage-exiting-loading';

  return (
    <div className={`layer-container-loading ${stageClass}`} aria-hidden="true">
      {/* Background ambient shade */}
      <div className="layer-ambient-shade-loading" />

      {/* Left Staggered Panel */}
      <div className="panel-slice-loading panel-left-loading">
        <div className="panel-gradient-loading" />
        <div className="panel-edge-highlight-loading" />
      </div>

      {/* Right Staggered Panel */}
      <div className="panel-slice-loading panel-right-loading">
        <div className="panel-gradient-loading" />
        <div className="panel-edge-highlight-loading" />
      </div>

      {/* Center Staggered Panel */}
      <div className="panel-slice-loading panel-center-loading">
        <div className="panel-gradient-loading" />
        <div className="panel-edge-highlight-loading" />
      </div>

      {/* Geometric background mesh lines */}
      <div className="layer-geo-grid-loading" />
    </div>
  );
}
