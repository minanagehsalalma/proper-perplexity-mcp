interface ToggleProps {
  enabled: boolean
  onChange: (enabled: boolean) => void
  disabled?: boolean
}

export function Toggle({ enabled, onChange, disabled = false }: ToggleProps) {
  return (
    <button
      role="switch"
      aria-checked={enabled}
      onClick={() => !disabled && onChange(!enabled)}
      disabled={disabled}
      className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full transition-colors duration-200 ${
        disabled ? 'cursor-not-allowed opacity-50' : ''
      } ${enabled ? 'bg-accent' : 'bg-border'}`}
    >
      <span
        className={`inline-block size-3.5 rounded-full bg-white shadow-sm transition-transform duration-200 ${
          enabled ? 'translate-x-[18px]' : 'translate-x-[3px]'
        }`}
      />
    </button>
  )
}
