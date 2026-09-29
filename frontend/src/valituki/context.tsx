import { createContext, useContext } from 'react';
import type { ViewScope } from './api';
import type { Mutation, Role, ValitukiView } from './types';

export type ClientTab = 'koti' | 'keskustelu' | 'harjoitukset' | 'edistyminen' | 'polku';
export type ProTab = 'jono' | 'loki' | 'terapeutit' | 'vaikuttavuus';

export interface ValitukiContextValue {
  view: ValitukiView;
  scope: ViewScope;
  role: Role;
  busy: boolean;
  /** Run one mutation; the returned view replaces the current one. Returns the result, or null on error. */
  run: <T>(action: (scope: ViewScope) => Promise<Mutation<T>>, describe?: (result: T) => string) => Promise<T | null>;
  announce: (text: string) => void;
  setRole: (role: Role) => void;
  setClientId: (clientId: string) => void;
  setTherapistId: (therapistId: string) => void;
  clientTab: ClientTab;
  setClientTab: (tab: ClientTab) => void;
  proTab: ProTab;
  setProTab: (tab: ProTab) => void;
  proClientId: string | null;
  setProClientId: (clientId: string | null) => void;
}

export const ValitukiContext = createContext<ValitukiContextValue | null>(null);

export function useValituki(): ValitukiContextValue {
  const ctx = useContext(ValitukiContext);
  if (!ctx) throw new Error('useValituki must be used inside ValitukiContext');
  return ctx;
}
