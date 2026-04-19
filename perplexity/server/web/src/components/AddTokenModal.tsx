import { useState, useRef } from 'react'
import { Modal } from './ui/Modal'
import { TokenConfig } from 'lib/api'

interface AddTokenModalProps {
  isOpen: boolean
  onClose: () => void
  onSubmit: (id: string, csrf: string, session: string) => void
  onImportConfig?: (tokens: TokenConfig[]) => void
}

export function AddTokenModal({
  isOpen,
  onClose,
  onSubmit,
  onImportConfig
}: AddTokenModalProps) {
  const [form, setForm] = useState({ id: '', csrf: '', session: '' })
  const [mode, setMode] = useState<'manual' | 'upload'>('manual')
  const [uploadedTokens, setUploadedTokens] = useState<TokenConfig[] | null>(
    null
  )
  const [uploadError, setUploadError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleSubmit = () => {
    if (mode === 'upload' && uploadedTokens && onImportConfig) {
      onImportConfig(uploadedTokens)
      resetForm()
    } else if (mode === 'manual' && form.id && form.csrf && form.session) {
      onSubmit(form.id, form.csrf, form.session)
      resetForm()
    }
  }

  const resetForm = () => {
    setForm({ id: '', csrf: '', session: '' })
    setMode('manual')
    setUploadedTokens(null)
    setUploadError(null)
  }

  const handleClose = () => {
    resetForm()
    onClose()
  }

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    setUploadError(null)
    const reader = new FileReader()
    reader.onload = (event) => {
      try {
        const content = event.target?.result as string
        const parsed = JSON.parse(content)

        let tokens: TokenConfig[]
        if (Array.isArray(parsed)) {
          tokens = parsed
        } else if (parsed.tokens && Array.isArray(parsed.tokens)) {
          tokens = parsed.tokens
        } else {
          throw new Error('Invalid format: expected array of tokens')
        }

        for (const token of tokens) {
          if (!token.id || !token.csrf_token || !token.session_token) {
            throw new Error(
              'Invalid token entry: missing required fields (id, csrf_token, session_token)'
            )
          }
        }

        setUploadedTokens(tokens)
      } catch (err) {
        setUploadError(
          err instanceof Error ? err.message : 'Failed to parse config file'
        )
        setUploadedTokens(null)
      }
    }
    reader.onerror = () => {
      setUploadError('Failed to read file')
      setUploadedTokens(null)
    }
    reader.readAsText(file)
  }

  const isSubmitDisabled =
    mode === 'upload'
      ? !uploadedTokens || !onImportConfig
      : !form.id || !form.csrf || !form.session

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      onConfirm={handleSubmit}
      title="Add Token"
      confirmText={mode === 'upload' ? 'Import Config' : 'Add Token'}
      variant="primary"
      confirmDisabled={isSubmitDisabled}
    >
      <div className="space-y-5">
        {/* Mode Toggle */}
        <div className="flex gap-1 rounded-lg border border-border-subtle bg-elevated p-1">
          <button
            onClick={() => setMode('manual')}
            className={`flex-1 rounded-md px-3 py-1.5 text-sm transition-all ${
              mode === 'manual'
                ? 'bg-accent/15 font-medium text-accent'
                : 'text-text-muted hover:text-text-secondary'
            }`}
          >
            Manual Input
          </button>
          <button
            onClick={() => setMode('upload')}
            className={`flex-1 rounded-md px-3 py-1.5 text-sm transition-all ${
              mode === 'upload'
                ? 'bg-accent/15 font-medium text-accent'
                : 'text-text-muted hover:text-text-secondary'
            }`}
          >
            Upload Config
          </button>
        </div>

        {mode === 'manual' ? (
          <>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-text-muted">
                Identifier
              </label>
              <input
                type="text"
                placeholder="e.g. main"
                value={form.id}
                onChange={(e) => setForm({ ...form, id: e.target.value })}
                className="w-full rounded-lg border border-border bg-elevated p-3 text-sm text-text-primary transition-colors placeholder:text-text-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-text-muted">
                CSRF Token
              </label>
              <textarea
                rows={2}
                placeholder="Enter CSRF token..."
                value={form.csrf}
                onChange={(e) => setForm({ ...form, csrf: e.target.value })}
                className="w-full rounded-lg border border-border bg-elevated p-3 font-mono text-xs text-text-primary transition-colors placeholder:text-text-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-text-muted">
                Session Token
              </label>
              <textarea
                rows={3}
                placeholder="Enter session token..."
                value={form.session}
                onChange={(e) => setForm({ ...form, session: e.target.value })}
                className="w-full rounded-lg border border-border bg-elevated p-3 font-mono text-xs text-text-primary transition-colors placeholder:text-text-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
              />
            </div>
          </>
        ) : (
          <div className="space-y-4">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-text-muted">
                Upload Config File (JSON)
              </label>
              <input
                ref={fileInputRef}
                type="file"
                accept=".json"
                onChange={handleFileUpload}
                className="hidden"
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                className="flex w-full flex-col items-center gap-2 rounded-xl border-2 border-dashed border-border bg-elevated p-8 text-sm text-text-muted transition-colors hover:border-accent/50 hover:text-accent"
              >
                <svg
                  className="size-8 opacity-40"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={1}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M12 16.5V9.75m0 0l3 3m-3-3l-3 3M6.75 19.5a4.5 4.5 0 01-1.41-8.775 5.25 5.25 0 0110.233-2.33 3 3 0 013.758 3.848A3.752 3.752 0 0118 19.5H6.75z"
                  />
                </svg>
                {uploadedTokens ? (
                  <span className="text-accent">
                    Config loaded: {uploadedTokens.length} token(s)
                  </span>
                ) : (
                  'Click to select tokens.json'
                )}
              </button>
            </div>

            {uploadError && (
              <div className="rounded-lg border border-error/20 bg-error/10 p-3 text-xs text-error">
                Error: {uploadError}
              </div>
            )}

            {uploadedTokens && (
              <div className="space-y-2 rounded-lg border border-border bg-elevated p-4 text-xs">
                <div className="text-text-secondary">
                  <span className="text-accent">Tokens:</span>{' '}
                  {uploadedTokens.length}
                </div>
                <div className="mt-2 border-t border-border-subtle pt-2 font-mono text-text-muted">
                  IDs: {uploadedTokens.map((t) => t.id).join(', ')}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </Modal>
  )
}
