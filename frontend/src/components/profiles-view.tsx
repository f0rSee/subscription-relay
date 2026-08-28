import { useState, type FormEvent } from "react"
import type {
  Profile,
  ProfileInput,
  ProfileUpdateInput,
  Subscription,
} from "@/api/types"
import {
  Alert,
  AlertAction,
  AlertDescription,
  AlertTitle,
} from "@/components/reui/alert"
import { Badge } from "@/components/reui/badge"
import {
  Frame,
  FrameDescription,
  FrameHeader,
  FramePanel,
  FrameTitle,
} from "@/components/reui/frame"
import {
  Sortable,
  SortableItem,
  SortableItemHandle,
} from "@/components/reui/sortable"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
import {
  CopyIcon,
  GripVerticalIcon,
  KeyRoundIcon,
  PencilIcon,
  PlusIcon,
  RadioIcon,
  RotateCwIcon,
  Trash2Icon,
  TriangleAlertIcon,
} from "lucide-react"
import { toast } from "sonner"

interface ProfilesViewProps {
  profiles: Profile[]
  subscriptions: Subscription[]
  loading: boolean
  error: string
  onRetry: () => void
  onCreate: (input: ProfileInput) => Promise<void>
  onUpdate: (profile: Profile, input: ProfileUpdateInput) => Promise<Profile>
  onDelete: (profile: Profile) => Promise<void>
}

interface ProfileSource {
  subscription: Subscription
  enabled: boolean
}

function orderedSources(
  subscriptions: Subscription[],
  enabledIds: string[],
): ProfileSource[] {
  const byId = new Map(subscriptions.map((subscription) => [subscription.id, subscription]))
  const enabled = enabledIds.flatMap((id) => {
    const subscription = byId.get(id)
    if (!subscription) return []
    byId.delete(id)
    return [{ subscription, enabled: true }]
  })
  return [
    ...enabled,
    ...subscriptions
      .filter((subscription) => byId.has(subscription.id))
      .map((subscription) => ({ subscription, enabled: false })),
  ]
}

