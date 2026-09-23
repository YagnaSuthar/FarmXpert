'use client';

// ============================================================
// FILE: src/components/ui/primitives.jsx
// The small pieces every app screen is built from. Pill buttons,
// soft inputs, forest panels: the Aaurawell language, in both themes.
// ============================================================

import { forwardRef, useId, useState } from 'react';
import { AlertCircle, CheckCircle2, Eye, EyeOff, Info, Loader2 } from 'lucide-react';

import { Link } from '@/i18n/navigation';
import { cn } from '@/lib/cn';

// ── buttons ─────────────────────────────────────────────────────────────────

const VARIANTS = {
  primary: 'bg-forest text-on-forest hover:bg-forest-deep shadow-card hover:shadow-soft',
  gold: 'bg-gold text-forest-deep hover:brightness-105 shadow-card',
  outline: 'border border-forest/70 text-forest hover:bg-forest hover:text-on-forest dark:text-leaf dark:border-leaf/60',
  light: 'bg-raised text-forest hover:bg-sage dark:text-ink',
  ghost: 'text-muted hover:text-ink hover:bg-sage',
  danger: 'bg-danger text-white hover:brightness-110',
};
const SIZES = {
  sm: 'h-9 px-4 text-xs gap-1.5',
  md: 'h-11 px-6 text-sm gap-2',
  lg: 'h-13 px-8 text-[0.95rem] gap-2.5',
  icon: 'h-10 w-10',
};

export const Button = forwardRef(function Button(
  { href, variant = 'primary', size = 'md', loading = false, className, children, disabled, ...props }, ref,
) {
  const classes = cn(
    'inline-flex shrink-0 items-center justify-center rounded-full font-medium tracking-[0.01em]',
    'transition-all duration-200 active:scale-[0.98] disabled:pointer-events-none disabled:opacity-55',
    VARIANTS[variant], SIZES[size], className,
  );
  if (href) {
    return <Link href={href} className={classes} {...props}>{children}</Link>;
  }
  return (
    <button ref={ref} className={classes} disabled={disabled || loading} aria-busy={loading || undefined} {...props}>
      {loading && <Loader2 className="size-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
});

// ── fields ──────────────────────────────────────────────────────────────────

export const inputClass = cn(
  'w-full rounded-2xl border border-line bg-surface px-4 py-3 text-[0.95rem] text-ink',
  'placeholder:text-faint transition-colors duration-150',
  'hover:border-leaf/40 focus:border-leaf focus:bg-raised focus:outline-none focus:ring-4 focus:ring-leaf/10',
  'aria-[invalid=true]:border-danger aria-[invalid=true]:ring-danger/10 disabled:opacity-60',
);

export function Field({ label, hint, error, optional, icon: Icon, className, children, id: givenId }) {
  const auto = useId();
  const id = givenId || auto;
  return (
    <div className={className}>
      {label && (
        <label htmlFor={id} className="mb-1.5 flex items-baseline justify-between gap-2 text-sm font-medium text-ink">
          <span>{label}</span>
          {optional && <span className="text-xs font-normal text-faint">{optional}</span>}
        </label>
      )}
      <div className="relative">
        {Icon && <Icon className="pointer-events-none absolute top-1/2 left-4 size-[1.1rem] -translate-y-1/2 text-faint" aria-hidden />}
        {children({ id, 'aria-invalid': error ? 'true' : undefined,
          'aria-describedby': error ? `${id}-error` : hint ? `${id}-hint` : undefined,
          className: cn(inputClass, Icon && 'pl-11') })}
      </div>
      {error ? (
        <p id={`${id}-error`} className="mt-1.5 flex items-center gap-1.5 text-xs text-danger">
          <AlertCircle className="size-3.5 shrink-0" aria-hidden />{error}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="mt-1.5 text-xs text-faint">{hint}</p>
      ) : null}
    </div>
  );
}

export function TextField({ label, hint, error, optional, icon, className, ...input }) {
  return (
    <Field label={label} hint={hint} error={error} optional={optional} icon={icon} className={className} id={input.id}>
      {(p) => <input {...p} {...input} />}
    </Field>
  );
}

export function PasswordField({ label, hint, error, showLabel = 'Show', hideLabel = 'Hide', icon, className, ...input }) {
  const [visible, setVisible] = useState(false);
  return (
    <Field label={label} hint={hint} error={error} icon={icon} className={className} id={input.id}>
      {(p) => (
        <>
          <input {...p} {...input} type={visible ? 'text' : 'password'} className={cn(p.className, 'pr-12')} />
          <button
            type="button"
            onClick={() => setVisible((v) => !v)}
            className="absolute top-1/2 right-2 grid size-9 -translate-y-1/2 place-items-center rounded-full text-faint hover:bg-sage hover:text-ink"
            aria-label={visible ? hideLabel : showLabel}
            aria-pressed={visible}
          >
            {visible ? <EyeOff className="size-4.5" /> : <Eye className="size-4.5" />}
          </button>
        </>
      )}
    </Field>
  );
}

export function SelectField({ label, hint, error, optional, options, placeholder, className, ...select }) {
  return (
    <Field label={label} hint={hint} error={error} optional={optional} className={className} id={select.id}>
      {(p) => (
        <select {...p} {...select} className={cn(p.className, 'appearance-none bg-[length:1.1rem] bg-[right_1rem_center] bg-no-repeat pr-10')}
          style={{ backgroundImage: 'url("data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 viewBox=%270 0 24 24%27 fill=%27none%27 stroke=%27%238c968e%27 stroke-width=%272%27%3E%3Cpath d=%27m6 9 6 6 6-6%27/%3E%3C/svg%3E")' }}>
          {placeholder && <option value="">{placeholder}</option>}
          {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      )}
    </Field>
  );
}

/** A row of pill toggles: single choice (value) or many (values). */
export function ChoiceChips({ options, value, values, onChange, multiple = false, className, label }) {
  const selected = (v) => (multiple ? values?.includes(v) : value === v);
  return (
    <div role={multiple ? 'group' : 'radiogroup'} aria-label={label} className={cn('flex flex-wrap gap-2', className)}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role={multiple ? 'checkbox' : 'radio'}
          aria-checked={selected(o.value)}
          onClick={() => onChange(multiple
            ? (selected(o.value) ? values.filter((v) => v !== o.value) : [...(values || []), o.value])
            : o.value)}
          className={cn(
            'inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm transition-all duration-150',
            selected(o.value)
              ? 'border-forest bg-forest text-on-forest shadow-card dark:border-leaf dark:bg-forest'
              : 'border-line bg-surface text-muted hover:border-leaf/50 hover:text-ink',
          )}
        >
          {o.icon && <o.icon className="size-4" aria-hidden />}
          {o.label}
        </button>
      ))}
    </div>
  );
}

