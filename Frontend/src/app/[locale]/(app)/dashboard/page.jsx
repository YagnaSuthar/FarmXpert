'use client';

import { Suspense } from 'react';

import Overview from '@/components/dashboard/Overview';

export default function DashboardPage() {
  return <Suspense><Overview /></Suspense>;
}
