import { useId, useState, type FormEvent } from "react"
import type { DeviceSettings, Subscription } from "@/api/types"
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
import { Switch } from "@/components/ui/switch"
import { SmartphoneIcon } from "lucide-react"

const fields: { key: keyof DeviceSettings; label: string }[] = [
  { key: "user_agent", label: "User-Agent" },
  { key: "hwid", label: "HWID" },
  { key: "os", label: "Операционная система" },
  { key: "os_version", label: "Версия ОС" },
  { key: "model", label: "Модель устройства" },
]

export function DeviceSettingsFields({ value, onChange, disabled = false }: {
  value: DeviceSettings
  onChange: (value: DeviceSettings) => void
  disabled?: boolean
}) {
  const id = useId()
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {fields.map(({ key, label }) => (
        <div key={key} className={key === "user_agent" ? "space-y-1.5 sm:col-span-2" : "space-y-1.5"}>
          <Label htmlFor={`${id}-${key}`}>{label}</Label>
          <Input
            id={`${id}-${key}`}
            value={value[key]}
            onChange={(event) => onChange({ ...value, [key]: event.target.value })}
            required
            maxLength={512}
            pattern="[!-~]([ -~]*[!-~])?"
            title="Печатные латинские символы без пробелов в начале и конце"
            disabled={disabled}
          />
        </div>
      ))}
    </div>
  )
}

export function SubscriptionDeviceDialog({ subscription, defaults, disabled, onSave }: {
  subscription: Subscription
  defaults: DeviceSettings | null
  disabled: boolean
  onSave: (value: DeviceSettings | null) => Promise<void>
}) {
  const [open, setOpen] = useState(false)
  const [inherit, setInherit] = useState(!subscription.device_settings)
  const [value, setValue] = useState(subscription.device_settings ?? defaults)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!value) return
    setSaving(true)
    setError("")
    try {
      await onSave(inherit ? null : value)
      setOpen(false)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось сохранить устройство")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (saving) return
        if (next) {
          setInherit(!subscription.device_settings)
          setValue(subscription.device_settings ?? defaults)
          setError("")
        }
        setOpen(next)
      }}
    >
      <DialogTrigger render={
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-auto max-w-full justify-start px-0 py-1 text-xs text-muted-foreground"
          disabled={disabled || !defaults}
        />
      }>
        <SmartphoneIcon aria-hidden="true" className="size-3 shrink-0" />
        <span className="truncate">{subscription.device_settings?.model ?? "Устройство по умолчанию"}</span>
        <span className="sr-only"> для {subscription.name}</span>
      </DialogTrigger>
      <DialogContent className="max-h-[90svh] overflow-y-auto">
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>Устройство для {subscription.name}</DialogTitle>
            <DialogDescription>
              Параметры устройства при запросе этой подписки. Применяются при следующем обновлении источника.
            </DialogDescription>
          </DialogHeader>
          <div className="my-5 space-y-5">
            <Label className="flex items-center justify-between gap-3">
              Использовать общие настройки
              <Switch checked={inherit} onCheckedChange={setInherit} disabled={saving} />
            </Label>
            {value && (
              <DeviceSettingsFields
                value={inherit && defaults ? defaults : value}
                onChange={setValue}
                disabled={inherit || saving}
              />
            )}
            {error && <p className="text-sm text-destructive" role="alert">{error}</p>}
          </div>
          <DialogFooter>
            <Button type="submit" disabled={saving || !value}>
              {saving ? "Сохраняю…" : "Сохранить"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function DefaultDeviceSettingsForm({ initial, onSave }: {
  initial: DeviceSettings
  onSave: (value: DeviceSettings) => Promise<void>
}) {
  const [value, setValue] = useState(initial)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSaving(true)
    setError("")
    try {
      await onSave(value)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось сохранить устройство")
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <DeviceSettingsFields value={value} onChange={setValue} disabled={saving} />
      {error && <p className="text-sm text-destructive" role="alert">{error}</p>}
      <Button type="submit" disabled={saving || JSON.stringify(value) === JSON.stringify(initial)}>
        {saving ? "Сохраняю…" : "Сохранить параметры устройства"}
      </Button>
    </form>
  )
}
