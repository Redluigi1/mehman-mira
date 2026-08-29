import type { ChipTone } from "../components/ui/Chip"
import type { GroundingVerdict, NextActionType, UserAct } from "./types"

export const NEXT_ACTION_TONE: Record<NextActionType, ChipTone> = {
  ask: "muted",
  search: "muted",
  refine_search: "muted",
  widen_or_ask: "muted",
  present: "accent",
  present_alternatives: "accent",
  answer_factual: "accent",
  quote: "good",
  hold: "good",
  upsell: "rust",
  resolve_conflict: "rust",
  surface_unknown: "rust",
  deflect: "muted",
}

export const NEXT_ACTION_LABEL: Record<NextActionType, string> = {
  ask: "Asking",
  search: "Searching",
  refine_search: "Refining search",
  widen_or_ask: "Widening search",
  present: "Presenting options",
  present_alternatives: "Presenting alternatives",
  answer_factual: "Answering",
  quote: "Quoting",
  hold: "Holding booking",
  upsell: "Offering add-ons",
  resolve_conflict: "Resolving conflict",
  surface_unknown: "Flagging unknown",
  deflect: "Deflecting",
}

export const USER_ACT_LABEL: Record<UserAct, string> = {
  new_request: "New request",
  modify: "Modified request",
  answer: "Answered",
  select: "Selected an option",
  objection: "Objected",
  question: "Asked a question",
  chitchat: "Chitchat",
  other: "Other",
}

export const GROUNDING_TONE: Record<GroundingVerdict, ChipTone> = {
  clean: "good",
  repaired: "accent",
  fallback: "rust",
}

export const GROUNDING_LABEL: Record<GroundingVerdict, string> = {
  clean: "Clean",
  repaired: "Repaired",
  fallback: "Template fallback",
}
