import { useMemo, useState, type FormEvent } from "react"
import type { DeviceSettings, Subscription, SubscriptionInput, UpstreamProxy } from "@/api/types"
import { Alert, AlertDescription, AlertTitle } from "@/components/reui/alert"
import { Badge, type BadgeProps } from "@/components/reui/badge"
import {
  DataGrid,
  DataGridContainer,
  dataGridFeatures,
  getColumnHeaderLabel,
  type DataGridFeatures,
} from "@/components/reui/data-grid/data-grid"
import { DataGridPagination } from "@/components/reui/data-grid/data-grid-pagination"
import { DataGridScrollArea } from "@/components/reui/data-grid/data-grid-scroll-area"
import { DataGridTable } from "@/components/reui/data-grid/data-grid-table"
import {
  Frame,
  FrameDescription,
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { SubscriptionDeviceDialog } from "@/components/device-settings"
import { TrafficUsageView } from "@/components/traffic-usage"
import { cn } from "@/lib/utils"
import { flexRender, useTable } from "@tanstack/react-table"
import type { ColumnDef, PaginationState, SortingState } from "@tanstack/react-table"
import {
  PlusIcon,
  RefreshCwIcon,
  SmartphoneIcon,
  Trash2Icon,
  TriangleAlertIcon,
} from "lucide-react"

interface SubscriptionsViewProps {
  subscriptions: Subscription[]
  defaultDeviceSettings: DeviceSettings | null
  settingsError: string
  onSaveDevice: (subscription: Subscription, value: DeviceSettings | null) => Promise<void>
  proxies: UpstreamProxy[]
  proxiesError: string
  loading: boolean
  error: string
  onRetry: () => void
  onCreate: (input: SubscriptionInput) => Promise<void>
  onToggle: (subscription: Subscription, enabled: boolean) => Promise<void>
  onAssignProxy: (subscription: Subscription, proxyId: string | null) => Promise<void>
  onSync: (subscription: Subscription) => Promise<void>
  onDelete: (subscription: Subscription) => Promise<void>
}

const statusPresentation: Record<
  string,
  { label: string; variant: BadgeProps["variant"] }
> = {
  healthy: { label: "Работает", variant: "success-outline" },
  error: { label: "Ошибка", variant: "destructive-outline" },
  never: { label: "Не проверена", variant: "warning-outline" },
}

const sortingOptions: { value: string; label: string; sorting: SortingState }[] = [
  { value: "default", label: "По умолчанию", sorting: [] },
  { value: "name:asc", label: "Название: А → Я", sorting: [{ id: "name", desc: false }] },
  { value: "name:desc", label: "Название: Я → А", sorting: [{ id: "name", desc: true }] },
  { value: "node_count:asc", label: "Серверы: по возрастанию", sorting: [{ id: "node_count", desc: false }] },
  { value: "node_count:desc", label: "Серверы: по убыванию", sorting: [{ id: "node_count", desc: true }] },
  { value: "traffic:asc", label: "Трафик: по возрастанию", sorting: [{ id: "traffic", desc: false }] },
  { value: "traffic:desc", label: "Трафик: по убыванию", sorting: [{ id: "traffic", desc: true }] },
]

function formatSyncDate(value: string | null) {
  if (!value) return "Ещё не запускалась"
  return new Intl.DateTimeFormat("ru", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value))
}

function proxyLabel(proxies: UpstreamProxy[], proxyId: string) {
  return proxyId === "direct"
    ? "Напрямую"
    : (proxies.find((proxy) => proxy.id === proxyId)?.name ?? "Прокси удалён")
}

