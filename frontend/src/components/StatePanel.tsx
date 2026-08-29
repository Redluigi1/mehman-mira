import { AlertTriangle, HelpCircle } from "lucide-react"
import type { ReactNode } from "react"
import { Chip } from "./ui/Chip"
import { formatDateRange, formatInr, titleCase } from "../lib/format"
import type { ConversationState, Slot } from "../lib/types"

function SlotField<T>({
  label,
  slot,
  turnIndex,
  render,
}: {
  label: string
  slot: Slot<T>
  turnIndex: number
  render: (v: T) => ReactNode
}) {
  const changed = slot.value !== null && slot.source_turn === turnIndex
  return (
    <div
      className={`flex items-start justify-between gap-3 rounded-lg px-2.5 py-2 transition-colors ${
        changed ? "bg-accent-soft" : ""
      }`}
    >
      <span className="pt-0.5 text-[12px] font-medium uppercase tracking-wide text-muted">{label}</span>
      <div className="flex flex-col items-end gap-1 text-right">
        {slot.value === null ? (
          <span className="inline-flex items-center gap-1 text-[13px] italic text-muted">
            <HelpCircle size={12} /> unknown
          </span>
        ) : (
          <span className="text-[14px] text-ink">{render(slot.value)}</span>
        )}
        {slot.is_assumption && slot.value !== null && (
          <span className="rounded-full bg-cream-deeper px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted-dark">
            assumption
          </span>
        )}
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-b border-ink/8 px-3 py-3 last:border-b-0">
      <h3 className="mb-1 px-2 font-serif text-[15px] italic text-muted-dark">{title}</h3>
      <div className="flex flex-col gap-0.5">{children}</div>
    </section>
  )
}

export function StatePanel({ state }: { state: ConversationState }) {
  const { intent } = state
  const turnIndex = state.turn_index

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <Section title="The ask">
        <SlotField label="Destination" slot={intent.destination} turnIndex={turnIndex}
          render={(d) => `${d.city}${d.area ? `, ${d.area}` : ""}${d.flexible ? " (flexible)" : ""}`} />
        <SlotField label="Dates" slot={intent.stay} turnIndex={turnIndex}
          render={(s) => `${formatDateRange(s.check_in, s.check_out)}${s.nights ? ` · ${s.nights}n` : ""}`} />
        <SlotField label="Guests" slot={intent.party} turnIndex={turnIndex}
          render={(p) => `${p.adults ?? "?"} adult${p.adults === 1 ? "" : "s"}${p.children.length ? ` + ${p.children.length} child(ren)` : ""}`} />
        <SlotField label="Budget" slot={intent.budget} turnIndex={turnIndex}
          render={(b) => `${formatInr(b.amount)} / ${b.basis === "per_night" ? "night" : "stay"}${b.hard ? " · hard limit" : ""}`} />
      </Section>

      {(intent.room_prefs.value || intent.amenities_required.value?.length || intent.property_prefs.value?.length) && (
        <Section title="Preferences">
          {intent.property_prefs.value && intent.property_prefs.value.length > 0 && (
            <SlotField label="Property type" slot={intent.property_prefs} turnIndex={turnIndex}
              render={(v) => v.map(titleCase).join(", ")} />
          )}
          {intent.room_prefs.value && (
            <SlotField label="Room" slot={intent.room_prefs} turnIndex={turnIndex}
              render={(r) => [r.private_pool && "private pool", r.bed_type && `${r.bed_type} bed`, r.view && `${r.view} view`].filter(Boolean).join(", ") || "no specifics"} />
          )}
          {intent.amenities_required.value && intent.amenities_required.value.length > 0 && (
            <SlotField label="Must have" slot={intent.amenities_required} turnIndex={turnIndex}
              render={(v) => v.join(", ")} />
          )}
        </Section>
      )}

      <Section title="Where things stand">
        <div className="flex items-center justify-between px-2.5 py-2">
          <span className="text-[12px] font-medium uppercase tracking-wide text-muted">Stage</span>
          <span className="text-[14px] text-ink">{titleCase(state.stage)}</span>
        </div>
        {state.focused_option && (
          <div className="flex items-start justify-between gap-3 px-2.5 py-2">
            <span className="pt-0.5 text-[12px] font-medium uppercase tracking-wide text-muted">Focused on</span>
            <span className="text-right text-[14px] text-ink">
              {state.focused_option.property_name}
              <span className="block text-[12px] text-muted">{state.focused_option.room_type_name}</span>
            </span>
          </div>
        )}
        {state.quote && (
          <div className="flex items-center justify-between px-2.5 py-2">
            <span className="text-[12px] font-medium uppercase tracking-wide text-muted">Quoted</span>
            <span className="text-[14px] font-semibold text-ink">{formatInr(state.quote.total)}</span>
          </div>
        )}
        {state.hold && (
          <div className="flex items-center justify-between px-2.5 py-2">
            <span className="text-[12px] font-medium uppercase tracking-wide text-muted">Held</span>
            <Chip tone="good">{state.hold.hold_id}</Chip>
          </div>
        )}
      </Section>

      {state.conflicts.filter((c) => !c.resolved).length > 0 && (
        <Section title="Flagged">
          {state.conflicts.filter((c) => !c.resolved).map((c, i) => (
            <div key={i} className="flex items-start gap-2 rounded-lg bg-rust-soft px-2.5 py-2 text-[13px] text-rust">
              <AlertTriangle size={14} className="mt-0.5 shrink-0" />
              <span>{c.detail}</span>
            </div>
          ))}
        </Section>
      )}

      {state.unknowns_surfaced.length > 0 && (
        <Section title="Answered honestly">
          {state.unknowns_surfaced.map((u, i) => (
            <div key={i} className="flex items-center justify-between px-2.5 py-1.5 text-[13px]">
              <span className="text-muted">{titleCase(u.question_key)}</span>
              <span className="italic text-muted">not on file</span>
            </div>
          ))}
        </Section>
      )}
    </div>
  )
}
