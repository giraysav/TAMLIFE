import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"

/**
 * Sunucu verisi onbellegi (TanStack Query). Varsayilanlar: 15 sn taze (ayni veri tekrar istenmez), tek yeniden deneme,
 * pencereye donuste otomatik yenileme yok (yonetim ekranlari kendi araligiyla tazelenir; sekme gizliyken beklenir).
 */
export const istemci = new QueryClient({
  defaultOptions: { queries: { staleTime: 15_000, retry: 1, refetchOnWindowFocus: false } },
})

export function Saglayicilar({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={istemci}>{children}</QueryClientProvider>
}
