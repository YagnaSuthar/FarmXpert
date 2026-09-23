// ============================================================
// FILE: src/app/[locale]/(app)/layout.jsx
//
// Shell for the signed-in app: auth pages, onboarding, dashboard.
// A route group, so the URLs stay /auth/login, /dashboard, ...
//
//  - Fonts (Aaurawell): Playfair Display for headings, Poppins for
//    text (it covers Devanagari, so Hindi and Marathi read natively),
//    Noto Sans Gujarati for Gujarati, Allura for the script accents.
//  - Theme: read from the fx_theme cookie so the first paint is right.
//  - Session: <AuthProvider> restores it with one silent refresh.
// ============================================================

import { Allura, Noto_Sans_Gujarati, Playfair_Display, Poppins } from 'next/font/google';
import { cookies } from 'next/headers';
import { setRequestLocale } from 'next-intl/server';

import { AuthProvider } from '@/context/AuthContext';
import { THEME_COOKIE, ThemeProvider } from '@/components/theme/ThemeProvider';
import '@/styles/app.css';

const playfair = Playfair_Display({ subsets: ['latin'], variable: '--font-playfair', display: 'swap' });
const poppins = Poppins({
  subsets: ['latin', 'devanagari'], weight: ['300', '400', '500', '600'], variable: '--font-poppins', display: 'swap',
});
const gujarati = Noto_Sans_Gujarati({
  subsets: ['gujarati'], weight: ['400', '500', '600'], variable: '--font-indic', display: 'swap',
});
const allura = Allura({ subsets: ['latin'], weight: '400', variable: '--font-allura', display: 'swap' });

export const metadata = {
  robots: { index: false, follow: false },   // private pages: never in search results
};

export default async function AppLayout({ children, params }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const saved = (await cookies()).get(THEME_COOKIE)?.value;
  const initial = ['light', 'dark', 'system'].includes(saved) ? saved : 'system';
  return (
    <ThemeProvider initial={initial}
      className={`${playfair.variable} ${poppins.variable} ${gujarati.variable} ${allura.variable}`}>
      <AuthProvider>{children}</AuthProvider>
    </ThemeProvider>
  );
}
