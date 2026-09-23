'use client';

// ============================================================
// FILE: src/hooks/useFormDraft.js
//
// Drop-in replacement for `useState` on a form's value object that
// survives a client-side navigation.
//
// Why it exists: switching locale calls router.replace() with a new
// prefix, which remounts the whole [locale] tree — so anything the user
// had typed was gone. The draft lives in a MODULE-LEVEL Map, which the
// bundle keeps across a soft navigation but drops on a real reload.
//
// Deliberately memory-only, never sessionStorage — the same reasoning
// `lib/api.js` applies to the JWT. `exclude` then keeps credentials out
// of even that: a password should not outlive the form that collected
// it, so it is re-typed after a locale switch by design.
//
//   const [form, setForm, clearDraft] = useFormDraft(
//     'auth:login',
//     { email: '', password: '' },
//     { exclude: ['password'] },
//   );
// ============================================================

import { useCallback, useEffect, useRef, useState } from 'react';

/** key -> retained subset of that form's values. */
const drafts = new Map();

/**
 * @param {string} key      stable id for this form
 * @param {object} initial  first-mount values
 * @param {{exclude?: string[]}} [options] fields never retained
 * @returns {[object, Function, Function]} values, setter, clear
 */
export default function useFormDraft(key, initial, { exclude = [] } = {}) {
  // Captured once — the exclusion list is a constant per form, and reading
  // it from a ref keeps the effect below off the render path.
  const excludeRef = useRef(exclude);

  const [values, setValues] = useState(() => ({ ...initial, ...(drafts.get(key) || {}) }));

  // Mirror into the module store. Writing to an external map is exactly
  // what an effect is for — no state is set here, so no cascading render.
  useEffect(() => {
    const retained = {};
    Object.keys(values).forEach((field) => {
      if (!excludeRef.current.includes(field)) retained[field] = values[field];
    });
    drafts.set(key, retained);
  }, [key, values]);

  /** Call once the form has served its purpose (successful submit). */
  const clearDraft = useCallback(() => {
    drafts.delete(key);
  }, [key]);

  return [values, setValues, clearDraft];
}

/** Escape hatch for tests / sign-out cleanup. */
export function clearAllFormDrafts() {
  drafts.clear();
}
