"""Aylik rapor hazir metinleri (uretim kutucuklar/rapor/servis.py). Yalniz veri ve kucuk bicimleyiciler."""

from __future__ import annotations

from app.ortak import ay_adi

# Taslak alanlari ve azami uzunluklari (uretim aylik.py TASLAK_ALANLARI).
# olumlu=positive, devam=ongoing, kritik=critical, bilgi=info, oneri=suggestions.
TASLAK_ALANLARI = {
    "konu": 200,
    "govde": 10000,
    "imza": 2000,
    "olumlu": 10000,
    "devam": 10000,
    "kritik": 10000,
    "bilgi": 20000,
    "oneri": 20000,
    "dil": 2,
}
DILLER = ("tr", "en")

VARSAYILAN_METINLER = {
    "tr": {
        "olumlu": "Bu dönem için ayrıca kayda değer bir olumlu gelişme raporlanmamıştır.",
        "devam": "Bu dönemde müşteri nezdinde devam eden açık bir çalışma raporlanmamıştır.",
        "kritik": "Bu dönemde aksiyon gerektiren kritik bir konu raporlanmamıştır.",
        "bilgi": "Bu dönem için ayrıca bir bilgilendirme bulunmamaktadır.",
        "oneri": "Bu dönem için ayrıca bir öneri sunulmamıştır.",
    },
    "en": {
        "olumlu": "No additional noteworthy developments were reported for this period.",
        "devam": "No open work items were reported at the customer for this period.",
        "kritik": "No critical issues requiring action were reported for this period.",
        "bilgi": "No additional information is provided for this period.",
        "oneri": "No additional suggestions are provided for this period.",
    },
}

# Formda hazir gelen, personelin uzerine yazabilecegi baslangic metinleri (uretim RAPOR_BASLANGIC_METINLERI).
BASLANGIC_METINLERI = {
    "tr": {
        "bilgi": (
            "Erişim & Arıza Takibi: İlgili dönemde iletilen lokasyon erişim kesintileri ve "
            "arıza kayıtları incelenmiş olup güncel durum çözümleriyle birlikte kayıt altına alınmıştır.\n\n"
            "SLA & Servis Performansı: Aylık arıza detayları, müdahale/çözüm süreleri ve SLA analiz "
            "özetiniz aşağıda bilgilerinize sunulmuş olup kapsamlı rapor ekte yer almaktadır.\n\n"
            "Trafik & Utilizasyon Analizi: Müşterimize ait kritik devrelerin aylık veri akışı ve bant "
            "genişliği kullanım grafikleri değerlendirilerek rapora işlenmiştir."
        ),
        "oneri": (
            "SD-WAN Dönüşüm Fırsatı: Mevcut MPLS altyapınız SD-WAN mimarisine tam uyumludur. "
            "Şifreli trafik, merkezi yönetim ve optimize edilmiş ağ performansı ile verimliliğinizi "
            "artırmak için Kurumsal Satış Yöneticiniz ile SD-WAN geçiş fırsatlarını "
            "değerlendirmenizi öneririz.\n\n"
            "İş Sürekliliği & SLA Testi: Operasyonel riskleri en aza indirmek için 6 aylık periyodik "
            "yedeklilik testlerinizin planlanması için Müşteri Teknik Yöneticiniz (TAC) ile "
            "iletişime geçebilirsiniz."
        ),
    },
    "en": {
        "bilgi": (
            "Access & Fault Tracking: Location access outages and fault records reported during the "
            "period have been reviewed and recorded together with their current resolution status.\n\n"
            "SLA & Service Performance: Your monthly fault details, response/resolution times and SLA "
            "analysis summary are presented below, and the full report is attached to this document.\n\n"
            "Traffic & Utilisation Analysis: Monthly data flow and bandwidth utilisation charts of your "
            "critical circuits have been evaluated and included in the report."
        ),
        "oneri": (
            "SD-WAN Transformation Opportunity: Your current MPLS infrastructure is fully compatible "
            "with the SD-WAN architecture. To increase efficiency through encrypted traffic, "
            "centralised management and optimised network performance, we recommend evaluating "
            "SD-WAN migration opportunities with your Corporate Sales Manager.\n\n"
            "Business Continuity & SLA Test: To minimise operational risks, you may contact your "
            "Technical Account Contact (TAC) to plan your six-monthly periodic redundancy tests."
        ),
    },
}

