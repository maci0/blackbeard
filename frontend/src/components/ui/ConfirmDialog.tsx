import * as Dialog from '@radix-ui/react-dialog'
import { X } from 'lucide-react'

interface ConfirmDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description: string
  confirmLabel?: string
  confirmVariant?: 'destructive' | 'default'
  onConfirm: () => void | Promise<void>
  loading?: boolean
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = 'Confirm',
  confirmVariant = 'default',
  onConfirm,
  loading,
}: ConfirmDialogProps) {
  const btnClass =
    confirmVariant === 'destructive'
      ? 'bg-red-600 text-white hover:bg-red-700'
      : 'bg-primary text-primary-foreground hover:opacity-90'

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50" />
        <Dialog.Content className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 bg-card border rounded-lg shadow-lg p-6 w-full max-w-md z-50">
          <Dialog.Title className="text-lg font-semibold">{title}</Dialog.Title>
          <Dialog.Description className="text-sm text-muted-foreground mt-2">
            {description}
          </Dialog.Description>
          <div className="flex justify-end gap-3 mt-6">
            <Dialog.Close asChild>
              <button className="px-4 py-2 text-sm rounded-lg border hover:bg-muted transition-colors">
                Cancel
              </button>
            </Dialog.Close>
            <button
              onClick={onConfirm}
              disabled={loading}
              className={`px-4 py-2 text-sm rounded-lg disabled:opacity-50 ${btnClass}`}
            >
              {loading ? 'Processing…' : confirmLabel}
            </button>
          </div>
          <Dialog.Close asChild>
            <button
              className="absolute top-4 right-4 text-muted-foreground hover:text-foreground transition-colors"
              aria-label="Close"
            >
              <X className="h-4 w-4" />
            </button>
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
