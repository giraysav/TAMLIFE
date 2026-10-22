import { cleanup, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"
import { CactiKarti, useCacti } from "@/musteri/cacti-paneli"
import { RaporOnizleme } from "@/musteri/rapor-onizleme"
import { AylikRapor } from "@/musteri/aylik-rapor"
import { oku, yaz } from "@/lib/sorgu"

vi.mock("@/lib/sorgu", () => ({ oku: vi.fn(), yaz: vi.fn(), hataMesaji: (_h: unknown, text: string) => text }))
afterEach(() => { cleanup(); vi.clearAllMocks() })
function wrapper() {
  const client = new QueryClient({defaultOptions:{queries:{retry:false}}})
  return ({children}: {children: ReactNode}) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
}
const ayar = {baglantilar:["7"],hazir:true,duzenleyebilir:true,kilitli:false,yil:2026,ay:9}
const grafik = {anahtar:"cacti-7",baslik:"Test Cacti",gorsel:"data:image/png;base64,test"}

describe("Cacti aylik rapor", () => {
  it("grafik alinamayinca Gonder kapali ve nedeni dugmenin altinda yazar (2026-10-22 ATU)", async () => {
    const taslak = {yil:2026,ay:9,birim:true,alanlar:{},varsayilanlar:{tr:{},en:{}},kayitli:false,guncelleyen:null,zaman:null,alicilar:{kime:"",bilgi:""},gonderim:null}
    vi.mocked(oku).mockImplementation(async url => {
      if (url.endsWith("/grafikler")) throw Object.assign(new Error("parola"), {durum:428})
      if (url.endsWith("/cacti")) return ayar
      if (url.endsWith("/taslak")) return taslak
      if (url.endsWith("/gecmis")) return []
      return {dosyalar:[],ekler:[]}
    })
    render(<AylikRapor musteriId={110} musteriAdi="Test" dil="tr" geriAlabilir={false} />,{wrapper:wrapper()})
    await waitFor(() => expect(screen.getByText(/CACTI grafikleri alınana kadar kapalı/)).toBeInTheDocument())
    expect(screen.getByRole("button",{name:"Raporu gönder"})).toBeDisabled()
  })
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
  it("Lookouteyes icin 428 gelince kisinin parolasini sorar, tek istekte gonderir ve alani temizler", async () => {
    const loe = "http://lookouteyes/lookouteyes/Modules/Graph.aspx?ct=Stock&miid=1&fn=AVG&val=val_delay"
    vi.mocked(oku).mockImplementation(async url => {
      if (url.endsWith("/grafikler")) throw Object.assign(new Error("parola"), {durum:428})
      return {...ayar,baglantilar:[loe],hazir:false}
    })
    vi.mocked(yaz).mockResolvedValue({yil:2026,ay:9,grafikler:[grafik]})
    function Kart(){const cacti=useCacti("/rapor"); return <><CactiKarti cacti={cacti} ingilizce={false}/><span>{cacti.engel ? "engelli" : "hazir"}</span></>}
    render(<Kart/>,{wrapper:wrapper()})
    const alan = await screen.findByLabelText(/Parolanız/)
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    expect(screen.queryByText(/LDAP hesabı: /)).not.toBeInTheDocument()  // sunucu hesabi Lookouteyes'ta kullanilmaz
    expect(screen.getByText("engelli")).toBeInTheDocument()
    fireEvent.change(alan, {target:{value:"gizli-parola"}})
    expect(alan).toHaveValue("gizli-parola")
    fireEvent.click(screen.getByRole("button",{name:"Grafikleri al"}))
    await waitFor(() => expect(screen.getByText("hazir")).toBeInTheDocument())
    expect(yaz).toHaveBeenCalledWith("POST", "/rapor/cacti/grafikler", expect.objectContaining({}))
    expect(screen.queryByLabelText(/Parolanız/)).not.toBeInTheDocument()
    expect(screen.getByText(/Rapora eklenen grafik/)).toBeInTheDocument()
  })
  it("grafik tanimli degilse ag erisimi yapmaz ve PDF'i engellemez", async () => {
    vi.mocked(oku).mockResolvedValue({...ayar,baglantilar:[],hazir:false})
    const {result}=renderHook(()=>useCacti("/rapor"),{wrapper:wrapper()})
    await waitFor(()=>expect(result.current.engel).toBe(false))
    expect(oku).toHaveBeenCalledTimes(1)
  })
})
