import { ReactNode } from 'react'

interface StatCardProps {
  label: string
  value: string | number
  icon?: ReactNode
  subtitle?: string
  accentColor?: string
}

export function StatCard({
  label,
  value,
  icon,
  subtitle,
  accentColor = 'rgb(var(--accent))'
}: StatCardProps) {
  return (
    <div className="group relative overflow-hidden rounded-xl border border-border-subtle bg-surface p-5 transition-colors hover:border-border">
      <div
        className="absolute inset-x-0 top-0 h-0.5"
        style={{ backgroundColor: accentColor }}
      />
      <div className="flex items-start justify-between">
        <div className="min-w-0 flex-1">
          <div className="mb-2 text-xs font-medium text-text-muted">
            {label}
          </div>
          <div className="truncate text-2xl font-semibold text-text-primary">
            {value}
          </div>
          {subtitle && (
            <div className="mt-1 text-xs text-text-muted">{subtitle}</div>
          )}
        </div>
        {icon && (
          <div
            className="ml-3 flex size-9 shrink-0 items-center justify-center rounded-lg"
            style={{ backgroundColor: `${accentColor}15`, color: accentColor }}
          >
            {icon}
          </div>
        )}
      </div>
    </div>
  )
}
