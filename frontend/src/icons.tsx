import type { ReactNode } from 'react';

export interface IconProps {
  size?: number;
  className?: string;
  title?: string;
}

interface SvgProps extends IconProps {
  viewBox?: string;
  children: ReactNode;
}

function Svg({ size = 24, className, title, viewBox = '0 0 24 24', children }: SvgProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox={viewBox}
      className={className ? `icon ${className}` : 'icon'}
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={title ? 'img' : undefined}
      aria-hidden={title ? undefined : true}
      focusable="false"
    >
      {title && <title>{title}</title>}
      {children}
    </svg>
  );
}

/* ---- Illustrative icons (48 grid, soft fills) ---- */

export function DnaIcon(props: IconProps) {
  return (
    <Svg viewBox="0 0 48 48" {...props}>
      <path d="M17 8h14M19 18.5h10M16 24h16M19 29.5h10M17 40h14" stroke="var(--icon-blue-strong)" strokeWidth={3} />
      <path d="M16 5c0 9.5 16 9.5 16 19S16 33.5 16 43" />
      <path d="M32 5c0 9.5-16 9.5-16 19s16 9.5 16 19" />
    </Svg>
  );
}

export function HeartHandIcon(props: IconProps) {
  return (
    <Svg viewBox="0 0 48 48" {...props}>
      <path d="M27 25s-9-5.6-9-12a4.7 4.7 0 0 1 9-1.6 4.7 4.7 0 0 1 9 1.6c0 6.4-9 12-9 12z" fill="var(--icon-green)" />
      <rect x="3" y="27" width="7" height="15" rx="1.5" fill="var(--icon-blue-strong)" />
      <path d="M10 30h6.5c1.5 0 3 .5 4.2 1.4l2.8 2.1H31a2.5 2.5 0 1 1 0 5h-8" />
      <path d="M31 38.5l6.5-3.2a2.8 2.8 0 0 1 2.6 4.9L30.5 44c-2.2 1.2-4.8 1.4-7.2.6L10 40.5" />
    </Svg>
  );
}

/** Hyvinvointidata: a heart with a pulse line (continuous data from the phone and the watch). */
export function PulseIcon(props: IconProps) {
  return (
    <Svg viewBox="0 0 48 48" {...props}>
      <path d="M24 41S7 30.5 7 18.5A8.5 8.5 0 0 1 24 14a8.5 8.5 0 0 1 17 4.5C41 30.5 24 41 24 41z" fill="var(--icon-pink)" />
      <path d="M4 25h10l3-6 5 12 4-9 2.5 3H44" />
    </Svg>
  );
}

export function CalendarIcon(props: IconProps) {
  return (
    <Svg viewBox="0 0 48 48" {...props}>
      <path d="M7 13a3 3 0 0 1 3-3h28a3 3 0 0 1 3 3v6H7z" fill="var(--icon-blue-strong)" stroke="none" />
      <rect x="7" y="10" width="34" height="31" rx="3" />
      <path d="M7 19h34M16 6v7M32 6v7" />
      <rect x="13" y="24" width="5" height="5" rx="1" fill="var(--icon-blue)" stroke="none" />
      <rect x="21.5" y="24" width="5" height="5" rx="1" fill="var(--icon-blue)" stroke="none" />
      <rect x="30" y="24" width="5" height="5" rx="1" fill="var(--icon-blue)" stroke="none" />
      <rect x="13" y="32" width="5" height="5" rx="1" fill="var(--icon-blue)" stroke="none" />
      <rect x="21.5" y="32" width="5" height="5" rx="1" fill="var(--icon-orange)" stroke="none" />
    </Svg>
  );
}

export function ChatIcon(props: IconProps) {
  return (
    <Svg viewBox="0 0 48 48" {...props}>
      <path d="M24 8C13.5 8 6 14.6 6 22.6c0 4.3 2.1 8.1 5.6 10.7L9.8 41l8.6-4.6c1.8.5 3.7.7 5.6.7 10.5 0 18-6.5 18-14.5S34.5 8 24 8z" fill="#fff" />
      <path d="M11.6 33.3L9.8 41l8.6-4.6c-2.5-.7-4.8-1.8-6.8-3.1z" fill="var(--icon-blue-strong)" />
      <circle cx="16" cy="22.6" r="2" fill="currentColor" stroke="none" />
      <circle cx="24" cy="22.6" r="2" fill="currentColor" stroke="none" />
      <circle cx="32" cy="22.6" r="2" fill="currentColor" stroke="none" />
    </Svg>
  );
}

