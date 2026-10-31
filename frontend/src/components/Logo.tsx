export function LogoMark({ size = 32 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="9" fill="#C62828" />
      <path d="M21.5 11.2a6.6 6.6 0 0 0-11.3 1.3" fill="none" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" />
      <path d="M10.5 20.8a6.6 6.6 0 0 0 11.3-1.3" fill="none" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" />
      <path d="M22.6 7.6v4.4h-4.4M9.4 24.4V20h4.4" fill="none" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="16" cy="16" r="2" fill="#FDECEC" />
    </svg>
  )
}

export function Wordmark({ collapsed = false, light = false }: { collapsed?: boolean; light?: boolean }) {
  return (
    <span className="flex items-center gap-2.5">
      <LogoMark />
      {!collapsed && (
        <span className="leading-none">
          <span className={`block font-display text-[19px] font-extrabold tracking-tight ${light ? 'text-white' : 'text-ink'}`}>
            subsy<span className="text-brand-500">.</span>
          </span>
          <span className={`mt-0.5 block text-[10px] font-medium tracking-wide ${light ? 'text-white/70' : 'text-ink-faint'}`}>Every Subscription, Simplified.</span>
        </span>
      )}
    </span>
  )
}
