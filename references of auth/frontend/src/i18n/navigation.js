// ============================================================
// FILE: src/i18n/navigation.js
//
// Locale-aware navigation primitives. Always import Link / useRouter /
// usePathname / redirect / getPathname from THIS file inside the app,
// never from `next/link` or `next/navigation` directly — otherwise the
// locale prefix won't be respected.
//
// Wrong:
//   import Link from 'next/link';
//   <Link href="/auth/register">...</Link>     // breaks /hi/auth/register
//
// Right:
//   import { Link } from '@/i18n/navigation';
//   <Link href="/auth/register">...</Link>     // resolves per active locale
// ============================================================

import { createNavigation } from 'next-intl/navigation';
import { routing } from './routing';

export const {
  Link,
  redirect,
  usePathname,
  useRouter,
  getPathname,
} = createNavigation(routing);