export function DocumentIcon(props: IconProps) {
  return (
    <Svg viewBox="0 0 48 48" {...props}>
      <path d="M11 5h17l9 9v29H11z" />
      <path d="M28 5v9h9z" fill="var(--icon-blue)" />
      <path d="M17 22h14M17 28h14M17 34h9" />
    </Svg>
  );
}

export function ClipboardIcon(props: IconProps) {
  return (
    <Svg viewBox="0 0 48 48" {...props}>
      <rect x="9" y="9" width="30" height="34" rx="3" />
      <rect x="18" y="5" width="12" height="7" rx="2" fill="var(--icon-blue-strong)" />
      <path d="M15 22l3 3 5.5-6M27 22h6" />
      <path d="M15 33l3 3 5.5-6M27 33h6" />
    </Svg>
  );
}

export function PhoneIcon(props: IconProps) {
  return (
    <Svg viewBox="0 0 48 48" {...props}>
      <path
        d="M14.5 6.5c1.2-.8 2.8-.5 3.6.7l3.6 5.4c.7 1.1.5 2.6-.5 3.4l-3 2.4c1.9 4.6 5.5 8.3 10.1 10.2l2.4-3c.8-1 2.3-1.2 3.4-.5l5.4 3.6c1.2.8 1.5 2.4.7 3.6l-2.6 3.6c-1.4 2-4 2.8-6.3 2C19.1 33.4 12.6 26.9 8.4 16.3c-.8-2.3 0-4.9 2-6.3z"
        fill="var(--icon-green)"
      />
      <path d="M30 12a8 8 0 0 1 6 6M31 6a14 14 0 0 1 11 11" />
    </Svg>
  );
}

export function SirenIcon(props: IconProps) {
  return (
    <Svg viewBox="0 0 48 48" {...props}>
      <path d="M24 5v4M12 10l2.8 2.8M36 10l-2.8 2.8" />
      <path d="M15 36V25a9 9 0 0 1 18 0v11" fill="var(--icon-orange)" />
      <rect x="9" y="36" width="30" height="6" rx="1.5" fill="var(--icon-navy)" />
    </Svg>
  );
}

export function UploadIcon(props: IconProps) {
  return (
    <Svg viewBox="0 0 48 48" {...props}>
      <path d="M11 5h17l9 9v29H11z" />
      <path d="M28 5v9h9" />
      <circle cx="24" cy="30" r="8" fill="var(--icon-blue)" stroke="none" />
      <path d="M24 35v-9M20 30l4-4 4 4" />
    </Svg>
  );
}

export function TestTubeIcon(props: IconProps) {
  return (
    <Svg viewBox="0 0 48 48" {...props}>
      <path d="M19.5 21h9v11.5a4.5 4.5 0 0 1-9 0z" fill="var(--icon-blue-strong)" stroke="none" />
      <path d="M17 5h14" />
      <path d="M19.5 5v27.5a4.5 4.5 0 0 0 9 0V5" />
      <circle cx="24" cy="27" r="1.6" fill="#fff" stroke="none" />
      <path d="M33 16h6M36 13v6" stroke="var(--icon-green-strong)" />
    </Svg>
  );
}

export function LockIcon(props: IconProps) {
  return (
    <Svg viewBox="0 0 48 48" {...props}>
      <rect x="10" y="21" width="28" height="21" rx="3" fill="var(--icon-blue)" />
      <path d="M16 21v-6a8 8 0 0 1 16 0v6" />
      <circle cx="24" cy="31" r="2.5" fill="currentColor" stroke="none" />
      <path d="M24 33v4" />
    </Svg>
  );
}

export function ShieldIcon(props: IconProps) {
  return (
    <Svg viewBox="0 0 48 48" {...props}>
      <path d="M24 5l15 5v12c0 9-6.5 16.5-15 21C15.5 38.5 9 31 9 22V10z" fill="var(--icon-blue)" />
      <path d="M17 23.5l5 5 9-10" />
    </Svg>
  );
}

/* Quiz illustrations */

export function WalkIcon(props: IconProps) {
  return (
    <Svg viewBox="0 0 48 48" {...props}>
      <circle cx="29" cy="8" r="3.5" fill="var(--icon-orange)" />
      <path d="M27 13l-5 9" />
      <path d="M22 22l-4 4-2 9" />
      <path d="M22 22l6 4 2 9" />
      <path d="M26 16l-7 2.5" />
      <path d="M26 16l7 3.5" />
      <path d="M8 42h32" stroke="var(--icon-blue-strong)" strokeWidth={3} />
    </Svg>
  );
}

