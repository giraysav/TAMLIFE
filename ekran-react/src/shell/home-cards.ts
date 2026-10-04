export type HomeCard = {
  key: string
  title: string
  i18n: string
  cardId: string
  empty: boolean
}

export const ANA_SAYFA_KARTLARI: readonly HomeCard[] = [
  {
    "key": "ekip",
    "title": "TAM Özet",
    "i18n": "card.ekip.title",
    "cardId": "dash-card-ekip",
    "empty": false
  },
  {
    "key": "takvim_ozet",
    "title": "TAM Takvim",
    "i18n": "card.takvim.title",
    "cardId": "dash-card-takvim",
    "empty": false
  },
  {
    "key": "sunum",
    "title": "TAM Sunum",
    "i18n": "card.sunum.title",
    "cardId": "dash-card-sunum",
    "empty": false
  },
  {
    "key": "radar",
    "title": "Müşteri Radar",
    "i18n": "card.radar.title",
    "cardId": "dash-card-radar",
    "empty": false
  },
  {
    "key": "musteri",
    "title": "Müşteri Yönetimi",
    "i18n": "musteri.tamPortfoy",
    "cardId": "dash-card-modul-portfoy",
    "empty": false
  },
  {
    "key": "rapor",
    "title": "Gönderilen Aylık Rapor",
    "i18n": "card.rapor.title",
    "cardId": "dash-card-rapor",
    "empty": false
  },
  {
    "key": "proje",
    "title": "Takip Edilen Projeler",
    "i18n": "card.proje.title",
    "cardId": "dash-card-proje",
    "empty": false
  },
  {
    "key": "onedesk",
    "title": "Onedesk",
    "i18n": "card.ats.title",
    "cardId": "dash-card-onedesk",
    "empty": false
  },
  {
    "key": "toptan",
    "title": "TAM Toptan",
    "i18n": "card.toptan.title",
    "cardId": "dash-card-toptan",
    "empty": true
  },
  {
    "key": "tamsms",
    "title": "TAM SMS",
    "i18n": "card.tamSms.title",
    "cardId": "dash-card-tamsms",
    "empty": false
  },
  {
    "key": "tamapn",
    "title": "TAM APN",
    "i18n": "card.tamApn.title",
    "cardId": "dash-card-tamapn",
    "empty": false
  },
  {
    "key": "gelir_uretim",
    "title": "TAM GELIR&URETIM",
    "i18n": "card.gelirUretim.title",
    "cardId": "dash-card-gelir-uretim",
    "empty": true
  },
  {
    "key": "takvim",
    "title": "İzin&Takvim Yönetimi",
    "i18n": "tab.takvim",
    "cardId": "dash-card-modul-takvim",
    "empty": false
  },
  {
    "key": "baglantili",
    "title": "Bağlantılı Araçlar",
    "i18n": "card.placeholder.title",
    "cardId": "dash-card-baglantili",
    "empty": false
  }
]
