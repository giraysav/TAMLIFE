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

# Yalnız admin. (id, etiket, aciklama, ikon)
ADMIN_ITEMS: tuple[tuple[str, str, str, str], ...] = (
    ("integrations", "Kurum Bağlantıları", "Kurumsal bağımlılıkların yapılandırma durumu", "network"),
    ("veri", "Veri Yönlendirici", "Veri kaynakları, aktarım kuralları ve skorlar", "database"),
    ("admin", "Sistem Yönetimi", "Kullanıcılar ve sistem yönetimi", "settings"),
)


def navigation_for(user: Principal, izinli: frozenset[str] | None = None) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for module in MODULES:
        if not module.in_nav or module.key not in PRESENTATION:
            continue
        if not can_open(user, module, get, izinli):
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
        rows.extend(
            {"id": key, "label": label, "description": text, "group": "admin", "icon": icon, "ready": True, "children": []}
            for key, label, text, icon in ADMIN_ITEMS
        )
    return rows
