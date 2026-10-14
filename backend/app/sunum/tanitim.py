"""TAMLIFE tanitim sayfasinin verisi (Ceyrek Bazli Sunum 'tanitim' kaynagi).

Sayilar OLCULUR, elle yazilmaz: satir ve dil dagilimi depo agacindan, modul / API ucu / tablo / revizyon kod yapisindan,
canli sayilar veritabanindan. Metinler (amac, fayda, dil gorevi) burada sabittir ve yalniz panelin gercekte yaptigini soyler.
Depo agaci yoksa (yalniz backend kopyalanmissa) 'kod' None olur; arayuz o bolumu gostermez.

Satir sayimi kurali: yalniz dolu (bos olmayan) satirlar; yalniz yazdigimiz kod (backend, ekran-react, kurulum klasorleri).
Hazir arayuz bilesenleri (components/ui), uc taraf kitapliklari (public), derleme ciktilari ve calisma verisi sayilmaz.
"""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.catalog import MODULES
from app.kullanicilar import personel
from app.models import Base, Customer, KullaniciBase, OnedeskRecord, ProjectItem, Report
from app.ortak import iso, simdi

KOK = Path(__file__).resolve().parents[3]  # depo koku: backend/app/sunum/tanitim.py
TEST_SAYILARI = Path(__file__).with_name("test_sayilari.json")  # {"olcum", "backend", "arayuz"}: son teslimdeki gercek test kosusu
KOKLER = ("backend", "ekran-react", "kurulum")
DISLANAN = frozenset({"node_modules", "dist", "public", "var", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".vite", ".git", "coverage", "playwright-report", "test-results"})
HAZIR_BILESEN = ("ekran-react", "src", "components", "ui")  # shadcn/ui: kopyalanan hazir bilesenler
DIL_UZANTILARI = {".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript", ".ps1": "PowerShell", ".css": "CSS"}
UC_DESENI = re.compile(r"^\s*@(?:router|app)\.(?:get|post|put|patch|delete)\(")

# dil -> (ne yapar TR, EN)
DIL_GOREVI = {
    "Python": ("Sunucu: API, iş kuralları, veritabanı, raporlama, kimlik doğrulama, ReportDB okuma", "Server: API, business rules, database, reporting, authentication, ReportDB reads"),
    "TypeScript": ("Arayüz: sayfalar, tablolar, grafikler, Türkçe / İngilizce dil desteği", "Interface: pages, tables, charts, Turkish / English language support"),
    "PowerShell": ("Kurulum ve işletim: başlatma görevleri, TLS vekili, taşıma betikleri", "Setup and operations: startup tasks, TLS proxy, transfer scripts"),
    "CSS": ("Görünüm: Turkcell renk ve yazı teması", "Look: Turkcell colour and type theme"),
}

AMAC = (
    "Müşteri, rapor, alarm, proje, gelir ve takvim verisini tek ekranda toplamak; dağınık Excel ve e-posta takibini bırakıp ekibi ve yönetimi aynı güncel veriyle buluşturmak.",
    "Bring customer, report, alarm, project, revenue and calendar data into one screen, replace scattered Excel and e-mail tracking, and give the team and management the same up-to-date data.",
)

# (baslik TR, baslik EN, aciklama TR, aciklama EN)
FAYDA = (
    ("Tek kaynak", "One source", "Ekip ve yönetim aynı veriye aynı ekrandan bakar.", "The team and management look at the same data on the same screen."),
    ("Hazır sunum", "Ready presentation", "Çeyrek özeti veriden çıkar; çeyrek bitince dondurulur.", "The quarterly summary comes from the data; it is frozen when the quarter ends."),
    ("İzlenebilirlik", "Traceability", "Rol bazlı erişim ve denetim kaydı: kim neyi değiştirdi bellidir.", "Role-based access and an audit log: who changed what is on record."),
    ("Kurum içi", "In-house", "Kurum sunucusunda çalışır; Active Directory ile girilir.", "Runs on the company server; sign-in is with Active Directory."),
)

YIGIN = ("Python", "FastAPI", "SQLAlchemy", "Alembic", "SQLite", "TypeScript", "React", "Vite", "Tailwind CSS")


def _test_dosyasi(parcalar: tuple[str, ...], ad: str) -> bool:
    return bool({"tests", "e2e"} & set(parcalar)) or ad.startswith("test_") or ".test." in ad or ".spec." in ad


def kod_olc(kok: Path = KOK) -> dict | None:
    """Dile gore dolu satir / dosya / test satiri. Hic kod dosyasi yoksa None."""
    sayim: dict[str, list[int]] = {}  # dil -> [satir, dosya, test satiri]
    for ust in KOKLER:
        for yol, altlar, dosyalar in os.walk(kok / ust):
            goreli = Path(yol).relative_to(kok).parts
            altlar[:] = [a for a in altlar if a not in DISLANAN and (*goreli, a) != HAZIR_BILESEN]
            for ad in dosyalar:
                dil = DIL_UZANTILARI.get(os.path.splitext(ad)[1].lower())
                if dil is None:
                    continue
                try:
                    with open(os.path.join(yol, ad), encoding="utf-8", errors="replace") as f:
                        dolu = sum(1 for satir in f if satir.strip())
                except OSError:
                    continue
                s = sayim.setdefault(dil, [0, 0, 0])
                s[0] += dolu
                s[1] += 1
                if _test_dosyasi(goreli, ad):
                    s[2] += dolu
    toplam = sum(s[0] for s in sayim.values())
    if toplam == 0:
        return None
    diller = [
        {"dil": d, "satir": s[0], "dosya": s[1], "pay": round(100 * s[0] / toplam, 1), "rol": DIL_GOREVI.get(d, ("", ""))[0], "rol_en": DIL_GOREVI.get(d, ("", ""))[1]}
        for d, s in sorted(sayim.items(), key=lambda kv: -kv[1][0])
    ]
    return {"satir": toplam, "dosya": sum(s[1] for s in sayim.values()), "test_satir": sum(s[2] for s in sayim.values()), "diller": diller}


