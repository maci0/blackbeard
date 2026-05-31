import { useState, useEffect, useRef, useCallback, type KeyboardEvent } from 'react'
import {
  Send,
  Square,
  Trash2,
  ChevronDown,
  ChevronRight,
  Clock,
  Hash,
  AlertTriangle,
  Gauge,
} from 'lucide-react'
import { useDocumentTitle } from '@/hooks'
import { api } from '@/api/client'
import { PageHeader } from '@/components/ui/PageHeader'
import { ModelSelectorSkeleton } from '@/components/ui/Skeleton'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { cn, getErrorMessage } from '@/lib/utils'

interface TokenUsage {
  prompt: number
  completion: number
  total: number
  prompt_time_ms?: number | null
  completion_time_ms?: number | null
}

interface ModelInfo {
  name: string
  provider: string | null
  model_id: string | null
}

interface Message {
  id: string
  role: 'system' | 'user' | 'assistant'
  content: string
  thinking?: string
  displayContent?: string
  streaming?: boolean
  tokens?: TokenUsage
  latency_ms?: number
  error?: string
}

function tokPerSec(tokenCount: number, timeMs: number): string {
  if (timeMs <= 0 || tokenCount <= 0) return '—'
  return (tokenCount / (timeMs / 1000)).toFixed(1)
}

function TokenBadge({ tokens, latency_ms }: { tokens: TokenUsage; latency_ms: number }) {
  const ppSpeed = tokens.prompt_time_ms ? tokPerSec(tokens.prompt, tokens.prompt_time_ms) : null
  const tgSpeed = tokens.completion_time_ms
    ? tokPerSec(tokens.completion, tokens.completion_time_ms)
    : null
  const totalSpeed = latency_ms > 0 ? tokPerSec(tokens.completion, latency_ms) : null

  return (
    <div className="mt-1.5 flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
      <span
        className="inline-flex items-center gap-1"
        title="Prompt tokens"
        aria-label={`${tokens.prompt.toLocaleString()} prompt tokens`}
      >
        <Hash className="h-3 w-3" aria-hidden="true" />
        {tokens.prompt.toLocaleString()} in
      </span>
      <span
        className="inline-flex items-center gap-1"
        title="Completion tokens"
        aria-label={`${tokens.completion.toLocaleString()} completion tokens`}
      >
        <Hash className="h-3 w-3" aria-hidden="true" />
        {tokens.completion.toLocaleString()} out
      </span>
      <span
        className="inline-flex items-center gap-1 border-l pl-3"
        title="Response latency"
        aria-label={`${latency_ms.toLocaleString()} milliseconds latency`}
      >
        <Clock className="h-3 w-3" aria-hidden="true" />
        {latency_ms.toLocaleString()} ms
      </span>
      {(ppSpeed || tgSpeed || totalSpeed) && (
        <span
          className="inline-flex items-center gap-1 border-l pl-3"
          title={
            ppSpeed && tgSpeed
              ? `Prompt processing: ${ppSpeed} tok/s, Text generation: ${tgSpeed} tok/s`
              : `${totalSpeed} tok/s (end-to-end)`
          }
        >
          <Gauge className="h-3 w-3" aria-hidden="true" />
          {ppSpeed && tgSpeed ? (
            <>
              prefill {ppSpeed} · decode {tgSpeed} tok/s
            </>
          ) : (
            <>{totalSpeed} tok/s</>
          )}
        </span>
      )}
    </div>
  )
}

