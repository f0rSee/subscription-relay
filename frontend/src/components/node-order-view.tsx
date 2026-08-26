import { useState } from "react"
import type { Profile, ProfileNode } from "@/api/types"
import { Alert, AlertDescription, AlertTitle } from "@/components/reui/alert"
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { GripVerticalIcon, ServerIcon, TriangleAlertIcon } from "lucide-react"

interface NodeOrderViewProps {
  profiles: Profile[]
  selectedProfileId: string
  onProfileChange: (id: string) => void
  nodes: ProfileNode[]
  loading: boolean
  error: string
  onSave: (profileId: string, nodes: ProfileNode[]) => Promise<void>
}

export function NodeOrderView({
  profiles,
  selectedProfileId,
  onProfileChange,
  nodes: loadedNodes,
  loading,
  error,
  onSave,
}: NodeOrderViewProps) {
  const [nodes, setNodes] = useState(loadedNodes)
  const [saveError, setSaveError] = useState("")
  const [saving, setSaving] = useState(false)

  async function commitOrder(value: ProfileNode[], previousValue: ProfileNode[]) {
    setSaving(true)
    setSaveError("")
    try {
      await onSave(selectedProfileId, value)
    } catch (reason) {
      setNodes(previousValue)
      setSaveError(reason instanceof Error ? reason.message : "Не удалось сохранить порядок")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Frame spacing="sm">
      <FrameHeader className="flex-row flex-wrap items-center justify-between gap-4">
        <div>
          <FrameTitle>Порядок серверов</FrameTitle>
          <FrameDescription>
            Перетащите серверы — новый порядок сразу применяется к URL профиля.
          </FrameDescription>
        </div>
        <div className="flex items-center gap-2">
          {saving && <span className="text-xs text-muted-foreground">Сохраняю…</span>}
          <Select value={selectedProfileId} onValueChange={(value) => value && onProfileChange(value)}>
            <SelectTrigger className="w-52" aria-label="Выберите профиль">
              <SelectValue placeholder="Выберите профиль" />
            </SelectTrigger>
            <SelectContent>
              {profiles.map((profile) => (
                <SelectItem key={profile.id} value={profile.id}>
                  {profile.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </FrameHeader>
      {(error || saveError) && (
        <Alert variant="destructive">
          <TriangleAlertIcon aria-hidden="true" />
          <AlertTitle>Порядок не сохранён</AlertTitle>
          <AlertDescription>{saveError || error}</AlertDescription>
        </Alert>
      )}
      {loading ? (
        <div className="space-y-1">
          {Array.from({ length: 6 }).map((_, index) => (
            <Skeleton key={index} className="h-14 w-full rounded-lg" />
          ))}
        </div>
      ) : nodes.length ? (
        <Sortable
          value={nodes}
          onValueChange={setNodes}
          onValueCommit={(value, meta) => void commitOrder(value, meta.previousValue)}
          getItemValue={(node) => node.id}
          strategy="vertical"
          className="space-y-1"
        >
          {nodes.map((node, index) => (
            <SortableItem key={node.id} value={node.id}>
              <FramePanel className="p-0!">
                <div className="group flex items-center gap-3 px-3 py-2.5">
                  <SortableItemHandle
                    className="text-muted-foreground hover:text-foreground"
                    aria-label={`Переместить ${node.name}`}
                  >
                    <GripVerticalIcon className="size-4" aria-hidden="true" />
                  </SortableItemHandle>
                  <span className="w-7 text-right text-xs tabular-nums text-muted-foreground">
                    {index + 1}
                  </span>
                  <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-muted">
                    <ServerIcon className="size-4 text-muted-foreground" aria-hidden="true" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{node.name}</p>
                    <p className="truncate text-xs text-muted-foreground">
                      {node.subscription_name}
                      {node.host ? ` · ${node.host}` : ""}
                    </p>
                  </div>
                  <Badge variant="outline" size="sm">
                    {node.protocol.toUpperCase()}
                  </Badge>
                  {node.duplicate && (
                    <Badge variant="warning-outline" size="sm">
                      Дубликат
                    </Badge>
                  )}
                </div>
              </FramePanel>
            </SortableItem>
          ))}
        </Sortable>
      ) : (
        <FramePanel>
          <p className="py-10 text-center text-sm text-muted-foreground">
            В этом профиле пока нет серверов. Синхронизируйте его источники.
          </p>
        </FramePanel>
      )}
    </Frame>
  )
}
