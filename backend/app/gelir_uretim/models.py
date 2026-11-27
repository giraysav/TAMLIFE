# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Gelir Faydasi Saglanan Isler tablolari. Base ortak (app.models); alembic ve create_all hepsini gorur."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class RevenueBenefit(Base):
    """Fayda saglanan is: planli is (kind=proje) ya da TAM inisiyatifi (kind=inisiyatif).

    Tutarlar kullanicinin Excel'inden gelen serbest metnin guvenli ayristirilmis halidir; sayiya cevrilemeyen metin *_note alanlarinda durur
    (tahmin yok). Kur cevirisi yoktur: tutar kendi para biriminde ve doneminde saklanir. end_date bos = devam ediyor.
    """

    __tablename__ = "revenue_benefit"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), default="proje")  # proje | inisiyatif
    benefit_type: Mapped[str] = mapped_column(String(20), default="gelir")  # gelir | tasarruf | verimlilik
    title: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), default="devam")  # baslamadi | devam | tamamlandi | iptal
    status_note: Mapped[str] = mapped_column(Text, default="")  # "Guncel durum" metni (en fazla 4000)
    description: Mapped[str] = mapped_column(Text, default="")  # "Detayli aciklama" (en fazla 8000)
    customers: Mapped[str] = mapped_column(String(500), default="")  # etkilenen musteri(ler), serbest metin
    revenue_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    revenue_currency: Mapped[str] = mapped_column(String(3), default="TRY")  # TRY | USD | EUR
    revenue_period: Mapped[str] = mapped_column(String(10), default="ay")  # ay | yil | tek_sefer
    revenue_note: Mapped[str] = mapped_column(String(500), default="")  # sayiya cevrilemeyen ya da ek metin
    year_revenue: Mapped[float | None] = mapped_column(Float, nullable=True)  # "yil ici gelir" (TL)
    hours_per_month: Mapped[float | None] = mapped_column(Float, nullable=True)  # saat efor kazanci / ay
    hours_note: Mapped[str] = mapped_column(String(500), default="")
    hours_per_year: Mapped[float | None] = mapped_column(Float, nullable=True)  # saat efor kazanci / 12 ay
    roadmap: Mapped[str] = mapped_column(Text, default="", server_default="")  # "Yol Haritasi" (en fazla 4000)
    extra_note: Mapped[str] = mapped_column(Text, default="")  # "Ek aciklamalar" (en fazla 4000)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    other_people: Mapped[str] = mapped_column(String(300), default="")  # panelde hesabi olmayan kisiler
    created_by: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_by: Mapped[str] = mapped_column(String(200), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Onay akisi (2026-10-15): yeni giris 'bekliyor' olur, modul sahibi ya da admin 'onayli' / 'reddedildi' yapar.
    # Yalniz onayli isler toplamlara, rapora ve ceyrek sunumuna girer. Akistan onceki kayitlar ve Excel ice aktarma onaylidir.
    approval: Mapped[str] = mapped_column(String(20), default="onayli", server_default="onayli")  # bekliyor | onayli | reddedildi
    approval_note: Mapped[str] = mapped_column(Text, default="", server_default="")  # ret gerekcesi
    approved_by: Mapped[str] = mapped_column(String(200), default="", server_default="")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # girisi yapan hesap (bekleyen kaydi gorur/duzeltir)


class RevenueBenefitPerson(Base):
    """Isin TAM'lari: yalniz app.kullanicilar.personel kumesi baglanir. Is silinince kisi baglari da gider."""

    __tablename__ = "revenue_benefit_person"
    item_id: Mapped[int] = mapped_column(ForeignKey("revenue_benefit.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), primary_key=True)
