import { AlertCircle, ChevronDown, Wrench } from "lucide-react"
import { useState } from "react"
import { Chip } from "./ui/Chip"
import { formatLatency } from "../lib/format"
import { GROUNDING_LABEL, GROUNDING_TONE, NEXT_ACTION_LABEL, NEXT_ACTION_TONE, USER_ACT_LABEL } from "../lib/semantics"
import type { ToolCall, TurnTrace } from "../lib/types"

export function TracePanel({ trace }: { trace: TurnTrace | null }) {
  if (!trace) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 px-8 text-center">
        <Wrench size={22} strokeWidth={1.5} className="text-muted" />
        <p className="text-[13px] text-muted">Send a message to see how Mira decided what to do.</p>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto px-4 py-4">
      <div className="flex flex-wrap items-center gap-2">
        <Chip tone="muted">{USER_ACT_LABEL[trace.user_act]}</Chip>
        <span className="text-muted">→</span>
        <Chip tone={NEXT_ACTION_TONE[trace.next_action.type]}>{NEXT_ACTION_LABEL[trace.next_action.type]}</Chip>
        <span className="ml-auto">
          <Chip tone={GROUNDING_TONE[trace.grounding_verdict]}>{GROUNDING_LABEL[trace.grounding_verdict]}</Chip>
        </span>
      </div>

      {trace.next_action.reason && (
        <p className="rounded-lg bg-cream-deep px-3 py-2 text-[13px] italic text-muted-dark">
          "{trace.next_action.reason}"
        </p>
      )}

      <div>
        <h3 className="mb-2 px-1 font-serif text-[15px] italic text-muted-dark">
          Tool calls {trace.tool_calls.length > 0 && `(${trace.tool_calls.length})`}
        </h3>
        {trace.tool_calls.length === 0 ? (
          <p className="px-1 text-[13px] text-muted">No tools needed this turn.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {trace.tool_calls.map((tc, i) => (
              <ToolCallCard key={i} call={tc} />
            ))}
          </div>
        )}
      </div>

      {trace.errors.length > 0 && (
        <div className="flex flex-col gap-1.5">
          {trace.errors.map((e, i) => (
            <div key={i} className="flex items-start gap-2 rounded-lg bg-rust-soft px-3 py-2 text-[12px] text-rust">
              <AlertCircle size={13} className="mt-0.5 shrink-0" />
              <span className="break-words">{e}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function ToolCallCard({ call }: { call: ToolCall }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="overflow-hidden rounded-xl border border-ink/10 bg-white/50">
      <button onClick={() => setOpen((o) => !o)} className="flex w-full items-center gap-2 px-3 py-2.5 text-left">
        <span className={`size-1.5 shrink-0 rounded-full ${call.ok ? "bg-good" : "bg-rust"}`} />
        <code className="flex-1 truncate text-[13px] font-medium text-ink">{call.name}</code>
        <span className="shrink-0 text-[11px] tabular-nums text-muted">{formatLatency(call.latency_ms)}</span>
        <ChevronDown size={14} className={`shrink-0 text-muted transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      <p className="px-3 pb-2.5 text-[12px] text-muted-dark">{call.result_summary}</p>
      {open && (
        <div className="border-t border-ink/8 bg-cream-deep/60 px-3 py-2.5">
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted">Args</p>
          <pre className="overflow-x-auto whitespace-pre-wrap break-all text-[11px] leading-relaxed text-muted-dark">
            {JSON.stringify(call.args, null, 2)}
          </pre>
          {call.error && (
            <>
              <p className="mb-1 mt-2 text-[10px] font-semibold uppercase tracking-wide text-rust">Error</p>
              <p className="text-[11px] text-rust">{call.error}</p>
            </>
          )}
        </div>
      )}
    </div>
  )
}
