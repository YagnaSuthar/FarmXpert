import createMiddleware from 'next-intl/middleware';
import { NextResponse } from 'next/server';
import { routing } from './i18n/routing';

const handleI18nRouting = createMiddleware(routing);

export default function middleware(req) {
  const { pathname } = req.nextUrl;
  const sid = req.cookies.get('sid')?.value;
  const refreshToken = req.cookies.get('refreshToken')?.value;
  const isAuthenticated = Boolean(sid || refreshToken);

  // Match any auth routes: /auth/login, /en/auth/login, /hi/auth/login, /gu/auth/login, etc.
  const isAuthPath = /\/(en|hi|gu)\/auth(\/|$)/.test(pathname) || /^\/auth(\/|$)/.test(pathname);

  // If authenticated user attempts to visit auth pages (login/register/forgot), redirect immediately at HTTP layer
  if (isAuthenticated && isAuthPath) {
    const match = pathname.match(/^\/(en|hi|gu)/);
    const locale = match ? match[1] : 'en';
    return NextResponse.redirect(new URL(`/${locale}/dashboard`, req.url));
  }

  return handleI18nRouting(req);
}

export const config = {
  matcher: [
    '/((?!api|_next|_vercel|.*\\..*).*)',
  ],
};
