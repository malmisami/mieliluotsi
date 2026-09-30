/* The chat shows Mieliluotsi's replies one short bubble at a time, like a person typing. The demo pilot waits until the
   chat has shown everything before Sami answers – and can hurry it (→ during a conversation, or a rebuild). */

let hurried = false;
let revealing = false;
const listeners = new Set<() => void>();

/** Show everything at once from now on (true) or return to the normal pace (false). */
export function hurryChat(on: boolean) {
  if (hurried === on) return;
  hurried = on;
  listeners.forEach((listener) => listener());
}

export function chatHurried() {
  return hurried;
}

export function subscribeChatHurry(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

/** Set by the chat: true while some of Mieliluotsi's bubbles are still to be shown. */
export function setChatRevealing(value: boolean) {
  revealing = value;
}

export function chatRevealing() {
  return revealing;
}

/** Mieliluotsi's message as chat bubbles: one sentence each, as a person would send them. A new sentence starts after
    . ! ? or … and a space, with a capital letter or a quote – an abbreviation or a date (esim. / 16.10.) stays whole. */
export function splitBubbles(text: string): string[] {
  return text
    .replace(/([.!?…]+[”"’)]*)[ \t]+(?=[A-ZÅÄÖ”"“])/g, '$1\n')
    .split('\n')
    .map((part) => part.trim())
    .filter(Boolean);
}

/** How long the typing dots show before a bubble: a little longer for a longer sentence, never slow. */
export function typingTime(text: string): number {
  return Math.min(1000, Math.max(500, 250 + text.length * 6));
}
