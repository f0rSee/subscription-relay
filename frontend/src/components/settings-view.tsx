import { useState } from "react"
import type { RelaySettings, RelaySettingsInput } from "@/api/types"
import { Alert, AlertDescription, AlertTitle } from "@/components/reui/alert"
import {
  Frame,
  FrameDescription,
  FrameHeader,
  FramePanel,
  FrameTitle,
} from "@/components/reui/frame"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
import {
  DatabaseZapIcon,
  ListFilterIcon,
  ScrollTextIcon,
  SmartphoneIcon,
  TriangleAlertIcon,
} from "lucide-react"

interface SettingsViewProps {
  settings: RelaySettings | null
  loading: boolean
  error: string
  onUpdate: (input: RelaySettingsInput) => Promise<void>
}

const settingItems = [
  {
    key: "deduplicate_servers",
    title: "Дедупликация серверов",
    description:
      "Убирать повторяющиеся серверы при объединении нескольких источников. По умолчанию выключено.",
    icon: ListFilterIcon,
  },
  {
    key: "request_logging_enabled",
    title: "Логи запросов",
    description:
      "Сохранять историю обращений к URL подписок. Уже записанные логи не удаляются при выключении.",
    icon: ScrollTextIcon,
  },
  {
    key: "device_tracking_enabled",
    title: "Учёт устройств",
    description:
      "Обновлять список клиентов по IP-адресу и User-Agent при каждом запросе подписки.",
    icon: SmartphoneIcon,
  },
  {
    key: "auto_refresh_enabled",
    title: "Автообновление источников",
    description:
      "Обновлять устаревшие источники во время запроса профиля. Ручная синхронизация работает всегда.",
    icon: DatabaseZapIcon,
  },
] as const satisfies ReadonlyArray<{
  key: keyof RelaySettingsInput
  title: string
  description: string
  icon: typeof ListFilterIcon
}>

export function SettingsView({ settings, loading, error, onUpdate }: SettingsViewProps) {
  const [pendingKey, setPendingKey] = useState<keyof RelaySettingsInput | "">("")
  const [saveError, setSaveError] = useState("")

  async function update(key: keyof RelaySettingsInput, checked: boolean) {
    setPendingKey(key)
    setSaveError("")
    try {
      await onUpdate({ [key]: checked })
    } catch (reason) {
      setSaveError(reason instanceof Error ? reason.message : "Не удалось сохранить настройку")
    } finally {
      setPendingKey("")
    }
  }

  return (
    <Frame spacing="sm">
      <FrameHeader>
        <FrameTitle>Настройки relay</FrameTitle>
        <FrameDescription>
          Изменения применяются сразу и хранятся в подключённой базе данных.
        </FrameDescription>
      </FrameHeader>
      {(error || saveError) && (
        <Alert variant="destructive" role="status">
          <TriangleAlertIcon aria-hidden="true" />
          <AlertTitle>Настройки не сохранены</AlertTitle>
          <AlertDescription>{saveError || error}</AlertDescription>
        </Alert>
      )}
      {loading || !settings ? (
        <div className="space-y-1">
          {settingItems.map((item) => (
            <Skeleton key={item.key} className="h-20 w-full rounded-lg" />
          ))}
        </div>
      ) : (
        <Frame stacked>
          {settingItems.map((item) => {
            const Icon = item.icon
            return (
              <FramePanel key={item.key} className="flex items-center gap-4">
                <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted">
                  <Icon className="size-4 text-muted-foreground" aria-hidden="true" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">{item.title}</p>
                  <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
                    {item.description}
                  </p>
                </div>
                <Switch
                  size="sm"
                  checked={Boolean(settings[item.key])}
                  disabled={Boolean(pendingKey)}
                  aria-label={item.title}
                  onCheckedChange={(checked) => void update(item.key, checked)}
                />
              </FramePanel>
            )
          })}
        </Frame>
      )}
      {pendingKey && (
        <p className="text-xs text-muted-foreground" role="status" aria-live="polite">
          Сохраняю…
        </p>
      )}
    </Frame>
  )
}
