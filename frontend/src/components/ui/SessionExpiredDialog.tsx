import { useNavigate } from 'react-router-dom'
import * as Dialog from '@radix-ui/react-dialog'
import { useAuthStore } from '@/stores/authStore'

interface SessionExpiredDialogProps {
  open: boolean
}

export function SessionExpiredDialog({ open }: SessionExpiredDialogProps) {
  const navigate = useNavigate()
  const logout = useAuthStore((s) => s.logout)

  const handleLogin = () => {
    logout()
    void navigate('/login')
  }

  return (
    <Dialog.Root open={open}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out data-[state=open]:fade-in" />
        <Dialog.Content
          onEscapeKeyDown={(e) => e.preventDefault()}
          onPointerDownOutside={(e) => e.preventDefault()}
          onInteractOutside={(e) => e.preventDefault()}
          className="fixed left-1/2 top-1/2 z-50 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-lg border bg-card p-6 shadow-lg data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95"
        >
          <Dialog.Title className="text-lg font-semibold">Session Expired</Dialog.Title>
          <Dialog.Description className="mt-2 text-sm text-muted-foreground">
            Your session has expired. Please log in again.
          </Dialog.Description>
          <div className="mt-6 flex justify-end">
            <button
              type="button"
              onClick={handleLogin}
              autoFocus
              className="inline-flex items-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              Log In
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
