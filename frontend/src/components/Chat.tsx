import { AlertCircle, ArrowUp, Sparkles } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { Chip } from "./ui/Chip"
import { GROUNDING_LABEL, GROUNDING_TONE } from "../lib/semantics"
import type { ChatMessage, GroundingVerdict } from "../lib/types"

const SUGGESTIONS = [
  "A villa in Goa for 2, next weekend",
  "Family trip to Coorg, 2 adults + a kid",
  "Somewhere in Alibaug with an airport pickup",
]

export function Chat({
  messages,
  groundingByTurn,
  isLoading,
  error,
  onSend,
  onRetry,
  disabled,
}: {
  messages: ChatMessage[]
  groundingByTurn: Record<number, GroundingVerdict>
  isLoading: boolean
  error: string | null
  onSend: (text: string) => void
  onRetry: () => void
  disabled: boolean
}) {
  const [draft, setDraft] = useState("")
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" })
  }, [messages.length, isLoading])

  function submit() {
    const text = draft.trim()
    if (!text || disabled) return
    onSend(text)
    setDraft("")
  }

  return (
    <div className="flex h-full flex-col">
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-6 sm:px-10">
        {messages.length === 0 ? (
          <EmptyState onPick={(s) => setDraft(s)} />
        ) : (
          <div className="mx-auto flex max-w-2xl flex-col gap-4">
            {messages.map((m, i) => (
              <MessageBubble key={i} message={m} verdict={groundingByTurn[m.turn_index]} />
            ))}
            {isLoading && <TypingBubble />}
            {error && (
              <div className="animate-rise flex items-start gap-3 rounded-lg border border-rust/25 bg-rust-soft px-4 py-3 text-sm text-rust">
                <AlertCircle size={16} className="mt-0.5 shrink-0" />
                <div className="flex-1">
                  <p className="font-medium">Mira couldn't respond.</p>
                  <p className="text-rust/80">{error}</p>
                </div>
                <button
                  onClick={onRetry}
                  className="shrink-0 rounded-md border border-rust/30 px-2.5 py-1 text-xs font-semibold hover:bg-rust/10"
                >
                  Retry
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="border-t border-ink/10 bg-cream px-6 py-4 sm:px-10">
        <div className="mx-auto flex max-w-2xl items-end gap-2 rounded-2xl border border-ink/12 bg-white/60 p-2 shadow-soft-sm focus-within:border-accent/40">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault()
                submit()
              }
            }}
            disabled={disabled}
            rows={1}
            placeholder={disabled ? "Viewing a past turn — return to live to keep chatting" : "Tell Mira what you're looking for…"}
            className="max-h-32 flex-1 resize-none bg-transparent px-3 py-2 text-[15px] leading-snug text-ink placeholder:text-muted focus:outline-none disabled:cursor-not-allowed"
          />
          <button
            onClick={submit}
            disabled={disabled || !draft.trim()}
            aria-label="Send message"
            className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-accent text-cream transition hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-30"
          >
            <ArrowUp size={18} />
          </button>
        </div>
        <p className="mx-auto mt-2 max-w-2xl text-center text-[11px] text-muted">
          Mira only states facts it looked up — never a guessed price or availability.
        </p>
      </div>
    </div>
  )
}

function EmptyState({ onPick }: { onPick: (s: string) => void }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-6 text-center">
      <div className="flex size-14 items-center justify-center rounded-2xl bg-accent/10 text-accent">
        <Sparkles size={26} strokeWidth={1.6} />
      </div>
      <div>
        <h1 className="font-serif text-[32px] leading-tight text-ink">Where shall we look?</h1>
        <p className="mx-auto mt-2 max-w-sm text-[15px] text-muted">
          Tell Mira the destination, dates and who's coming — she'll search, quote and hold, grounded in real availability.
        </p>
      </div>
      <div className="flex flex-wrap justify-center gap-2">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            onClick={() => onPick(s)}
            className="rounded-full border border-ink/12 bg-white/50 px-3.5 py-2 text-[13px] text-muted-dark transition hover:border-accent/30 hover:bg-accent-soft hover:text-accent"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  )
}

function MessageBubble({ message, verdict }: { message: ChatMessage; verdict?: GroundingVerdict }) {
  const isGuest = message.role === "guest"
  return (
    <div className={`animate-rise flex ${isGuest ? "justify-end" : "justify-start"}`}>
      <div className={`flex max-w-[85%] flex-col gap-1 ${isGuest ? "items-end" : "items-start"}`}>
        {!isGuest && <span className="px-1 font-serif text-[13px] italic text-muted">Mira</span>}
        <div
          className={
            isGuest
              ? "rounded-2xl rounded-br-sm bg-accent px-4 py-2.5 text-[15px] leading-relaxed text-cream shadow-soft-sm"
              : "rounded-2xl rounded-bl-sm border border-ink/10 bg-white/70 px-4 py-2.5 text-[15px] leading-relaxed text-ink shadow-soft-sm"
          }
        >
          {message.text}
        </div>
        {!isGuest && verdict && verdict !== "clean" && (
          <Chip tone={GROUNDING_TONE[verdict]}>{GROUNDING_LABEL[verdict]}</Chip>
        )}
      </div>
    </div>
  )
}

function TypingBubble() {
  return (
    <div className="animate-rise flex justify-start">
      <div className="flex flex-col items-start gap-1">
        <span className="px-1 font-serif text-[13px] italic text-muted">Mira</span>
        <div className="flex items-center gap-1.5 rounded-2xl rounded-bl-sm border border-ink/10 bg-white/70 px-4 py-3.5 shadow-soft-sm">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="typing-dot size-1.5 rounded-full bg-muted"
              style={{ animationDelay: `${i * 0.15}s` }}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