MAIL_GOVDESI = {
    "tr": (
        "Sayın Müşterimiz,\n\n"
        "Kurumsal Hizmet Yönetimi (TAM) prensiplerimiz doğrultusunda, altyapınızın sürekliliğini ve "
        "hizmet kalitemizi düzenli olarak takip ediyor; operasyonel şeffaflık ilkelerimiz gereği "
        "sonuçlarımızı sizlerle paylaşıyoruz.\n\n"
        "Şirketinize sunulan servislerin {donem} dönemine ait operasyonel değerlendirme ve SLA "
        "performans raporu ekte bilginize sunulmuştur.\n\n"
        "Rapor içeriğiyle ilgili ek bilgi talepleriniz veya geliştirilmesini istediğiniz hususlar "
        "olması hâlinde tarafımla iletişime geçebilirsiniz.\n\n"
        "Saygılarımızla,"
    ),
    "en": (
        "Dear Customer,\n\n"
        "In line with our Technical Account Management (TAM) principles, we continuously monitor the "
        "continuity of your infrastructure and the quality of our services, and we share the results "
        "with you as part of our operational transparency commitment.\n\n"
        "The operational assessment and SLA performance report of the services provided to your "
        "company for the {donem} period is attached for your information.\n\n"
        "Should you need further details about the report or wish to suggest improvements, please "
        "feel free to contact me.\n\n"
        "Kind regards,"
    ),
}


def mail_konusu(musteri_adi: str, ay: int, yil: int, dil: str = "tr") -> str:
    """2026-11-24 kullanici: 'Musteri Unvani - TAM Aylik Rapor - Ay Yil' sirasi."""
    baslik = "TAM Monthly Report" if dil == "en" else "TAM Aylık Rapor"
    return f"{musteri_adi} - {baslik} - {ay_adi(ay, dil)} {yil}"


ESKI_UNVANLAR = ("Teknik Müşteri Yöneticisi (TAM)", "Technical Account Manager (TAM)")  # 2026-11-24 oncesi hazir imza satiri


def eski_hazir_metni_guncelle(alanlar: dict, musteri_adi: str, ay: int, yil: int) -> dict:
    """Gonderilmemis taslakta 2026-11-24 oncesi HAZIR konu ('TAM Aylik Rapor - Ay Yil | Musteri') ve imza unvan satiri yenisine
    cevrilir; personelin elle yazdigi metne dokunulmaz."""
    sonuc = dict(alanlar)
    for dil in DILLER:
        baslik = "TAM Monthly Report" if dil == "en" else "TAM Aylık Rapor"
        if sonuc.get("konu") == f"{baslik} - {ay_adi(ay, dil)} {yil} | {musteri_adi}":
            sonuc["konu"] = mail_konusu(musteri_adi, ay, yil, dil)
    if isinstance(sonuc.get("imza"), str):
        sonuc["imza"] = "\n".join("Technical Account Manager" if s.strip() in ESKI_UNVANLAR else s for s in sonuc["imza"].split("\n"))
    return sonuc


def mail_govdesi(ay: int, yil: int, dil: str = "tr") -> str:
    return MAIL_GOVDESI.get(dil, MAIL_GOVDESI["tr"]).format(donem=f"{ay_adi(ay, dil)} {yil}")


def imza(personel_adi: str, dil: str = "tr") -> str:
    if not personel_adi:
        return ""
    if dil == "en":
        return f"{personel_adi}\nTechnical Account Manager\nTurkcell Corporate Customer Management"
    return f"{personel_adi}\nTechnical Account Manager\nTurkcell Kurumsal Müşteri Yönetimi"
