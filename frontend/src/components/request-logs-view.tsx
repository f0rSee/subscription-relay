import { useMemo, useState } from "react"
import type { RequestLog } from "@/api/types"
import { Alert, AlertDescription, AlertTitle } from "@/components/reui/alert"
import { Badge } from "@/components/reui/badge"
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
import { useTable } from "@tanstack/react-table"
import type { ColumnDef, PaginationState, SortingState } from "@tanstack/react-table"
import { RefreshCwIcon, TriangleAlertIcon } from "lucide-react"

interface RequestLogsViewProps {
  logs: RequestLog[]
  loading: boolean
  error: string
  onRefresh: () => void
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("ru", {
    dateStyle: "short",
    timeStyle: "medium",
  }).format(new Date(value))
}

export function RequestLogsView({
  logs,
  loading,
  error,
  onRefresh,
}: RequestLogsViewProps) {
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 25,
  })
  const [sorting, setSorting] = useState<SortingState>([
    { id: "requested_at", desc: true },
  ])

  const columns = useMemo<ColumnDef<DataGridFeatures, RequestLog>[]>(
    () => [
      {
        accessorKey: "requested_at",
        header: "Время",
        cell: ({ row }) => (
          <span className="whitespace-nowrap text-muted-foreground">
            {formatDate(row.original.requested_at)}
          </span>
        ),
        size: 160,
        enableSorting: true,
      },
      {
        accessorKey: "profile_name",
        header: "Профиль",
        cell: ({ row }) => (
          <div className="min-w-40">
            <p className="font-medium text-foreground">{row.original.profile_name}</p>
            <p className="text-xs text-muted-foreground">
              {row.original.request_type === "default" ? "Основной URL" : "URL профиля"}
            </p>
          </div>
        ),
        size: 180,
        enableSorting: true,
      },
      {
        accessorKey: "client_name",
        header: "Клиент",
        cell: ({ row }) => (
          <div className="min-w-52">
            <p className="font-medium text-foreground">{row.original.client_name}</p>
            <p
              className="max-w-72 truncate text-xs text-muted-foreground"
              title={row.original.user_agent}
            >
              {row.original.user_agent}
            </p>
          </div>
        ),
        size: 260,
        enableSorting: true,
      },
      {
        accessorKey: "ip_address",
        header: "IP",
        cell: ({ row }) => (
          <span className="whitespace-nowrap font-mono text-xs">
            {row.original.ip_address}
          </span>
        ),
        size: 140,
      },
      {
        accessorKey: "status_code",
        header: "Результат",
        cell: ({ row }) => {
          const success = row.original.status_code >= 200 && row.original.status_code < 300
          return (
            <div className="min-w-32 space-y-1">
              <Badge variant={success ? "success-outline" : "destructive-outline"}>
                HTTP {row.original.status_code}
              </Badge>
              {row.original.error && (
                <p
                  className="max-w-52 truncate text-xs text-destructive"
                  title={row.original.error}
                >
                  {row.original.error}
                </p>
              )}
            </div>
          )
        },
        size: 150,
        enableSorting: true,
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
    ],
    [],
  )

  const table = useTable({
    features: dataGridFeatures,
    columns,
    data: logs,
    pageCount: Math.max(1, Math.ceil(logs.length / pagination.pageSize)),
    getRowId: (row: RequestLog) => row.id,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
  })

  return (
    <Frame spacing="sm">
      <FrameHeader className="flex-row items-center justify-between gap-4">
        <div>
          <FrameTitle>Запросы подписок</FrameTitle>
          <FrameDescription>
            Последние обращения к основному URL и ссылкам профилей.
          </FrameDescription>
        </div>
        <Button type="button" size="sm" variant="outline" onClick={onRefresh}>
          <RefreshCwIcon className={loading ? "animate-spin" : ""} aria-hidden="true" />
          Обновить
        </Button>
      </FrameHeader>
      <FramePanel className="p-2!">
        {error && (
          <Alert variant="destructive" className="mb-2" role="status">
            <TriangleAlertIcon aria-hidden="true" />
            <AlertTitle>Не удалось загрузить логи</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        <DataGrid
          table={table}
          recordCount={logs.length}
          isLoading={loading}
          loadingMode="skeleton"
          emptyMessage="Запросов пока нет. Новые обращения появятся здесь автоматически."
          tableLayout={{ headerBackground: true, rowBorder: true, columnsResizable: true }}
        >
          <div className="w-full space-y-2.5">
            <DataGridContainer>
              <DataGridScrollArea>
                <DataGridTable />
              </DataGridScrollArea>
            </DataGridContainer>
            {logs.length > pagination.pageSize && (
              <DataGridPagination rowsPerPageLabel="Строк на странице" />
            )}
          </div>
        </DataGrid>
      </FramePanel>
    </Frame>
  )
}
