# 07 ? API tasarimi

## Kararlar

- Dis sozlesme on eki `/api/v1`. Kaynak kirilinca `/api/v2`; eski onek bir surum yan yana kalir, ic ice yol versiyonu yok.
- Kaynak adlari cogul Ingilizce isim, modul klasoru Turkce anahtar degil yol parcasi: `/api/v1/customers` gibi. Modul anahtari query veya govdede `module` alanidir. v3.5 `modul.id` (`ozet`, `sms`) URL olmaz.
- Hata govdesi tek sekil. Basari `{"status":"success","data":...}`. Prod workspace ve `integrations` bu sekli kullanir. v3.5 de `status` + `message` kullanir.
- Liste: `page` (1 taban), `per_page` (1-100). Prod `GET /api/v1/customers` bu siniri kodda dogrular (`workspace_api_bp.py`). Arama `search` en fazla 150 karakter (ayni dosya).
- Yazma: JSON. Dosya ucu ayri, cok parcali, ust sinir. Prod `MAX_CONTENT_LENGTH` 50 MiB. v3.5 21 MiB. Hedef: JSON 1 MiB, dosya 20 MiB (tasarim; prod 50 ile birebir degil, acik soru).
- Kimlik cerez. `Authorization: Bearer` yok. OpenAPI semasi `cookieAuth`.

## Acik sorular

- v3.5 yollari `/api/...` (v1 degil) ve Flask. Bunlar kirilir. Eski yolu yonlendiren ince katman olsun mu?
- `package.json` `api:uret` port 8118 ve `/api/v1/openapi.json`. `src/lib/api.ts` port 8119. Ikisi de dize; dinleyen port dogrulanmadi.
- HTML rotalar (`/`, `/admin`, `/app`, `/classic`, `/login`) SPA'ya gecer. Sunucu yalniz API + statik dosya. Eski Jinja kaldirilmadan once `09` parite testi.
- `GET /api/matrix_config/<key>` sahibi dogrulanmadi (`04`).

## Hata modeli

```json
{"status":"error","code":"TL-VAL-01","message":"Gonderilen veri gecersiz","reference":"3f9a1c2b"}
```

`reference` ilk 8 hex; tam uuid yalniz log. Ham istisna yok. Kodlar prod `hatalar.py`: `TL-DB-01`, `TL-DB-02`, `TL-MOD-01`, `TL-VAL-01`, `TL-EXCEL-01`, `TL-SMTP-01`, `TL-ORA-01`, `TL-SRV-01`. HTTP: 400/422 dogrulama, 401 oturum, 403 yetki, 404 kayit, 409 catisma, 429 limit, 503 kaynak yok (sahte Oracle kapaliyken `TL-ORA-01`).

Sayfalama zarfi:

```json
{"status":"success","data":{"items":[],"page":1,"per_page":20,"total":0}}
```

Filtre yalniz acik query anahtarlari. Serbest SQL yok. Siralama `sort` alani semada izinli liste; liste disi 422.

## Versiyon

`/api/v1` zorunlu. Prod'da bu onek yalniz uc yolda vardir: `GET /api/v1/session`, `GET /api/v1/dashboard`, `GET /api/v1/customers`, arti `GET /api/v1/integrations` (onek blueprint'te degil, tam yol). Diger 100 dekorator `/api/v1` degildir veya HTML'dir. Toplam dekorator 104.

v3.5 (Flask, `/api/v1` yok) ? dosyada gorulen yollar:

| Yontem | Yol |
|---|---|
| GET | `/` |
| GET | `/api/saglik` |
| POST | `/api/giris` |
| POST | `/api/cikis` |
| GET | `/api/yetkiler` |
| GET | `/api/roller` |
| POST | `/api/roller` |
| GET | `/api/admin/kapi` |
| GET | `/api/admin/veri-agaci` |
| GET | `/api/admin/baglantilar` |
| POST | `/api/admin/baglantilar/<slot_id>` |
| POST | `/api/admin/baglantilar/<slot_id>/dene` |
| GET | `/api/admin/ice-aktar` |
| POST | `/api/admin/ice-aktar` |

