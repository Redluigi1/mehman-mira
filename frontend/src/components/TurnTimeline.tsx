import { Radio } from "lucide-react"
import { NEXT_ACTION_LABEL, NEXT_ACTION_TONE } from "../lib/semantics"
import type { TurnTrace } from "../lib/types"

const DOT_TONE: Record<string, string> = {
  accent: "bg-accent",
  good: "bg-good",
  rust: "bg-rust",
  muted: "bg-muted",
}

export function TurnTimeline({
  traces,
  viewingTurn,
  latestTurn,
  onSelect,
  onGoLive,
}: {
  traces: TurnTrace[]
  viewingTurn: number
  latestTurn: number
  onSelect: (turnIndex: number) => void
  onGoLive: () => void
}) {
  if (traces.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 px-8 text-center">
        <Radio size={22} strokeWidth={1.5} className="text-muted" />
        <p className="text-[13px] text-muted">Every turn will appear here — click one to time-travel the console.</p>
      </div>
    )
  }

  const isLive = viewingTurn === latestTurn

  return (
    <div className="flex h-full flex-col overflow-y-auto px-3 py-4">
      {!isLive && (
        <button
          onClick={onGoLive}
          className="mb-3 flex items-center justify-center gap-1.5 rounded-lg border border-accent/25 bg-accent-soft px-3 py-2 text-[12px] font-semibold text-accent hover:bg-accent/15"
        >
          <Radio size={12} /> Back to live · turn {latestTurn}
        </button>
      )}
      <ol className="relative flex flex-col gap-0.5 pl-3">
        <span className="absolute bottom-2 left-[15px] top-2 w-px bg-ink/10" aria-hidden />
        {traces.map((t) => {
          const selected = t.turn_index === viewingTurn
          const tone = NEXT_ACTION_TONE[t.next_action.type]
          return (
            <li key={t.turn_index}>
              <button
                onClick={() => onSelect(t.turn_index)}
                className={`relative flex w-full items-start gap-3 rounded-lg px-2.5 py-2 text-left transition-colors ${
                  selected ? "bg-accent-soft" : "hover:bg-cream-deep"
                }`}
              >
                <span className={`relative z-10 mt-1.5 size-2.5 shrink-0 rounded-full ring-4 ring-cream ${DOT_TONE[tone]}`} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-[12px] font-semibold text-ink">Turn {t.turn_index}</span>
                    <span className="text-[10px] uppercase tracking-wide text-muted">{t.user_act.replace(/_/g, " ")}</span>
                  </div>
                  <p className="truncate text-[12px] text-muted-dark">{NEXT_ACTION_LABEL[t.next_action.type]}</p>
                </div>
              </button>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