// ── feedback ────────────────────────────────────────────────────────────────

const ALERT = {
  error: { icon: AlertCircle, cls: 'border-danger/25 bg-danger/8 text-danger' },
  success: { icon: CheckCircle2, cls: 'border-leaf/30 bg-sage text-leaf' },
  info: { icon: Info, cls: 'border-gold/30 bg-gold-soft/60 text-ink' },
};

export function Alert({ tone = 'error', children, className }) {
  if (!children) return null;
  const { icon: Icon, cls } = ALERT[tone];
  return (
    <div role={tone === 'error' ? 'alert' : 'status'}
      className={cn('flex items-start gap-3 rounded-2xl border px-4 py-3 text-sm animate-rise', cls, className)}>
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div className="leading-relaxed">{children}</div>
    </div>
  );
}

export function Card({ className, children, as: Tag = 'section', ...props }) {
  return (
    <Tag className={cn('rounded-[1.75rem] border border-line bg-surface shadow-card', className)} {...props}>
      {children}
    </Tag>
  );
}

/** Gold hairline divider with an optional centred label: "── SUPPORT ──". */
export function Eyebrow({ children, className, line = true }) {
  return (
    <p className={cn('eyebrow flex items-center gap-3 text-gold', className)}>
      {line && <span className="h-px w-8 bg-gold/60" aria-hidden />}
      {children}
      {line && <span className="h-px w-8 bg-gold/60" aria-hidden />}
    </p>
  );
}

export function Skeleton({ className }) {
  return <div className={cn('skeleton rounded-xl', className)} aria-hidden />;
}