function ProfileSourcesEditor({
  sources,
  disabled,
  onChange,
}: {
  sources: ProfileSource[]
  disabled: boolean
  onChange: (sources: ProfileSource[]) => void
}) {
  function toggleSource(id: string, enabled: boolean) {
    onChange(
      sources.map((source) =>
        source.subscription.id === id ? { ...source, enabled } : source,
      ),
    )
  }

  if (!sources.length) {
    return (
      <Frame spacing="xs">
        <FramePanel>
          <p className="py-5 text-center text-sm text-muted-foreground">
            Сначала добавьте хотя бы один источник.
          </p>
        </FramePanel>
      </Frame>
    )
  }

  return (
    <Frame spacing="xs">
      <Sortable
        value={sources}
        onValueChange={onChange}
        getItemValue={(source) => source.subscription.id}
        strategy="vertical"
        className="grid gap-1"
      >
        {sources.map((source, index) => (
          <SortableItem
            key={source.subscription.id}
            value={source.subscription.id}
            disabled={disabled}
          >
            <FramePanel className="p-0!">
              <div className="flex items-center gap-3 px-3 py-2.5">
                <SortableItemHandle
                  className="text-muted-foreground hover:text-foreground"
                  aria-label={`Изменить приоритет источника ${source.subscription.name}`}
                >
                  <GripVerticalIcon className="size-4" aria-hidden="true" />
                </SortableItemHandle>
                <span className="w-5 text-right text-xs tabular-nums text-muted-foreground">
                  {index + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex min-w-0 items-center gap-2">
                    <p className="truncate text-sm font-medium">
                      {source.subscription.name}
                    </p>
                    {!source.subscription.enabled && (
                      <Badge variant="warning-outline" size="xs">
                        Глобально выключен
                      </Badge>
                    )}
                  </div>
                  <p className="truncate text-xs text-muted-foreground">
                    {source.subscription.node_count} серверов · приоритет в профиле {index + 1}
                  </p>
                </div>
                <Switch
                  size="sm"
                  checked={source.enabled}
                  disabled={disabled}
                  aria-label={`${source.enabled ? "Выключить" : "Включить"} источник ${source.subscription.name} в профиле`}
                  onCheckedChange={(enabled) =>
                    toggleSource(source.subscription.id, enabled)
                  }
                />
              </div>
            </FramePanel>
          </SortableItem>
        ))}
      </Sortable>
    </Frame>
  )
}

function NewProfileDialog({
  subscriptions,
  onCreate,
}: Pick<ProfilesViewProps, "subscriptions" | "onCreate">) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState("")
  const [sources, setSources] = useState<ProfileSource[]>([])
  const [error, setError] = useState("")
  const [submitting, setSubmitting] = useState(false)

  function changeOpen(nextOpen: boolean) {
    setOpen(nextOpen)
    if (nextOpen) {
      setName("")
      setSources(orderedSources(subscriptions, subscriptions.map(({ id }) => id)))
      setError("")
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError("")
    try {
      await onCreate({
        name,
        subscription_ids: sources
          .filter((source) => source.enabled)
          .map((source) => source.subscription.id),
      })
      setOpen(false)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось создать профиль")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={changeOpen}>
      <DialogTrigger render={<Button size="sm" />}>
        <PlusIcon aria-hidden="true" />
        Новый профиль
      </DialogTrigger>
      <DialogContent className="max-h-[calc(100svh-2rem)] overflow-hidden sm:max-w-xl">
        <form className="flex min-h-0 flex-col" onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>Новый профиль</DialogTitle>
            <DialogDescription>
              Выберите источники и расположите их в порядке выдачи серверов.
            </DialogDescription>
          </DialogHeader>
          <div className="my-5 grid min-h-0 gap-5 overflow-y-auto pr-1">
            <div className="grid gap-1.5">
              <Label htmlFor="new-profile-name">Название</Label>
              <Input
                id="new-profile-name"
                placeholder="Телефон"
                value={name}
                onChange={(event) => setName(event.target.value)}
                disabled={submitting}
                required
              />
            </div>
            <fieldset className="grid gap-2">
              <legend className="text-sm font-medium">Источники</legend>
              <p className="text-xs text-muted-foreground">
                Перетаскивайте для изменения приоритета и выключайте ненужные.
              </p>
              <ProfileSourcesEditor
                sources={sources}
                disabled={submitting}
                onChange={setSources}
              />
            </fieldset>
            {error && (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            )}
          </div>
          <DialogFooter>
            <Button type="submit" disabled={submitting}>
              {submitting ? "Создаю…" : "Создать"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function EditProfileDialog({
  profile,
  subscriptions,
  onUpdate,
}: Pick<ProfilesViewProps, "subscriptions" | "onUpdate"> & { profile: Profile }) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState(profile.name)
  const [sources, setSources] = useState<ProfileSource[]>([])
  const [error, setError] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [rotating, setRotating] = useState(false)

  function changeOpen(nextOpen: boolean) {
    setOpen(nextOpen)
    if (nextOpen) {
      setName(profile.name)
      setSources(orderedSources(subscriptions, profile.subscription_ids))
      setError("")
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError("")
    try {
      await onUpdate(profile, {
        name,
        subscription_ids: sources
          .filter((source) => source.enabled)
          .map((source) => source.subscription.id),
      })
      toast.success("Профиль обновлён")
      setOpen(false)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось обновить профиль")
    } finally {
      setSubmitting(false)
    }
  }

  async function rotateToken() {
    if (!window.confirm("Старая ссылка перестанет работать. Перевыпустить URL профиля?")) {
      return
    }
    setRotating(true)
    setError("")
    try {
      await onUpdate(profile, { rotate_token: true })
      toast.success("Ссылка профиля перевыпущена")
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось перевыпустить ссылку")
    } finally {
      setRotating(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={changeOpen}>
      <DialogTrigger render={<Button type="button" variant="outline" size="sm" />}>
        <PencilIcon aria-hidden="true" />
        Настроить
      </DialogTrigger>
      <DialogContent className="max-h-[calc(100svh-2rem)] overflow-hidden sm:max-w-xl">
        <form className="flex min-h-0 flex-col" onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>Настройки профиля</DialogTitle>
            <DialogDescription>
              Название, состав и порядок источников применяются к публичной ссылке.
            </DialogDescription>
          </DialogHeader>
          <div className="my-5 grid min-h-0 gap-5 overflow-y-auto pr-1">
            <div className="grid gap-1.5">
              <Label htmlFor={`profile-name-${profile.id}`}>Название</Label>
              <Input
                id={`profile-name-${profile.id}`}
                value={name}
                onChange={(event) => setName(event.target.value)}
                disabled={submitting || rotating}
                required
              />
            </div>
            <fieldset className="grid gap-2">
              <legend className="text-sm font-medium">Источники и порядок</legend>
              <p className="text-xs text-muted-foreground">
                Серверы группируются по источникам сверху вниз.
              </p>
              <ProfileSourcesEditor
                sources={sources}
                disabled={submitting || rotating}
                onChange={setSources}
              />
            </fieldset>
            <Alert variant={profile.is_default ? "info" : "warning"}>
              <KeyRoundIcon aria-hidden="true" />
              <AlertTitle>Публичная ссылка</AlertTitle>
              <AlertDescription>
                {profile.is_default
                  ? "URL основного профиля задаётся через RELAY_TOKEN."
                  : "Перевыпуск немедленно отключит старую ссылку профиля."}
              </AlertDescription>
              {!profile.is_default && (
                <AlertAction>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={submitting || rotating}
                    onClick={() => void rotateToken()}
                  >
                    <RotateCwIcon aria-hidden="true" />
                    {rotating ? "Перевыпускаю…" : "Перевыпустить"}
                  </Button>
                </AlertAction>
              )}
            </Alert>
            {error && (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            )}
          </div>
          <DialogFooter>
            <Button type="submit" disabled={submitting || rotating}>
              {submitting ? "Сохраняю…" : "Сохранить"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function ProfilesView({
  profiles,
  subscriptions,
  loading,
  error,
  onRetry,
  onCreate,
  onUpdate,
  onDelete,
}: ProfilesViewProps) {
  const [pendingId, setPendingId] = useState("")
  const subscriptionsById = new Map(
    subscriptions.map((subscription) => [subscription.id, subscription]),
  )

  async function run(id: string, action: () => Promise<void>) {
    setPendingId(id)
    try {
      await action()
    } catch (reason) {
      toast.error(reason instanceof Error ? reason.message : "Операция не выполнена")
    } finally {
      setPendingId("")
    }
  }

  async function copyUrl(profile: Profile) {
    try {
      const url = new URL(profile.url, window.location.origin).toString()
      await navigator.clipboard.writeText(url)
      toast.success("URL профиля скопирован")
    } catch {
      toast.error("Не удалось скопировать URL")
    }
  }

  return (
    <Frame spacing="sm">
      <FrameHeader className="flex-row items-center justify-between gap-4">
        <div className="min-w-0">
          <FrameTitle>Профили выдачи</FrameTitle>
          <FrameDescription>
            Отдельные ссылки с независимым составом и приоритетом источников.
          </FrameDescription>
        </div>
        <NewProfileDialog subscriptions={subscriptions} onCreate={onCreate} />
      </FrameHeader>
      {error && (
        <Alert variant="destructive" role="status">
          <TriangleAlertIcon aria-hidden="true" />
          <AlertTitle>Профили не загружены</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
          <AlertAction>
            <Button type="button" variant="outline" size="sm" onClick={onRetry}>
              Повторить
            </Button>
          </AlertAction>
        </Alert>
      )}
      <div className="grid gap-2 md:grid-cols-2">
        {loading
          ? Array.from({ length: 4 }).map((_, index) => (
              <Skeleton key={index} className="h-36 rounded-xl" />
            ))
          : profiles.map((profile) => {
              const sourceNames = profile.subscription_ids.flatMap((id) => {
                const subscription = subscriptionsById.get(id)
                return subscription ? [subscription.name] : []
              })
              return (
                <FramePanel key={profile.id}>
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted">
                      <RadioIcon className="size-4 text-muted-foreground" aria-hidden="true" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="font-medium">{profile.name}</p>
                        {profile.is_default && <Badge variant="info-outline">Основной</Badge>}
                        {!profile.enabled && (
                          <Badge variant="warning-outline">Выключен</Badge>
                        )}
                      </div>
                      <p
                        className="mt-1 truncate text-xs text-muted-foreground"
                        title={sourceNames.join(" → ")}
                      >
                        {sourceNames.length
                          ? sourceNames.join(" → ")
                          : "Все источники выключены"}
                      </p>
                    </div>
                    <Switch
                      size="sm"
                      checked={profile.enabled}
                      disabled={pendingId === profile.id}
                      aria-label={`${profile.enabled ? "Выключить" : "Включить"} ${profile.name}`}
                      onCheckedChange={(enabled) =>
                        void run(profile.id, async () => {
                          await onUpdate(profile, { enabled })
                          toast.success(enabled ? "Профиль включён" : "Профиль выключен")
                        })
                      }
                    />
                  </div>
                  <div className="mt-4 flex flex-wrap items-center gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => void copyUrl(profile)}
                    >
                      <CopyIcon aria-hidden="true" />
                      Копировать URL
                    </Button>
                    <EditProfileDialog
                      profile={profile}
                      subscriptions={subscriptions}
                      onUpdate={onUpdate}
                    />
                    {!profile.is_default && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`Удалить ${profile.name}`}
                        disabled={pendingId === profile.id}
                        onClick={() => {
                          if (window.confirm(`Удалить профиль «${profile.name}»?`)) {
                            void run(profile.id, async () => {
                              await onDelete(profile)
                            })
                          }
                        }}
                      >
                        <Trash2Icon aria-hidden="true" />
                      </Button>
                    )}
                  </div>
                </FramePanel>
              )
            })}
        {!loading && profiles.length === 0 && (
          <FramePanel className="md:col-span-2">
            <p className="py-8 text-center text-sm text-muted-foreground">
              Профилей пока нет.
            </p>
          </FramePanel>
        )}
      </div>
    </Frame>
  )
}
