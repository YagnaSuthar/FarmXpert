// FILE: components/ecosystem/CenterCore.jsx
import React, { useRef, useEffect } from 'react';
import ParticleCanvas from '../animation/particlecanvas';

export default function CenterCore({ activeShape = 'sphere', globalSystemRef }) {
  const localSystemRef = useRef(null);
  const activeRef = globalSystemRef || localSystemRef;

  // When activeShape changes, tell ParticleSystem to morph
  useEffect(() => {
    if (activeRef.current && typeof activeRef.current.morphTo === 'function') {
      activeRef.current.morphTo(activeShape);
    }
  }, [activeShape, activeRef]);

  return (
    <div className="eco-center-wrapper">
      <div className="eco-center-halo"></div>
      {!globalSystemRef && (
        <ParticleCanvas 
          systemRef={localSystemRef} 
          autoMorph={false} // We control morphing via state now
          className="eco-particle-canvas"
        />
      )}
    </div>
  );
}
