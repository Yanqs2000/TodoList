export function safeSetItem(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch (e) {
    console.warn(`Failed to save "${key}" to localStorage:`, e);
  }
}

export function safeGetItem(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch (e) {
    console.warn(`Failed to read "${key}" from localStorage:`, e);
    return null;
  }
}
