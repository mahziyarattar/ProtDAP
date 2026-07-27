import type { HTMLAttributes, ReactNode } from 'react'

/**
 * Text direction follows the content (Persian/Arabic → RTL, English → LTR).
 * Use on any user/LLM-facing copy. Do NOT put this on the app shell/layout
 * or the whole chrome will flip and break English UI structure.
 */
export function DirAuto({
  children,
  className,
  as: Tag = 'div',
  ...rest
}: {
  children: ReactNode
  className?: string
  as?: 'div' | 'p' | 'span' | 'h1' | 'h2' | 'h3' | 'li'
} & HTMLAttributes<HTMLElement>) {
  return (
    <Tag dir="auto" className={className} {...rest}>
      {children}
    </Tag>
  )
}

/**
 * Keep accessions, sequences, and other Latin/code tokens LTR even when the
 * surrounding paragraph is RTL (unicode-bidi: isolate).
 */
export function LtrIsolate({
  children,
  className,
  as: Tag = 'span',
  ...rest
}: {
  children: ReactNode
  className?: string
  as?: 'span' | 'div' | 'code'
} & HTMLAttributes<HTMLElement>) {
  return (
    <Tag dir="ltr" className={`ltr-isolate ${className ?? ''}`} {...rest}>
      {children}
    </Tag>
  )
}
