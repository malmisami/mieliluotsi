import type { ReactNode } from 'react';
import { api } from '../api';
import { useValituki } from '../context';
import { FlagIcon, ForwardIcon, PlayIcon, PulseIcon, UserSearchIcon } from '../icons';

export interface DemoAction { label: string; icon: ReactNode; action: () => unknown }

/** The presenter's actions, shared by the demo dock and the step controller next to the phone. */
export function useDemoActions() {
  const { view, run, role, setRole, setClientId, setClientTab, setProTab, setProClientId } = useValituki();
  const demo = view.demo;
  const presenter = demo.presenter;

  async function openSlot() {
    const result = await run((s) => api.openSlot(s), (r) =>
      `${r.therapistName}: asiakaspaikka vapautui – MatchingAgent ajoi matchingin ${r.matchedClients.length} asiakkaalle.`);
    if (result && role === 'client') setClientTab('polku');
  }

  async function deteriorate(id: string) {
    const result = await run((s) => api.deteriorate(s, id), (r) =>
      r.trendChanged ? `Mieliluotsi huomasi muutoksen (${r.days} päivää simuloitiin). Tarkistuspyyntö luotiin ammattilaiselle.`
        : `${r.days} päivää simuloitiin – muutosta ei vielä tunnistettu.`);
    if (result && role === 'client') setClientTab('koti');
  }

  async function firstSession(id: string) {
    await run((s) => api.firstSession(s, id), (r) => `Ensimmäinen tapaaminen pidettiin (${r.days} päivää eteenpäin). Terapian välituki alkoi.`);
  }

  async function endTherapy(id: string) {
    const result = await run((s) => api.demoEndTherapy(s, id), (r) =>
      `Terapia päättyi (${r.sessions} tapaamista, ${r.days} päivää eteenpäin). Seuranta terapian jälkeen alkoi.`);
    if (result && role === 'client') setClientTab('polku');
  }

  const weeks = () => run((s) => api.advance(s, 14), (r) => `14 päivää simuloitiin – Mieliluotsi teki ${r.agentActions} toimenpidettä.`);

  async function crisis() {
    setClientId('cl-crisis');
    setRole('client');
    await run((s) => api.crisis({ ...s, clientId: 'cl-crisis' }), () => 'Kriisipolku: turvallisuusnäkymä keskeytti tavallisen tuen.');
  }

  /** Rebuild the demo at a prepared scene (Sami's journey). */
  async function jump(key: string) {
    if (!key) return;
    await run((s) => api.scene(s, key), () => `Demo siirrettiin vaiheeseen: ${demo.scenes.find((sc) => sc.key === key)?.label ?? key}`);
    setClientId('cl-aino');
    setProClientId(null);
    setProTab('jono');
  }

  // The script follows Sami, so its next action always targets Sami.
  const NEXT: Record<string, DemoAction> = {
    weeks: { label: 'Simuloi 14 päivää', icon: <ForwardIcon size={15} />, action: weeks },
    change: { label: 'Simuloi voinnin heikkeneminen', icon: <PulseIcon size={15} />, action: () => deteriorate('cl-aino') },
    matches: { label: 'Avaa terapeutin vapaa aika', icon: <UserSearchIcon size={15} />, action: openSlot },
    firstSession: { label: 'Pidä 1. tapaaminen', icon: <PlayIcon size={14} />, action: () => firstSession('cl-aino') },
    aftercare: { label: 'Terapia päättyy', icon: <FlagIcon size={14} />, action: () => endTherapy('cl-aino') },
  };
  const nextAction = presenter.nextKey ? NEXT[presenter.nextKey] : undefined;

  return { nextAction, weeks, deteriorate, openSlot, firstSession, endTherapy, crisis, jump };
}
