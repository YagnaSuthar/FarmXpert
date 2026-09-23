'use client';

import React, { useEffect, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from '@/i18n/navigation';
import { useAuth, getDashboardPath } from '@/context/AuthContext';

/**
 * ProtectedRoute Component
 *
 * Client-side guard for UX protection:
 * - Redirects unauthenticated users to /auth/login
 * - Redirects authenticated users with mismatched role to their correct dashboard
 * - Prevents flash of protected content
 *
 * Uses a ref for router to prevent the redirect effect from re-firing
 * when the router object's identity changes across renders.
 *
 * NOTE: Backend authorization (RBAC) remains the actual security boundary.
 */
export default function ProtectedRoute({ children, allowedRoles = [] }) {
  const t = useTranslations('dashboard');
  const { user, role, loading, isAuthenticated } = useAuth();
  const router = useRouter();
  const routerRef = useRef(router);
  routerRef.current = router;

  useEffect(() => {
    if (loading) return;

    if (!isAuthenticated) {
      routerRef.current.replace('/auth/login');
      return;
    }

    if (allowedRoles.length > 0 && role && !allowedRoles.includes(role)) {
      const correctDashboard = getDashboardPath(role);
      routerRef.current.replace(correctDashboard);
    }
    // router is accessed via stable ref — not needed in deps
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, isAuthenticated, role, allowedRoles]);

  if (loading) {
    return (
      <div className="dashboard-viewport-dash">
        <div className="dashboard-loading-dash">
          <span>{t('common.loading')}</span>
        </div>
      </div>
    );
  }

  if (!isAuthenticated || (allowedRoles.length > 0 && !allowedRoles.includes(role))) {
    return null;
  }

  return <>{children}</>;
}
