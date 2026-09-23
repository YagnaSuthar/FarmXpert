'use client';

import React from 'react';
import { usePageTransition } from './usePageTransition';
import TransitionLayer from './TransitionLayer';
import TransitionField from './TransitionField';
import TransitionLoader from './TransitionLoader';
import TransitionText from './TransitionText';

/**
 * PageTransition - Master orchestrator component
 * Mounts as a full-screen fixed overlay above the whole app during route transitions.
 * Coordinates the staggered non-uniform entrance, the abstract loader stage, and the upward reveal.
 * Every CSS class strictly adheres to the '-loading' suffix rule.
 */
export default function PageTransition() {
  const { state } = usePageTransition();
  const { status, text, subtitle } = state;

  if (status === 'IDLE') {
    return null;
  }

  const isContentVisible = status === 'COVERED' || status === 'ENTERING';

  return (
    <div
      className={`overlay-root-loading status-${status.toLowerCase()}-loading`}
      role="status"
      aria-live="polite"
    >
      <TransitionLayer status={status} />

      {/* the cross-section fills whatever the panels have covered */}
      {isContentVisible && <TransitionField />}

      {isContentVisible && (
        <div className="content-center-loading">
          <TransitionLoader />
          <TransitionText title={text} subtitle={subtitle} />
        </div>
      )}
    </div>
  );
}
