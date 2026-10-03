import type { LucideIcon } from "lucide-react"
import { BarChart3, Calendar, CalendarClock, CircleDollarSign, ClipboardList, FileText, FolderKanban, Headset, Home, Link2, MessageSquare, Radar, Radio, Store, Users } from "lucide-react"

import type { ChartConfig } from "@/components/ui/chart"

export type Dil = "tr" | "en"

export const DIL_ANAHTARI = "tamlife-dil"

export function dilOku(): Dil {
  try {
    return localStorage.getItem(DIL_ANAHTARI) === "en" ? "en" : "tr"
  } catch {
    return "tr"
  }
}

export interface App1Person {
  name: string
  initials: string
  avatar: string
}

export const app1People = {
  giray: { name: "Giray", initials: "GS", avatar: "" },
  planlama: { name: "Planlama", initials: "PL", avatar: "" },
  operasyon: { name: "Operasyon", initials: "OP", avatar: "" },
  rapor: { name: "Raporlama", initials: "RP", avatar: "" },
  radar: { name: "Radar", initials: "MR", avatar: "" },
} satisfies Record<string, App1Person>

export interface App1NavItem {
  id: string
  ad: Record<Dil, string>
  icon: LucideIcon
}

export interface App1Project {
  id: string
  name: Record<Dil, string>
  description: Record<Dil, string>
  progress: number
  status: "progress" | "review" | "planning"
  team: App1Person[]
  due: Record<Dil, string>
}

export interface App1ActivityItem {
  id: string
  person: App1Person
  action: Record<Dil, string>
  time: Record<Dil, string>
}

export const app1User = { ...app1People.giray, email: "giray@tamlife.local" }

export const app1Team: (App1Person & { role: Record<Dil, string>; online: boolean })[] = [
  { ...app1People.planlama, role: { tr: "Plan", en: "Plan" }, online: true },
  { ...app1People.operasyon, role: { tr: "Operasyon", en: "Operations" }, online: true },
  { ...app1People.rapor, role: { tr: "Rapor", en: "Report" }, online: false },
]

export const app1Nav: App1NavItem[] = [
  { id: "ozet", ad: { tr: "TAM Özet", en: "TAM Summary" }, icon: Home },
  { id: "takvim", ad: { tr: "TAM Takvim", en: "TAM Calendar" }, icon: Calendar },
  { id: "sunum", ad: { tr: "TAM Sunum", en: "TAM Presentation" }, icon: FileText },
  { id: "radar", ad: { tr: "Müşteri Radar", en: "Customer radar" }, icon: Radar },
  { id: "musteri", ad: { tr: "Müşteri Yönetimi", en: "Customer management" }, icon: Users },
  { id: "rapor", ad: { tr: "Gönderilen Aylık Rapor", en: "Sent monthly report" }, icon: ClipboardList },
  { id: "proje", ad: { tr: "Takip Edilen Projeler", en: "Tracked projects" }, icon: FolderKanban },
  { id: "onedesk", ad: { tr: "OneDesk", en: "OneDesk" }, icon: Headset },
  { id: "toptan", ad: { tr: "TAM Toptan", en: "TAM Wholesale" }, icon: Store },
  { id: "sms", ad: { tr: "TAM SMS", en: "TAM SMS" }, icon: MessageSquare },
  { id: "apn", ad: { tr: "TAM APN", en: "TAM APN" }, icon: Radio },
  { id: "gelir", ad: { tr: "Gelir üretim", en: "Revenue production" }, icon: CircleDollarSign },
  { id: "izin", ad: { tr: "Takvim yönetimi", en: "Calendar management" }, icon: CalendarClock },
  { id: "baglantili", ad: { tr: "Bağlantılı Araçlar", en: "Connected tools" }, icon: Link2 },
  { id: "utilizasyon", ad: { tr: "TAM Utilizasyon", en: "TAM Utilization" }, icon: BarChart3 },
]

export const app1Chart = [
  { week: 1, opened: 34, completed: 28 },
  { week: 2, opened: 41, completed: 33 },
  { week: 3, opened: 29, completed: 37 },
  { week: 4, opened: 45, completed: 39 },
  { week: 5, opened: 38, completed: 44 },
  { week: 6, opened: 52, completed: 46 },
  { week: 7, opened: 47, completed: 51 },
  { week: 8, opened: 43, completed: 55 },
]

