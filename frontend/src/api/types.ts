export type AuthSession =
  | {
      authenticated: true
      username: string
      csrf_token: string
      admin_configured: true
    }
  | {
      authenticated: false
      admin_configured: boolean
    }

export interface DashboardSummary {
  subscriptions: number
  healthy_subscriptions: number
  nodes: number
  profiles: number
  persistent_storage: boolean
}

export interface Subscription {
  id: string
  name: string
  url_hint: string
  enabled: boolean
  priority: number
  status: "never" | "healthy" | "error" | string
  node_count: number
  last_error: string | null
  last_sync_at: string | null
  created_at: string
  updated_at: string
}

export interface Profile {
  id: string
  name: string
  token: string
  enabled: boolean
  subscription_ids: string[]
  url: string
  created_at?: string
}

export interface ProfileNode {
  id: string
  name: string
  protocol: string
  host: string | null
  subscription_id: string
  subscription_name: string
  enabled: boolean
  pinned: boolean
  duplicate: boolean
}

export interface SubscriptionInput {
  name: string
  url: string
  enabled?: boolean
  priority?: number
}

export interface ProfileInput {
  name: string
  subscription_ids: string[]
}
