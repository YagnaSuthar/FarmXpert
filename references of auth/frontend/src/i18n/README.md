# FarmXpert i18n — Architecture & Guide

This document covers the multilingual system for the **landing page only** —
backend, agent responses, dashboard, and admin panel are explicitly out of
scope at this point. The architecture is designed so those can be layered on
without touching this code.

---

## 1. Stack

| Concern | Tool |
|---|---|
| Framework | Next.js 16 (App Router) |
| Translation runtime | [`next-intl`](https://next-intl.dev) v4 |
| Message format | ICU MessageFormat (placeholders, plurals, select) |
| Persistence | `NEXT_LOCALE` cookie (1y), written by middleware |
| Detection | URL prefix → cookie → `Accept-Language` → defaultLocale |
| Type safety | `IntlMessages` augmented from `en.json` via `src/global.d.ts` |

## 2. File layout

```
Frontend/
├── next.config.mjs              ← wraps config with createNextIntlPlugin
├── jsconfig.json                ← resolveJsonModule + @/* path alias
└── src/
    ├── app/
    │   ├── [locale]/
    │   │   ├── layout.jsx       ← root layout (owns <html>/<body>),
    │   │   │                       loads messages, injects provider,
    │   │   │                       generateStaticParams + generateMetadata
    │   │   └── page.jsx         ← landing page entry
    │   ├── globals.css
    │   └── favicon.ico
    ├── i18n/
    │   ├── routing.js           ← locales, defaultLocale, cookie config
    │   ├── navigation.js        ← locale-aware Link, useRouter, redirect
    │   ├── request.js           ← server-side message loader (lazy import)
    │   └── README.md            ← (this file)
    ├── messages/
    │   ├── en.json              ← canonical source of truth
    │   ├── hi.json
    │   └── gu.json
    ├── providers/
    │   └── locale-provider.jsx  ← NextIntlClientProvider wrapper
    ├── components/
    │   ├── LanguageSwitcher.jsx
    │   ├── Navbar.jsx           ← consumes navbar.*
    │   ├── Footer.jsx           ← consumes footer.*
    │   └── landingpage/
    │       ├── HeroSection.jsx
    │       ├── AgentsSection.jsx
    │       ├── FeaturesSection.jsx
    │       ├── HowItWorksSection.jsx
    │       ├── TechSection.jsx
    │       ├── ChipSceneSection.jsx
    │       └── CTASection.jsx
    ├── middleware.js            ← createMiddleware(routing)
    └── global.d.ts              ← IntlMessages declaration for IDE intel
```

## 3. URL strategy

`localePrefix: 'as-needed'` gives:

| Route | English | Hindi | Gujarati |
|---|---|---|---|
| Landing | `/` | `/hi` | `/gu` |
| Future `/about` | `/about` | `/hi/about` | `/gu/about` |

The default locale (English) has no prefix → cleaner canonical URLs for SEO.
Non-default locales always carry their prefix → easy to share, easy to index.

## 4. How locale is selected on every request

1. **URL prefix** wins (`/hi/...` → Hindi)
2. **`NEXT_LOCALE` cookie** (set by middleware when the user picks a language)
3. **`Accept-Language` header** (browser preference)
4. **`defaultLocale`** from `routing.js` (currently `en`)

The middleware persists the user's choice on every successful match, so the
next visit lands on the right locale without any extra logic in the app.

## 5. Adding a new locale

Worked example: adding **Bengali (`bn`)**.

1. **Register the code** in `src/i18n/routing.js`:
   ```js
   export const locales = ['en', 'hi', 'gu', 'bn'];
   ```
2. **Add the message bundle**:
   - Copy `src/messages/en.json` to `src/messages/bn.json`.
   - Translate values, **keep all keys identical** to `en.json`.
3. **Add a label** in every existing message file (so the language
   switcher renders Bengali's name in every locale's UI):
   ```jsonc
   "languageSwitcher": {
     ...
     "bn": "বাংলা"
   }
   ```
4. **(Optional) Localize the brand wordmark** — leave proper nouns
   (e.g. tech stack names, the FarmXpert logo) in their original
   Latin spelling unless brand guidance says otherwise.
5. Rebuild. `generateStaticParams` picks up the new locale automatically;
   `generateMetadata` will produce SEO for it; the middleware will route
   `/bn/...` correctly. **No component code needs to change.**

If you add a key that exists in `en.json` but is missing in `bn.json`,
`LocaleProvider`'s `getMessageFallback` will render the key path
(`hero.titleParts.before`) in production, and throw loudly in development,
so translator gaps are obvious before release.

## 6. Adding new translatable copy

Worked example: adding a hero subhead.

1. Add the key to **every** message file under the matching namespace:
   ```jsonc
   // en.json
   "hero": {
     ...
     "subhead": "AI agents, working the field with you."
   }
   ```
   ```jsonc
   // hi.json
   "hero": { ..., "subhead": "AI एजेंट, आपके खेत में आपके साथ।" }
   ```
2. Consume in the component:
   ```jsx
   const t = useTranslations('hero');
   <p className="hero-subhead">{t('subhead')}</p>
   ```
3. If you're in TS (or VS Code with this project's jsconfig), the key
   autocompletes against the `en.json` shape. Typos light up red.

