'use client';

import { Suspense } from 'react';

import Assistant from '@/components/dashboard/Assistant';

export default function AssistantPage() {
  return <Suspense><Assistant /></Suspense>;
}
