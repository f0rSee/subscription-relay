import { useCallback, useEffect, useState } from "react"
import { api, ApiError, setCsrfToken } from "@/api/client"
import type {
  AuthSession,
  DashboardSummary,
  Profile,
  ProfileInput,
  ProfileNode,
  Subscription,
  SubscriptionInput,
} from "@/api/types"
import { LoginView } from "@/components/login-view"
import { NodeOrderView } from "@/components/node-order-view"
import { ProfilesView } from "@/components/profiles-view"
import { Alert, AlertDescription, AlertTitle } from "@/components/reui/alert"
import { Badge } from "@/components/reui/badge"
import { Frame, FramePanel } from "@/components/reui/frame"
import { SubscriptionsView } from "@/components/subscriptions-view"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import {
  DatabaseIcon,
  ExternalLinkIcon,
  Layers3Icon,
  LogOutIcon,
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

function errorMessage(reason: unknown) {
  return reason instanceof Error ? reason.message : "Неизвестная ошибка"
}

export default function App() {
  const [session, setSession] = useState<AuthSession | null>(null)
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([])
  const [profiles, setProfiles] = useState<Profile[]>([])
  const [nodes, setNodes] = useState<ProfileNode[]>([])
  const [selectedProfileId, setSelectedProfileId] = useState("")
  const [initialError, setInitialError] = useState("")
  const [subscriptionsError, setSubscriptionsError] = useState("")
  const [nodesError, setNodesError] = useState("")
  const [loadingDashboard, setLoadingDashboard] = useState(false)
  const [loadingNodes, setLoadingNodes] = useState(false)

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

  async function toggleProfile(profile: Profile, enabled: boolean) {
    await api.updateProfile(profile.id, { enabled })
    toast.success(enabled ? "Профиль включён" : "Профиль выключен")
    await loadDashboard()
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
      <div className="min-h-svh">
        <header className="border-b bg-background/90 backdrop-blur">
          <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 sm:px-6">
            <div className="flex items-center gap-3">
              <div className="flex size-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                <RadioTowerIcon className="size-4" aria-hidden="true" />
              </div>
              <div>
                <h1 className="font-semibold tracking-tight">Subscription Relay</h1>
                <p className="text-xs text-muted-foreground">{session.username}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={!profiles[0]}
                render={
                  profiles[0] ? (
                    <a href={profiles[0].url} target="_blank" rel="noopener noreferrer" />
                  ) : undefined
                }
              >
                Проверить relay
                <ExternalLinkIcon aria-hidden="true" />
              </Button>
              <Button type="button" size="icon-sm" variant="ghost" aria-label="Выйти" onClick={() => void logout()}>
                <LogOutIcon aria-hidden="true" />
              </Button>
            </div>
          </div>
        </header>

        <main className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6 sm:py-8">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">Управление подписками</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Источники, профили и порядок серверов применяются без изменения env.
            </p>
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
                <div key={label} className="flex items-center gap-3 lg:border-r lg:last:border-r-0">
                  <Icon className="size-4 text-muted-foreground" aria-hidden="true" />
                  <div>
                    <p className="text-xs text-muted-foreground">{label}</p>
                    <p className="text-xl font-semibold tabular-nums">{summary?.[key] ?? 0}</p>
                  </div>
                </div>
              ))}
            </FramePanel>
          </Frame>

          <Tabs defaultValue="subscriptions">
            <TabsList variant="line" className="mb-2">
              <TabsTrigger value="subscriptions">Источники</TabsTrigger>
              <TabsTrigger value="profiles">
                Профили
                <Badge variant="outline" size="sm">{profiles.length}</Badge>
              </TabsTrigger>
              <TabsTrigger value="order">Порядок серверов</TabsTrigger>
            </TabsList>
            <TabsContent value="subscriptions">
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
            </TabsContent>
            <TabsContent value="profiles">
              <ProfilesView
                profiles={profiles}
                subscriptions={subscriptions}
                onCreate={createProfile}
                onToggle={toggleProfile}
                onDelete={deleteProfile}
              />
            </TabsContent>
            <TabsContent value="order">
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
            </TabsContent>
          </Tabs>
        </main>
      </div>
      <Toaster position="bottom-right" />
    </TooltipProvider>
  )
}
