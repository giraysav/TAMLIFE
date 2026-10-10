# HTTPS sertifikası (Dev)

Bu klasörde yalnız **herkese açık** sertifika parçaları durur. Özel anahtar (`.pfx`, `.key`, `.p12`) buraya konmaz ve hiçbir betikle taşınmaz.

| Dosya | Nedir | Kullanım |
|---|---|---|
| `tamlife_sunucu.cer` | Sunucu sertifikası (tek blok) | `certreq -accept` |
| `tamlife.crt` | Sunucu + Turkcell Enterprise CA 4 + Turkcell Root CA 2 (bu sırayla) | Zincir doğrulama |
| `kurumsal_ca.pem` | **Eksik — offline sunucudan getirilecek.** Ara + kök CA | `backend\.env` → `AD_CA_CERT_FILE` (LDAPS doğrulaması) |
| `tamlife.csr` | Mevcut sertifikanın isteği | Yenilemede konu/SAN referansı |
| `yeni_istek.inf` | Yenileme şablonu (`Exportable = TRUE`) | Bir sonraki sertifikada anahtar PFX'e çıkabilsin diye |

- Konu: `CN=tamlife.turkcell.entp.tgc, O=Turkcell, L=Istanbul, C=TR`
- SAN: `tamlife.turkcell.entp.tgc`, `tamlife`, `172.28.100.7`
- Veren: Turkcell Enterprise CA 4 → Turkcell Root CA 2
- Bitiş: **2028-09-20**

## Özel anahtar neden taşınmıyor

Anahtar offline sunucuda `certreq -new` ile **dışa aktarılamaz** üretildi. Windows deposunda (`Cert:\LocalMachine\My`) kilitli duruyor ve Python onu kullanamıyor; Windows'un `http.sys` katmanı kullanabiliyor. Bu yüzden canlı panelde TLS'i Windows sonlandırıyor:

```
istemci --TLS--> http.sys:443 --> tls_vekili.ps1 --> 127.0.0.1:<uygulama portu>
```

Dev offline sunucuda aynı yöntemle çalışacak, hedef port `127.0.0.1:8117` olacak (canlıya geçiş adımı). Eski panel 443'ü ve iç 8443 portunu kullandığı sürece Dev **ayrı bir port** almalı (örn. 9443, kendi `netsh http add sslcert ipport=0.0.0.0:9443 certhash=<parmak izi> ...` kaydıyla). Lokal PC'de HTTPS gerekmiyor.

## Yenileme

`yeni_istek.inf` ile yenileyin: `Exportable = TRUE` sayesinde yeni anahtar PFX'e çıkabilir ve Windows vekiline gerek kalmaz. Konu ve SAN listesi aynı kalmalı; `172.28.100.7` düşerse IP ile bağlananlar sertifika hatası alır.
