import { useCallback, useEffect, useState } from "react"
import { api, ApiError, setCsrfToken } from "@/api/client"
import type {
  AuthSession,
  ClientDevice,
  DashboardSummary,
  Profile,
  ProfileInput,
  ProfileNode,
  ProfileUpdateInput,
  RelaySettings,
  RelaySettingsInput,
  RequestLog,
  Subscription,
  SubscriptionInput,
} from "@/api/types"
import {
  DashboardSidebar,
  type DashboardView,
} from "@/components/dashboard-sidebar"
import { DevicesView } from "@/components/devices-view"
import { LoginView } from "@/components/login-view"
import { NodeOrderView } from "@/components/node-order-view"
import { ProfilesView } from "@/components/profiles-view"
import { RequestLogsView } from "@/components/request-logs-view"
import { Alert, AlertDescription, AlertTitle } from "@/components/reui/alert"
import { Frame, FramePanel } from "@/components/reui/frame"
import { SubscriptionsView } from "@/components/subscriptions-view"
import { SettingsView } from "@/components/settings-view"
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import { Skeleton } from "@/components/ui/skeleton"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import {
  DatabaseIcon,
  Layers3Icon,
  RadioTowerIcon,
  ServerIcon,
  TriangleAlertIcon,
  UsersIcon,
} from "lucide-react"
import { toast } from "sonner"

const summaryItems = [
  { label: "Источники", key: "subscriptions", icon: Layers3Icon },
  { label: "Работают", key: "healthy_subscriptions", icon: RadioTowerIcon },
  { label: "Серверы", key: "nodes", icon: ServerIcon },
  { label: "Профили", key: "profiles", icon: UsersIcon },
] as const

const viewCopy: Record<DashboardView, { title: string; description: string }> = {
  subscriptions: {
    title: "Источники",
    description: "Добавляйте и синхронизируйте подписки без изменения окружения.",
  },
  profiles: {
    title: "Профили",
    description: "Собирайте отдельные ссылки для устройств и сценариев подключения.",
  },
  order: {
    title: "Порядок серверов",
    description: "Управляйте приоритетом серверов для каждого профиля.",
  },
  logs: {
    title: "Логи",
    description: "Следите за обращениями клиентов к ссылкам подписок.",
  },
  devices: {
    title: "Устройства",
    description: "Просматривайте VPN-клиенты, которые запрашивали подписки.",
  },
  settings: {
    title: "Настройки",
    description: "Управляйте поведением relay без изменения переменных окружения.",
  },
}

function errorMessage(reason: unknown) {
  return reason instanceof Error ? reason.message : "Неизвестная ошибка"
}