export function chartConfig(dil: Dil): ChartConfig {
  return {
    completed: { label: dil === "tr" ? "Tamamlanan" : "Completed", color: "var(--foreground)" },
    opened: { label: dil === "tr" ? "Açılan" : "Opened", color: "var(--muted-foreground)" },
  }
}

export const app1Projects: App1Project[] = [
  {
    id: "p-1",
    name: { tr: "TAM Sunum", en: "TAM Presentation" },
    description: { tr: "Haftalık sunum taslağı", en: "Weekly presentation draft" },
    progress: 75,
    status: "progress",
    team: [app1People.giray, app1People.planlama],
    due: { tr: "15 Ara", en: "15 Dec" },
  },
  {
    id: "p-2",
    name: { tr: "TAM Takvim", en: "TAM Calendar" },
    description: { tr: "İzin ve takvim özeti", en: "Leave and calendar summary" },
    progress: 45,
    status: "planning",
    team: [app1People.operasyon, app1People.rapor],
    due: { tr: "20 Oca", en: "20 Jan" },
  },
  {
    id: "p-3",
    name: { tr: "TAM Utilizasyon", en: "TAM Utilization" },
    description: { tr: "Kapasite görünümü", en: "Capacity view" },
    progress: 90,
    status: "review",
    team: [app1People.rapor, app1People.planlama],
    due: { tr: "10 Ara", en: "10 Dec" },
  },
  {
    id: "p-4",
    name: { tr: "Müşteri Radar", en: "Customer radar" },
    description: { tr: "Takip listesi güncellemesi", en: "Watch list update" },
    progress: 30,
    status: "progress",
    team: [app1People.radar, app1People.operasyon],
    due: { tr: "2 Şub", en: "2 Feb" },
  },
]

export const app1Activity: App1ActivityItem[] = [
  { id: "a-1", person: app1People.planlama, action: { tr: "TAM Takvim kaydını güncelledi", en: "updated the TAM Calendar record" }, time: { tr: "2 saat önce", en: "2 hours ago" } },
  { id: "a-2", person: app1People.operasyon, action: { tr: "TAM Sunum notu ekledi", en: "added a TAM Presentation note" }, time: { tr: "4 saat önce", en: "4 hours ago" } },
  { id: "a-3", person: app1People.rapor, action: { tr: "TAM Utilizasyon dosyası yükledi", en: "uploaded a TAM Utilization file" }, time: { tr: "6 saat önce", en: "6 hours ago" } },
  { id: "a-4", person: app1People.radar, action: { tr: "Müşteri Radar listesini yeniledi", en: "refreshed the Customer radar list" }, time: { tr: "8 saat önce", en: "8 hours ago" } },
  { id: "a-5", person: app1People.giray, action: { tr: "TAM Özet görünümünü açtı", en: "opened the TAM Summary view" }, time: { tr: "10 saat önce", en: "10 hours ago" } },
  { id: "a-6", person: app1People.operasyon, action: { tr: "TAM SMS gönderimini işaretledi", en: "marked the TAM SMS send" }, time: { tr: "12 saat önce", en: "12 hours ago" } },
]

export type ArayuzMetin = {
  menu: string
  ekip: string
  hosgeldin: (ad: string) => string
  ara: string
  bildirim: string
  dil: string
  toplamProje: string
  toplamProjeIpucu: string
  aktifGorev: string
  aktifGorevIpucu: string
  ekipUyeleri: string
  ekipUyeleriIpucu: string
  tamamlanma: string
  tamamlanmaIpucu: string
  grafikBaslik: string
  grafikAciklama: string
  hafta: (n: number) => string
  aktifProjeler: string
  aktifProjelerAciklama: string
  durum: Record<App1Project["status"], string>
  sonTarih: string
  ilerleme: string
  sonHareket: string
  sonHareketAciklama: string
  bosModul: string
  anaSayfa: string
  rol: string
  admin: string
  cikis: string
  veriBaslik: string
  veriYukleniyor: string
  veriHata: string
  tanimli: string
  degil: string
  ikinciKaynak: string
  rolAciklama: string
  rolKaydet: string
  rolKaydedildi: string
  rolHata: string
  rolModul: string
  rolYukleniyor: string
}

