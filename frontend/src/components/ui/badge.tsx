import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'

import { cn } from '@/lib/utils'

const badgeVariants = cva(
  'inline-flex items-center gap-1.5 px-2.5 py-0.5 text-[11px] font-medium leading-[16px] rounded-full border',
  {
    variants: {
      tone: {
        default:     'bg-transparent border-[var(--color-hairline-strong)] text-[var(--color-ash)]',
        secondary:   'bg-[rgba(0,113,227,0.10)] border-[var(--color-rust)]/40 text-[var(--color-rust)]',
        success:     'bg-[rgba(16,185,129,0.10)] border-[var(--color-patina)]/40 text-[var(--color-patina)]',
        warning:     'bg-[rgba(245,158,11,0.10)] border-[var(--color-ember)]/40 text-[var(--color-ember)]',
        destructive: 'bg-[rgba(239,68,68,0.10)] border-[var(--color-iron)]/40 text-[var(--color-iron)]',
        info:        'bg-[rgba(0,113,227,0.10)] border-[var(--color-rust)]/40 text-[var(--color-rust)]',
      },
      size: {
        default: 'px-2.5 py-0.5',
        sm: 'px-2 py-0',
        lg: 'px-3 py-1',
      },
    },
    defaultVariants: {
      tone: 'default',
      size: 'default',
    },
  }
)

export function Badge({
  className,
  tone,
  size,
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone, size }), className)} {...props} />
}
