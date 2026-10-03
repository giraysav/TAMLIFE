"""FastAPI uygulama nesnesi. Is kurali yok."""

from __future__ import annotations

import importlib

from fastapi import FastAPI

# topoloji Q2 gecici varsayilani: ayri modul. Doc 10 yorum satiri 00 notunda.
_CORE_SETUPS = (
    "app.core.errors",
    "app.core.session",
    "app.core.authz",
    "app.core.audit",
    "app.modules.catalog",
)
_MODULE_ROUTES = (
    "musteri",
    "takvim",
    "onedesk",
    "utilizasyon",
    "roller",
    "talep",
    "ekip",
    "rapor",
    "proje",
    "tamsms",
    "tamapn",
    "gelir_uretim",
    "toptan",
    "sunum",
    "radar",
    "baglantili",
    "topoloji",
)


def create_app() -> FastAPI:
    app = FastAPI(title="TAMLIFE", version="3.5.0")
    _wire(app)

    @app.get("/api/v1/health")
    def health() -> dict:
        return {"status": "success", "data": {"service": "tamlife"}}

    return app


def _wire(app: FastAPI) -> None:
    for name in _CORE_SETUPS:
        module = importlib.import_module(name)
        setup = getattr(module, "setup", None)
        if setup is not None:
            setup(app)
    for key in _MODULE_ROUTES:
        module = importlib.import_module(f"app.modules.{key}.routes")
        router = getattr(module, "router", None)
        if router is not None:
            app.include_router(router, prefix="/api/v1")


app = create_app()
