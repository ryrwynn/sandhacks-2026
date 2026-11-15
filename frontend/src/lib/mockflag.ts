// Tiny store: set when any screen is showing contract fixtures instead of live API data.
let on = false;
const subs = new Set<() => void>();

export function markMock() {
  if (on) return;
  on = true;
  subs.forEach((f) => f());
}
export function subscribeMock(f: () => void) {
  subs.add(f);
  return () => subs.delete(f);
}
export const getMockSnapshot = () => on;
