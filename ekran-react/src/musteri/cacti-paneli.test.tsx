import { cleanup, render, renderHook, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"
import { CactiKarti, useCacti } from "@/musteri/cacti-paneli"
import { RaporOnizleme } from "@/musteri/rapor-onizleme"
import { oku } from "@/lib/sorgu"

vi.mock("@/lib/sorgu", () => ({ oku: vi.fn(), yaz: vi.fn(), hataMesaji: (_h: unknown, text: string) => text }))
afterEach(() => { cleanup(); vi.clearAllMocks() })
function wrapper() {
  const client = new QueryClient({defaultOptions:{queries:{retry:false}}})
  return ({children}: {children: ReactNode}) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
}
const ayar = {baglantilar:["7"],hazir:true,duzenleyebilir:true,kilitli:false,yil:2026,ay:9}
const grafik = {anahtar:"cacti-7",baslik:"Test Cacti",gorsel:"data:image/png;base64,test"}

describe("Cacti aylik rapor", () => {
  it("grafikleri otomatik getirir ve rapor onizlemesine ekler", async () => {
    vi.mocked(oku).mockImplementation(async url => url.endsWith("/grafikler") ? {yil:2026,ay:9,grafikler:[grafik]} : ayar)
    const {result} = renderHook(() => useCacti("/rapor"), {wrapper:wrapper()})
    await waitFor(() => expect(result.current.engel).toBe(false))
    expect(result.current.grafikler).toEqual([grafik])
    render(<RaporOnizleme musteriAdi="Test" donem="Eylül 2026" dil="tr" alanlar={{}} grafikler={[]} ekler={result.current.grafikler} />)
    expect(screen.getByAltText("Test Cacti")).toHaveAttribute("src",grafik.gorsel)
  })
  it("grafik hatasinda PDF uretimini bekletir ve parola gostermez", async () => {
    vi.mocked(oku).mockImplementation(async url => {if(url.endsWith("/grafikler")) throw new Error("offline"); return ayar})
    function Kart(){const cacti=useCacti("/rapor"); return <CactiKarti cacti={cacti} ingilizce={false}/>}
    render(<Kart/>,{wrapper:wrapper()})
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument())
    expect(screen.queryByLabelText(/parola|password/i)).not.toBeInTheDocument()
    expect(screen.getByText(/LDAP hesabı: Tanımlı/)).toBeInTheDocument()
    expect(screen.getByRole("button",{name:"Tekrar dene"})).toBeInTheDocument()
  })
  it("grafik tanimli degilse ag erisimi yapmaz ve PDF'i engellemez", async () => {
    vi.mocked(oku).mockResolvedValue({...ayar,baglantilar:[],hazir:false})
    const {result}=renderHook(()=>useCacti("/rapor"),{wrapper:wrapper()})
    await waitFor(()=>expect(result.current.engel).toBe(false))
    expect(oku).toHaveBeenCalledTimes(1)
  })
})
