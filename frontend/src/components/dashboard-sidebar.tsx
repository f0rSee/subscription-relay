import { useTheme } from "next-themes"
import { cn } from "@/lib/utils"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarSeparator,
  useSidebar,
} from "@/components/ui/sidebar"
import {
  Layers3Icon,
  ListOrderedIcon,
  LogOutIcon,
  MonitorIcon,
  MoonIcon,
  RadioTowerIcon,
  ScrollTextIcon,
  SettingsIcon,
  SmartphoneIcon,
  SunIcon,
  UsersIcon,
} from "lucide-react"

export type DashboardView =
  | "subscriptions"
  | "profiles"
  | "order"
  | "logs"
  | "devices"
  | "settings"

interface DashboardSidebarProps {
  activeView: DashboardView
  subscriptionsCount: number
  profilesCount: number
  nodesCount: number
  logsCount: number
  devicesCount: number
  username: string
  onViewChange: (view: DashboardView) => void
  onLogout: () => Promise<void>
}

const navigationGroups = [
  {
    label: "Управление",
    items: [
      {
        id: "subscriptions",
        label: "Источники",
        icon: Layers3Icon,
        countKey: "subscriptionsCount",
      },
      {
        id: "profiles",
        label: "Профили",
        icon: UsersIcon,
        countKey: "profilesCount",
      },
      {
        id: "order",
        label: "Порядок серверов",
        icon: ListOrderedIcon,
        countKey: "nodesCount",
      },
    ],
  },
  {
    label: "Наблюдение",
    items: [
      {
        id: "logs",
        label: "Логи",
        icon: ScrollTextIcon,
        countKey: "logsCount",
      },
      {
        id: "devices",
        label: "Устройства",
        icon: SmartphoneIcon,
        countKey: "devicesCount",
      },
    ],
  },
  {
    label: "Система",
    items: [
      {
        id: "settings",
        label: "Настройки",
        icon: SettingsIcon,
      },
    ],
  },
] as const

const themeOptions = [
  { value: "system", label: "Устройство", icon: MonitorIcon },
  { value: "light", label: "Светлая", icon: SunIcon },
  { value: "dark", label: "Тёмная", icon: MoonIcon },
] as const

export function DashboardSidebar({
  activeView,
  subscriptionsCount,
  profilesCount,
  nodesCount,
  logsCount,
  devicesCount,
  username,
  onViewChange,
  onLogout,
}: DashboardSidebarProps) {
  const { isMobile, setOpen, setOpenMobile } = useSidebar()
  const { theme = "system", setTheme } = useTheme()
  const counts = {
    subscriptionsCount,
    profilesCount,
    nodesCount,
    logsCount,
    devicesCount,
  }
  const selectedTheme =
    themeOptions.find((option) => option.value === theme) ?? themeOptions[0]
  const SelectedThemeIcon = selectedTheme.icon

  function navigate(view: DashboardView) {
    onViewChange(view)
    if (isMobile) setOpenMobile(false)
  }

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <div className="flex h-12 min-w-0 items-center gap-2 px-2 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0">
          <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <RadioTowerIcon className="size-4" aria-hidden="true" />
          </div>
          <div className="min-w-0 leading-tight group-data-[collapsible=icon]:hidden">
            <p className="truncate text-sm font-semibold">Subscription Relay</p>
            <p className="truncate text-xs text-sidebar-foreground/60">Control center</p>
          </div>
        </div>
      </SidebarHeader>
      <SidebarSeparator />
      <SidebarContent>
        {navigationGroups.map((group) => (
          <SidebarGroup key={group.label}>
            <SidebarGroupLabel>{group.label}</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {group.items.map((item) => {
                  const Icon = item.icon
                  return (
                    <SidebarMenuItem key={item.id}>
                      <SidebarMenuButton
                        type="button"
                        isActive={activeView === item.id}
                        tooltip={item.label}
                        onClick={() => navigate(item.id)}
                      >
                        <Icon aria-hidden="true" />
                        <span>{item.label}</span>
                      </SidebarMenuButton>
                      {"countKey" in item && (
                        <SidebarMenuBadge>{counts[item.countKey]}</SidebarMenuBadge>
                      )}
                    </SidebarMenuItem>
                  )
                })}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ))}
      </SidebarContent>
      <SidebarSeparator />
      <SidebarFooter>
        <div
          className="grid grid-cols-3 gap-1 px-1 group-data-[collapsible=icon]:hidden"
          role="radiogroup"
          aria-label="Тема интерфейса"
        >
          {themeOptions.map((option) => {
            const Icon = option.icon
            const selected = option.value === theme
            return (
              <button
                key={option.value}
                type="button"
                role="radio"
                aria-checked={selected}
                className={cn(
                  "flex min-w-0 flex-col items-center gap-1 rounded-md px-1 py-2 text-[10px] text-sidebar-foreground/65 outline-none transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:ring-2 focus-visible:ring-sidebar-ring",
                  selected && "bg-sidebar-accent text-sidebar-accent-foreground",
                )}
                onClick={() => setTheme(option.value)}
              >
                <Icon className="size-4" aria-hidden="true" />
                <span className="truncate">{option.label}</span>
              </button>
            )
          })}
        </div>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              type="button"
              tooltip={`Тема: ${selectedTheme.label.toLowerCase()}`}
              className="hidden group-data-[collapsible=icon]:flex"
              onClick={() => setOpen(true)}
            >
                <SelectedThemeIcon aria-hidden="true" />
                <span>Тема: {selectedTheme.label.toLowerCase()}</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <SidebarMenuButton
              type="button"
              size="lg"
              tooltip={`Выйти: ${username}`}
              onClick={() => void onLogout()}
            >
              <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-sidebar-accent font-medium text-sidebar-accent-foreground">
                {username.slice(0, 1).toUpperCase()}
              </div>
              <div className="min-w-0 flex-1 text-left leading-tight">
                <span className="block truncate text-sm font-medium">{username}</span>
                <span className="block truncate text-xs text-sidebar-foreground/60">
                  Администратор
                </span>
              </div>
              <LogOutIcon className="ml-auto" aria-hidden="true" />
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  )
}
