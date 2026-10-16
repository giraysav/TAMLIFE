"""DPAPI gercek Windows API testi; yalniz sentetik kimlik ve tmp_path."""

import os
import subprocess

import pytest

from app.rapor import cacti_kimlik as k

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI testi")


def test_dpapi_gidis_donus():
    sifreli = k.koru("sentetik-Şifre-42!")
    assert "sentetik" not in sifreli
    assert k.coz(sifreli) == "sentetik-Şifre-42!"
    assert k.koru("sentetik-Şifre-42!") != sifreli
    for bozuk in ("not base64!", "", "YWJj", sifreli[:-8]):
        with pytest.raises(k.CactiKimlikHata):
            k.coz(bozuk)


def test_acik_metne_geri_donmez(monkeypatch):
    for ad in (k.KULLANICI_ANAHTARI, k.PAROLA_ANAHTARI):
        monkeypatch.delenv(ad, raising=False)
    monkeypatch.setenv("TAMLIFE_CACTI_USERNAME", "sentetik-user")
    monkeypatch.setenv("TAMLIFE_CACTI_PASSWORD", "sentetik-password")
    assert not k.hazir()
    with pytest.raises(k.CactiKimlikHata):
        k.oku()
    monkeypatch.setenv(k.KULLANICI_ANAHTARI, k.koru("sentetik-user"))
    monkeypatch.setenv(k.PAROLA_ANAHTARI, "broken")
    assert k.hazir()
    with pytest.raises(k.CactiKimlikHata):
        k.oku()


def test_kimlik_oku(monkeypatch):
    monkeypatch.setenv(k.KULLANICI_ANAHTARI, k.koru("sentetik-user"))
    monkeypatch.setenv(k.PAROLA_ANAHTARI, k.koru("sentetik-password"))
    assert k.oku() == ("sentetik-user", "sentetik-password")


def test_env_gecisi_diger_alanlari_korur(tmp_path):
    from araclar.cacti_kimlik_koru import _alanlar, env_gecir

    env = tmp_path / ".env"
    original = (
        b"# ayar\r\nOTHER=unchanged\r\nTAMLIFE_CACTI_USERNAME=sentetik-user\r\n"
        b'TAMLIFE_CACTI_PASSWORD="sentetik-password"\r\nTAMLIFE_CACTI_PASSWORD=sentetik-password\r\n'
    )
    env.write_bytes(original)
    env_gecir(env)
    content = env.read_bytes()
    assert b"sentetik-user" not in content and b"sentetik-password" not in content
    assert b"OTHER=unchanged\r\n" in content and b"# ayar\r\n" in content
    fields = _alanlar(content.decode())
    assert fields["TAMLIFE_CACTI_PASSWORD"] == fields["TAMLIFE_CACTI_USERNAME"] == ""
    assert k.coz(fields[k.KULLANICI_ANAHTARI]) == "sentetik-user"
    assert k.coz(fields[k.PAROLA_ANAHTARI]) == "sentetik-password"
    env_gecir(env)
    assert env.read_bytes() == content
    assert not list(tmp_path.glob("*.tmp"))


def test_dogrulama_basarisizsa_env_degismez(tmp_path):
    from araclar.cacti_kimlik_koru import kaydet

    env = tmp_path / ".env"
    env.write_text("OTHER=unchanged\n", encoding="utf-8")
    with pytest.raises(k.CactiKimlikHata):
        kaydet(env, {k.KULLANICI_ANAHTARI: k.koru("sentetik-user"), k.PAROLA_ANAHTARI: "broken"})
    assert env.read_text(encoding="utf-8") == "OTHER=unchanged\n"
    assert not list(tmp_path.glob("*.tmp"))


def test_dotnet_ile_uyum():
    # Same CurrentUser scope as the local PowerShell credential dialog.
    code = """
Add-Type -AssemblyName System.Security
$b = [Text.Encoding]::UTF8.GetBytes('synthetic-password')
[Convert]::ToBase64String([Security.Cryptography.ProtectedData]::Protect($b, $null, [Security.Cryptography.DataProtectionScope]::CurrentUser))
"""
    sifreli = subprocess.check_output(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", code], text=True, creationflags=subprocess.CREATE_NO_WINDOW
    ).strip()
    assert k.coz(sifreli) == "synthetic-password"