function ThinkingBlock({ text }: { text: string }) {
  const [open, setOpen] = useState(false)
  return (
    <details
      className="mt-1 rounded border border-violet-200 bg-violet-50 dark:border-violet-800 dark:bg-violet-950/30"
      open={open}
      onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
    >
      <summary className="cursor-pointer select-none rounded px-3 py-1.5 text-xs font-medium text-violet-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring dark:text-violet-400">
        {open ? 'Hide' : 'Show'} thinking ({text.length} chars)
      </summary>
      <div className="max-h-48 overflow-y-auto whitespace-pre-wrap border-t border-violet-200 px-3 py-2 font-mono text-xs text-muted-foreground dark:border-violet-800">
        {text}
      </div>
    </details>
  )
}

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === 'user'
  const visibleText = message.displayContent ?? message.content

  return (
    <div className={cn('flex', isUser ? 'justify-end' : 'justify-start')}>
      <div
        aria-label={`${isUser ? 'You' : 'Assistant'} message`}
        className={cn(
          'max-w-[80%] rounded-lg px-4 py-3',
          isUser
            ? 'bg-primary text-primary-foreground'
            : message.error
              ? 'border border-destructive/20 bg-destructive/5'
              : 'border bg-card',
        )}
      >
        <p className="text-xs font-medium uppercase tracking-wide opacity-60">
          {isUser ? 'You' : 'Assistant'}
        </p>
        {message.thinking && !message.streaming && <ThinkingBlock text={message.thinking} />}
        <div className="mt-1 whitespace-pre-wrap text-sm">
          {visibleText}
          {message.streaming && (
            <span className="animate-pulse text-primary motion-reduce:animate-none">&#9613;</span>
          )}
        </div>
        {message.error && (
          <div className="mt-2 flex items-center gap-1.5 text-xs text-destructive">
            <AlertTriangle className="h-3 w-3 shrink-0" aria-hidden="true" />
            {message.error}
          </div>
        )}
        {message.tokens && message.latency_ms != null && !message.streaming && (
          <TokenBadge tokens={message.tokens} latency_ms={message.latency_ms} />
        )}
      </div>
    </div>
  )
}

