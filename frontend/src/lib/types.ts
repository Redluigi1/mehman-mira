// Mirrors backend/app/domain/*.py and backend/app/pipeline/*.py Pydantic
// models 1:1. Keep field names identical to the JSON the API actually sends
// — this file is hand-mirrored, not generated (plan §11 lists both as
// acceptable; hand-mirroring was simpler for a schema this size).

export type Stage = "discover" | "search" | "present" | "negotiate" | "confirm" | "held"

export type PropertyType = "hotel" | "resort" | "villa" | "homestay" | "guesthouse" | "boutique"
export type TripPurpose = "leisure" | "business" | "workation"
export type Occasion = "anniversary" | "birthday" | "honeymoon" | "bachelor_bachelorette" | "reunion"
export type PartyType = "solo" | "couple" | "family_with_kids" | "friends_group" | "extended_family" | "unknown"
export type BudgetBasis = "per_night" | "total"
export type BedType = "king" | "twin" | "queen" | "bunk"
export type ViewType = "sea" | "pool" | "garden" | "mountain" | "city" | "none"

export interface Slot<T> {
  value: T | null
  confidence: number
  source_turn: number | null
  asked_count: number
  is_assumption: boolean
}

export interface Destination {
  city: string
  area: string | null
  flexible: boolean
}

export interface StayWindow {
  check_in: string | null
  check_out: string | null
  nights: number | null
  flex_days: number
}

export interface ChildAge {
  age: number
}

export interface Party {
  adults: number | null
  children: ChildAge[]
  rooms_needed: number | null
}

export interface Budget {
  amount: number
  basis: BudgetBasis
  hard: boolean
}

export interface RoomPrefs {
  bed_type: BedType | null
  view: ViewType | null
  private_pool: boolean | null
  connecting_rooms: boolean | null
}

export interface PolicyNeeds {
  smoking: boolean | null
  pets: boolean | null
  early_checkin: boolean | null
  late_checkout: boolean | null
  party_friendly: boolean | null
}

export interface GuestIntent {
  destination: Slot<Destination>
  stay: Slot<StayWindow>
  party: Slot<Party>
  budget: Slot<Budget>
  property_prefs: Slot<PropertyType[]>
  room_prefs: Slot<RoomPrefs>
  amenities_required: Slot<string[]>
  amenities_nice: Slot<string[]>
  policy_needs: Slot<PolicyNeeds>
  special_requirements: Slot<string[]>
  trip_purpose: Slot<TripPurpose>
  occasion: Slot<Occasion>
  party_type: PartyType
}

export type RelaxationKind = "date_shift" | "over_budget" | "capacity_split" | "policy_conflict" | "min_stay"

export interface Relaxation {
  kind: RelaxationKind
  detail: string
}

export interface OptionRef {
  option_id: string
  property_id: string
  room_type_id: string
  ordinal: number
  property_name: string
  room_type_name: string
  city: string
  area: string | null
  star_tier: number
  rooms_needed: number
  nights: number
  price_per_night: number
  estimated_total: number
  relaxations: Relaxation[]
}

export interface ReferentRegistry {
  options: OptionRef[]
}

export type RejectionReason = "price" | "location" | "capacity" | "amenities" | "policy" | "other"

export interface Rejection {
  option_id: string
  reason: RejectionReason
  turn_index: number
}

export type ConflictKind = "capacity" | "budget" | "policy" | "min_stay" | "past_date" | "contradiction"

export interface Conflict {
  kind: ConflictKind
  detail: string
  field_paths: string[]
  resolved: boolean
}

export type UnknownFactResolution = "answered_unknown" | "escalated"

export interface UnknownFact {
  property_id: string
  question_key: string
  turn_index: number
  resolution_path: UnknownFactResolution
}

export interface QuoteLineItem {
  label: string
  amount: number
}

export interface Quote {
  option_id: string
  nights: number
  room_subtotal: number
  line_items: QuoteLineItem[]
  taxes: number
  fixed_fees: number
  total: number
  currency: string
}

export interface BookingHold {
  hold_id: string
  option_id: string
  quote_total: number
  idempotency_key: string
  expires_at: string
}

export interface ConversationState {
  conversation_id: string
  turn_index: number
  stage: Stage
  intent: GuestIntent
  shortlist: OptionRef[]
  referents: ReferentRegistry
  focused_option: OptionRef | null
  quote: Quote | null
  hold: BookingHold | null
  upsell_offered_for_quote: string | null
  rejected: Rejection[]
  conflicts: Conflict[]
  open_questions: string[]
  unknowns_surfaced: UnknownFact[]
}

export type UserAct = "new_request" | "modify" | "answer" | "select" | "objection" | "question" | "chitchat" | "other"

export type NextActionType =
  | "ask" | "search" | "present" | "present_alternatives" | "widen_or_ask" | "refine_search"
  | "answer_factual" | "surface_unknown" | "resolve_conflict" | "quote" | "upsell" | "hold" | "deflect"

export interface NextAction {
  type: NextActionType
  ask_field: string | null
  reason: string
}

export interface ToolCall {
  name: string
  args: Record<string, unknown>
  result_summary: string
  latency_ms: number
  ok: boolean
  error: string | null
}

export type GroundingVerdict = "clean" | "repaired" | "fallback"

export interface TurnTrace {
  conversation_id: string
  turn_index: number
  user_act: UserAct
  next_action: NextAction
  tool_calls: ToolCall[]
  grounding_verdict: GroundingVerdict
  errors: string[]
}

export interface CreateConversationResponse {
  conversation_id: string
}

export interface MessageResponse {
  reply: string
  state: ConversationState
  next_action: NextAction
  trace: TurnTrace
  errors: string[]
}

export interface ConversationDetail {
  conversation_id: string
  turn_count: number
  snapshots: ConversationState[]
  traces: TurnTrace[]
  replies: string[]
}

export interface TurnDetail {
  turn_index: number
  state: ConversationState
  trace: TurnTrace | null
}

export interface Property {
  id: string
  name: string
  city: string
  area: string | null
  type: PropertyType
  star_tier: number
  description: string
  amenities: string[]
  images: string[]
  check_in_time: string
  check_out_time: string
}

export interface ChatMessage {
  turn_index: number
  role: "guest" | "mira"
  text: string
  options?: OptionRef[]
}

export interface ApiError {
  status: number
  detail: string
}
