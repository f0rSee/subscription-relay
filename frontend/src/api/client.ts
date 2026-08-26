import type {
  AuthSession,
  DashboardSummary,
  Profile,
  ProfileInput,
  ProfileNode,
  Subscription,
  SubscriptionInput,
} from "@/api/types"

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = "ApiError"
    this.status = status
  }
}

let csrfToken = ""

export function setCsrfToken(token: string | undefined) {
  csrfToken = token ?? ""
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json")
  }
  if (init.method && !["GET", "HEAD"].includes(init.method.toUpperCase())) {
    headers.set("X-CSRF-Token", csrfToken)
  }

  const response = await fetch(path, {
    ...init,
    credentials: "include",
    headers,
  })

  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try {
      const body = (await response.json()) as { detail?: string }
      if (body.detail) message = body.detail
    } catch {
      // The generic status message is enough when an upstream returns no JSON.
    }
    throw new ApiError(message, response.status)
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const api = {
  session: () => request<AuthSession>("/api/auth/session"),
  login: (username: string, password: string) =>
    request<AuthSession>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  logout: () => request<void>("/api/auth/logout", { method: "POST" }),
  dashboard: () => request<DashboardSummary>("/api/dashboard"),
  subscriptions: () => request<Subscription[]>("/api/subscriptions"),
  createSubscription: (input: SubscriptionInput) =>
    request<Subscription>("/api/subscriptions", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  updateSubscription: (id: string, input: Partial<SubscriptionInput>) =>
    request<Subscription>(`/api/subscriptions/${id}`, {
      method: "PATCH",
      body: JSON.stringify(input),
    }),
  deleteSubscription: (id: string) =>
    request<void>(`/api/subscriptions/${id}`, { method: "DELETE" }),
  syncSubscription: (id: string) =>
    request<{ status: string; node_count: number }>(
      `/api/subscriptions/${id}/sync`,
      { method: "POST" },
    ),
  profiles: () => request<Profile[]>("/api/profiles"),
  createProfile: (input: ProfileInput) =>
    request<Profile>("/api/profiles", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  updateProfile: (
    id: string,
    input: Partial<ProfileInput> & { enabled?: boolean; rotate_token?: boolean },
  ) =>
    request<Profile>(`/api/profiles/${id}`, {
      method: "PATCH",
      body: JSON.stringify(input),
    }),
  deleteProfile: (id: string) =>
    request<void>(`/api/profiles/${id}`, { method: "DELETE" }),
  profileNodes: (id: string) =>
    request<ProfileNode[]>(`/api/profiles/${id}/nodes`),
  updateNodeOrder: (id: string, nodeIds: string[]) =>
    request<{ updated: number }>(`/api/profiles/${id}/node-order`, {
      method: "PUT",
      body: JSON.stringify({ node_ids: nodeIds }),
    }),
}
