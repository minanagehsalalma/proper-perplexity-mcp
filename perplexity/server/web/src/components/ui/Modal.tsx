import { ReactNode } from 'react'

interface ModalProps {
  isOpen: boolean
  title: string
  children: ReactNode
  onClose: () => void
  onConfirm: () => void
  confirmText?: string
  variant?: 'primary' | 'danger'
  confirmDisabled?: boolean
}

export function Modal({
  isOpen,
  title,
  children,
  onClose,
  onConfirm,
  confirmText = 'Confirm',
  variant = 'primary',
  confirmDisabled = false
}: ModalProps) {
  if (!isOpen) return null

  const confirmClass =
    variant === 'danger'
      ? 'bg-error text-white hover:bg-red-600'
      : 'bg-accent text-white hover:bg-accent-hover'

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="mx-4 w-full max-w-lg animate-scale-in rounded-xl border border-border bg-surface p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-text-primary">{title}</h3>
          <button
            onClick={onClose}
            className="flex size-7 items-center justify-center rounded-lg text-text-muted transition-colors hover:bg-elevated hover:text-text-secondary"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 14 14"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            >
              <path d="M1 1l12 12M13 1L1 13" />
            </svg>
          </button>
        </div>
        <div className="text-text-secondary">{children}</div>
        <div className="mt-6 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="rounded-lg border border-border px-4 py-2 text-sm text-text-secondary transition-colors hover:bg-elevated"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={confirmDisabled}
            className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${confirmClass} ${
              confirmDisabled ? 'cursor-not-allowed opacity-50' : ''
            }`}
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  )
}
