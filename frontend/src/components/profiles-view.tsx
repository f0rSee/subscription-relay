import { useState, type FormEvent } from "react"
import type { Profile, ProfileInput, Subscription } from "@/api/types"
import { Badge } from "@/components/reui/badge"
import {
  Frame,
  FrameDescription,
  FrameHeader,
  FramePanel,
  FrameTitle,
} from "@/components/reui/frame"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
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
import { Switch } from "@/components/ui/switch"
import { CopyIcon, PlusIcon, RadioIcon, Trash2Icon } from "lucide-react"
import { toast } from "sonner"

interface ProfilesViewProps {
  profiles: Profile[]
  subscriptions: Subscription[]
  onCreate: (input: ProfileInput) => Promise<void>
  onToggle: (profile: Profile, enabled: boolean) => Promise<void>
  onDelete: (profile: Profile) => Promise<void>
}

function NewProfileDialog({
  subscriptions,
  onCreate,
}: Pick<ProfilesViewProps, "subscriptions" | "onCreate">) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState("")
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [error, setError] = useState("")
  const [submitting, setSubmitting] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError("")
    try {
      await onCreate({ name, subscription_ids: selectedIds })
      setName("")
      setSelectedIds([])
      setOpen(false)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось создать профиль")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button size="sm" />}>
        <PlusIcon aria-hidden="true" />
        Новый профиль
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>Новый профиль</DialogTitle>
            <DialogDescription>
              Профиль получает свой постоянный URL и объединяет выбранные источники.
            </DialogDescription>
          </DialogHeader>
          <div className="my-5 space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="profile-name">Название</Label>
              <Input
                id="profile-name"
                placeholder="Телефон"
                value={name}
                onChange={(event) => setName(event.target.value)}
                required
              />
            </div>
            <fieldset className="space-y-2">
              <legend className="mb-2 text-sm font-medium">Источники</legend>
              {subscriptions.map((subscription) => (
                <Label
                  key={subscription.id}
                  className="flex items-center gap-2 rounded-lg border p-2.5 font-normal"
                >
                  <Checkbox
                    checked={selectedIds.includes(subscription.id)}
                    onCheckedChange={(checked) =>
                      setSelectedIds((current) =>
                        checked
                          ? [...current, subscription.id]
                          : current.filter((id) => id !== subscription.id),
                      )
                    }
                  />
                  {subscription.name}
                </Label>
              ))}
              <p className="text-xs text-muted-foreground">
                Если ничего не выбрать, подключатся все источники.
              </p>
            </fieldset>
            {error && <p className="text-sm text-destructive">{error}</p>}
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

export function ProfilesView({
  profiles,
  subscriptions,
  onCreate,
  onToggle,
  onDelete,
}: ProfilesViewProps) {
  const [pendingId, setPendingId] = useState("")

  async function run(id: string, action: () => Promise<void>) {
    setPendingId(id)
    try {
      await action()
    } finally {
      setPendingId("")
    }
  }

  async function copyUrl(profile: Profile) {
    const url = new URL(profile.url, window.location.origin).toString()
    await navigator.clipboard.writeText(url)
    toast.success("URL профиля скопирован")
  }

  return (
    <Frame spacing="sm">
      <FrameHeader className="flex-row items-center justify-between gap-4">
        <div>
          <FrameTitle>Профили выдачи</FrameTitle>
          <FrameDescription>
            Отдельные ссылки для устройств с независимым порядком серверов.
          </FrameDescription>
        </div>
        <NewProfileDialog subscriptions={subscriptions} onCreate={onCreate} />
      </FrameHeader>
      <div className="grid gap-2 md:grid-cols-2">
        {profiles.map((profile) => {
          const sourceNames = subscriptions
            .filter((item) => profile.subscription_ids.includes(item.id))
            .map((item) => item.name)
          return (
            <FramePanel key={profile.id}>
              <div className="flex items-start gap-3">
                <div className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted">
                  <RadioIcon className="size-4 text-muted-foreground" aria-hidden="true" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="font-medium">{profile.name}</p>
                    {!profile.enabled && <Badge variant="warning-outline">Выключен</Badge>}
                  </div>
                  <p className="mt-1 truncate text-xs text-muted-foreground" title={sourceNames.join(", ")}>
                    {sourceNames.length ? sourceNames.join(", ") : "Нет источников"}
                  </p>
                </div>
                <Switch
                  size="sm"
                  checked={profile.enabled}
                  disabled={pendingId === profile.id}
                  aria-label={`${profile.enabled ? "Выключить" : "Включить"} ${profile.name}`}
                  onCheckedChange={(checked) =>
                    void run(profile.id, () => onToggle(profile, checked))
                  }
                />
              </div>
              <div className="mt-4 flex items-center gap-2">
                <Button type="button" variant="outline" size="sm" onClick={() => void copyUrl(profile)}>
                  <CopyIcon aria-hidden="true" />
                  Копировать URL
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  aria-label={`Удалить ${profile.name}`}
                  disabled={pendingId === profile.id}
                  onClick={() => {
                    if (window.confirm(`Удалить профиль «${profile.name}»?`)) {
                      void run(profile.id, () => onDelete(profile))
                    }
                  }}
                >
                  <Trash2Icon aria-hidden="true" />
                </Button>
              </div>
            </FramePanel>
          )
        })}
        {profiles.length === 0 && (
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
