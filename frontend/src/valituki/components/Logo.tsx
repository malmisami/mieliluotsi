/* Mieliluotsi's mark, "Luotsilippu": a rounded square divided by a pilot flag's wave – light teal and the brand teal.
   The same shapes are in public/favicon.svg. */

// The wave runs from the top edge to the bottom edge; both halves share it, so the mark needs no clipping.
const WAVE = 'C57 14 57 34 51 54 C46 70 44 86 50 100';
const WAVE_BACK = 'C44 86 46 70 51 54 C57 34 57 14 50 0';

export function LogoMark({ size = 30, label }: { size?: number; label?: string }) {
  return (
    <svg className="logo-mark" width={size} height={size} viewBox="0 0 100 100" role={label ? 'img' : undefined}
      aria-label={label} aria-hidden={label ? undefined : true} focusable="false">
      <path d={`M50 0 ${WAVE} H30 A30 30 0 0 1 0 70 V30 A30 30 0 0 1 30 0 Z`} fill="#a9cccb" />
      <path d={`M50 0 H70 A30 30 0 0 1 100 30 V70 A30 30 0 0 1 70 100 H50 ${WAVE_BACK} Z`} fill="#0d5f6f" />
    </svg>
  );
}

/** The mark with the name, as in the logo: "Mieliluotsi" in the serif face. */
export function Logo({ size = 22 }: { size?: number }) {
  return (
    <span className="logo">
      <LogoMark size={size} />
      <span className="logo-name">Mieliluotsi</span>
    </span>
  );
}