export default function Chat() {
  useDocumentTitle('Chat')

  const [models, setModels] = useState<ModelInfo[]>([])
  const [modelsLoading, setModelsLoading] = useState(true)
  const [modelsError, setModelsError] = useState<string | null>(null)
  const [selectedModel, setSelectedModel] = useState('')
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [systemPrompt, setSystemPrompt] = useState('')
  const [systemPromptOpen, setSystemPromptOpen] = useState(false)
  const [temperature, setTemperature] = useState('0.7')
  const [maxTokens, setMaxTokens] = useState('4096')

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, scrollToBottom])

  const fetchModels = useCallback(() => {
    setModelsLoading(true)
    setModelsError(null)
    api
      .get<ModelInfo[]>('/api/v1/models/available')
      .then((data) => {
        setModels(data)
        if (data.length > 0) {
          setSelectedModel((prev) => prev || data[0]!.name)
        }
      })
      .catch((err: unknown) => {
        setModelsError(getErrorMessage(err, 'Failed to load models'))
      })
      .finally(() => {
        setModelsLoading(false)
      })
  }, [])

  useEffect(() => {
    fetchModels()
  }, [fetchModels])

  const autoResizeTextarea = useCallback(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }, [])

  useEffect(() => {
    autoResizeTextarea()
  }, [input, autoResizeTextarea])

  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    return () => {
      abortRef.current?.abort()
    }
  }, [])

  const handleSend = useCallback(async () => {
    const trimmed = input.trim()
    if (!trimmed || !selectedModel || sending) return

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: trimmed,
    }

    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setSending(true)

    const chatMessages: { role: string; content: string }[] = []
    if (systemPrompt.trim()) {
      chatMessages.push({ role: 'system', content: systemPrompt.trim() })
    }
    for (const m of [...messages, userMsg]) {
      if (m.role === 'user' || m.role === 'assistant') {
        chatMessages.push({ role: m.role, content: m.content })
      }
    }

    const body: Record<string, unknown> = {
      model: selectedModel,
      messages: chatMessages,
    }
    const temp = parseFloat(temperature)
    if (!isNaN(temp) && temp >= 0 && temp <= 2) {
      body.temperature = temp
    }
    const tokens = parseInt(maxTokens, 10)
    if (!isNaN(tokens) && tokens >= 1) {
      body.max_tokens = tokens
    }

    const msgId = crypto.randomUUID()
    const assistantMsg: Message = {
      id: msgId,
      role: 'assistant',
      content: '',
      streaming: true,
    }
    setMessages((prev) => [...prev, assistantMsg])

    const controller = new AbortController()
    abortRef.current = controller
    let accumulated = ''
    let accumulatedThinking = ''
    let rafPending = 0

    function flushContent() {
      rafPending = 0
      const snapshot = accumulated
      setMessages((prev) => prev.map((m) => (m.id === msgId ? { ...m, content: snapshot } : m)))
    }

    try {
      const resp = await fetch('/api/v1/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...api.getAuthHeaders() },
        body: JSON.stringify(body),
        signal: controller.signal,
      })

      if (!resp.ok || !resp.body) {
        const text = await resp.text().catch(() => 'Unknown error')
        throw new Error(text)
      }

      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const dataStr = line.slice(6).trim()
          if (!dataStr) continue
          try {
            const event = JSON.parse(dataStr) as {
              content?: string
              reasoning_content?: string
              done?: boolean
              error?: string
              tokens?: TokenUsage
              latency_ms?: number
              model?: string
            }
            if (event.error) {
              if (rafPending) {
                cancelAnimationFrame(rafPending)
                rafPending = 0
              }
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === msgId
                    ? {
                        ...m,
                        content: accumulated || 'Failed to get a response.',
                        error: event.error,
                        streaming: false,
                      }
                    : m,
                ),
              )
              setSending(false)
              textareaRef.current?.focus()
              return
            }
            if (event.reasoning_content) {
              accumulatedThinking += event.reasoning_content
            }
            if (event.content) {
              accumulated += event.content
              if (!rafPending) {
                rafPending = requestAnimationFrame(flushContent)
              }
            }
            if (event.done) {
              if (rafPending) {
                cancelAnimationFrame(rafPending)
                rafPending = 0
              }
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === msgId
                    ? {
                        ...m,
                        content: accumulated,
                        thinking: accumulatedThinking || undefined,
                        streaming: false,
                        tokens: event.tokens,
                        latency_ms: event.latency_ms,
                      }
                    : m,
                ),
              )
            }
          } catch (parseErr) {
            console.debug('[chat] unparseable SSE chunk:', dataStr?.slice(0, 200), parseErr)
            continue
          }
        }
      }
    } catch (err: unknown) {
      if (rafPending) {
        cancelAnimationFrame(rafPending)
        rafPending = 0
      }
      if (controller.signal.aborted) return
      const errorText = err instanceof Error ? err.message : getErrorMessage(err, 'Request failed')
      setMessages((prev) =>
        prev.map((m) =>
          m.id === msgId
            ? {
                ...m,
                content: accumulated.length > 0 ? accumulated : 'Failed to get a response.',
                error: errorText,
                streaming: false,
              }
            : m,
        ),
      )
    } finally {
      setSending(false)
      abortRef.current = null
      textareaRef.current?.focus()
    }
  }, [input, selectedModel, sending, systemPrompt, messages, temperature, maxTokens])

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        void handleSend()
      }
    },
    [handleSend],
  )

  const handleStop = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setSending(false)
    setMessages((prev) => prev.map((m) => (m.streaming ? { ...m, streaming: false } : m)))
    textareaRef.current?.focus()
  }, [])

  const [clearOpen, setClearOpen] = useState(false)

  const handleClear = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setMessages([])
    setSending(false)
    setClearOpen(false)
    textareaRef.current?.focus()
  }, [])

  return (
    <div className="page-enter flex flex-1 flex-col overflow-hidden">
      <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col overflow-hidden p-6">
        <div className="mb-4">
          <PageHeader
            title="Chat"
            description="Test models with ad-hoc conversations"
            actions={
              messages.length > 0 ? (
                <button
                  type="button"
                  onClick={() => setClearOpen(true)}
                  className="inline-flex items-center gap-1.5 rounded-md border bg-background px-3 py-2 text-sm transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  aria-label="Clear conversation"
                >
                  <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                  Clear
                </button>
              ) : undefined
            }
          />
        </div>

        <div className="mb-4 flex flex-wrap items-end gap-3">
          <div className="min-w-[200px] flex-1">
            <label htmlFor="chat-model" className="mb-1.5 block text-xs font-medium">
              Model
            </label>
            {modelsLoading ? (
              <ModelSelectorSkeleton />
            ) : modelsError ? (
              <div className="flex h-9 items-center gap-2 rounded-md border border-destructive/30 px-3 text-sm text-destructive">
                <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                <span className="flex-1 truncate">{modelsError}</span>
                <button
                  type="button"
                  onClick={fetchModels}
                  className="shrink-0 text-xs font-medium underline underline-offset-2 hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  Retry
                </button>
              </div>
            ) : (
              <select
                id="chat-model"
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                disabled={sending}
                className="w-full rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
              >
                {models.map((m) => (
                  <option key={m.name} value={m.name}>
                    {m.name}
                    {m.provider ? ` (${m.provider})` : ''}
                  </option>
                ))}
              </select>
            )}
          </div>

          <div className="w-24">
            <label htmlFor="chat-temperature" className="mb-1.5 block text-xs font-medium">
              Temperature
            </label>
            <input
              id="chat-temperature"
              type="number"
              min="0"
              max="2"
              step="0.1"
              value={temperature}
              onChange={(e) => setTemperature(e.target.value)}
              disabled={sending}
              className="w-full rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
            />
          </div>

          <div className="w-28">
            <label htmlFor="chat-max-tokens" className="mb-1.5 block text-xs font-medium">
              Max tokens
            </label>
            <input
              id="chat-max-tokens"
              type="number"
              min="1"
              max="128000"
              step="1"
              value={maxTokens}
              onChange={(e) => setMaxTokens(e.target.value)}
              disabled={sending}
              className="w-full rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
            />
          </div>
        </div>

        <div className="mb-4">
          <button
            type="button"
            onClick={() => setSystemPromptOpen((v) => !v)}
            className="inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            aria-expanded={systemPromptOpen}
            aria-controls="system-prompt-area"
          >
            {systemPromptOpen ? (
              <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
            )}
            System prompt
            {systemPrompt.trim() && (
              <span className="rounded-full bg-primary/10 px-1.5 py-0.5 text-[10px] text-primary">
                set
              </span>
            )}
          </button>
          {systemPromptOpen && (
            <textarea
              id="system-prompt-area"
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              disabled={sending}
              placeholder="You are a helpful assistant..."
              aria-label="System prompt"
              rows={3}
              className="mt-2 w-full resize-y rounded-md border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
            />
          )}
        </div>

        <div
          className="flex-1 overflow-y-auto rounded-lg border bg-muted/20 p-4"
          role="log"
          aria-label="Chat messages"
          aria-live="polite"
        >
          {messages.length === 0 ? (
            <div className="flex h-full items-center justify-center">
              <p className="text-sm text-muted-foreground">
                {selectedModel
                  ? 'Send a message to start the conversation.'
                  : 'Select a model to get started.'}
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {messages.map((m) => (
                <MessageBubble key={m.id} message={m} />
              ))}
              {sending && (
                <div className="flex justify-start">
                  <div className="flex items-center gap-2 rounded-lg border bg-card px-4 py-3">
                    <div className="flex gap-1" role="status" aria-label="Generating response">
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/60 [animation-delay:-0.3s] motion-reduce:animate-none" />
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/60 [animation-delay:-0.15s] motion-reduce:animate-none" />
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/60 motion-reduce:animate-none" />
                    </div>
                    <span className="text-sm text-muted-foreground">Thinking...</span>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        <div className="mt-3 flex gap-2">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={!selectedModel}
            placeholder={
              selectedModel
                ? 'Type a message... (Enter to send, Shift+Enter for newline)'
                : 'Select a model first'
            }
            rows={1}
            className="flex-1 resize-none rounded-md border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
            aria-label="Message input"
            aria-describedby="chat-input-hint"
          />
          <span id="chat-input-hint" className="sr-only">
            Press Enter to send, Shift+Enter for a new line
          </span>
          {sending ? (
            <button
              type="button"
              onClick={handleStop}
              aria-label="Stop generating"
              className="flex min-h-[44px] min-w-[44px] items-center justify-center rounded-md bg-destructive px-4 text-destructive-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Square className="h-4 w-4" aria-hidden="true" />
            </button>
          ) : (
            <button
              type="button"
              onClick={() => void handleSend()}
              disabled={!input.trim() || !selectedModel}
              aria-label="Send message"
              className="flex min-h-[44px] min-w-[44px] items-center justify-center rounded-md bg-primary px-4 text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Send className="h-4 w-4" aria-hidden="true" />
            </button>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={clearOpen}
        onOpenChange={setClearOpen}
        title="Clear conversation"
        description="This will delete all messages in the current conversation. This cannot be undone."
        confirmLabel="Clear"
        confirmVariant="destructive"
        onConfirm={handleClear}
      />
    </div>
  )
}
