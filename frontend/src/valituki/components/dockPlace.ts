/* Where the demo control sits: the top bar, or – the presenter's choice – a column on the right, beside the backstage panel
   in the client's view and beside the page in the others: everything that is not the service is on the right, the phone
   gets the screen's whole height and the stage's narration stays in one place. The choice is remembered in this browser;
   the slot is the element the control moves into. */
import { useSyncExternalStore } from 'react';

const KEY = 'mieliluotsi.dockSide';
// Beside the panel only when the window has room for a third column: narrower, the control stays in the top bar.
const ROOMY = '(min-width: 900px)';

let side = readSide();
let slot: HTMLElement | null = null;
const listeners = new Set<() => void>();

function readSide(): boolean {
  try {
    return window.localStorage.getItem(KEY) === '1';
  } catch {
    return false;
  }
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

function emit() {
  listeners.forEach((l) => l());
}

export function setDockSide(value: boolean) {
  if (side === value) return;
  side = value;
  try { window.localStorage.setItem(KEY, value ? '1' : '0'); } catch { /* the choice just is not remembered */ }
  emit();
}

/** The presenter wants the control beside the panel. */
export function useDockSide(): boolean {
  return useSyncExternalStore(subscribe, () => side);
}

/** A callback ref for the client view's place beside the panel. */
export function setDockSlot(el: HTMLElement | null) {
  if (slot === el) return;
  slot = el;
  emit();
}

export function useDockSlot(): HTMLElement | null {
  return useSyncExternalStore(subscribe, () => slot);
}

function subscribeRoomy(listener: () => void) {
  const query = window.matchMedia(ROOMY);
  query.addEventListener('change', listener);
  return () => query.removeEventListener('change', listener);
}

/** The window is wide enough for the control beside the panel. */
export function useDockRoomy(): boolean {
  return useSyncExternalStore(subscribeRoomy, () => window.matchMedia(ROOMY).matches);
}
