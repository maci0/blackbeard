import { useEffect, useRef } from 'react'
import hljs from 'highlight.js/lib/core'
import yaml from 'highlight.js/lib/languages/yaml'
import json from 'highlight.js/lib/languages/json'
import 'highlight.js/styles/github-dark.min.css'
import { cn } from '@/lib/utils'

if (!hljs.getLanguage('yaml')) hljs.registerLanguage('yaml', yaml)
if (!hljs.getLanguage('json')) hljs.registerLanguage('json', json)

interface CodeBlockProps {
  code: string
  language?: 'yaml' | 'json'
  className?: string
}

export function CodeBlock({ code, language = 'yaml', className }: CodeBlockProps) {
  const codeRef = useRef<HTMLElement>(null)

  useEffect(() => {
    if (codeRef.current) {
      codeRef.current.removeAttribute('data-highlighted')
      hljs.highlightElement(codeRef.current)
    }
  }, [code, language])

  return (
    <div
      role="region"
      aria-label={`${language.toUpperCase()} code`}
      tabIndex={0}
      className={cn(
        'overflow-auto rounded-lg border border-border bg-[#0d1117] text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring',
        className,
      )}
    >
      <pre className="m-0 p-4">
        <code ref={codeRef} className={`language-${language} !bg-transparent`}>
          {code}
        </code>
      </pre>
    </div>
  )
}