## 7. ICU placeholders

For dynamic values, use the ICU `{name}` syntax:

```jsonc
"footer": {
  "copyright": "© {year} FarmXpert. AI-powered precision agriculture."
}
```

```jsx
t('copyright', { year: new Date().getFullYear() });
```

For pluralization later (e.g. notifications), use ICU `plural`:

```jsonc
"notifications": {
  "count": "{count, plural, =0 {no notifications} one {# notification} other {# notifications}}"
}
```

next-intl handles the locale-correct plural rules automatically.

## 8. Server Components vs Client Components

| Where | Hook |
|---|---|
| Server Component (`page.jsx`, `layout.jsx`, metadata) | `await getTranslations({ locale, namespace })` from `next-intl/server` |
| Client Component (`'use client'`) | `useTranslations('namespace')` from `next-intl` |

The provider in `src/providers/locale-provider.jsx` is what makes the
client hook work — it ships the resolved messages down via React context.
Don't import it into Server Components; they read messages directly
from `getTranslations`.

## 9. Navigation (do **not** import from `next/link`)

```diff
- import Link from 'next/link';
- import { useRouter, usePathname } from 'next/navigation';
+ import { Link, useRouter, usePathname } from '@/i18n/navigation';
```

This guarantees the active locale prefix follows the user. Skipping this
is the #1 source of broken locale routing.

External links (`href="https://..."`) and same-page anchor links
(`href="#agents"`) stay on the native `<a>` element — they don't need
locale-aware routing.

## 10. Metadata (SEO)

`generateMetadata` in `[locale]/layout.jsx` produces per-locale
`<title>`, `<meta description>`, OG cards, and `alternates.languages`.
Search engines see localized SERPs without any duplication penalty.

To customize per-page metadata (e.g. a dedicated `/about` page), add
`generateMetadata` to that page file using the same pattern.

## 11. Performance notes

- **Lazy loading**: `src/i18n/request.js` does a dynamic `import()`
  keyed by locale. A user on `/hi` never downloads `en.json` or `gu.json`.
- **Static rendering**: `setRequestLocale(locale)` in every page/layout
  keeps the route statically renderable, so Next caches the HTML per
  locale.
- **Bundle size**: next-intl tree-shakes to ~6 kB gzipped for the client
  runtime. Messages are JSON, gzip-compressible.

## 12. Out-of-scope (deliberate)

Per the brief, these are **not** wired up here:

- Backend / API translation
- AI / agent response translation
- Dashboard or admin panel
- Mobile apps

The architecture is designed so these can plug in later without rework.
For example, when the dashboard arrives, mirror the same `[locale]`
segment structure under `app/[locale]/dashboard/...` — it'll share
the same messages, provider, middleware, and switcher with no changes.

## 13. Sanity check

After cloning or pulling, verify the system end-to-end:

```bash
cd Frontend
npm install                    # picks up next-intl
npm run dev
```

Then in the browser:

1. Visit `/` → should render English. URL stays at `/`.
2. Use the language switcher → URL becomes `/hi` or `/gu`, page swaps.
3. Open DevTools → Application → Cookies → `NEXT_LOCALE` is set.
4. Refresh — language sticks.
5. Reset by deleting the cookie; `Accept-Language` should pick the closest
   locale or fall back to English.

If any step fails, the most common culprits are:

- Importing `Link` from `next/link` instead of `@/i18n/navigation`.
- A new key in `en.json` that wasn't mirrored in `hi.json`/`gu.json`.
- Forgetting `'use client'` on a component that calls `useTranslations()`.
