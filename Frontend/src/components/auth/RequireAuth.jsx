'use client';

// ============================================================
// FILE: src/components/auth/RequireAuth.jsx
// Guards a signed-in page. While the session is being restored it
// shows `fallback` (a skeleton), never the login form flashing past.
//   signed out          -> /auth/login?next=<this page>
//   signed in, new user -> /onboarding (unless this IS onboarding)
// ============================================================

import { useEffect } from 'react';

import { usePathname, useRouter } from '@/i18n/navigation';
import { useAuth } from '@/context/AuthContext';

export default function RequireAuth({ children, onboarding = false, fallback = null }) {
  const { status, user } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (status === 'anonymous') {
      router.replace(`/auth/login?next=${encodeURIComponent(pathname)}`);
    } else if (status === 'authenticated' && !onboarding && !user?.onboarded) {
      router.replace('/onboarding');
    }
  }, [status, user, onboarding, router, pathname]);

  if (status !== 'authenticated' || (!onboarding && !user?.onboarded)) return fallback;
  return children;
}
