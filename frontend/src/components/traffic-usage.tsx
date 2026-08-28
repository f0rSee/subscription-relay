import type { ProfileTraffic, TrafficUsage } from "@/api/types"
import { Badge, type BadgeProps } from "@/components/reui/badge"
import {
  Progress,
  ProgressLabel,
  ProgressValue,
} from "@/components/ui/progress"
import { formatBytes } from "@/lib/format-bytes"
import { cn } from "@/lib/utils"

function expirationPresentation(value: string | null): {
  label: string
  variant: BadgeProps["variant"]
} | null {
  if (!value) return null
  const expiresAt = new Date(value)
  if (Number.isNaN(expiresAt.getTime())) return null
  const remainingDays = (expiresAt.getTime() - Date.now()) / 86_400_000
  const formatted = new Intl.DateTimeFormat("ru", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(expiresAt)
  if (remainingDays < 0) {
    return { label: `Истекла ${formatted}`, variant: "destructive-outline" }
  }
  if (remainingDays <= 7) {
    return { label: `До ${formatted}`, variant: "warning-outline" }
  }
  return { label: `До ${formatted}`, variant: "outline" }
}

function isProfileTraffic(
  traffic: TrafficUsage | ProfileTraffic,
): traffic is ProfileTraffic {
  return "sources_reporting" in traffic
}

export function TrafficUsageView({
  traffic,
  className,
}: {
  traffic: TrafficUsage | ProfileTraffic | null
  className?: string
}) {
  if (!traffic || (isProfileTraffic(traffic) && traffic.sources_reporting === 0)) {
    return <Badge variant="outline">Нет данных о трафике</Badge>
  }

  const percent =
    traffic.total && traffic.total > 0
      ? Math.min((traffic.used / traffic.total) * 100, 100)
      : null
  const expiration = expirationPresentation(traffic.expire_at)
  const totalLabel = traffic.unlimited
    ? "Безлимит"
    : traffic.total !== null
      ? `из ${formatBytes(traffic.total)}`
      : "Лимит не передан"

  return (
    <div className={cn("grid min-w-0 gap-1.5", className)}>
      <Progress
        value={percent}
        className={cn(
          "gap-1.5",
          percent !== null && percent >= 90 &&
            "[&_[data-slot=progress-indicator]]:bg-warning",
          percent !== null && percent >= 100 &&
            "[&_[data-slot=progress-indicator]]:bg-destructive",
        )}
      >
        <ProgressLabel className="text-xs">
          Использовано {formatBytes(traffic.used)}
        </ProgressLabel>
        <ProgressValue className="text-xs">{() => totalLabel}</ProgressValue>
      </Progress>
      <div className="flex flex-wrap items-center gap-1.5">
        {traffic.remaining !== null && (
          <span className="text-xs text-muted-foreground">
            Осталось {formatBytes(traffic.remaining)}
          </span>
        )}
        {isProfileTraffic(traffic) && (
          <Badge variant="info-outline" size="xs">
            Данные: {traffic.sources_reporting} из {traffic.sources_total}
          </Badge>
        )}
        {expiration && (
          <Badge variant={expiration.variant} size="xs">
            {expiration.label}
          </Badge>
        )}
      </div>
    </div>
  )
}