export function AppleIcon(props: IconProps) {
  return (
    <Svg viewBox="0 0 48 48" {...props}>
      <path
        d="M24 17c-3.5-3-9.5-2-11.5 3.5-2.3 6.3 0 14 4 18 2.2 2.2 4.5 2.2 7.5 1 3 1.2 5.3 1.2 7.5-1 4-4 6.3-11.7 4-18C33.5 15 27.5 14 24 17z"
        fill="var(--icon-green)"
      />
      <path d="M24 17c0-3.5 1.2-6 3.5-8" />
      <path d="M25.5 12c2.5-2.5 6-2.5 8-1-2 2.5-5.5 3-8 1z" fill="var(--icon-green-strong)" />
    </Svg>
  );
}

export function NoSmokingIcon(props: IconProps) {
  return (
    <Svg viewBox="0 0 48 48" {...props}>
      <circle cx="24" cy="24" r="18" />
      <rect x="9" y="21" width="27" height="6" rx="1" fill="#fff" />
      <rect x="9" y="21" width="7" height="6" rx="1" fill="var(--icon-orange)" />
      <path d="M38 10L10 38" stroke="var(--icon-burgundy)" strokeWidth={3} />
    </Svg>
  );
}

export function GlassIcon(props: IconProps) {
  return (
    <Svg viewBox="0 0 48 48" {...props}>
      <path d="M15 6h18v8c0 6-4 10-9 10s-9-4-9-10z" fill="var(--icon-pink)" />
      <path d="M24 24v13M16 40h16" />
    </Svg>
  );
}

export function MoonIcon(props: IconProps) {
  return (
    <Svg viewBox="0 0 48 48" {...props}>
      <path d="M26 6a15 15 0 1 0 16 22.5A12.5 12.5 0 0 1 26 6z" fill="var(--icon-blue)" />
      <path d="M11 9l1.1 2.4 2.4 1.1-2.4 1.1L11 16l-1.1-2.4L7.5 12.5l2.4-1.1z" fill="var(--icon-orange)" stroke="none" />
    </Svg>
  );
}

export function FamilyIcon(props: IconProps) {
  return (
    <Svg viewBox="0 0 48 48" {...props}>
      <circle cx="13" cy="12" r="4.5" />
      <path d="M4 37v-6.5a9 9 0 0 1 18 0V37" />
      <circle cx="35" cy="12" r="4.5" />
      <path d="M26 37v-6.5a9 9 0 0 1 18 0V37" />
      <circle cx="24" cy="24" r="3.5" fill="var(--icon-orange)" />
      <path d="M17.5 42v-4.5a6.5 6.5 0 0 1 13 0V42" fill="var(--icon-blue)" />
    </Svg>
  );
}

export function StethoscopeIcon(props: IconProps) {
  return (
    <Svg viewBox="0 0 48 48" {...props}>
      <path d="M13 6v12a9 9 0 0 0 18 0V6" />
      <path d="M22 27v5a8 8 0 0 0 16 0v-4" />
      <circle cx="38" cy="24" r="4" fill="var(--icon-blue-strong)" />
      <circle cx="13" cy="6" r="1.6" fill="currentColor" stroke="none" />
      <circle cx="31" cy="6" r="1.6" fill="currentColor" stroke="none" />
    </Svg>
  );
}

export function LeafIcon(props: IconProps) {
  return (
    <Svg viewBox="0 0 48 48" {...props}>
      <path d="M40 8C22 8 10 18 10 34c0 2.5.5 4.5 1.3 6.2C29 40 40 27 40 8z" fill="var(--icon-green)" />
      <path d="M11.3 40.2C16 31 24 22 34 14" />
    </Svg>
  );
}

export function SproutIcon(props: IconProps) {
  return (
    <Svg viewBox="0 0 48 48" {...props}>
      <path d="M10 42h28" />
      <path d="M24 42V22" />
      <path d="M24 30c0-7-5.5-11.5-12.5-11.5C11.5 25.5 17 30 24 30z" fill="var(--icon-green)" />
      <path d="M24 22c0-7 5.5-11.5 12.5-11.5C36.5 17.5 31 22 24 22z" fill="var(--icon-green-strong)" />
    </Svg>
  );
}