function AddSubscriptionDialog({
  onCreate,
  proxies,
  proxiesError,
}: Pick<SubscriptionsViewProps, "onCreate" | "proxies" | "proxiesError">) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState("")
  const [url, setUrl] = useState("")
  const [proxyId, setProxyId] = useState("direct")
  const [error, setError] = useState("")
  const [submitting, setSubmitting] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError("")
    try {
      await onCreate({ name, url, proxy_id: proxyId === "direct" ? null : proxyId })
      setName("")
      setUrl("")
      setProxyId("direct")
      setOpen(false)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось добавить источник")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button size="sm" />}>
        <PlusIcon aria-hidden="true" />
        Добавить источник
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>Новая подписка</DialogTitle>
            <DialogDescription>
              URL будет зашифрован в базе и не возвращается в браузер после сохранения.
            </DialogDescription>
          </DialogHeader>
          <div className="my-5 space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="subscription-name">Название</Label>
              <Input
                id="subscription-name"
                placeholder="Основная подписка"
                value={name}
                onChange={(event) => setName(event.target.value)}
                required
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="subscription-url">URL подписки</Label>
              <Input
                id="subscription-url"
                type="url"
                placeholder="https://provider.example/subscription"
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                required
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="subscription-proxy">Прокси для обновления</Label>
              <Select value={proxyId} onValueChange={(value) => setProxyId(value ?? "direct")} disabled={Boolean(proxiesError)}>
                <SelectTrigger id="subscription-proxy" className="w-full">
                  {proxyLabel(proxies, proxyId)}
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="direct">Напрямую</SelectItem>
                  {proxies.map((proxy) => (
                    <SelectItem key={proxy.id} value={proxy.id}>{proxy.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
          </div>
          <DialogFooter>
            <Button type="submit" disabled={submitting}>
              {submitting ? "Сохраняю…" : "Сохранить"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function SubscriptionsView(props: SubscriptionsViewProps) {
  const { subscriptions, proxies, proxiesError, loading, error, onRetry, onCreate, onToggle, onAssignProxy, onSync, onDelete, defaultDeviceSettings, settingsError, onSaveDevice } = props
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 10,
  })
  const [sorting, setSorting] = useState<SortingState>([])
  const [pendingId, setPendingId] = useState("")
  const [actionError, setActionError] = useState("")
  const [deviceSubscription, setDeviceSubscription] = useState<Subscription | null>(null)

  async function run(id: string, action: () => Promise<void>) {
    setPendingId(id)
    setActionError("")
    try {
      await action()
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : "Не удалось обновить источник")
    } finally {
      setPendingId("")
    }
  }

  const columns = useMemo<ColumnDef<DataGridFeatures, Subscription>[]>(
    () => [
      {
        accessorKey: "name",
        header: "Источник",
        cell: ({ row }) => (
          <div className="min-w-0 space-y-0.5">
            <p className="font-medium wrap-anywhere text-foreground">{row.original.name}</p>
            <p className="truncate text-xs text-muted-foreground" title={row.original.url_hint}>
              {row.original.url_hint}
            </p>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-auto max-w-full justify-start px-0 py-1 text-xs text-muted-foreground"
              disabled={pendingId === row.original.id || !defaultDeviceSettings}
              onClick={() => setDeviceSubscription(row.original)}
            >
              <SmartphoneIcon aria-hidden="true" className="size-3 shrink-0" />
              <span className="truncate">{row.original.device_settings?.model ?? "Устройство по умолчанию"}</span>
              <span className="sr-only"> для {row.original.name}</span>
            </Button>
          </div>
        ),
        meta: { headerClassName: "w-[16%]" },
        enableSorting: true,
      },
      {
        id: "proxy",
        header: "Прокси",
        cell: ({ row }) => (
          <Select
            value={row.original.proxy_id ?? "direct"}
            onValueChange={(value) => {
              if (value) void run(row.original.id, () => onAssignProxy(row.original, value === "direct" ? null : value))
            }}
            disabled={Boolean(proxiesError) || pendingId === row.original.id}
          >
            <SelectTrigger size="sm" className="w-full min-w-0" aria-label={`Прокси для ${row.original.name}`}>
              <span className="truncate" title={proxyLabel(proxies, row.original.proxy_id ?? "direct")}>
                {proxyLabel(proxies, row.original.proxy_id ?? "direct")}
              </span>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="direct">Напрямую</SelectItem>
              {proxies.map((proxy) => (
                <SelectItem key={proxy.id} value={proxy.id}>{proxy.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        ),
        meta: { headerClassName: "w-[13%]" },
      },
      {
        accessorKey: "status",
        header: "Статус",
        cell: ({ row }) => {
          const presentation = statusPresentation[row.original.status] ?? {
            label: row.original.status,
            variant: "outline" as const,
          }
          return (
            <div className="space-y-1">
              <Badge variant={presentation.variant} className="max-w-full whitespace-normal wrap-anywhere">
                {presentation.label}
              </Badge>
              {row.original.last_error && (
                <p className="truncate text-xs text-destructive" title={row.original.last_error}>
                  {row.original.last_error}
                </p>
              )}
            </div>
          )
        },
        meta: { headerClassName: "w-[11%]" },
      },
      {
        accessorKey: "node_count",
        header: "Серверы",
        cell: ({ row }) => (
          <span className="font-medium tabular-nums">{row.original.node_count}</span>
        ),
        meta: { headerClassName: "w-[8%]" },
        enableSorting: true,
      },
      {
        id: "traffic",
        accessorFn: (subscription) => subscription.traffic?.used ?? -1,
        header: "Трафик",
        cell: ({ row }) => (
          <TrafficUsageView traffic={row.original.traffic} />
        ),
        meta: { headerClassName: "w-[21%]" },
        enableSorting: true,
      },
      {
        accessorKey: "last_sync_at",
        header: "Последняя синхронизация",
        cell: ({ row }) => (
          <span className="text-muted-foreground">
            {formatSyncDate(row.original.last_sync_at)}
          </span>
        ),
        meta: { headerClassName: "w-[13%]" },
      },
      {
        id: "enabled",
        header: "Включена",
        cell: ({ row }) => (
          <Switch
            size="sm"
            checked={row.original.enabled}
            disabled={pendingId === row.original.id}
            aria-label={`${row.original.enabled ? "Выключить" : "Включить"} ${row.original.name}`}
            onCheckedChange={(checked) =>
              void run(row.original.id, () => onToggle(row.original, checked))
            }
          />
        ),
        meta: { headerClassName: "w-[9%]" },
      },
      {
        id: "actions",
        header: "Действия",
        cell: ({ row }) => (
          <div className="flex items-center gap-1">
            <Button
              type="button"
              size="icon-sm"
              variant="ghost"
              disabled={pendingId === row.original.id}
              aria-label={`Синхронизировать ${row.original.name}`}
              onClick={() => void run(row.original.id, () => onSync(row.original))}
            >
              <RefreshCwIcon
                className={pendingId === row.original.id ? "animate-spin" : ""}
                aria-hidden="true"
              />
            </Button>
            <Button
              type="button"
              size="icon-sm"
              variant="ghost"
              disabled={pendingId === row.original.id}
              aria-label={`Удалить ${row.original.name}`}
              onClick={() => {
                if (window.confirm(`Удалить источник «${row.original.name}» и его серверы?`)) {
                  void run(row.original.id, () => onDelete(row.original))
                }
              }}
            >
              <Trash2Icon aria-hidden="true" />
            </Button>
          </div>
        ),
        meta: { headerClassName: "w-[9%]" },
      },
    ],
    [onAssignProxy, onDelete, onSync, onToggle, pendingId, proxies, proxiesError, defaultDeviceSettings],
  )

  const table = useTable({
    features: dataGridFeatures,
    columns,
    data: subscriptions,
    pageCount: Math.max(1, Math.ceil(subscriptions.length / pagination.pageSize)),
    getRowId: (row: Subscription) => row.id,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
  })
  const sortValue = sorting[0]
    ? `${sorting[0].id}:${sorting[0].desc ? "desc" : "asc"}`
    : "default"

  return (
    <Frame spacing="sm">
      <FrameHeader className="flex-row flex-wrap items-center justify-between gap-4">
        <div className="min-w-0">
          <FrameTitle>Источники подписок</FrameTitle>
          <FrameDescription>
            Сервис забирает данные по URL и обновляет список серверов для профилей.
          </FrameDescription>
        </div>
        <AddSubscriptionDialog onCreate={onCreate} proxies={proxies} proxiesError={proxiesError} />
      </FrameHeader>
      <FramePanel className="p-2!">
        {(error || actionError) && (
          <Alert variant="destructive" className="mb-2">
            <TriangleAlertIcon aria-hidden="true" />
            <AlertTitle>Ошибка источника</AlertTitle>
            <AlertDescription>{actionError || error}</AlertDescription>
            {error && <Button type="button" size="sm" variant="outline" onClick={onRetry}>Повторить</Button>}
          </Alert>
        )}
        {settingsError && (
          <Alert variant="destructive" className="mb-2">
            <TriangleAlertIcon aria-hidden="true" />
            <AlertTitle>Параметры устройства недоступны</AlertTitle>
            <AlertDescription>{settingsError}</AlertDescription>
            <Button type="button" size="sm" variant="outline" onClick={onRetry}>Повторить</Button>
          </Alert>
        )}
        {proxiesError && (
          <Alert variant="destructive" className="mb-2">
            <TriangleAlertIcon aria-hidden="true" />
            <AlertTitle>Прокси недоступны</AlertTitle>
            <AlertDescription>{proxiesError}</AlertDescription>
          </Alert>
        )}
        <DataGrid
          table={table}
          recordCount={subscriptions.length}
          isLoading={loading}
          loadingMode="skeleton"
          emptyMessage="Источников пока нет. Добавьте первую подписку."
          tableLayout={{
            headerBackground: true,
            rowBorder: true,
            width: "auto",
          }}
          tableClassNames={{
            base: "table-fixed",
            headerRow: "[&>th]:px-2 [&>th]:py-2 [&>th]:wrap-anywhere",
            bodyRow: "[&>td]:px-2",
          }}
        >
          <div className="@container w-full min-w-0 space-y-2.5">
            <div className="flex flex-wrap items-center gap-2 px-1 py-2">
              <Label htmlFor="subscription-sort">Сортировка</Label>
              <Select
                value={sortValue}
                onValueChange={(value) => {
                  const option = sortingOptions.find((item) => item.value === value)
                  if (!option) return
                  setSorting(option.sorting)
                  table.setPageIndex(0)
                }}
                disabled={loading || subscriptions.length === 0}
              >
                <SelectTrigger id="subscription-sort" size="sm" className="w-full min-w-0 @sm:w-64">
                  <span className="truncate">
                    {sortingOptions.find((option) => option.value === sortValue)?.label}
                  </span>
                </SelectTrigger>
                <SelectContent>
                  {sortingOptions.map((option) => (
                    <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <DataGridContainer className="hidden @5xl:block">
              <DataGridScrollArea>
                <DataGridTable />
              </DataGridScrollArea>
            </DataGridContainer>
            <div className="grid gap-3 @5xl:hidden">
              {loading ? (
                Array.from({ length: 3 }, (_, index) => (
                  <Skeleton key={index} className="h-72 w-full rounded-lg" />
                ))
              ) : subscriptions.length === 0 ? (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  Источников пока нет. Добавьте первую подписку.
                </p>
              ) : (
                table.getRowModel().rows.map((row) => (
                  <article key={row.id} aria-label={row.original.name} className="min-w-0 rounded-lg border p-4">
                    <dl className="grid grid-cols-2 gap-4 @xl:grid-cols-3">
                      {row.getVisibleCells().map((cell) => (
                        <div
                          key={cell.id}
                          className={cn("min-w-0", {
                            "col-span-2": ["name", "traffic", "last_sync_at"].includes(cell.column.id),
                            "@xl:col-span-1": cell.column.id !== "traffic",
                          })}
                        >
                          <dt className="mb-1.5 text-xs text-muted-foreground">
                            {getColumnHeaderLabel(cell.column)}
                          </dt>
                          <dd className="text-sm">
                            {flexRender(cell.column.columnDef.cell, cell.getContext())}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  </article>
                ))
              )}
            </div>
            {subscriptions.length > pagination.pageSize && <DataGridPagination />}
          </div>
        </DataGrid>
      </FramePanel>
      {deviceSubscription && (
        <SubscriptionDeviceDialog
          subscription={deviceSubscription}
          defaults={defaultDeviceSettings}
          onClose={() => setDeviceSubscription(null)}
          onSave={(value) => onSaveDevice(deviceSubscription, value)}
        />
      )}
    </Frame>
  )
}
