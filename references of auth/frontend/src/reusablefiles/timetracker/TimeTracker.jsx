'use client';

// ============================================================
// FILE: src/reusablefiles/timetracker/TimeTracker.jsx
//
// Running timer on the generative navy surface.
//
//   <TimeTracker title={t('timeTracker.title')}
//                task={t('timeTracker.task')}
//                initialSeconds={5048}
//                onStop={handleStop} />
//
// Uncontrolled by default (it owns the tick) but every transition is
// reported upward through onPause / onResume / onStop / onTick, so a
// page can persist the session whenever a backend exists for it.
//
// All labels arrive translated — this component holds no copy.
// ============================================================

import React, { useCallback, useEffect, useRef, useState } from 'react';
import Card from '@/reusablefiles/card/Card';
import GenerativeTexture from '@/reusablefiles/texture/GenerativeTexture';

const pad = (n) => String(n).padStart(2, '0');

export const formatDuration = (total) => {
  const s = Math.max(0, Math.floor(total));
  return `${pad(Math.floor(s / 3600))}:${pad(Math.floor(s / 60) % 60)}:${pad(s % 60)}`;
};

export default function TimeTracker({
  title,
  task,
  initialSeconds = 0,
  autoStart = true,
  span = 3,
  pauseLabel = 'Pause',
  resumeLabel = 'Resume',
  stopLabel = 'Stop',
  onTick,
  onPause,
  onResume,
  onStop,
  className = '',
}) {
  const [seconds, setSeconds] = useState(initialSeconds);
  const [running, setRunning] = useState(autoStart);
  // Kept in a ref so the interval always calls the latest handler
  // without the interval itself restarting on every parent render.
  const tickRef = useRef(onTick);
  useEffect(() => { tickRef.current = onTick; }, [onTick]);

  useEffect(() => {
    if (!running) return undefined;
    const id = setInterval(() => {
      setSeconds((prev) => {
        const next = prev + 1;
        if (tickRef.current) tickRef.current(next);
        return next;
      });
    }, 1000);
    return () => clearInterval(id);
  }, [running]);

  const toggle = useCallback(() => {
    setRunning((prev) => {
      const next = !prev;
      if (next) onResume?.(seconds);
      else onPause?.(seconds);
      return next;
    });
  }, [onPause, onResume, seconds]);

  const stop = useCallback(() => {
    setRunning(false);
    setSeconds(0);
    onStop?.(seconds);
  }, [onStop, seconds]);

  return (
    <Card tone="deep" span={span} className={`ui-tracker ${className}`.trim()}>
      <GenerativeTexture variant="tracker" />

      <div className="ui-tracker-inner">
        <h3 className="ui-tracker-title">{title}</h3>

        <div className="ui-tracker-read">
          <div className="ui-tracker-clock" role="timer" aria-live="off">
            {formatDuration(seconds)}
          </div>
          {task ? <div className="ui-tracker-task">{task}</div> : null}
        </div>

        <div className="ui-tracker-controls">
          <button
            type="button"
            className="ui-tracker-btn is-toggle"
            onClick={toggle}
            aria-label={running ? pauseLabel : resumeLabel}
          >
            <svg width="19" height="19" viewBox="0 0 24 24" aria-hidden="true">
              {running ? (
                <>
                  <rect x="6.5" y="4.5" width="4" height="15" rx="1.4" />
                  <rect x="13.5" y="4.5" width="4" height="15" rx="1.4" />
                </>
              ) : (
                <path d="M8 5.2v13.6l11-6.8-11-6.8Z" />
              )}
            </svg>
          </button>

          <button
            type="button"
            className="ui-tracker-btn is-stop"
            onClick={stop}
            aria-label={stopLabel}
          >
            <svg width="17" height="17" viewBox="0 0 24 24" aria-hidden="true">
              <rect x="4.5" y="4.5" width="15" height="15" rx="3.4" />
            </svg>
          </button>
        </div>
      </div>
    </Card>
  );
}
