'use client';

import React, { createContext, useContext, useState, useCallback, useRef } from 'react';
import { useRouter } from '@/i18n/navigation';
import { TRANSITION_CONFIG } from './transition.config';

const PageTransitionContext = createContext(null);

export function PageTransitionProvider({ children }) {
  const router = useRouter();
  const [state, setState] = useState({
    status: 'IDLE', // 'IDLE' | 'ENTERING' | 'COVERED' | 'EXITING'
    text: TRANSITION_CONFIG.defaultTitle,
    subtitle: TRANSITION_CONFIG.defaultSubtitle,
    duration: TRANSITION_CONFIG.loadingDuration,
  });

  const callbacksRef = useRef({
    onCovered: null,
    onComplete: null,
    targetRoute: null,
    replace: false,
  });

  const trigger = useCallback(
    ({ to, replace = false, text, subtitle, duration, onCovered, onComplete } = {}) => {
      if (state.status !== 'IDLE') return;

      callbacksRef.current = {
        onCovered,
        onComplete,
        targetRoute: to,
        replace,
      };

      const loadDuration = duration || TRANSITION_CONFIG.loadingDuration;

      // 1. Start Entry Animation (Top -> Downwards)
      setState({
        status: 'ENTERING',
        text: text || TRANSITION_CONFIG.defaultTitle,
        subtitle: subtitle || TRANSITION_CONFIG.defaultSubtitle,
        duration: loadDuration,
      });

      // 2. Screen is fully covered after enterDuration + max stagger
      const maxEnterDelay = Math.max(...Object.values(TRANSITION_CONFIG.enterStagger));
      const totalCoverTime = TRANSITION_CONFIG.enterDuration + maxEnterDelay;

      setTimeout(() => {
        setState((prev) => ({ ...prev, status: 'COVERED' }));

        // Execute destination navigation while covered
        if (callbacksRef.current.targetRoute) {
          if (callbacksRef.current.replace) {
            router.replace(callbacksRef.current.targetRoute);
          } else {
            router.push(callbacksRef.current.targetRoute);
          }
        }

        if (callbacksRef.current.onCovered) {
          callbacksRef.current.onCovered();
        }

        // 3. Keep covered briefly for buffer then glide out
        setTimeout(() => {
          setState((prev) => ({ ...prev, status: 'EXITING' }));

          // 4. Panels exit towards the top, revealing destination underneath
          const maxExitDelay = Math.max(...Object.values(TRANSITION_CONFIG.exitStagger));
          const totalExitTime = TRANSITION_CONFIG.exitDuration + maxExitDelay;

          setTimeout(() => {
            setState((prev) => ({ ...prev, status: 'IDLE' }));

            if (callbacksRef.current.onComplete) {
              callbacksRef.current.onComplete();
            }
          }, totalExitTime + 60);
        }, loadDuration);
      }, totalCoverTime + 40);
    },
    [router, state.status]
  );

  return (
    <PageTransitionContext.Provider value={{ state, trigger }}>
      {children}
    </PageTransitionContext.Provider>
  );
}

export function usePageTransition() {
  const context = useContext(PageTransitionContext);
  if (!context) {
    throw new Error('usePageTransition must be used within a PageTransitionProvider');
  }
  return context;
}
