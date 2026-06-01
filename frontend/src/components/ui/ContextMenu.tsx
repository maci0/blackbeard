import * as ContextMenuPrimitive from '@radix-ui/react-context-menu'

function ContextMenu({ children }: { children: React.ReactNode }) {
  return <ContextMenuPrimitive.Root>{children}</ContextMenuPrimitive.Root>
}

function ContextMenuTrigger({ children }: { children: React.ReactNode }) {
  return <ContextMenuPrimitive.Trigger asChild>{children}</ContextMenuPrimitive.Trigger>
}

function ContextMenuContent({ children }: { children: React.ReactNode }) {
  return (
    <ContextMenuPrimitive.Portal>
      <ContextMenuPrimitive.Content className="z-50 min-w-[180px] rounded-lg border border-border bg-card py-1 shadow-lg data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95">
        {children}
      </ContextMenuPrimitive.Content>
    </ContextMenuPrimitive.Portal>
  )
}

function ContextMenuItem({
  children,
  onSelect,
  disabled,
}: {
  children: React.ReactNode
  onSelect?: () => void
  disabled?: boolean
}) {
  return (
    <ContextMenuPrimitive.Item
      onSelect={onSelect}
      disabled={disabled}
      className="mx-1 cursor-pointer rounded-sm px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-muted focus:bg-muted focus:outline-none data-[disabled]:pointer-events-none data-[disabled]:opacity-50"
    >
      {children}
    </ContextMenuPrimitive.Item>
  )
}

function ContextMenuSeparator() {
  return <ContextMenuPrimitive.Separator className="mx-2 my-1 h-px bg-border" />
}

function ContextMenuLabel({ children }: { children: React.ReactNode }) {
  return (
    <ContextMenuPrimitive.Label className="px-3 py-1.5 text-xs font-semibold text-muted-foreground">
      {children}
    </ContextMenuPrimitive.Label>
  )
}

export {
  ContextMenu,
  ContextMenuTrigger,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuLabel,
}
