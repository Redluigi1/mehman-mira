import type {
  ConversationDetail, CreateConversationResponse, MessageResponse, Property, TurnDetail,
} from "./types"

const BASE = "/api"

export class ApiRequestError extends Error {
  status: number
  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
    this.name = "ApiRequestError"
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    })
  } catch {
    throw new ApiRequestError(0, "Can't reach Mira's backend — is it running?")
  }
  if (!res.ok) {
    let detail: string | null = null
    try {
      const body = await res.json()
      detail = body.detail ?? null
    } catch {
      // non-JSON error body (e.g. the dev proxy's own 502 page) — fall through to a friendly default
    }
    if (!detail) {
      detail =
        res.status === 502 || res.status === 503
          ? "Can't reach Mira's backend — make sure it's running on port 8000."
          : `Request failed (${res.status}).`
    }
    throw new ApiRequestError(res.status, detail)
  }
  return res.json() as Promise<T>
}

export function createConversation(): Promise<CreateConversationResponse> {
  return request("/conversations", { method: "POST" })
}

export function postMessage(conversationId: string, text: string): Promise<MessageResponse> {
  return request(`/conversations/${conversationId}/messages`, {
    method: "POST",
    body: JSON.stringify({ text }),
  })
}

export function getConversation(conversationId: string): Promise<ConversationDetail> {
  return request(`/conversations/${conversationId}`)
}

export function getTurn(conversationId: string, turnIndex: number): Promise<TurnDetail> {
  return request(`/conversations/${conversationId}/turns/${turnIndex}`)
}

export function getProperty(propertyId: string): Promise<Property> {
  return request(`/catalogue/properties/${propertyId}`)
}
