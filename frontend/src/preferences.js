import { useSyncExternalStore } from 'react';

const KEY = 'researchPreferences';
const EVENT = 'research-preferences-changed';
export const preferenceDefaults = { depth: 3, fresh: false, starters: true, compact: false, sort: 'newest', diagrams: false };

export function readPreferences() {
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch { /* Use defaults for invalid saved data. */ }
  return {
    depth: Number.isInteger(saved.depth) && saved.depth >= 1 && saved.depth <= 5 ? saved.depth : 3,
    fresh: saved.fresh === true,
    starters: saved.starters !== false,
    compact: saved.compact === true,
    sort: ['newest', 'oldest', 'sources'].includes(saved.sort) ? saved.sort : 'newest',
    diagrams: localStorage.getItem('visualPlanner') === 'true',
  };
}
export function savePreferences(patch) {
  const next = { ...readPreferences(), ...patch };
  // Preserve compatibility with the existing research and diagram controls.
  if ('diagrams' in patch) localStorage.setItem('visualPlanner', String(next.diagrams));
  localStorage.setItem(KEY, JSON.stringify(next));
  window.dispatchEvent(new Event(EVENT));
}
function subscribe(callback) {
  window.addEventListener(EVENT, callback);
  window.addEventListener('storage', callback);
  return () => { window.removeEventListener(EVENT, callback); window.removeEventListener('storage', callback); };
}
function snapshot() { return JSON.stringify(readPreferences()); }
export function usePreferences() {
  return JSON.parse(useSyncExternalStore(subscribe, snapshot, () => JSON.stringify(preferenceDefaults)));
}
