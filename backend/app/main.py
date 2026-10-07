"""FastAPI uygulamasi: ara katmanlar, hata isleyiciler, router'lar ve (varsa) derlenmis arayuz. Is kurali burada degil, ilgili paketlerde."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.audit import audit_log
from app.config import get_settings
from app.gelir.api import router as gelir_router
from app.katalog_api import router as katalog_router
from app.musteri.api import router as musteri_router
from app.onedesk.api import router as onedesk_router
from app.ortak import UygulamaHatasi, ok
from app.oturum_api import router as oturum_router
from app.rol_api import router as rol_router
from app.security import install as install_security
from app.skor.api import router as skor_router
from app.takvim.api import router as takvim_router
from app.tampon.router import router as tampon_router
from app.yonetim import dosya_gunlugu
from app.yonetim.gunlukler import kalici_yaz
from app.yonetim.router import router as yonetim_router
from app.yonetim.yakalayici import genel_istisna


async def uygulama_hatasi(_: Request, exc: UygulamaHatasi) -> JSONResponse:
    """Servis katmaninin bilinen hatalari (kod = HTTP durumu); RaporHata gibi ek alan tasiyanlar govdeye eklenir."""
    return JSONResponse({"detail": exc.mesaj, **getattr(exc, "ek", {})}, status_code=exc.kod)


def create_app() -> FastAPI:
    settings = get_settings()
    dev = settings.env in {"dev", "test"}
    app = FastAPI(
        title="TAMLIFE",
        version="3.5.0",
        docs_url="/docs" if dev else None,
        redoc_url=None,
        openapi_url="/openapi.json" if dev else None,
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts_list)
    install_security(app)
    app.add_exception_handler(UygulamaHatasi, uygulama_hatasi)  # bilinen is hatasi: kod + mesaj
    app.add_exception_handler(Exception, genel_istisna)  # beklenmeyen hata: kod + kayit no, ham metin yok
    audit_log.sink = kalici_yaz  # denetim olaylari audit_event'e KALICI yazilir
    if settings.env != "test":
        dosya_gunlugu.kur()
    for router in (oturum_router, katalog_router, rol_router, musteri_router, skor_router, onedesk_router, gelir_router, takvim_router, yonetim_router, tampon_router):
        app.include_router(router)

    @app.get("/api/v1/health")
    def health() -> dict:
        ayar = get_settings()
        return ok(
            {
                "service": "tamlife",
                "database": ayar.database_url.split(":", 1)[0].split("+", 1)[0],
                "database_configured": bool(ayar.database_url),
            }
        )

    _arayuz_bagla(app, settings.static_dir)
    return app


def _arayuz_bagla(app: FastAPI, dizin: str) -> None:
    """Derlenmis arayuzu (ekran-react/dist) kok yolda sunar. Dizin yoksa yalniz API calisir."""
    kok = Path(dizin).resolve() if dizin else None
    if kok is None or not (kok / "index.html").is_file():
        return
    if (kok / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=kok / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    def arayuz_index() -> FileResponse:
        return FileResponse(kok / "index.html")

    @app.get("/{dosya}", include_in_schema=False)
    def arayuz_dosya(dosya: str) -> FileResponse:
        yol = (kok / dosya).resolve()
        if yol.parent != kok or not yol.is_file():
            raise HTTPException(status_code=404, detail="Yok")
        return FileResponse(yol)


app = create_app()
