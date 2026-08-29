import clsx from "clsx"
import type { ReactNode } from "react"

export type ChipTone = "accent" | "good" | "rust" | "muted"

const TONE_CLASSES: Record<ChipTone, string> = {
  accent: "bg-accent-soft text-accent",
  good: "bg-good-soft text-good",
  rust: "bg-rust-soft text-rust",
  muted: "bg-cream-deep text-muted-dark",
}

export function Chip({ tone = "muted", children, icon }: { tone?: ChipTone; children: ReactNode; icon?: ReactNode }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide",
        TONE_CLASSES[tone],
      )}
    >
      {icon}
      {children}
    </span>
  )
}
