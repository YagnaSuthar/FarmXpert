// ============================================================
// FILE: src/global.d.ts
//
// Even though this project is JavaScript, this declaration file
// gives VS Code (and any editor running tsserver) end-to-end
// autocomplete on translation keys:
//
//   const t = useTranslations('hero');
//   t('description')           ← suggested
//   t('descripshun')           ← red-underlined typo
//
// next-intl reads the `IntlMessages` interface to type-check
// t() calls. We point it at the shape of en.json — by convention
// English is the canonical source of truth; every other locale
// must mirror its key tree (the docs/i18n.md migration guide
// covers how to keep them in sync).
//
// Note: this file is intentionally a .ts file. JS projects can
// include .d.ts files without converting any source code; tsc
// is run in --noEmit mode purely for IDE intel.
// ============================================================

import type messages from './messages/en.json';

declare global {
  // eslint-disable-next-line @typescript-eslint/no-empty-object-type
  interface IntlMessages extends RemoveReadonly<typeof messages> {}
}

// Strip the `readonly` modifier JSON imports add — next-intl's
// types expect a mutable shape so this conversion is purely cosmetic.
type RemoveReadonly<T> = {
  -readonly [K in keyof T]: T[K] extends object ? RemoveReadonly<T[K]> : T[K];
};

export {};
