// FILE: components/ecosystem/AgentCard.jsx
import React from 'react';

export default function AgentCard({ agent, isActive, onClick, style }) {
  return (
    <div 
      className={`eco-agent-card ${isActive ? 'active' : ''}`}
      style={style}
      onClick={() => onClick(agent)}
    >
      <h4 className="eco-card-title-small">{agent.id}</h4>
      <h3 className="eco-card-title-large">{agent.title}</h3>
    </div>
  );
}
