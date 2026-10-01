import { useState, type FormEvent } from "react"
import type { Subscription, UpstreamProxy, UpstreamProxyInput } from "@/api/types"
import { Alert, AlertDescription, AlertTitle } from "@/components/reui/alert"
import {
  Frame,
  FrameHeader,
  FramePanel,
  FrameTitle,
} from "@/components/reui/frame"
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
import { PencilIcon, PlusIcon, Trash2Icon, TriangleAlertIcon } from "lucide-react"

interface ProxiesViewProps {
  proxies: UpstreamProxy[]
  subscriptions: Subscription[]
  loading: boolean
  error: string
  onRetry: () => void
  onCreate: (input: UpstreamProxyInput) => Promise<void>
  onUpdate: (proxy: UpstreamProxy, input: Partial<UpstreamProxyInput>) => Promise<void>
  onDelete: (proxy: UpstreamProxy) => Promise<void>
}

function ProxyDialog({ proxy, onSave }: {
  proxy?: UpstreamProxy
  onSave: (name: string, url: string) => Promise<void>
}) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState(proxy?.name ?? "")
  const [url, setUrl] = useState("")
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")

  function changeOpen(next: boolean) {
    setOpen(next)
    if (next) {
      setName(proxy?.name ?? "")
      setUrl("")
      setError("")
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSaving(true)
    setError("")
    try {
      await onSave(name, url)
      setOpen(false)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось сохранить прокси")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={changeOpen}>
      <DialogTrigger render={<Button type="button" size={proxy ? "icon-sm" : "sm"} variant={proxy ? "ghost" : "default"} />}>
        {proxy ? <PencilIcon aria-hidden="true" /> : <PlusIcon aria-hidden="true" />}
        {proxy ? <span className="sr-only">Изменить {proxy.name}</span> : "Добавить прокси"}
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>{proxy ? "Изменить прокси" : "Новый прокси"}</DialogTitle>
            <DialogDescription>
              Адрес и учётные данные шифруются в базе. После сохранения адрес скрыт.
            </DialogDescription>
          </DialogHeader>
          <div className="my-5 space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor={`proxy-name-${proxy?.id ?? "new"}`}>Название</Label>
              <Input
                id={`proxy-name-${proxy?.id ?? "new"}`}
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Основной прокси"
                required
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor={`proxy-url-${proxy?.id ?? "new"}`}>URL прокси</Label>
              <Input
                id={`proxy-url-${proxy?.id ?? "new"}`}
                type="url"
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                placeholder={proxy ? "Оставьте пустым, чтобы сохранить текущий" : "http://user:password@proxy.example:8080"}
                required={!proxy}
                autoComplete="off"
              />
            </div>
            {error && <p className="text-sm text-destructive" role="status">{error}</p>}
          </div>
          <DialogFooter>
            <Button type="submit" disabled={saving}>
              {saving ? "Сохраняю…" : "Сохранить"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function ProxiesView({
  proxies, subscriptions, loading, error, onRetry, onCreate, onUpdate, onDelete,
}: ProxiesViewProps) {
  const [pendingId, setPendingId] = useState("")
  const [actionError, setActionError] = useState("")

  async function remove(proxy: UpstreamProxy) {
    const assigned = subscriptions.filter((source) => source.proxy_id === proxy.id).length
    const message = assigned
      ? `Удалить прокси «${proxy.name}»? ${assigned} источников будут обновляться напрямую.`
      : `Удалить прокси «${proxy.name}»?`
    if (!window.confirm(message)) return
    setPendingId(proxy.id)
    setActionError("")
    try {
      await onDelete(proxy)
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : "Не удалось удалить прокси")
    } finally {
      setPendingId("")
    }
  }

  return (
    <Frame spacing="sm">
      <FrameHeader className="flex-row items-center justify-between gap-4">
        <div>
          <FrameTitle>Прокси</FrameTitle>
        </div>
        <ProxyDialog onSave={(name, url) => onCreate({ name, url })} />
      </FrameHeader>
      {(error || actionError) && (
        <Alert variant="destructive" role="status">
          <TriangleAlertIcon aria-hidden="true" />
          <AlertTitle>Ошибка прокси</AlertTitle>
          <AlertDescription>{actionError || error}</AlertDescription>
          {error && <Button size="sm" variant="outline" onClick={onRetry}>Повторить</Button>}
        </Alert>
      )}
      {loading ? (
        <Skeleton className="h-24 w-full" />
      ) : proxies.length === 0 ? (
        <FramePanel className="text-sm text-muted-foreground">Прокси пока нет.</FramePanel>
      ) : (
        <FramePanel className="divide-y p-0!">
          {proxies.map((proxy) => {
            const assigned = subscriptions.filter((source) => source.proxy_id === proxy.id).length
            return (
              <div key={proxy.id} className="flex min-w-0 items-center gap-4 px-4 py-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{proxy.name}</p>
                  <p className="truncate text-xs text-muted-foreground">{proxy.url_hint}</p>
                </div>
                <span className="hidden shrink-0 text-xs text-muted-foreground sm:block">
                  Источников: {assigned}
                </span>
                <div className="flex shrink-0 items-center gap-1">
                  <ProxyDialog
                    proxy={proxy}
                    onSave={(name, url) => onUpdate(proxy, { name, ...(url ? { url } : {}) })}
                  />
                  <Button
                    type="button"
                    size="icon-sm"
                    variant="ghost"
                    disabled={pendingId === proxy.id}
                    aria-label={`Удалить ${proxy.name}`}
                    onClick={() => void remove(proxy)}
                  >
                    <Trash2Icon aria-hidden="true" />
                  </Button>
                </div>
              </div>
            )
          })}
        </FramePanel>
      )}
    </Frame>
  )
}
