import { useTheme } from "next-themes"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
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
  SunIcon,
  UsersIcon,
} from "lucide-react"

export type DashboardView = "subscriptions" | "profiles" | "order"

interface DashboardSidebarProps {
  activeView: DashboardView
  subscriptionsCount: number
  profilesCount: number
  nodesCount: number
  username: string
  onViewChange: (view: DashboardView) => void
  onLogout: () => Promise<void>
}

const navigation = [
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
  username,
  onViewChange,
  onLogout,
}: DashboardSidebarProps) {
  const { isMobile, setOpenMobile } = useSidebar()
  const { theme = "system", setTheme } = useTheme()
  const counts = { subscriptionsCount, profilesCount, nodesCount }
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
        <SidebarGroup>
          <SidebarGroupLabel>Управление</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {navigation.map((item) => {
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
                    <SidebarMenuBadge>{counts[item.countKey]}</SidebarMenuBadge>
                  </SidebarMenuItem>
                )
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarSeparator />
      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <SidebarMenuButton type="button" tooltip="Тема интерфейса" />
                }
              >
                <SelectedThemeIcon aria-hidden="true" />
                <span>Тема: {selectedTheme.label.toLowerCase()}</span>
              </DropdownMenuTrigger>
              <DropdownMenuContent side="right" align="end" className="w-48">
                <DropdownMenuLabel>Тема интерфейса</DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuRadioGroup value={theme} onValueChange={setTheme}>
                  {themeOptions.map((option) => {
                    const Icon = option.icon
                    return (
                      <DropdownMenuRadioItem key={option.value} value={option.value}>
                        <Icon aria-hidden="true" />
                        {option.label}
                      </DropdownMenuRadioItem>
                    )
                  })}
                </DropdownMenuRadioGroup>
              </DropdownMenuContent>
            </DropdownMenu>
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