export default function App() {
  const [activeView, setActiveView] = useState<DashboardView>("subscriptions")
  const [session, setSession] = useState<AuthSession | null>(null)
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([])
  const [profiles, setProfiles] = useState<Profile[]>([])
  const [nodes, setNodes] = useState<ProfileNode[]>([])
  const [requestLogs, setRequestLogs] = useState<RequestLog[]>([])
  const [devices, setDevices] = useState<ClientDevice[]>([])
  const [relaySettings, setRelaySettings] = useState<RelaySettings | null>(null)
  const [selectedProfileId, setSelectedProfileId] = useState("")
  const [initialError, setInitialError] = useState("")
  const [subscriptionsError, setSubscriptionsError] = useState("")
  const [nodesError, setNodesError] = useState("")
  const [logsError, setLogsError] = useState("")
  const [devicesError, setDevicesError] = useState("")
  const [settingsError, setSettingsError] = useState("")
  const [loadingDashboard, setLoadingDashboard] = useState(false)
  const [loadingNodes, setLoadingNodes] = useState(false)
  const [loadingLogs, setLoadingLogs] = useState(false)
  const [loadingDevices, setLoadingDevices] = useState(false)
  const [loadingSettings, setLoadingSettings] = useState(false)

  const loadDashboard = useCallback(async () => {
    setLoadingDashboard(true)
    setSubscriptionsError("")
    try {
      const [nextSummary, nextSubscriptions, nextProfiles] = await Promise.all([
        api.dashboard(),
        api.subscriptions(),
        api.profiles(),
      ])
      setSummary(nextSummary)
      setSubscriptions(nextSubscriptions)
      setProfiles(nextProfiles)
      setSelectedProfileId((current) =>
        nextProfiles.some((profile) => profile.id === current)
          ? current
          : (nextProfiles[0]?.id ?? ""),
      )
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 401) {
        setCsrfToken(undefined)
        setSession({ authenticated: false, admin_configured: true })
      } else {
        setSubscriptionsError(errorMessage(reason))
      }
    } finally {
      setLoadingDashboard(false)
    }
  }, [])

  const loadLogs = useCallback(async () => {
    setLoadingLogs(true)
    setLogsError("")
    try {
      const [nextLogs, nextSummary] = await Promise.all([
        api.requestLogs(),
        api.dashboard(),
      ])
      setRequestLogs(nextLogs)
      setSummary(nextSummary)
    } catch (reason) {
      setLogsError(errorMessage(reason))
    } finally {
      setLoadingLogs(false)
    }
  }, [])

  const loadDevices = useCallback(async () => {
    setLoadingDevices(true)
    setDevicesError("")
    try {
      const [nextDevices, nextSummary] = await Promise.all([
        api.devices(),
        api.dashboard(),
      ])
      setDevices(nextDevices)
      setSummary(nextSummary)
    } catch (reason) {
      setDevicesError(errorMessage(reason))
    } finally {
      setLoadingDevices(false)
    }
  }, [])

  const loadSettings = useCallback(async () => {
    setLoadingSettings(true)
    setSettingsError("")
    try {
      setRelaySettings(await api.settings())
    } catch (reason) {
      setSettingsError(errorMessage(reason))
    } finally {
      setLoadingSettings(false)
    }
  }, [])

  useEffect(() => {
    void api
      .session()
      .then((nextSession) => {
        setSession(nextSession)
        if (nextSession.authenticated) {
          setCsrfToken(nextSession.csrf_token)
          void loadDashboard()
        }
      })
      .catch((reason) => setInitialError(errorMessage(reason)))
  }, [loadDashboard])

  useEffect(() => {
    if (!session?.authenticated || !selectedProfileId) {
      return
    }
    setLoadingNodes(true)
    setNodesError("")
    void api
      .profileNodes(selectedProfileId)
      .then(setNodes)
      .catch((reason) => setNodesError(errorMessage(reason)))
      .finally(() => setLoadingNodes(false))
  }, [selectedProfileId, session])

  async function login(username: string, password: string) {
    const nextSession = await api.login(username, password)
    if (!nextSession.authenticated) throw new Error("Сервер не создал сессию")
    setCsrfToken(nextSession.csrf_token)
    setSession(nextSession)
    await loadDashboard()
  }

  async function logout() {
    await api.logout()
    setCsrfToken(undefined)
    setSession({ authenticated: false, admin_configured: true })
    setSummary(null)
    setSubscriptions([])
    setProfiles([])
    setNodes([])
    setRequestLogs([])
    setDevices([])
    setRelaySettings(null)
  }

  async function createSubscription(input: SubscriptionInput) {
    await api.createSubscription(input)
    toast.success("Источник добавлен")
    await loadDashboard()
  }

  async function toggleSubscription(subscription: Subscription, enabled: boolean) {
    await api.updateSubscription(subscription.id, { enabled })
    toast.success(enabled ? "Источник включён" : "Источник выключен")
    await loadDashboard()
  }

  async function syncSubscription(subscription: Subscription) {
    const result = await api.syncSubscription(subscription.id)
    toast.success(`Получено серверов: ${result.node_count}`)
    await loadDashboard()
    if (selectedProfileId) setNodes(await api.profileNodes(selectedProfileId))
  }

  async function deleteSubscription(subscription: Subscription) {
    await api.deleteSubscription(subscription.id)
    toast.success(`Источник «${subscription.name}» удалён`)
    await loadDashboard()
  }

  async function createProfile(input: ProfileInput) {
    await api.createProfile(input)
    toast.success("Профиль создан")
    await loadDashboard()
  }

  async function updateProfile(
    profile: Profile,
    input: ProfileUpdateInput,
  ): Promise<Profile> {
    const updated = await api.updateProfile(profile.id, input)
    setProfiles((current) =>
      current.map((item) => (item.id === updated.id ? updated : item)),
    )
    if (selectedProfileId === profile.id) {
      setNodes(await api.profileNodes(profile.id))
    }
    return updated
  }

  async function deleteProfile(profile: Profile) {
    await api.deleteProfile(profile.id)
    toast.success(`Профиль «${profile.name}» удалён`)
    await loadDashboard()
  }

  async function saveNodeOrder(profileId: string, orderedNodes: ProfileNode[]) {
    await api.updateNodeOrder(
      profileId,
      orderedNodes.map((node) => node.id),
    )
    toast.success("Порядок серверов сохранён")
  }

  async function updateRelaySettings(input: RelaySettingsInput) {
    const nextSettings = await api.updateSettings(input)
    setRelaySettings(nextSettings)
    toast.success("Настройка сохранена")
  }

  function changeView(view: DashboardView) {
    setActiveView(view)
    if (view === "logs") void loadLogs()
    if (view === "devices") void loadDevices()
    if (view === "settings") void loadSettings()
  }

  if (!session) {
    return (
      <main className="mx-auto flex min-h-svh max-w-6xl items-center px-4">
        {initialError ? (
          <Alert variant="destructive">
            <TriangleAlertIcon aria-hidden="true" />
            <AlertTitle>Дашборд недоступен</AlertTitle>
            <AlertDescription>{initialError}</AlertDescription>
          </Alert>
        ) : (
          <Skeleton className="mx-auto h-72 w-full max-w-md rounded-xl" />
        )}
      </main>
    )
  }

  if (!session.authenticated) {
    return <LoginView adminConfigured={session.admin_configured} onLogin={login} />
  }

  return (
    <TooltipProvider>
      <SidebarProvider>
        <DashboardSidebar
          activeView={activeView}
          subscriptionsCount={subscriptions.length}
          profilesCount={profiles.length}
          nodesCount={summary?.nodes ?? 0}
          logsCount={summary?.request_logs ?? 0}
          devicesCount={summary?.devices ?? 0}
          username={session.username}
          onViewChange={changeView}
          onLogout={logout}
        />
        <SidebarInset className="min-w-0 overflow-x-hidden">
          <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-6 px-4 py-6 sm:px-6 sm:py-8">
            <div className="flex items-start gap-3">
              <SidebarTrigger
                type="button"
                className="mt-0.5 shrink-0"
                aria-label="Открыть или свернуть боковую панель"
              />
              <div className="min-w-0">
                <h1 className="text-2xl font-semibold tracking-tight">
                  {viewCopy[activeView].title}
                </h1>
                <p className="mt-1 text-sm text-muted-foreground">
                  {viewCopy[activeView].description}
                </p>
              </div>
            </div>

            {summary?.persistent_storage === false && (
              <Alert variant="warning">
                <DatabaseIcon aria-hidden="true" />
                <AlertTitle>Используется временная база</AlertTitle>
                <AlertDescription>
                  Подключите DATABASE_URL от Neon, иначе изменения могут исчезнуть после пересоздания инстанса.
                </AlertDescription>
              </Alert>
            )}

            <Frame spacing="xs">
              <FramePanel className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {summaryItems.map(({ label, key, icon: Icon }) => (
                  <div
                    key={label}
                    className="flex items-center gap-3 lg:border-r lg:last:border-r-0"
                  >
                    <Icon className="size-4 text-muted-foreground" aria-hidden="true" />
                    <div>
                      <p className="text-xs text-muted-foreground">{label}</p>
                      <p className="text-xl font-semibold tabular-nums">
                        {summary?.[key] ?? 0}
                      </p>
                    </div>
                  </div>
                ))}
              </FramePanel>
            </Frame>

            {activeView === "subscriptions" && (
              <SubscriptionsView
                subscriptions={subscriptions}
                loading={loadingDashboard}
                error={subscriptionsError}
                onRetry={() => void loadDashboard()}
                onCreate={createSubscription}
                onToggle={toggleSubscription}
                onSync={syncSubscription}
                onDelete={deleteSubscription}
              />
            )}
            {activeView === "profiles" && (
              <ProfilesView
                profiles={profiles}
                subscriptions={subscriptions}
                loading={loadingDashboard}
                error={subscriptionsError}
                onRetry={() => void loadDashboard()}
                onCreate={createProfile}
                onUpdate={updateProfile}
                onDelete={deleteProfile}
              />
            )}
            {activeView === "order" && (
              <NodeOrderView
                key={`${selectedProfileId}:${nodes.map((node) => node.id).join(":")}`}
                profiles={profiles}
                selectedProfileId={selectedProfileId}
                onProfileChange={setSelectedProfileId}
                nodes={nodes}
                loading={loadingNodes}
                error={nodesError}
                onSave={saveNodeOrder}
              />
            )}
            {activeView === "logs" && (
              <RequestLogsView
                logs={requestLogs}
                loading={loadingLogs}
                error={logsError}
                onRefresh={() => void loadLogs()}
              />
            )}
            {activeView === "devices" && (
              <DevicesView
                devices={devices}
                loading={loadingDevices}
                error={devicesError}
                onRefresh={() => void loadDevices()}
              />
            )}
            {activeView === "settings" && (
              <SettingsView
                settings={relaySettings}
                loading={loadingSettings}
                error={settingsError}
                onUpdate={updateRelaySettings}
              />
            )}
          </div>
        </SidebarInset>
      </SidebarProvider>
      <Toaster position="bottom-right" />
    </TooltipProvider>
  )
}