Hedef karsilik (oneri, henuz kod yok): saglik `GET /api/v1/health`; giris `POST /api/v1/session`; cikis `DELETE /api/v1/session`; yetkiler `GET /api/v1/session`; roller `GET/PUT /api/v1/roles`; baglanti ve ice aktarma admin altinda kalir, slot id'leri kodda `oracle_reportdb` ve `ikinci_kaynak` (`api.py` `SLOTLAR`). Gercek Oracle acilmaz; `dene` yalniz TCP veya sahte adaptordur.

## Prod yol -> hedef modul

Yontem dekoratorde yoksa Flask varsayilani GET'tir; tabloda `GET?` yazilir.

| Eski yol | Modul |
|---|---|
| GET `/api/health` | core |
| POST `/api/sistem/kod_kontrol`, POST `/api/sistem/guncelleme_denetimi`, GET `/api/sistem/kod_kontrol/son` | core isletim; hedef API'de yok, `09` disinda |
| GET `/api/sistem/kullanici_loglari` | core audit |
| GET `/api/sistem/eposta`, POST `/api/sistem/eposta_test` | mail adaptoru, admin |
| POST `/api/update_user_role/<user_id>`, POST `/api/add_user`, POST `/api/update_user_name/<user_id>`, DELETE `/api/delete_user/<user_id>`, POST `/api/update_user_pin` | roller; pin ucu hedefte ayri tasarlanir, deger loglanmaz |
| GET `/api/backup`, POST `/api/restore` | core yedek; `05` haric listesi olmadan tasinmaz |
| GET+POST `/login`, GET `/logout`, GET `/api/oturum_canli` | core session |
| POST `/api/asistan` | P3, modul yok |
| POST `/api/add_customer`, GET `/api/musteri_karti/<id>`, POST kimlik/iletisim/ayri_rapor/tam_degistir, DELETE `/api/delete_customer/<id>` | musteri |
| POST `/api/urun_tutar_yukle/<id>`, GET `/api/portfoy_raporu` | musteri |
| POST `/api/upload_excel/<id>`, GET `/api/sla_analizi/<id>`, GET `/api/sla_ozet`, GET `/api/sla_bildirimleri` | rapor + onedesk (sla_deposu bolunmesi `04`) |
| GET `/api/ats_kayitlari/<id>/<tur>`, POST `/api/ats_analizi/<id>/<tur>`, POST `/api/update_ats_closed_count` | onedesk |
| POST `/api/rapor_alicilari/<id>`, POST `/api/rapor_ceviri/<id>`, POST `/api/send_customer_report_email/<id>`, POST `/api/aylik_rapor_taslak/<id>`, GET `/api/aylik_rapor_pdf/<id>`, POST geri_al / kaydi_sil / gecmisi_temizle, GET `/api/gonderilen_raporlar` | rapor |
| GET `/`, GET `/admin`, GET `/customer/<id>`, GET `/app`, GET `/app/<page>`, GET `/classic`, GET `/workspace/<module>` | HTML; hedef SPA, API degil |
| GET `/api/v1/integrations` | admin envanter |
| GET `/api/takvim_kayitlari/<yil>`, POST `/api/save_calendar` | takvim |
| GET `/api/qbr_report/<quarter>`, POST `/api/save_qbr_report` | sunum |
| POST `/api/add_radar_prospect`, DELETE `/api/delete_radar_prospect/<id>` | radar |
| GET `/api/tam_personal_summary/<user_id>` | ekip |
| GET+POST `/api/util_criteria`, GET+POST `/api/util_criteria_istirak` | utilizasyon |
| GET `/api/matrix_config/<key>`, POST `/api/save_matrix_config/<key>` | dogrulanmadi |
| POST `/api/add_project_entry`, DELETE `/api/delete_project_entry/<id>`, POST `/api/add_project_item`, GET `/api/proje_raporu`, POST update/delete item, POST `/api/add_project_action` | proje |
| POST `/api/proje_musteri_calisma` | proje |
| POST `/api/add_ict_revenue`, DELETE `/api/delete_ict_revenue/<id>` | tamsms |
| POST `/api/add_apn_revenue`, DELETE `/api/delete_apn_revenue/<id>` | tamapn |
| POST `/api/save_customer_score`, POST `/api/skor_toplu/onizleme`, POST `/api/skor_toplu/uygula`, GET `/api/skor_agaci`, POST `/api/istirak_final_dahil/<id>`, POST `/api/puanlama_personeli`, POST `/api/request_score_approval`, GET `/api/score_approval_requests`, POST `/api/resolve_score_approval/<id>` | utilizasyon |
| POST `/api/talep_olustur`, POST `/api/talep_guncelle/<id>`, DELETE `/api/talep_sil/<id>`, POST `/api/talep_bildirim_okundu` | talep |
| GET `/api/onedesk/incidents` | onedesk |
| POST `/api/topology/analyze` | topoloji, yetki musteri |
| GET `/veri_yonlendirici` | HTML |
| GET `/api/veri/kaynaklar`, POST `/api/veri/db/<kaynak>/test`, POST `/api/veri/db/<kaynak>/cek`, POST `/api/veri/yukle`, GET+DELETE `/api/veri/set/<id>`, GET `/api/veri/kriter_meta`, POST `/api/veri/kaynak_onizle`, POST `/api/veri/kriter_dene` | utilizasyon; `db/<kaynak>` sahte adaptore gider, canli Oracle yok |
| GET `/api/v1/session`, GET `/api/v1/dashboard`, GET `/api/v1/customers` | core + ekip ozet + musteri |

