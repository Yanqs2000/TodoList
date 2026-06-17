export function generateId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  const rand = () => Math.random().toString(36).slice(2, 12);
  return `${Date.now().toString(36)}-${rand()}${rand()}`;
}
