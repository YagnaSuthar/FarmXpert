'use client';

// ============================================================
// FILE: src/reusablefiles/inputbox/InputBox.jsx
//
// Text field / select for the dashboard surfaces.
//
//   <InputBox value={q} onChange={setQ} placeholder={t('search')}
//             icon={<SearchIcon/>} hint="⌘K" />
//   <InputBox as="select" options={roles} value={r} onChange={setR} />
//
// `onChange` receives the VALUE, not the event — every call site was
// unwrapping `e.target.value` anyway. Pass `rawEvent` if the event is
// actually needed.
//
// Holds no user-facing text: label / placeholder / options arrive
// already translated.
// ============================================================

import React, { useId } from 'react';

export default function InputBox({
  as = 'input',
  type = 'text',
  value,
  onChange,
  rawEvent = false,
  label,
  placeholder,
  icon = null,
  hint = null,
  options = [],
  size = 'md',
  invalid = false,
  disabled = false,
  block = true,
  id: idProp,
  className = '',
  ...rest
}) {
  const autoId = useId();
  const id = idProp || autoId;

  const handle = (e) => {
    if (!onChange) return;
    onChange(rawEvent ? e : e.target.value);
  };

  const controlClass = [
    'ui-input',
    `ui-input-${size}`,
    icon ? 'has-icon' : '',
    hint ? 'has-hint' : '',
    invalid ? 'is-invalid' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div
      className={`ui-field${block ? ' is-block' : ''} ${className}`.trim()}
    >
      {label ? (
        <label className="ui-field-label" htmlFor={id}>
          {label}
        </label>
      ) : null}

      <div className="ui-field-control">
        {icon ? <span className="ui-input-icon" aria-hidden="true">{icon}</span> : null}

        {as === 'select' ? (
          <select
            id={id}
            className={controlClass}
            value={value}
            onChange={handle}
            disabled={disabled}
            {...rest}
          >
            {options.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        ) : (
          <input
            id={id}
            type={type}
            className={controlClass}
            value={value}
            onChange={handle}
            placeholder={placeholder}
            disabled={disabled}
            {...rest}
          />
        )}

        {hint ? <kbd className="ui-input-hint">{hint}</kbd> : null}
      </div>
    </div>
  );
}
