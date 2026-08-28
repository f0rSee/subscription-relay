import { useMemo, useState, type FormEvent } from "react"
import type { Subscription, SubscriptionInput } from "@/api/types"
import { Alert, AlertDescription, AlertTitle } from "@/components/reui/alert"
import { Badge, type BadgeProps } from "@/components/reui/badge"
import {
  DataGrid,
  DataGridContainer,
  dataGridFeatures,
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
import { Switch } from "@/components/ui/switch"
import { TrafficUsageView } from "@/components/traffic-usage"
import { useTable } from "@tanstack/react-table"
import type { ColumnDef, PaginationState, SortingState } from "@tanstack/react-table"
import {
  PlusIcon,
  RefreshCwIcon,
  Trash2Icon,
  TriangleAlertIcon,
} from "lucide-react"

interface SubscriptionsViewProps {
  subscriptions: Subscription[]
  loading: boolean
  error: string
  onRetry: () => void
  onCreate: (input: SubscriptionInput) => Promise<void>
  onToggle: (subscription: Subscription, enabled: boolean) => Promise<void>
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

function formatSyncDate(value: string | null) {
  if (!value) return "Ещё не запускалась"
  return new Intl.DateTimeFormat("ru", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value))
}

function AddSubscriptionDialog({
  onCreate,
}: Pick<SubscriptionsViewProps, "onCreate">) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState("")
  const [url, setUrl] = useState("")
  const [error, setError] = useState("")
  const [submitting, setSubmitting] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError("")
    try {
      await onCreate({ name, url })
      setName("")
      setUrl("")
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
  const { subscriptions, loading, error, onRetry, onCreate, onToggle, onSync, onDelete } = props
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 10,
  })
  const [sorting, setSorting] = useState<SortingState>([])
  const [pendingId, setPendingId] = useState("")

  async function run(id: string, action: () => Promise<void>) {
    setPendingId(id)
    try {
      await action()
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
          <div className="min-w-52 space-y-0.5">
            <p className="font-medium text-foreground">{row.original.name}</p>
            <p className="max-w-80 truncate text-xs text-muted-foreground">
              {row.original.url_hint}
            </p>
          </div>
        ),
        size: 300,
        enableSorting: true,
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
              <Badge variant={presentation.variant}>{presentation.label}</Badge>
              {row.original.last_error && (
                <p className="max-w-52 truncate text-xs text-destructive" title={row.original.last_error}>
                  {row.original.last_error}
                </p>
              )}
            </div>
          )
        },
        size: 150,
      },
      {
        accessorKey: "node_count",
        header: "Серверы",
        cell: ({ row }) => (
          <span className="font-medium tabular-nums">{row.original.node_count}</span>
        ),
        size: 90,
        enableSorting: true,
      },
      {
        id: "traffic",
        accessorFn: (subscription) => subscription.traffic?.used ?? -1,
        header: "Трафик",
        cell: ({ row }) => (
          <TrafficUsageView
            traffic={row.original.traffic}
            className="min-w-64"
          />
        ),
        size: 280,
        enableSorting: true,
      },
      {
        accessorKey: "last_sync_at",
        header: "Последняя синхронизация",
        cell: ({ row }) => (
          <span className="whitespace-nowrap text-muted-foreground">
            {formatSyncDate(row.original.last_sync_at)}
          </span>
        ),
        size: 180,
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
        size: 90,
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
        size: 100,
      },
    ],
    [onDelete, onSync, onToggle, pendingId],
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

  return (
    <Frame spacing="sm">
      <FrameHeader className="flex-row items-center justify-between gap-4">
        <div>
          <FrameTitle>Источники подписок</FrameTitle>
          <FrameDescription>
            Сервис забирает данные по URL и обновляет список серверов для профилей.
          </FrameDescription>
        </div>
        <AddSubscriptionDialog onCreate={onCreate} />
      </FrameHeader>
      <FramePanel className="p-2!">
        {error && (
          <Alert variant="destructive" className="mb-2">
            <TriangleAlertIcon aria-hidden="true" />
            <AlertTitle>Не удалось загрузить источники</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
            <Button type="button" size="sm" variant="outline" onClick={onRetry}>
              Повторить
            </Button>
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
            columnsResizable: true,
          }}
        >
          <div className="w-full space-y-2.5">
            <DataGridContainer>
              <DataGridScrollArea>
                <DataGridTable />
              </DataGridScrollArea>
            </DataGridContainer>
            {subscriptions.length > pagination.pageSize && <DataGridPagination />}
          </div>
        </DataGrid>
      </FramePanel>
    </Frame>
  )
}
