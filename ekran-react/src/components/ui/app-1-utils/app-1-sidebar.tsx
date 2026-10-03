import { useEffect, useRef, useState } from "react"

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/app-1-utils/sidebar"
import { app1Nav, app1Team, type ArayuzMetin, type Dil } from "@/components/ui/app-1-utils/app-1-data"

export function App1Sidebar({
  dil,
  metin,
  gorunen,
  menuRol,
  menuAdmin,
  oturum,
  selectedId,
  onSelect,
  onCikis,
  kullanici,
}: {
  kullanici: { name: string; initials: string; email: string }
  dil: Dil
  metin: ArayuzMetin
  gorunen: string[]
  menuRol: boolean
  menuAdmin: boolean
  oturum: boolean
  selectedId: string
  onSelect: (id: string) => void
  onCikis: () => void
}) {
  const { setOpenMobile } = useSidebar()
  const [menuAcik, setMenuAcik] = useState(false)
  const kutu = useRef<HTMLDivElement>(null)
  const nav = app1Nav.filter((item) => gorunen.includes(item.id))

  useEffect(() => {
    if (!menuAcik) return
    const kapat = (event: MouseEvent) => {
      if (!kutu.current?.contains(event.target as Node)) setMenuAcik(false)
    }
    document.addEventListener("mousedown", kapat)
    return () => document.removeEventListener("mousedown", kapat)
  }, [menuAcik])

  function sec(id: string) {
    onSelect(id)
    setOpenMobile(false)
    setMenuAcik(false)
  }

  return (
    <Sidebar>
      <SidebarHeader>
        <a
          href="#ozet"
          className="flex min-h-11 items-center gap-2 rounded-lg px-2 font-semibold"
          onClick={() => sec("ozet")}
        >
          <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary text-sm text-primary-foreground">
            T
          </span>
          TAM Life
        </a>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <nav aria-label="TAM Life">
              <SidebarMenu>
                {nav.map((item) => {
                  const active = item.id === selectedId
                  return (
                    <SidebarMenuItem key={item.id}>
                      <SidebarMenuButton
                        isActive={active}
                        render={
                          <a
                            href={`#${item.id}`}
                            aria-current={active ? "page" : undefined}
                            onClick={() => sec(item.id)}
                          />
                        }
                      >
                        <item.icon />
                        <span>{item.ad[dil]}</span>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  )
                })}
              </SidebarMenu>
            </nav>
          </SidebarGroupContent>
        </SidebarGroup>
        <SidebarGroup>
          <SidebarGroupLabel>{metin.ekip}</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {app1Team.map((member) => (
                <SidebarMenuItem key={member.name}>
                  <SidebarMenuButton render={<a href="#ekip" onClick={() => setOpenMobile(false)} />}>
                    <span className="relative shrink-0">
                      <Avatar className="size-6">
                        <AvatarImage src={member.avatar} alt="" />
                        <AvatarFallback className="text-[10px]">{member.initials}</AvatarFallback>
                      </Avatar>
                      {member.online ? (
                        <span
                          aria-hidden
                          className="absolute bottom-0 right-0 size-2 rounded-full border-2 border-sidebar bg-primary"
                        />
                      ) : null}
                    </span>
                    <span className="truncate">{member.name}</span>
                    <span className="ml-auto shrink-0 text-xs opacity-70">{member.role[dil]}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter>
        <div className="relative" ref={kutu}>
          {menuAcik && (menuRol || menuAdmin) ? (
            <div
              role="menu"
              className="absolute bottom-full left-0 z-20 mb-1 w-full min-w-56 rounded-md border bg-popover p-1 text-popover-foreground shadow-md"
            >
              {menuRol ? (
                <button
                  type="button"
                  role="menuitem"
                  className="flex w-full rounded-sm px-2 py-2 text-left text-sm hover:bg-accent"
                  onClick={() => sec("rol")}
                >
                  {metin.rol}
                </button>
              ) : null}
              {menuAdmin ? (
                <button
                  type="button"
                  role="menuitem"
                  className="flex w-full rounded-sm px-2 py-2 text-left text-sm hover:bg-accent"
                  onClick={() => sec("admin")}
                >
                  {metin.admin}
                </button>
              ) : null}
            </div>
          ) : null}
          <div className="flex items-center gap-1">
            <SidebarMenu className="min-w-0 flex-1">
              <SidebarMenuItem>
                <SidebarMenuButton
                  className="min-h-12"
                  aria-haspopup={menuRol || menuAdmin ? "menu" : undefined}
                  aria-expanded={menuRol || menuAdmin ? menuAcik : undefined}
                  onClick={() => {
                    if (menuRol || menuAdmin) setMenuAcik((acik) => !acik)
                  }}
                >
                  <Avatar className="size-7">
                    <AvatarFallback>{kullanici.initials}</AvatarFallback>
                  </Avatar>
                  <span className="min-w-0 flex-1 text-left">
                    <span className="block truncate font-medium">{kullanici.name}</span>
                    
                  </span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
            {oturum ? (
              <button
                type="button"
                className="shrink-0 rounded-md border border-sidebar-border px-2 py-1.5 text-sm font-medium hover:bg-sidebar-accent"
                onClick={() => {
                  setMenuAcik(false)
                  setOpenMobile(false)
                  onCikis()
                }}
              >
                {metin.cikis}
              </button>
            ) : null}
          </div>
        </div>
      </SidebarFooter>
    </Sidebar>
  )
}

export default App1Sidebar
