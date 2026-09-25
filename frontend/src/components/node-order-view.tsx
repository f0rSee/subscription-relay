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
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import {
  GripVerticalIcon,
  SearchIcon,
  ServerIcon,
  TriangleAlertIcon,
} from "lucide-react"

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
  const [searchQuery, setSearchQuery] = useState("")

  const groups: Array<{ id: string; name: string; nodes: ProfileNode[] }> = []
  const groupsById = new Map<string, (typeof groups)[number]>()
  for (const node of nodes) {
    const group = groupsById.get(node.subscription_id)
    if (group) {
      group.nodes.push(node)
    } else {
      const nextGroup = {
        id: node.subscription_id,
        name: node.subscription_name,
        nodes: [node],
      }
      groups.push(nextGroup)
      groupsById.set(node.subscription_id, nextGroup)
    }
  }

  const query = searchQuery.trim().toLowerCase()
  const displayedGroups = query
    ? groups
        .map((group) => ({
          ...group,
          nodes: group.nodes.filter(
            (node) =>
              node.name.toLowerCase().includes(query) ||
              (node.host && node.host.toLowerCase().includes(query)) ||
              node.protocol.toLowerCase().includes(query),
          ),
        }))
        .filter((group) => group.nodes.length > 0)
    : groups

  function replaceGroup(sourceId: string, value: ProfileNode[]) {
    let sourceIndex = 0
    return nodes.map((node) =>
      node.subscription_id === sourceId ? value[sourceIndex++] : node,
    )
  }

  function changeGroup(sourceId: string, value: ProfileNode[]) {
    setNodes(replaceGroup(sourceId, value))
  }

  async function commitOrder(
    sourceId: string,
    value: ProfileNode[],
    previousValue: ProfileNode[],
  ) {
    const nextNodes = replaceGroup(sourceId, value)
    const previousNodes = replaceGroup(sourceId, previousValue)
    setSaving(true)
    setSaveError("")
    try {
      await onSave(selectedProfileId, nextNodes)
    } catch (reason) {
      setNodes(previousNodes)
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
            Источники идут в порядке профиля; здесь серверы сортируются внутри каждой группы.
          </FrameDescription>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {saving && <span className="text-xs text-muted-foreground">Сохраняю…</span>}
          <div className="relative">
            <SearchIcon
              className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden="true"
            />
            <Input
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="Поиск серверов…"
              className="h-9 w-44 pl-8 text-xs sm:w-56"
            />
          </div>
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
        <Alert variant="destructive" role="status">
          <TriangleAlertIcon aria-hidden="true" />
          <AlertTitle>Порядок не сохранён</AlertTitle>
          <AlertDescription>{saveError || error}</AlertDescription>
        </Alert>
      )}
      {query && (
        <p className="px-1 text-xs text-muted-foreground">
          Фильтрация активна. Сортировка перетаскиванием доступна при сбросе поиска.
        </p>
      )}
      {loading ? (
        <div className="grid gap-1">
          {Array.from({ length: 6 }).map((_, index) => (
            <Skeleton key={index} className="h-14 w-full rounded-lg" />
          ))}
        </div>
      ) : displayedGroups.length ? (
        <div className="grid gap-5">
          {displayedGroups.map((group, groupIndex) => (
            <section key={group.id} className="grid gap-2">
              <div className="flex items-center justify-between gap-3 px-1">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">
                    {groupIndex + 1}. {group.name}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Приоритет источника настраивается в профиле
                  </p>
                </div>
                <Badge variant="outline" size="sm">
                  {group.nodes.length}
                </Badge>
              </div>
              <Sortable
                value={group.nodes}
                onValueChange={(value) => changeGroup(group.id, value)}
                onValueCommit={(value, meta) =>
                  void commitOrder(group.id, value, meta.previousValue)
                }
                getItemValue={(node) => node.id}
                strategy="vertical"
                className="grid gap-1"
              >
                {group.nodes.map((node, index) => (
                  <SortableItem
                    key={node.id}
                    value={node.id}
                    disabled={saving || Boolean(query)}
                  >
                    <FramePanel className="p-0!">
                      <div className="group flex items-center gap-3 px-3 py-2.5">
                        <SortableItemHandle
                          className={query ? "text-muted-foreground/40 cursor-not-allowed" : "text-muted-foreground hover:text-foreground"}
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
                            {node.host ?? "Хост не указан"}
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
            </section>
          ))}
        </div>
      ) : query ? (
        <FramePanel>
          <p className="py-10 text-center text-sm text-muted-foreground">
            Серверы не найдены по запросу «{searchQuery}».
          </p>
        </FramePanel>
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
