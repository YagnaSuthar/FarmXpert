// FILE: components/ecosystem/AgentCards.jsx
import React, { useEffect, useState } from 'react';
import AgentCard from './AgentCard';

const agentsList = [
  { id: 'soil', title: 'Soil Health Agent', shape: 'leaf' },
  { id: 'irrigation', title: 'Irrigation AI', shape: 'sphere' },
  { id: 'market', title: 'Market Predictor', shape: 'sphere' },
  { id: 'yield', title: 'Yield Estimator', shape: 'leaf' },
  { id: 'task', title: 'Task Automator', shape: 'sphere' },
  { id: 'map', title: 'Spatial Mapping', shape: 'mapPin' },
  { id: 'orchestrator', title: 'Core Orchestrator', shape: 'sphere' },
  { id: 'voice', title: 'Voice Assistant', shape: 'sphere' },
  { id: 'pest', title: 'Pest Control AI', shape: 'leaf' },
  { id: 'growth', title: 'Growth Modeler', shape: 'leaf' },
  { id: 'crop', title: 'Crop Manager', shape: 'leaf' },
  { id: 'coach', title: 'Farm Coach AI', shape: 'sphere' }
];

export default function AgentCards({ activeAgentId, onAgentClick }) {
  const [positions, setPositions] = useState([]);

  useEffect(() => {
    // Calculate orbital positions
    const calculatePositions = () => {
      const isMobile = window.innerWidth <= 768;
      if (isMobile) {
        // Mobile layout is flex-wrapped, no absolute positioning needed
        setPositions(agentsList.map(() => ({})));
        return;
      }

      // Read radius from CSS variable or use default
      const rootStyle = getComputedStyle(document.documentElement);
      const orbitRadiusStr = rootStyle.getPropertyValue('--eco-orbit-radius').trim() || '350px';
      const radius = parseInt(orbitRadiusStr, 10);
      
      const count = agentsList.length;
      const newPositions = agentsList.map((agent, index) => {
        // Distribute evenly around a circle
        const angle = (index / count) * (2 * Math.PI);
        
        // Add slight organic offset to break perfect symmetry
        const randomOffsetRadius = radius + (Math.sin(index * 42) * 30);
        const randomOffsetAngle = angle + (Math.cos(index * 13) * 0.1);

        const x = Math.cos(randomOffsetAngle) * randomOffsetRadius;
        const y = Math.sin(randomOffsetAngle) * randomOffsetRadius;

        return {
          left: `calc(50% + ${x}px)`,
          top: `calc(50% + ${y}px)`,
        };
      });
      setPositions(newPositions);
    };

    calculatePositions();
    window.addEventListener('resize', calculatePositions);
    return () => window.removeEventListener('resize', calculatePositions);
  }, []);

  return (
    <div className="eco-orbit-system">
      {agentsList.map((agent, index) => (
        <AgentCard 
          key={agent.id}
          agent={agent}
          isActive={activeAgentId === agent.id}
          onClick={onAgentClick}
          style={positions[index] || {}}
        />
      ))}
    </div>
  );
}
