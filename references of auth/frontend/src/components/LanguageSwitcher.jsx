'use client';

// ============================================================
// FILE: src/components/LanguageSwitcher.jsx
//
// Custom styled language switcher with accessible menu,
// smooth animated chevron, and active checkmarks.
// ============================================================

import { useState, useRef, useEffect, useTransition } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { usePathname, useRouter } from '@/i18n/navigation';
import { locales } from '@/i18n/routing';

export default function LanguageSwitcher() {
  const t = useTranslations('languageSwitcher');
  const router = useRouter();
  const pathname = usePathname();
  const activeLocale = useLocale();
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef(null);
  const buttonRef = useRef(null);
  const [isPending, startTransition] = useTransition();

  // Close dropdown on outside click or Escape key
  useEffect(() => {
    function handleClickOutside(e) {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setIsOpen(false);
      }
    }
    function handleKeyDown(e) {
      if (e.key === 'Escape') {
        setIsOpen(false);
        buttonRef.current?.focus();
      }
    }
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      document.addEventListener('keydown', handleKeyDown);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen]);

  function selectLocale(nextLocale) {
    setIsOpen(false);
    if (nextLocale === activeLocale) return;
    startTransition(() => {
      router.replace(pathname, { locale: nextLocale });
    });
  }

  return (
    <div
      ref={containerRef}
      className={`lang-switcher ${isOpen ? 'is-open' : ''}`}
      data-pending={isPending || undefined}
    >
      <button
        ref={buttonRef}
        type="button"
        className="lang-switcher__btn"
        onClick={() => setIsOpen((prev) => !prev)}
        disabled={isPending}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-label={t('label')}
      >
        <span className="lang-switcher__btn-text">{t(activeLocale)}</span>
        <svg
          className={`lang-switcher__chevron ${isOpen ? 'is-open' : ''}`}
          width="12"
          height="12"
          viewBox="0 0 12 12"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          <path
            d="M2.5 4.5L6 8L9.5 4.5"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>

      {isOpen && (
        <div className="lang-switcher__menu" role="listbox" aria-label={t('label')}>
          {locales.map((code) => {
            const isSelected = code === activeLocale;
            return (
              <button
                key={code}
                type="button"
                role="option"
                aria-selected={isSelected}
                className={`lang-switcher__option ${isSelected ? 'is-active' : ''}`}
                onClick={() => selectLocale(code)}
              >
                <span>{t(code)}</span>
                {isSelected && (
                  <svg
                    className="lang-switcher__check"
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