/* ---- Small UI icons (24 grid) ---- */

export function ChevronRightIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M9 5l7 7-7 7" />
    </Svg>
  );
}

export function ArrowLeftIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M19 12H5M11 6l-6 6 6 6" />
    </Svg>
  );
}

export function ArrowRightIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M5 12h14M13 6l6 6-6 6" />
    </Svg>
  );
}

export function ExternalIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
    </Svg>
  );
}

export function PersonIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21a8 8 0 0 1 16 0" />
    </Svg>
  );
}

export function CheckIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M5 12.5l4.5 4.5L19 7.5" />
    </Svg>
  );
}

export function CrossIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M6 6l12 12M18 6L6 18" />
    </Svg>
  );
}

export function MinusIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M6 12h12" />
    </Svg>
  );
}

export function QuestionIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.3-1 .9-1 1.7" />
      <circle cx="12" cy="17" r=".9" fill="currentColor" stroke="none" />
    </Svg>
  );
}

export function AlertIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 8v5" />
      <circle cx="12" cy="16.5" r=".9" fill="currentColor" stroke="none" />
    </Svg>
  );
}

export function InfoIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5" />
      <circle cx="12" cy="8" r=".9" fill="currentColor" stroke="none" />
    </Svg>
  );
}

export function ClockIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3.5 2" />
    </Svg>
  );
}

export function DotIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="3" fill="currentColor" stroke="none" />
    </Svg>
  );
}

export function WarningIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M12 4L2.5 20h19z" />
      <path d="M12 10v4" />
      <circle cx="12" cy="17" r=".9" fill="currentColor" stroke="none" />
    </Svg>
  );
}

export function PrintIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M7 9V4h10v5M7 17H4v-8h16v8h-3" />
      <rect x="7" y="14" width="10" height="6" />
    </Svg>
  );
}

export function TrashIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" />
    </Svg>
  );
}

/* ---- Mieliluotsi UI icons (24 grid) ---- */

export function HomeIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M4 11l8-6.5 8 6.5M6 9.5V20h4.5v-5h3v5H18V9.5" />
    </Svg>
  );
}

export function CompassIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M15.5 8.5l-2 5-5 2 2-5z" />
    </Svg>
  );
}

export function TrendIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M4 19h16" />
      <path d="M5 15l4-4 3 3 6-6" />
      <path d="M15 8h3v3" />
    </Svg>
  );
}

export function UsersIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="9" cy="8.5" r="3.5" />
      <path d="M2.5 20a6.5 6.5 0 0 1 13 0" />
      <path d="M16 5.2a3.5 3.5 0 0 1 0 6.6M18 14.2a6.5 6.5 0 0 1 3.5 5.8" />
    </Svg>
  );
}

export function LifebuoyIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="4" />
      <path d="M5.6 5.6l3.6 3.6M14.8 14.8l3.6 3.6M18.4 5.6l-3.6 3.6M9.2 14.8l-3.6 3.6" />
    </Svg>
  );
}

export function SparkleIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M12 3.5l1.9 5.1 5.1 1.9-5.1 1.9L12 17.5l-1.9-5.1L5 10.5l5.1-1.9z" />
      <path d="M18.5 16v4M16.5 18h4" />
    </Svg>
  );
}

export function QuoteIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M9.5 7C6.5 7.5 5 9.6 5 12.5V17h5v-4.5H7.3c0-2 .9-3.1 2.2-3.5zM18.5 7c-3 .5-4.5 2.6-4.5 5.5V17h5v-4.5h-2.7c0-2 .9-3.1 2.2-3.5z" />
    </Svg>
  );
}

export function BarsIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M4 20h16M7 17v-5M12 17V7M17 17v-8" />
    </Svg>
  );
}

export function BellIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z" />
      <path d="M10 20.5a2 2 0 0 0 4 0" />
    </Svg>
  );
}

export function ListIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M9 6h11M9 12h11M9 18h11" />
      <circle cx="4.5" cy="6" r="1" fill="currentColor" stroke="none" />
      <circle cx="4.5" cy="12" r="1" fill="currentColor" stroke="none" />
      <circle cx="4.5" cy="18" r="1" fill="currentColor" stroke="none" />
    </Svg>
  );
}

export function SendIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M4 12l16-7-6 16-2.5-6.5z" />
      <path d="M11.5 14.5L20 5" />
    </Svg>
  );
}
