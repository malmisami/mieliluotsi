import { useState } from 'react';
import type { LoopDashboard } from '../loop/types';

/** Busy / error / status-message handling shared by every view that mutates the demo state. */
export function useRunner(setDashboard: (dashboard: LoopDashboard) => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState('');

  async function run<T extends { dashboard: LoopDashboard }>(action: () => Promise<T>, describe?: (result: T) => string): Promise<T | null> {
    setBusy(true);
    setError(null);
    try {
      const result = await action();
      setDashboard(result.dashboard);
      setMessage(describe ? describe(result) : '');
      return result;
    } catch (e) {
      setError((e as Error).message);
      return null;
    } finally {
      setBusy(false);
    }
  }

  return { busy, error, message, run, setMessage, setError };
}
