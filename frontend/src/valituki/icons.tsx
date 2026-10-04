import type { ReactNode } from 'react';

/* Mieliluotsi line icons: 24px grid, 1.75 stroke, round caps. Decorative by default (aria-hidden) unless a title is given. */

export interface IconProps { size?: number; className?: string; title?: string }

function Icon({ size = 20, className, title, children }: IconProps & { children: ReactNode }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round"
      strokeLinejoin="round" className={className ? `ico ${className}` : 'ico'} role={title ? 'img' : undefined}
      aria-hidden={title ? undefined : true} focusable="false">
      {title && <title>{title}</title>}
      {children}
    </svg>
  );
}

export const SunIcon = (p: IconProps) => <Icon {...p}><circle cx="12" cy="12" r="4" /><path d="M12 2.5v2M12 19.5v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M2.5 12h2M19.5 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4" /></Icon>;
export const RouteIcon = (p: IconProps) => <Icon {...p}><circle cx="6" cy="19" r="2" /><circle cx="18" cy="5" r="2" /><path d="M8 19h7.5a3.5 3.5 0 0 0 0-7h-7a3.5 3.5 0 0 1 0-7H16" /></Icon>;
export const ClipboardIcon = (p: IconProps) => <Icon {...p}><rect x="5" y="4" width="14" height="17" rx="2.5" /><path d="M9 4.5V3.5h6v1M9 12l2 2 4-4" /></Icon>;
export const UserSearchIcon = (p: IconProps) => <Icon {...p}><circle cx="10" cy="8" r="3.5" /><path d="M3.5 20a6.5 6.5 0 0 1 10-5.5" /><circle cx="17" cy="16.5" r="2.8" /><path d="M19.1 18.6 21 20.5" /></Icon>;
export const ChatIcon = (p: IconProps) => <Icon {...p}><path d="M20 12a7.5 7.5 0 0 1-11.2 6.5L4 20l1.5-4.3A7.5 7.5 0 1 1 20 12Z" /></Icon>;
export const ShieldIcon = (p: IconProps) => <Icon {...p}><path d="M12 3 19 6v5.5c0 4.3-3 7.9-7 9.5-4-1.6-7-5.2-7-9.5V6l7-3Z" /><path d="m9 12 2 2 4-4" /></Icon>;
export const LifebuoyIcon = (p: IconProps) => <Icon {...p}><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="3.8" /><path d="m5.6 5.6 3.7 3.7M14.7 14.7l3.7 3.7M18.4 5.6l-3.7 3.7M9.3 14.7l-3.7 3.7" /></Icon>;
export const CheckIcon = (p: IconProps) => <Icon {...p}><path d="m5 12.5 4.5 4.5L19 7.5" /></Icon>;
export const CrossIcon = (p: IconProps) => <Icon {...p}><path d="M6 6l12 12M18 6 6 18" /></Icon>;
export const PlusIcon = (p: IconProps) => <Icon {...p}><path d="M12 5v14M5 12h14" /></Icon>;
export const MinusIcon = (p: IconProps) => <Icon {...p}><path d="M5 12h14" /></Icon>;
export const ChevronRightIcon = (p: IconProps) => <Icon {...p}><path d="m9 6 6 6-6 6" /></Icon>;
export const ChevronDownIcon = (p: IconProps) => <Icon {...p}><path d="m6 9 6 6 6-6" /></Icon>;
export const ArrowRightIcon = (p: IconProps) => <Icon {...p}><path d="M5 12h14M13 6l6 6-6 6" /></Icon>;
export const ArrowLeftIcon = (p: IconProps) => <Icon {...p}><path d="M19 12H5M11 6l-6 6 6 6" /></Icon>;
export const ArrowDownIcon = (p: IconProps) => <Icon {...p}><path d="M12 5v14M6 13l6 6 6-6" /></Icon>;
export const SparkleIcon = (p: IconProps) => <Icon {...p}><path d="M12 3.5 13.8 9l5.7 1.9-5.7 1.9L12 18.5l-1.8-5.7L4.5 11l5.7-2Z" /><path d="M19 3v3M17.5 4.5h3" /></Icon>;
export const EyeIcon = (p: IconProps) => <Icon {...p}><path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" /><circle cx="12" cy="12" r="2.8" /></Icon>;
export const EyeOffIcon = (p: IconProps) => <Icon {...p}><path d="M9.9 5.8A9 9 0 0 1 12 5.5C18 5.5 21.5 12 21.5 12a17 17 0 0 1-2.7 3.6M6.2 7.6C3.9 9.3 2.5 12 2.5 12S6 18.5 12 18.5a9 9 0 0 0 4.3-1.1" /><path d="M10 10a2.8 2.8 0 0 0 4 4" /><path d="m4 4 16 16" /></Icon>;
export const PuzzleIcon = (p: IconProps) => <Icon {...p}><path d="M9.5 4.5a2 2 0 1 1 4 0V6H18v4.5h-1.5a2 2 0 1 0 0 4H18V19h-4.5v-1.5a2 2 0 1 0-4 0V19H5v-4.5h1.5a2 2 0 1 0 0-4H5V6h4.5Z" /></Icon>;
export const LockIcon = (p: IconProps) => <Icon {...p}><rect x="5" y="10.5" width="14" height="10" rx="2.5" /><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5" /></Icon>;
export const CalendarIcon = (p: IconProps) => <Icon {...p}><rect x="3.5" y="5" width="17" height="15.5" rx="2.5" /><path d="M3.5 10h17M8 3v4M16 3v4" /></Icon>;
export const ClockIcon = (p: IconProps) => <Icon {...p}><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /></Icon>;
export const BellIcon = (p: IconProps) => <Icon {...p}><path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15Z" /><path d="M10 20.5a2 2 0 0 0 4 0" /></Icon>;
export const SendIcon = (p: IconProps) => <Icon {...p}><path d="m4 12 16-7.5L13.5 20l-2.2-6.3Z" /><path d="m11.3 13.7 8.7-9.2" /></Icon>;
export const EditIcon = (p: IconProps) => <Icon {...p}><path d="M4 20h4L19 9l-4-4L4 16Z" /><path d="m13.5 6.5 4 4" /></Icon>;
export const TrashIcon = (p: IconProps) => <Icon {...p}><path d="M4.5 7h15M10 11v6M14 11v6M6.5 7l1 13h9l1-13M9.5 7V4.5h5V7" /></Icon>;
export const UndoIcon = (p: IconProps) => <Icon {...p}><path d="M9 7 4.5 11.5 9 16" /><path d="M5 11.5h9.5a5 5 0 0 1 0 10H11" /></Icon>;
export const ResetIcon = (p: IconProps) => <Icon {...p}><path d="M4.5 5v5h5" /><path d="M5.2 14.5A7.5 7.5 0 1 0 6.8 7L4.5 10" /></Icon>;
export const ForwardIcon = (p: IconProps) => <Icon {...p}><path d="m4 6 7 6-7 6Z" /><path d="m12 6 7 6-7 6Z" /></Icon>;
export const PlayIcon = (p: IconProps) => <Icon {...p}><path d="m7 5 12 7-12 7Z" /></Icon>;
export const AlertIcon = (p: IconProps) => <Icon {...p}><path d="M12 4 21 19.5H3Z" /><path d="M12 10v4M12 17h.01" /></Icon>;
export const InfoIcon = (p: IconProps) => <Icon {...p}><circle cx="12" cy="12" r="8.5" /><path d="M12 11v5.5M12 7.8h.01" /></Icon>;
export const HeartIcon = (p: IconProps) => <Icon {...p}><path d="M12 20s-7.5-4.6-7.5-10.2A4.3 4.3 0 0 1 12 7.2a4.3 4.3 0 0 1 7.5 2.6C19.5 15.4 12 20 12 20Z" /></Icon>;
export const LeafIcon = (p: IconProps) => <Icon {...p}><path d="M5 19c0-8 5-13 14-14 0 9-5 14-13 14Z" /><path d="M5 19 13 11" /></Icon>;
export const MoonIcon = (p: IconProps) => <Icon {...p}><path d="M19.5 14.5A8 8 0 0 1 9.5 4.5a8 8 0 1 0 10 10Z" /></Icon>;
export const PulseIcon = (p: IconProps) => <Icon {...p}><path d="M3 12h4l2-5 4 10 2-5h6" /></Icon>;
export const UsersIcon = (p: IconProps) => <Icon {...p}><circle cx="9" cy="8.5" r="3.2" /><path d="M3 19.5a6 6 0 0 1 12 0" /><circle cx="17" cy="9.5" r="2.5" /><path d="M16.5 14.5a5 5 0 0 1 5 5" /></Icon>;
export const PersonIcon = (p: IconProps) => <Icon {...p}><circle cx="12" cy="8" r="3.6" /><path d="M5 20a7 7 0 0 1 14 0" /></Icon>;
export const StethoscopeIcon = (p: IconProps) => <Icon {...p}><path d="M6 3.5v5a4 4 0 0 0 8 0v-5" /><path d="M10 12.5V15a5 5 0 0 0 10 0v-1.5" /><circle cx="20" cy="11.5" r="2" /></Icon>;
export const DocumentIcon = (p: IconProps) => <Icon {...p}><path d="M6 3h8l4 4v14H6Z" /><path d="M14 3v4h4M9 12h6M9 16h6" /></Icon>;
export const NodesIcon = (p: IconProps) => <Icon {...p}><circle cx="12" cy="12" r="2.6" /><circle cx="5" cy="6" r="2" /><circle cx="19" cy="6" r="2" /><circle cx="5" cy="18" r="2" /><circle cx="19" cy="18" r="2" /><path d="m6.6 7.2 3.4 3M17.4 7.2l-3.4 3M6.6 16.8l3.4-3M17.4 16.8l-3.4-3" /></Icon>;
export const VideoIcon = (p: IconProps) => <Icon {...p}><rect x="3" y="6.5" width="12.5" height="11" rx="2.5" /><path d="m15.5 10.5 5.5-3v9l-5.5-3" /></Icon>;
export const GlobeIcon = (p: IconProps) => <Icon {...p}><circle cx="12" cy="12" r="8.5" /><path d="M3.5 12h17M12 3.5c2.5 2.6 3.5 5.4 3.5 8.5s-1 5.9-3.5 8.5c-2.5-2.6-3.5-5.4-3.5-8.5s1-5.9 3.5-8.5Z" /></Icon>;
export const PhoneIcon = (p: IconProps) => <Icon {...p}><path d="M5 4h3.5l1.5 4-2 1.5a11 11 0 0 0 6.5 6.5L16 14l4 1.5V19a2 2 0 0 1-2.2 2A16 16 0 0 1 3 6.2 2 2 0 0 1 5 4Z" /></Icon>;
export const QuoteIcon = (p: IconProps) => <Icon {...p}><path d="M9.5 7C6.5 8 5 10.2 5 13.5V17h4.5v-4.5H7M19 7c-3 1-4.5 3.2-4.5 6.5V17H19v-4.5h-2.5" /></Icon>;
export const FlagIcon = (p: IconProps) => <Icon {...p}><path d="M5 21V4M5 4.5h11l-2 4 2 4H5" /></Icon>;
export const LayersIcon = (p: IconProps) => <Icon {...p}><path d="m12 3.5 9 5-9 5-9-5Z" /><path d="m3 13 9 5 9-5" /></Icon>;
export const TargetIcon = (p: IconProps) => <Icon {...p}><circle cx="12" cy="12" r="8.5" /><circle cx="12" cy="12" r="4.5" /><circle cx="12" cy="12" r="1" /></Icon>;
export const BarsIcon = (p: IconProps) => <Icon {...p}><path d="M5 20V11M10 20V5M15 20v-7M20 20V9" /></Icon>;
export const SlidersIcon = (p: IconProps) => <Icon {...p}><path d="M4 7h9M17 7h3M4 17h3M11 17h9" /><circle cx="15" cy="7" r="2" /><circle cx="9" cy="17" r="2" /></Icon>;
export const SortIcon = (p: IconProps) => <Icon {...p}><path d="m8 9 4-4 4 4M8 15l4 4 4-4" /></Icon>;
export const PresentIcon = (p: IconProps) => <Icon {...p}><rect x="3" y="4" width="18" height="12" rx="2" /><path d="M12 16v4M8 20h8" /></Icon>;
export const PanelRightIcon = (p: IconProps) => <Icon {...p}><rect x="3" y="4.5" width="18" height="15" rx="2.5" /><path d="M15 4.5v15" /></Icon>;
export const PanelTopIcon = (p: IconProps) => <Icon {...p}><rect x="3" y="4.5" width="18" height="15" rx="2.5" /><path d="M3 9.5h18" /></Icon>;
export const HandHeartIcon = (p: IconProps) => <Icon {...p}><path d="M12 10.5s-3.2-2-3.2-4.2A1.8 1.8 0 0 1 12 5.2a1.8 1.8 0 0 1 3.2 1.1c0 2.2-3.2 4.2-3.2 4.2Z" /><path d="M3 14.5h3.5l3 1.5h3.5a1.5 1.5 0 0 1 0 3H9M13 17.5l5-2.5a1.6 1.6 0 0 1 2 2.4L14 21H7l-4-2" /></Icon>;
export const ListIcon = (p: IconProps) => <Icon {...p}><path d="M9 6.5h11M9 12h11M9 17.5h11" /><circle cx="4.5" cy="6.5" r="1" /><circle cx="4.5" cy="12" r="1" /><circle cx="4.5" cy="17.5" r="1" /></Icon>;
export const HomeIcon = (p: IconProps) => <Icon {...p}><path d="M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-4.5v-6h-5v6H5a1 1 0 0 1-1-1Z" /></Icon>;
export const GridIcon = (p: IconProps) => <Icon {...p}><rect x="4" y="4" width="6.5" height="6.5" rx="1.6" /><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.6" /><rect x="4" y="13.5" width="6.5" height="6.5" rx="1.6" /><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.6" /></Icon>;
export const TrendIcon = (p: IconProps) => <Icon {...p}><path d="M3.5 17.5 9 12l3.5 3.5L20.5 7.5" /><path d="M15.5 7.5h5v5" /></Icon>;
export const SearchIcon = (p: IconProps) => <Icon {...p}><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4.5 4.5" /></Icon>;
export const StairsIcon = (p: IconProps) => <Icon {...p}><path d="M3.5 20.5h5v-4.5h4.5v-4.5h4.5V7h3" /></Icon>;
export const FlaskIcon = (p: IconProps) => <Icon {...p}><path d="M9.5 3.5h5M10.5 3.5v5.2L5.3 18.1A1.6 1.6 0 0 0 6.7 20.5h10.6a1.6 1.6 0 0 0 1.4-2.4l-5.2-9.4V3.5" /><path d="M8 14.5h8" /></Icon>;
export const ThoughtIcon = (p: IconProps) => <Icon {...p}><path d="M7.5 15.5a4.5 4.5 0 0 1-.6-8.9 5.5 5.5 0 0 1 10.3 1.2 3.9 3.9 0 0 1-.7 7.7Z" /><circle cx="7" cy="19" r="1.2" /><circle cx="4.5" cy="21" r=".7" /></Icon>;
export const CopyIcon = (p: IconProps) => <Icon {...p}><rect x="8.5" y="8.5" width="11" height="11" rx="2.2" /><path d="M15.5 8.5V6a1.5 1.5 0 0 0-1.5-1.5H6A1.5 1.5 0 0 0 4.5 6v8A1.5 1.5 0 0 0 6 15.5h2.5" /></Icon>;
export const StopIcon = (p: IconProps) => <Icon {...p}><rect x="6.5" y="6.5" width="11" height="11" rx="2" /></Icon>;
export const BookIcon = (p: IconProps) => <Icon {...p}><path d="M5 4.5h11a2 2 0 0 1 2 2v13H7a2 2 0 0 1-2-2Z" /><path d="M5 17.5a2 2 0 0 1 2-2h11M9 8.5h5" /></Icon>;