def uc_say(kok: Path = KOK) -> int:
    """API ucu: @router/@app.get|post|put|patch|delete bildirimleri (arayuz dosyasi sunan include_in_schema=False yollari haric)."""
    sayi = 0
    for yol in (kok / "backend" / "app").rglob("*.py"):
        try:
            satirlar = yol.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        sayi += sum(1 for s in satirlar if UC_DESENI.match(s) and "include_in_schema=False" not in s)
    return sayi


def revizyon_say(kok: Path = KOK) -> int:
    """Alembic sema revizyonu (0001_... gibi numarali dosyalar)."""
    return sum(1 for _ in (kok / "backend" / "alembic" / "versions").glob("[0-9]*.py"))


def otomatik_test_say() -> int | None:
    """Son teslimdeki test kosusunun toplami (backend + arayuz); dosya yoksa None."""
    try:
        v = json.loads(TEST_SAYILARI.read_text(encoding="utf-8"))
        return int(v["backend"]) + int(v["arayuz"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def moduller() -> list[dict]:
    """Panelin hazir modulleri (katalogdaki ad; yeni modul hazir olunca kendiliginden listeye girer)."""
    return [{"ad": m.title, "ad_en": m.title_en or m.title} for m in MODULES if m.ready]


_kilit = threading.Lock()
_onbellek: dict = {}


def depo_olcumu() -> dict:
    """Depo olcumu gunde bir kez yapilir (dosya agaci taranir); ayni gun icinde bellekten verilir."""
    gun = simdi().date()
    with _kilit:
        if _onbellek.get("gun") != gun:
            _onbellek.update(gun=gun, veri={"olcum": iso(simdi()), "kod": kod_olc(), "uc": uc_say(), "revizyon": revizyon_say(), "test": otomatik_test_say()})
        return _onbellek["veri"]


def _canli(db: Session) -> list[dict]:
    def say(sorgu) -> int:
        return db.scalar(sorgu) or 0

    cati = say(select(func.count()).select_from(Customer).where(Customer.parent_id.is_(None)))
    istirak = say(select(func.count()).select_from(Customer).where(Customer.parent_id.is_not(None)))
    liste = [
        {"ad": "Çatı müşteri", "ad_en": "Parent customers", "deger": cati},
        {"ad": "İştirak", "ad_en": "Affiliates", "deger": istirak},
        {"ad": "TAM", "ad_en": "TAMs", "deger": len(personel(db))},
        {"ad": "Aylık rapor kaydı", "ad_en": "Monthly report records", "deger": say(select(func.count()).select_from(Report))},
        {"ad": "Onedesk kaydı", "ad_en": "Onedesk records", "deger": say(select(func.count()).select_from(OnedeskRecord))},
        {"ad": "Proje kalemi", "ad_en": "Project items", "deger": say(select(func.count()).select_from(ProjectItem))},
    ]
    return liste if any(x["deger"] for x in liste) else []  # bos panelde tum sifirlari gostermek anlamsiz


def ozet(db: Session) -> dict:
    """Tanitim sayfasinin icerigi. servis._tanitim 'stil' ve genel 'kpi' alanlarini ekler."""
    d = depo_olcumu()
    liste = moduller()
    sayilar = [{"kod": "modul", "ad": "Modül", "ad_en": "Modules", "deger": len(liste)}]
    if d["kod"]:
        sayilar.insert(0, {"kod": "dosya", "ad": "Dosya", "ad_en": "Files", "deger": d["kod"]["dosya"]})
    sayilar += [
        {"kod": "uc", "ad": "API ucu", "ad_en": "API endpoints", "deger": d["uc"]},
        {"kod": "tablo", "ad": "Veri tablosu", "ad_en": "Data tables", "deger": len(Base.metadata.tables) + len(KullaniciBase.metadata.tables)},
    ]
    if d["test"] is not None:
        sayilar.append({"kod": "test", "ad": "Otomatik test", "ad_en": "Automated tests", "deger": d["test"]})
    sayilar.append({"kod": "goc", "ad": "Şema göçü", "ad_en": "Schema migrations", "deger": d["revizyon"]})
    return {
        "olcum": d["olcum"],
        "amac": {"tr": AMAC[0], "en": AMAC[1]},
        "kapsam": liste,
        "fayda": [{"ad": a, "ad_en": ae, "aciklama": b, "aciklama_en": be} for a, ae, b, be in FAYDA],
        "kod": d["kod"],
        "sayilar": sayilar,
        "canli": _canli(db),
        "yigin": list(YIGIN),
    }
