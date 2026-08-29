import { Layers, MessageCircle, PanelRightClose, PanelRightOpen, RotateCcw } from "lucide-react"
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react"
import { Chat } from "./components/Chat"
import { StatePanel } from "./components/StatePanel"
import { TracePanel } from "./components/TracePanel"
import { TurnTimeline } from "./components/TurnTimeline"
import { ApiRequestError, createConversation, getConversation, postMessage } from "./lib/api"
import type { ChatMessage, ConversationState, GroundingVerdict, TurnTrace } from "./lib/types"

type Tab = "state" | "trace" | "timeline"
type BootStatus = "loading" | "ready" | "error"

function App() {
  const [bootStatus, setBootStatus] = useState<BootStatus>("loading")
  const [bootError, setBootError] = useState<string | null>(null)
  const [conversationId, setConversationId] = useState<string | null>(null)

  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [snapshots, setSnapshots] = useState<ConversationState[]>([])
  const [traces, setTraces] = useState<TurnTrace[]>([])
  const [viewingTurn, setViewingTurn] = useState(0)

  const [isSending, setIsSending] = useState(false)
  const [sendError, setSendError] = useState<string | null>(null)
  const lastFailedTextRef = useRef<string | null>(null)

  const [tab, setTab] = useState<Tab>("state")
  const [consoleOpen, setConsoleOpen] = useState(true)

  useEffect(() => {
    let cancelled = false
    async function boot() {
      try {
        const { conversation_id } = await createConversation()
        const detail = await getConversation(conversation_id)
        if (cancelled) return
        setConversationId(conversation_id)
        setSnapshots(detail.snapshots)
        setViewingTurn(0)
        setBootStatus("ready")
      } catch (e) {
        if (cancelled) return
        setBootError(e instanceof ApiRequestError ? e.message : "Something went wrong starting the conversation.")
        setBootStatus("error")
      }
    }
    boot()
    return () => {
      cancelled = true
    }
  }, [])

  const latestTurn = snapshots.length > 0 ? snapshots[snapshots.length - 1].turn_index : 0
  const isLive = viewingTurn === latestTurn

  const sendTurn = useCallback(
    async (text: string, appendGuestBubble: boolean) => {
      if (!conversationId) return
      if (appendGuestBubble) {
        setMessages((prev) => [...prev, { turn_index: latestTurn + 1, role: "guest", text }])
      }
      setIsSending(true)
      setSendError(null)
      try {
        const res = await postMessage(conversationId, text)
        setSnapshots((prev) => [...prev, res.state])
        setTraces((prev) => [...prev, res.trace])
        const showsOptions = res.trace.next_action.type === "present" || res.trace.next_action.type === "present_alternatives"
        setMessages((prev) => [
          ...prev,
          {
            turn_index: res.state.turn_index,
            role: "mira",
            text: res.reply,
            options: showsOptions ? res.state.shortlist : undefined,
          },
        ])
        setViewingTurn(res.state.turn_index)
        lastFailedTextRef.current = null
      } catch (e) {
        lastFailedTextRef.current = text
        setSendError(e instanceof ApiRequestError ? e.message : "Mira didn't respond — check your connection.")
      } finally {
        setIsSending(false)
      }
    },
    [conversationId, latestTurn],
  )

  const handleSend = useCallback((text: string) => sendTurn(text, true), [sendTurn])
  const handleRetry = useCallback(() => {
    if (lastFailedTextRef.current) sendTurn(lastFailedTextRef.current, false)
  }, [sendTurn])

  const groundingByTurn: Record<number, GroundingVerdict> = {}
  for (const t of traces) groundingByTurn[t.turn_index] = t.grounding_verdict

  const viewedState = snapshots.find((s) => s.turn_index === viewingTurn) ?? snapshots[snapshots.length - 1] ?? null
  const viewedTrace = traces.find((t) => t.turn_index === viewingTurn) ?? null

  if (bootStatus === "loading") {
    return <FullScreenMessage title="Waking Mira up…" subtitle="Loading the catalogue and starting a conversation." spinner />
  }
  if (bootStatus === "error" || !conversationId || !viewedState) {
    return (
      <FullScreenMessage
        title="Couldn't connect to Mira"
        subtitle={bootError ?? "Unknown error"}
        action={{ label: "Try again", onClick: () => window.location.reload() }}
      />
    )
  }

  return (
    <div className="flex h-screen flex-col bg-cream">
      <header className="flex shrink-0 items-center justify-between border-b border-ink/10 bg-cream px-6 py-3.5 sm:px-8">
        <div className="flex items-baseline gap-2.5">
          <span className="font-serif text-[22px] italic text-ink">Mira</span>
          <span className="hidden text-[12px] text-muted sm:inline">the Mehman guest concierge</span>
        </div>
        <button
          onClick={() => setConsoleOpen((o) => !o)}
          className="flex items-center gap-1.5 rounded-lg border border-ink/12 px-2.5 py-1.5 text-[12px] font-medium text-muted-dark transition hover:bg-cream-deep"
        >
          {consoleOpen ? <PanelRightClose size={14} /> : <PanelRightOpen size={14} />}
          {consoleOpen ? "Hide console" : "Show console"}
        </button>
      </header>

      <div className="flex min-h-0 flex-1">
        <main className={`min-w-0 flex-1 ${consoleOpen ? "border-r border-ink/10" : ""}`}>
          <Chat
            messages={messages}
            groundingByTurn={groundingByTurn}
            isLoading={isSending}
            error={sendError}
            onSend={handleSend}
            onRetry={handleRetry}
            disabled={!isLive || isSending}
          />
        </main>

        {consoleOpen && (
          <aside className="hidden w-[380px] shrink-0 flex-col bg-cream-deep/40 md:flex">
            <nav className="flex shrink-0 gap-1 border-b border-ink/10 px-3 pt-3">
              <TabButton active={tab === "state"} onClick={() => setTab("state")} icon={<Layers size={13} />} label="State" />
              <TabButton active={tab === "trace"} onClick={() => setTab("trace")} icon={<MessageCircle size={13} />} label="Trace" />
              <TabButton active={tab === "timeline"} onClick={() => setTab("timeline")} icon={<RotateCcw size={13} />} label="Timeline" />
            </nav>
            <div className="min-h-0 flex-1">
              {tab === "state" && <StatePanel state={viewedState} />}
              {tab === "trace" && <TracePanel trace={viewedTrace} />}
              {tab === "timeline" && (
                <TurnTimeline
                  traces={traces}
                  viewingTurn={viewingTurn}
                  latestTurn={latestTurn}
                  onSelect={setViewingTurn}
                  onGoLive={() => setViewingTurn(latestTurn)}
                />
              )}
            </div>
          </aside>
        )}
      </div>
    </div>
  )
}

function TabButton({ active, onClick, icon, label }: { active: boolean; onClick: () => void; icon: ReactNode; label: string }) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 rounded-t-lg px-3 py-2 text-[12px] font-semibold transition ${
        active ? "bg-cream text-accent" : "text-muted hover:text-muted-dark"
      }`}
    >
      {icon}
      {label}
    </button>
  )
}

function FullScreenMessage({
  title,
  subtitle,
  spinner,
  action,
}: {
  title: string
  subtitle: string
  spinner?: boolean
  action?: { label: string; onClick: () => void }
}) {
  return (
    <div className="flex h-screen flex-col items-center justify-center gap-4 bg-cream px-6 text-center">
      {spinner && <div className="size-8 animate-spin rounded-full border-2 border-accent/25 border-t-accent" />}
      <div>
        <h1 className="font-serif text-[26px] italic text-ink">{title}</h1>
        <p className="mt-1.5 max-w-sm text-[14px] text-muted">{subtitle}</p>
      </div>
      {action && (
        <button
          onClick={action.onClick}
          className="rounded-lg bg-accent px-4 py-2 text-[13px] font-semibold text-cream hover:bg-accent-hover"
        >
          {action.label}
        </button>
      )}
    </div>
  )
}

export default App
