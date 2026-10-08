// SPDX-License-Identifier: AGPL-3.0-or-later
const PATHS: Record<string, string> = {
  back: 'M15 18l-6-6 6-6',
  plus: 'M12 5v14M5 12h14',
  gear: 'M12 15a3 3 0 100-6 3 3 0 000 6zM19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z',
  list: 'M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01',
  marker: 'M9 11l-6 6v3h9l3-3M22 12l-4.6 4.6a2 2 0 01-2.8 0l-5.2-5.2a2 2 0 010-2.8L14 4',
  type: 'M4 7V4h16v3M9 20h6M12 4v16',
  trash: 'M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6',
  close: 'M18 6L6 18M6 6l12 12',
  more: 'M12 13a1 1 0 100-2 1 1 0 000 2zM19 13a1 1 0 100-2 1 1 0 000 2zM5 13a1 1 0 100-2 1 1 0 000 2z',
  note: 'M4 4h16v12H8l-4 4z',
  left: 'M15 18l-6-6 6-6',
  right: 'M9 6l6 6-6 6',
}

export function Icon({ name, size = 20, className = '' }: { name: keyof typeof PATHS | string
                                                           size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
         className={className}>
      <path d={PATHS[name]} />
    </svg>
  )
}

export function IconButton({ icon, label, onClick, active = false, className = '' }: {
  icon: string; label: string; onClick: () => void; active?: boolean; className?: string
}) {
  return (
    <button type="button" onClick={onClick} aria-label={label} title={label}
            className={`grid h-10 w-10 place-items-center rounded-full transition-colors
                        hover:bg-ink/10 ${active ? 'bg-ink/10 text-accent' : ''} ${className}`}>
      <Icon name={icon} />
    </button>
  )
}
