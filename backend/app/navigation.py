"""Calisma alani menusu. Yetki kurali authz.can_open; etiketlerin kaynagi catalog."""

from __future__ import annotations

from app.authz import can_open, is_admin
from app.catalog import MODULES, get
from app.session import Principal

# Sunum bilgisi: (grup, ikon, aciklama, aciklama_en). Uretim application/navigation.py ile ayni.
PRESENTATION: dict[str, tuple[str, str, str, str]] = {
    "musteri": ("work", "customers", "Portföy, iştirakler ve müşteri kayıtları", "Portfolio, affiliates and customer records"),
    "takvim": ("work", "calendar", "İzin ve kişisel takvim işlemleri", "Leave and personal calendar"),
    "takvim_ozet": ("insights", "calendar", "Yetkiniz kapsamındaki takvim özeti", "Calendar summary within your permissions"),
    "onedesk": ("work", "inbox", "Alarm, talep ve şikayet takibi", "Alarm, request and complaint tracking"),
    "utilizasyon": ("admin", "chart", "Kurumsal skor ve kriter yönetimi", "Corporate score and criteria management"),
    "roller": ("admin", "shield", "Kullanıcılar, roller ve erişim yetkileri", "Users, roles and access permissions"),
    "talep": ("work", "message", "Geliştirme talepleri ve değişiklikler", "Development requests and changes"),
    "rapor": ("insights", "file", "Aylık raporlar ve gönderim durumu", "Monthly reports and delivery status"),
    "proje": ("insights", "layers", "Projeler ve müşteri bazlı çalışmalar", "Projects and customer-based work"),
    "tamsms": ("work", "message", "ICT SMS gelir ve üretim kayıtları", "ICT SMS revenue and production records"),
    "tamapn": ("work", "network", "APN gelir ve kurulum kayıtları", "APN revenue and installation records"),
    "gelir_uretim": ("insights", "chart", "Gelir faydası sağlanan işler", "Work that delivered revenue benefit"),
    "sunum": ("insights", "presentation", "Çeyrek bazlı sunumları hazırlayın", "Prepare quarterly presentations"),
    "radar": ("insights", "radar", "Müşteri fırsatları ve takip kayıtları", "Customer opportunities and follow-ups"),
    "baglantili": ("work", "link", "Kurum içi bağlantılı araçlar", "Internal connected tools"),
}

# Yalnız admin: TEK giriş, sekiz bölüm (kimlik "yonetim/<bolum>"). Eski admin / integrations / veri / roller girişleri buraya indi.
# Katalogdaki "utilizasyon" modülü (yalnız admin) arayüzde yonetim/utilizasyon bölümüne açılır.
YONETIM_BOLUMLERI: tuple[tuple[str, str, str, str, str], ...] = (
    ("durum", "Genel Durum", "Sağlık kontrolleri ve göstergeler", "Overview", "Health checks and indicators"),
    ("utilizasyon", "TAM Utilizasyon", "Final skor kriterleri, toplu atama, skor ağacı", "TAM Utilization", "Final score criteria, bulk assignment, score tree"),
    ("tampon", "Veri Girişi", "Dış kaynak verisi: tampon, analiz, dağıtım", "Data intake", "External data: buffer, analysis, distribution"),
    ("kurum", "Kurum Bağlantıları", "AD/LDAPS durumu, ayarları ve erişim testi", "Corporate connections", "AD/LDAPS status, settings and reachability test"),
    ("veritabani", "Veritabanı", "Sürüm, tablolar, bütünlük ve yedek", "Database", "Version, tables, integrity and backup"),
    ("roller", "Roller", "Rol görünümleri ve giriş sayfaları", "Roles", "Role views and landing pages"),
    ("arizalar", "Arızalar", "Hata kayıtları ve çözüm adımları", "Faults", "Fault records and resolution steps"),
    ("gunlukler", "Günlükler", "Denetim olayları, oturumlar, uygulama günlüğü", "Logs", "Audit events, sessions, application log"),
)
# Admin için ayrı menü öğesi olmayan, Yönetim altına katlanan modüller (admin olmayana rol görünümüyle aynen görünür).
YONETIME_KATLANAN = frozenset({"roller"})


def navigation_for(user: Principal, izinli: frozenset[str] | None = None) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for module in MODULES:
        if not module.in_nav or module.key not in PRESENTATION:
            continue
        if not can_open(user, module, get, izinli):
            continue
        if is_admin(user) and module.key in YONETIME_KATLANAN:
            continue
        group, icon, description, description_en = PRESENTATION[module.key]
        rows.append(
            {
                "id": module.key,
                "label": module.title,
                "label_en": module.title_en,
                "description": description,
                "description_en": description_en,
                "group": group,
                "icon": icon,
                "ready": module.ready,
                "children": [
                    {
                        "id": f"{module.key}/{c.key}",
                        "label": c.title,
                        "label_en": c.title_en,
                        "description": c.description,
                        "description_en": c.description_en,
                        "ready": c.ready,
                    }
                    for c in module.children
                    if izinli is None or is_admin(user) or f"{module.key}/{c.key}" in izinli
                ],
            }
        )
    if is_admin(user):
        rows.append(
            {
                "id": "yonetim",
                "label": "Yönetim",
                "label_en": "Administration",
                "description": "Veritabanı, roller, arızalar, günlükler ve veri girişi",
                "description_en": "Database, roles, faults, logs and data intake",
                "group": "admin",
                "icon": "settings",
                "ready": True,
                "children": [
                    {"id": f"yonetim/{key}", "label": label, "label_en": label_en, "description": text, "description_en": text_en, "ready": True}
                    for key, label, text, label_en, text_en in YONETIM_BOLUMLERI
                ],
            }
        )
    return rows