export function arayuz(dil: Dil): ArayuzMetin {
  if (dil === "en") {
    return {
      menu: "Toggle navigation",
      ekip: "Team",
      hosgeldin: (ad) => `Welcome back, ${ad}`,
      ara: "Search",
      bildirim: "Notifications",
      dil: "Language",
      toplamProje: "Total projects",
      toplamProjeIpucu: "+2 from last month",
      aktifGorev: "Active tasks",
      aktifGorevIpucu: "+12 from yesterday",
      ekipUyeleri: "Team members",
      ekipUyeleriIpucu: "+1 new member",
      tamamlanma: "Completion rate",
      tamamlanmaIpucu: "+5% from last week",
      grafikBaslik: "Task throughput",
      grafikAciklama: "Tasks opened against tasks completed over the last eight weeks",
      hafta: (n) => `Wk ${n}`,
      aktifProjeler: "Active projects",
      aktifProjelerAciklama: "Your current project progress",
      durum: { progress: "In progress", review: "In review", planning: "Planning" },
      sonTarih: "Due",
      ilerleme: "progress",
      sonHareket: "Recent activity",
      sonHareketAciklama: "Latest updates from your team",
      bosModul: "This module is not connected yet.",
      anaSayfa: "Home",
      rol: "Role management",
      admin: "Admin",
      cikis: "Sign out",
      veriBaslik: "Data tree",
      veriYukleniyor: "Loading",
      veriHata: "The data tree could not be loaded.",
      tanimli: "defined",
      degil: "not defined",
      ikinciKaynak: "Second source is not defined",
      rolAciklama: "Grant module access for team manager and team member. Admin always sees every module and this page; saving cannot remove that access. TAM Summary stays on for everyone.",
      rolKaydet: "Save",
      rolKaydedildi: "Saved.",
      rolHata: "Role permissions could not be saved.",
      rolModul: "Module",
      rolYukleniyor: "Loading",
    }
  }
  return {
    menu: "Menüyü aç veya kapat",
    ekip: "Ekip",
    hosgeldin: (ad) => `Tekrar hoş geldin, ${ad}`,
    ara: "Ara",
    bildirim: "Bildirimler",
    dil: "Dil",
    toplamProje: "Toplam proje",
    toplamProjeIpucu: "geçen aydan +2",
    aktifGorev: "Aktif görev",
    aktifGorevIpucu: "dünden +12",
    ekipUyeleri: "Ekip üyeleri",
    ekipUyeleriIpucu: "+1 yeni üye",
    tamamlanma: "Tamamlanma oranı",
    tamamlanmaIpucu: "geçen haftadan +%5",
    grafikBaslik: "Görev hacmi",
    grafikAciklama: "Son sekiz haftada açılan ve tamamlanan görevler",
    hafta: (n) => `Hf ${n}`,
    aktifProjeler: "Aktif projeler",
    aktifProjelerAciklama: "Güncel proje ilerlemesi",
    durum: { progress: "Devam ediyor", review: "İncelemede", planning: "Planlama" },
    sonTarih: "Son tarih",
    ilerleme: "ilerleme",
    sonHareket: "Son hareketler",
    sonHareketAciklama: "Ekipten son güncellemeler",
    bosModul: "Bu modül henüz bağlı değil.",
    anaSayfa: "Ana sayfa",
    rol: "Rol yönetimi",
    admin: "Admin",
    cikis: "Çıkış",
    veriBaslik: "Veri ağacı",
    veriYukleniyor: "Yükleniyor",
    veriHata: "Veri ağacı alınamadı.",
    tanimli: "tanımlı",
    degil: "değil",
    ikinciKaynak: "İkinci kaynak tanımlı değil",
    rolAciklama: "Takım yöneticisi ve takım üyesi rollerine modül erişimi verin. Yönetici her modülü ve bu sayfayı görür; kayıt yönetici erişimini kapatmaz. TAM Özet herkese açıktır.",
    rolKaydet: "Kaydet",
    rolKaydedildi: "Kaydedildi.",
    rolHata: "Rol yetkileri kaydedilemedi.",
    rolModul: "Modül",
    rolYukleniyor: "Yükleniyor",
  }
}
