// FILE: components/ecosystem/AgentOrbitSystem.jsx
'use client';

import React, { useState } from 'react';
import AgentCards from './AgentCards';
import CenterCore from './CenterCore';
import AgentTitleDisplay from './AgentTitleDisplay';
import '@/styles/ecosystem.css';
import '@/styles/cards.css';

export default function AgentOrbitSystem({ systemRef }) {
  const [activeAgent, setActiveAgent] = useState(null);

  const handleAgentClick = (agent) => {
    // Toggle off if clicking the already active agent, or set new active
    if (activeAgent?.id === agent.id) {
      setActiveAgent(null);
    } else {
      setActiveAgent(agent);
    }
  };

  // Determine what shape the core should morph into
  // Default to 'sphere' if no agent is active, otherwise use the agent's specific shape
  const activeShape = activeAgent ? activeAgent.shape : 'sphere';

  return (
    <section className="eco-container">
      {/* Background ambient lighting */}
      <div className="eco-ambient-bg"></div>
      <div className="eco-ambient-lines"></div>

      {/* Center 3D Particle Core */}
      <CenterCore activeShape={activeShape} globalSystemRef={systemRef} />

      {/* Orbiting Agent Cards */}
      <AgentCards 
        activeAgentId={activeAgent?.id} 
        onAgentClick={handleAgentClick} 
      />

      {/* Floating Active Title Display */}
      <AgentTitleDisplay activeAgent={activeAgent} />
    </section>
  );
}
