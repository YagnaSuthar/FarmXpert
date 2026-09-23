/** Join class names, skipping falsy ones. */
export function cn(...parts) {
  return parts.flat().filter(Boolean).join(' ');
}
