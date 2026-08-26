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
  request_logs: number
  devices: number
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
  duplicate: boolean
}

export interface RequestLog {
  id: string
  profile_id: string | null
  profile_name: string
  request_type: "default" | "profile" | string
  device_id: string | null
  client_name: string
  user_agent: string
  ip_address: string
  status_code: number
  node_count: number
  error: string | null
  requested_at: string
}

export interface ClientDevice {
  id: string
  name: string
  user_agent: string
  ip_address: string
  request_count: number
  last_profile_name: string | null
  last_status_code: number | null
  first_seen_at: string
  last_seen_at: string
}

export interface RelaySettings {
  deduplicate_servers: boolean
  request_logging_enabled: boolean
  device_tracking_enabled: boolean
  auto_refresh_enabled: boolean
  updated_at: string
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

export type RelaySettingsInput = Partial<
  Pick<
    RelaySettings,
    | "deduplicate_servers"
    | "request_logging_enabled"
    | "device_tracking_enabled"
    | "auto_refresh_enabled"
  >
>
