// ============================================================
// FILE: components/ui/Card.jsx
// Reusable dark glass card component.
// Dark background, rounded corners, border glow on hover.
// ============================================================

'use client';

export default function Card({
  children,
  className = '',
  hoverable = true,
  glass = false,
  onClick,
  onMouseEnter,
  onMouseLeave,
  ...rest
}) {
  const baseClass = glass ? 'glass-card' : 'card';
  const hoverClass = hoverable ? 'card--hoverable' : '';

  return (
    <div
      className={`${baseClass} ${hoverClass} ${className}`}
      onClick={onClick}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      {...rest}
    >
      {children}
    </div>
  );
}
