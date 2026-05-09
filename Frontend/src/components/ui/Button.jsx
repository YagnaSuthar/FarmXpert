'use client';

import React from 'react';

export default function Button({
  children,
  variant = 'primary',
  size = 'md',
  className = '',
  type = 'button',
  onClick,
  disabled = false,
  ...rest
}) {
  const variantClass = variant === 'ghost' ? 'btn--ghost' : 'btn--primary';
  const sizeClass = size === 'lg' ? 'btn--lg' : size === 'sm' ? 'btn--sm' : 'btn--md';

  return (
    <button
      type={type}
      className={`btn ${variantClass} ${sizeClass} ${disabled ? 'btn--disabled' : ''} ${className}`}
      onClick={onClick}
      disabled={disabled}
      {...rest}
    >
      {children}
    </button>
  );
}
