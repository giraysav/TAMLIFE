import { ANA_SAYFA_KARTLARI } from "@/shell/home-cards"

export function SideNav() {
  return (
    <nav aria-label="Ana menu" className="h-full overflow-y-auto border-r border-sidebar-border bg-sidebar text-sidebar-foreground">
      <ol className="flex flex-col gap-1 p-3">
        {ANA_SAYFA_KARTLARI.map((card) => (
          <li key={card.cardId}>
            <a className="block rounded-md px-3 py-2 text-sm hover:bg-accent" href={"#/" + card.key} data-card-id={card.cardId}>
              {card.title}
            </a>
          </li>
        ))}
      </ol>
    </nav>
  )
}
