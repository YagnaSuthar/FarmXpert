// FILE: components/ecosystem/AgentTitleDisplay.jsx
import React from 'react';

export default function AgentTitleDisplay({ activeAgent }) {
  if (!activeAgent) return null;

  return (
    <div className={`eco-active-info ${activeAgent ? 'visible' : ''}`}>
      <div className="eco-info-subtitle">Active Agent</div>
      <h2 className="eco-info-title">{activeAgent.title}</h2>
      {/* Could add description or metrics here later */}
    </div>
  );
}
