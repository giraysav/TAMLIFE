"""Calisma alani menusu. Yetki kurali authz.can_open; etiketlerin kaynagi catalog."""

from __future__ import annotations

from app.authz import can_open, is_admin
from app.catalog import MODULES, get
from app.session import Principal

# Sunum bilgisi: (grup, ikon, aciklama). Uretim application/navigation.py ile ayni.
PRESENTATION: dict[str, tuple[str, str, str]] = {
    "musteri": ("work", "customers", "Portföy, iştirakler ve müşteri kayıtları"),
    "takvim": ("work", "calendar", "İzin ve kişisel takvim işlemleri"),
    "takvim_ozet": ("insights", "calendar", "Yetkiniz kapsamındaki takvim özeti"),
    "onedesk": ("work", "inbox", "Alarm, talep ve şikayet takibi"),
    "utilizasyon": ("admin", "chart", "Kurumsal skor ve kriter yönetimi"),
    "roller": ("admin", "shield", "Kullanıcılar, roller ve erişim yetkileri"),
    "talep": ("work", "message", "Geliştirme talepleri ve değişiklikler"),
    "rapor": ("insights", "file", "Aylık raporlar ve gönderim durumu"),
    "proje": ("insights", "layers", "Projeler ve müşteri bazlı çalışmalar"),
    "tamsms": ("work", "message", "ICT SMS gelir ve üretim kayıtları"),
    "tamapn": ("work", "network", "APN gelir ve kurulum kayıtları"),
    "gelir_uretim": ("insights", "chart", "Gelir faydası sağlanan işler"),
    "sunum": ("insights", "presentation", "Çeyrek bazlı sunumları hazırlayın"),
    "radar": ("insights", "radar", "Müşteri fırsatları ve takip kayıtları"),
    "baglantili": ("work", "link", "Kurum içi bağlantılı araçlar"),
}

# Yalnız admin: TEK giriş, altı bölüm (kimlik "yonetim/<bolum>"). Eski admin / integrations / veri / roller girişleri buraya indi.
YONETIM_BOLUMLERI: tuple[tuple[str, str, str], ...] = (
    ("durum", "Genel Durum", "Sağlık kontrolleri ve göstergeler"),
    ("tampon", "Veri Girişi", "Dış kaynak verisi: tampon, analiz, dağıtım"),
    ("veritabani", "Veritabanı", "Sürüm, tablolar, bütünlük ve yedek"),
    ("roller", "Roller", "Rol görünümleri ve giriş sayfaları"),
    ("arizalar", "Arızalar", "Hata kayıtları ve çözüm adımları"),
    ("gunlukler", "Günlükler", "Denetim olayları, oturumlar, uygulama günlüğü"),
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
        group, icon, description = PRESENTATION[module.key]
        if group == "admin" and not is_admin(user):
            group = "work"  # admin disi role verilen yonetim modulu Benim Yerim altinda gorunur
        rows.append(
            {
                "id": module.key,
                "label": module.title,
                "description": description,
                "group": group,
                "icon": icon,
                "ready": module.ready,
                "children": [
                    {
                        "id": f"{module.key}/{c.key}",
                        "label": c.title,
                        "description": c.description,
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
                "description": "Veritabanı, roller, arızalar, günlükler ve veri girişi",
                "group": "admin",
                "icon": "settings",
                "ready": True,
                "children": [
                    {"id": f"yonetim/{key}", "label": label, "description": text, "ready": True}
                    for key, label, text in YONETIM_BOLUMLERI
                ],
            }
        )
    return rows