Yeni kaynak eklemek bu tabloya satir ister. Tabloda olmayan yol yazilmaz. OpenAPI, router dosyalarindan uretilir; `src/lib/api-tipler.ts` bugun elde tutulmus tipler icerebilir (5503 bayt) ? uretici komut calismadan guncel sayilmaz.

## Duz dekorator listesi (104)

Hepsi `D:\Project\TAM_Life\TAMLIFE\backend` altinda, 2026-10-03. `GET?` = methods yazilmayan `@route` (Flask varsayilani GET). Workspace ucu oneksiz gorunur; blueprint `url_prefix='/api/v1'`.

- GET `/api/health` ? `app/__init__.py`
- POST `/api/sistem/kod_kontrol`, POST `/api/sistem/guncelleme_denetimi`, GET `/api/sistem/kod_kontrol/son`, GET `/api/sistem/kullanici_loglari`, GET `/api/sistem/eposta`, POST `/api/sistem/eposta_test` ? `admin_bp.py`
- POST `/api/update_user_role/<int:user_id>`, POST `/api/add_user`, POST `/api/update_user_name/<int:user_id>`, DELETE `/api/delete_user/<int:user_id>`, POST `/api/update_user_pin`, GET `/api/backup`, POST `/api/restore` ? `admin_bp.py`
- GET+POST `/login`, POST `/api/asistan`, GET `/api/oturum_canli`, GET? `/logout` ? `auth_bp.py`
- POST `/api/add_customer`, GET `/api/musteri_karti/<int:customer_id>`, POST `/api/musteri_kimlik_guncelle/<int:customer_id>`, POST `/api/musteri_iletisim/<int:customer_id>`, POST `/api/musteri_ayri_rapor/<int:customer_id>`, POST `/api/musteri_tam_degistir/<int:customer_id>`, DELETE `/api/delete_customer/<int:customer_id>` ? `customer_bp.py`
- POST `/api/urun_tutar_yukle/<int:customer_id>`, POST `/api/upload_excel/<int:customer_id>`, GET `/api/sla_analizi/<int:customer_id>`, GET `/api/ats_kayitlari/<int:customer_id>/<tur>`, POST `/api/ats_analizi/<int:customer_id>/<tur>`, GET `/api/sla_ozet`, GET `/api/sla_bildirimleri` ? `customer_bp.py`
- POST `/api/rapor_alicilari/<int:customer_id>`, POST `/api/rapor_ceviri/<int:customer_id>`, POST `/api/send_customer_report_email/<int:customer_id>`, POST `/api/aylik_rapor_taslak/<int:customer_id>`, GET `/api/aylik_rapor_pdf/<int:gonderim_id>`, POST `/api/aylik_rapor_geri_al/<int:gonderim_id>`, POST `/api/aylik_rapor_kaydi_sil`, POST `/api/aylik_rapor_gecmisi_temizle`, GET `/api/portfoy_raporu`, GET `/api/gonderilen_raporlar` ? `customer_bp.py`
- GET? `/`, GET? `/admin`, GET? `/customer/<int:customer_id>` ? `dashboard_bp.py`
- GET `/api/v1/integrations` ? `integrations_bp.py`
- GET `/api/takvim_kayitlari/<int:yil>`, POST `/api/save_calendar`, GET `/api/qbr_report/<quarter>`, POST `/api/save_qbr_report`, POST `/api/add_radar_prospect`, DELETE `/api/delete_radar_prospect/<int:prospect_id>`, GET? `/api/tam_personal_summary/<int:user_id>` ? `operations_bp.py`
- GET `/api/util_criteria`, POST `/api/save_util_criteria`, GET `/api/util_criteria_istirak`, POST `/api/save_util_criteria_istirak`, GET `/api/matrix_config/<key>`, POST `/api/save_matrix_config/<key>`, POST `/api/update_ats_closed_count` ? `operations_bp.py`
- POST `/api/add_project_entry`, DELETE `/api/delete_project_entry/<int:entry_id>`, POST `/api/add_project_item`, POST `/api/proje_musteri_calisma`, GET `/api/proje_raporu`, POST `/api/update_project_item/<int:item_id>`, DELETE `/api/delete_project_item/<int:item_id>`, POST `/api/add_project_action` ? `projects_bp.py`
- POST `/api/add_ict_revenue`, DELETE `/api/delete_ict_revenue/<int:entry_id>`, POST `/api/add_apn_revenue`, DELETE `/api/delete_apn_revenue/<int:entry_id>` ? `projects_bp.py`
- POST `/api/save_customer_score`, POST `/api/skor_toplu/onizleme`, POST `/api/skor_toplu/uygula`, GET `/api/skor_agaci`, POST `/api/istirak_final_dahil/<int:customer_id>`, POST `/api/puanlama_personeli`, POST `/api/request_score_approval`, GET `/api/score_approval_requests`, POST `/api/resolve_score_approval/<int:request_id>` ? `projects_bp.py`
- POST `/api/talep_olustur`, POST `/api/talep_guncelle/<int:talep_id>`, DELETE `/api/talep_sil/<int:talep_id>`, POST `/api/talep_bildirim_okundu` ? `talep_bp.py`
- GET? `/api/onedesk/incidents`, POST `/api/topology/analyze` ? `topology_bp.py`
- GET? `/veri_yonlendirici`, GET `/api/veri/kaynaklar`, POST `/api/veri/db/<kaynak>/test`, POST `/api/veri/db/<kaynak>/cek`, POST `/api/veri/yukle`, GET `/api/veri/set/<int:set_id>`, DELETE `/api/veri/set/<int:set_id>`, GET `/api/veri/kriter_meta`, POST `/api/veri/kaynak_onizle`, POST `/api/veri/kriter_dene` ? `veri_bp.py`
- GET `/api/v1/session`, GET `/api/v1/dashboard`, GET `/api/v1/customers` ? `workspace_api_bp.py` (dekoratorde yol `/session`, `/dashboard`, `/customers`)
- GET? `/app`, GET? `/app/<path:page>`, GET? `/classic`, GET? `/workspace/<module>` ? `workspace_bp.py`

v3.5'te bu 104 yol yoktur. Orada 14 Flask yolu vardir (yukaridaki tablo). FastAPI OpenAPI `/api/v1/openapi.json` ureten dosya yoktur.
