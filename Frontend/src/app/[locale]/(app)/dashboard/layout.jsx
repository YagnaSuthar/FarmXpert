'use client';

import RequireAuth from '@/components/auth/RequireAuth';
import DashboardShell from '@/components/dashboard/DashboardShell';
import { Skeleton } from '@/components/ui/primitives';
import { FarmProvider } from '@/context/FarmContext';

function ShellSkeleton() {
  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[17.5rem_minmax(0,1fr)]">
      <div className="panel-forest hidden h-dvh lg:block" />
      <div className="container-app space-y-6 py-10">
        <Skeleton className="h-44 rounded-[1.75rem]" />
        <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
          {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-32 rounded-[1.5rem]" />)}
        </div>
      </div>
    </div>
  );
}

export default function DashboardLayout({ children }) {
  return (
    <RequireAuth fallback={<ShellSkeleton />}>
      <FarmProvider>
        <DashboardShell>{children}</DashboardShell>
      </FarmProvider>
    </RequireAuth>
  );
}
