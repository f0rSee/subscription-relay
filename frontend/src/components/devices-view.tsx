import { useMemo, useState } from "react"
import type { ClientDevice } from "@/api/types"
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

interface DevicesViewProps {
  devices: ClientDevice[]
  loading: boolean
  error: string
  onRefresh: () => void
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("ru", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value))
}

export function DevicesView({ devices, loading, error, onRefresh }: DevicesViewProps) {
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 25,
  })
  const [sorting, setSorting] = useState<SortingState>([
    { id: "last_seen_at", desc: true },
  ])

  const columns = useMemo<ColumnDef<DataGridFeatures, ClientDevice>[]>(
    () => [
      {
        accessorKey: "name",
        header: "Устройство",
        cell: ({ row }) => (
          <div className="min-w-56">
            <p className="font-medium text-foreground">{row.original.name}</p>
            <p
              className="max-w-80 truncate text-xs text-muted-foreground"
              title={row.original.user_agent}
            >
              {row.original.user_agent}
            </p>
          </div>
        ),
        size: 300,
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
        size: 150,
      },
      {
        accessorKey: "last_profile_name",
        header: "Последний профиль",
        cell: ({ row }) => row.original.last_profile_name ?? "—",
        size: 180,
        enableSorting: true,
      },
      {
        accessorKey: "request_count",
        header: "Запросы",
        cell: ({ row }) => (
          <span className="font-medium tabular-nums">{row.original.request_count}</span>
        ),
        size: 90,
        enableSorting: true,
      },
      {
        accessorKey: "last_status_code",
        header: "Последний статус",
        cell: ({ row }) => {
          const status = row.original.last_status_code
          if (status === null) return "—"
          const success = status >= 200 && status < 300
          return (
            <Badge variant={success ? "success-outline" : "destructive-outline"}>
              HTTP {status}
            </Badge>
          )
        },
        size: 140,
        enableSorting: true,
      },
      {
        accessorKey: "first_seen_at",
        header: "Первый запрос",
        cell: ({ row }) => (
          <span className="whitespace-nowrap text-muted-foreground">
            {formatDate(row.original.first_seen_at)}
          </span>
        ),
        size: 160,
        enableSorting: true,
      },
      {
        accessorKey: "last_seen_at",
        header: "Последний запрос",
        cell: ({ row }) => (
          <span className="whitespace-nowrap text-muted-foreground">
            {formatDate(row.original.last_seen_at)}
          </span>
        ),
        size: 160,
        enableSorting: true,
      },
    ],
    [],
  )

  const table = useTable({
    features: dataGridFeatures,
    columns,
    data: devices,
    pageCount: Math.max(1, Math.ceil(devices.length / pagination.pageSize)),
    getRowId: (row: ClientDevice) => row.id,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
  })

  return (
    <Frame spacing="sm">
      <FrameHeader className="flex-row items-center justify-between gap-4">
        <div>
          <FrameTitle>Устройства</FrameTitle>
          <FrameDescription>
            Клиенты определяются по комбинации IP-адреса и User-Agent.
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
            <AlertTitle>Не удалось загрузить устройства</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        <DataGrid
          table={table}
          recordCount={devices.length}
          isLoading={loading}
          loadingMode="skeleton"
          emptyMessage="Устройств пока нет. Они появятся после первого запроса подписки."
          tableLayout={{ headerBackground: true, rowBorder: true, columnsResizable: true }}
        >
          <div className="w-full space-y-2.5">
            <DataGridContainer>
              <DataGridScrollArea>
                <DataGridTable />
              </DataGridScrollArea>
            </DataGridContainer>
            {devices.length > pagination.pageSize && (
              <DataGridPagination rowsPerPageLabel="Строк на странице" />
            )}
          </div>
        </DataGrid>
      </FramePanel>
    </Frame>
  )
}
