'use client';

import React from 'react';

/**
 * TransitionText - Animated character-reveal typography
 * Splits title text into individual span characters with staggered entrance and subtle luminous glow.
 * Every CSS class strictly adheres to the '-loading' suffix rule.
 */
export default function TransitionText({ title, subtitle }) {
  const characters = Array.from(title || '');

  return (
    <div className="text-container-loading">
      <h3 className="text-title-loading" aria-label={title}>
        {characters.map((char, index) => (
          <span
            key={index}
            className="text-char-loading"
            style={{
              animationDelay: `${index * 32 + 100}ms`,
            }}
          >
            {char === ' ' ? '\u00A0' : char}
          </span>
        ))}
      </h3>

      {subtitle && (
        <p className="text-subtitle-loading">
          <span className="text-pulse-dot-loading" />
          {subtitle}
        </p>
      )}
    </div>
  );
}
