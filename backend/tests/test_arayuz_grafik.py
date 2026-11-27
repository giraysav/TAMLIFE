# Copyright (c) 2026 Giray Sav. Tum haklari saklidir. TAMLIFE paneli - izinsiz kopyalanamaz, dagitilamaz.
"""Aylik rapor devre grafigi (derlenmis ekran-react/dist/rapor-trafik.js) Node'da gercek bicimli veriyle uretilir.
2026-11-27: renk satirina yorum eklenince gecikme/jitter/kayip/erisim renkleri tanimsiz kaldi, grafik coktu ve rapora hic gorsel
eklenmedi; bu test o sinifi yakalar. Node yoksa atlanir."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[2]
BETIK = KOK / "ekran-react" / "dist" / "rapor-trafik.js"
DENEME = Path(__file__).parent / "arayuz" / "grafik_dene.js"


def _veri() -> dict:
    t0 = 1_793_000_000_000
    kalite = [[t0 + i * 3_600_000, 1.0 if i != 5 else 0.0, 0.005, 0.0004, 0.0, 1] for i in range(48)]
    trafik = [[t0 + i * 7_200_000, 120e6 + i * 1e6, 40e6] for i in range(24)]
    return {
        "yil": 2026, "ay": 11, "aralik": {"bas_ms": t0, "bit_ms": t0 + 48 * 3_600_000},
        "ayar": {"metrikler": ["erisim", "trafik", "kayip", "jitter", "gecikme"], "aralik": None},
        "devreler": [{
            "id": 1, "ci": "ci-ornek", "baslik": "Merkez hat", "durum": "hazir", "cekildi": "2026-11-27T10:00:00", "exchours": "",
            "ozet": {"erisilebilirlik": 0.98, "gecikme": 0.005, "jitter": 0.0004, "kayip": 0.0}, "noktalar": kalite,
            "trafik": {"adim": 7200, "noktalar": trafik, "giris": {"son": 143e6, "en_yuksek": 143e6, "ort": 131.5e6},
                       "cikis": {"son": 40e6, "en_yuksek": 40e6, "ort": 40e6}},
        }],
    }  # fmt: skip


@pytest.mark.skipif(shutil.which("node") is None, reason="node yok")
def test_rapor_grafigi_tum_paneller_ve_gorsel_uretilir(tmp_path):
    veri = tmp_path / "veri.json"
    veri.write_text(json.dumps(_veri()), encoding="utf-8")
    r = subprocess.run(["node", str(DENEME), str(BETIK), str(veri)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-1500:]
    sonuc = json.loads(r.stdout)
    assert sonuc["hata"] == ""
    assert sonuc["paneller"] == ["Availability", "Trafik", "Delay & Jitter", "Packet Loss"]
    assert sonuc["seri"] == 6 and sonuc["gorsel"] == 1  # rapora bir gorsel eklenir
