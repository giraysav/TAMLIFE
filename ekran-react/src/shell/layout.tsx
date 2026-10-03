import { ANA_SAYFA_KARTLARI } from "@/shell/home-cards"
import { SideNav } from "@/shell/nav"
import { EmptyState } from "@/shared/empty"
import { tr } from "@/lib/i18n/tr"

export function ShellLayout() {
  return (
    <div className="flex h-dvh w-full overflow-hidden bg-background text-foreground">
      <aside className="w-64 shrink-0">
        <SideNav />
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center justify-end gap-3 border-b px-4">
          <a href="#/talep">{tr["modul.talep.title"]}</a>
          <span className="text-sm text-muted-foreground">Cikis</span>
        </header>
        <main className="min-h-0 flex-1 overflow-y-auto p-4">
          <ol className="grid gap-3" data-home-cards="14">
            {ANA_SAYFA_KARTLARI.map((card) => (
              <li key={card.cardId} data-card-id={card.cardId} className="rounded-xl border bg-card p-4 text-card-foreground shadow-xs">
                <h2 className="text-base font-medium">{card.title}</h2>
                {card.empty ? <EmptyState /> : null}
              </li>
            ))}
          </ol>
        </main>
      </div>
    </div>
  )
}
