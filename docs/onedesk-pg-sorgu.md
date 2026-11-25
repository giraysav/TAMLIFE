# Onedesk PostgreSQL sorgusu (ONEDESKDB) — eski + yeni sistem

Karar (2026-11-06, kullanıcı): iki şema da kullanılır, kayıtlar **01.01.2026 00:00**'dan itibaren alınır.
Eski sistemde `TICKETTYPEID = 1` ve `TICKETSUBTYPEID` 1 = alarm, 2 = şikayet, 3 = talep.

| Sistem | Tablo |
|---|---|
| Eski | `elysion_customdata_fix."T_SOL_INCIDENT_TICKETS"` |
| Yeni | `elysion_soxdata_octopuscorp."T_OCT_CORPORATE_MAIN"` |

**Önkoşul:** panelin ONEDESKDB hesabına iki şemada `USAGE` ve iki tabloda `SELECT` verilmeli (2026-11-06 itibarıyla `permission denied for schema`).

## Hat
`backend/.env` → `ONEDESKDB_PG_IMPORT_QUERY` (tek satır SELECT) → `python -m app.isci pg-cek --kaynak pg_onedesk` → tampon partisi `pg_onedesk_import` → Veri Girişi'nden Onedesk'e aktarım (`ice_al.parti_aktar`). Sütun başlıkları `onedesk/ice_al.py` `SUTUN_ADLARI` ile tanınır; aşağıdaki takma adlar buna göre seçildi.

## Sorgu (doğrulanmadı: yetki gelince tür/durum değerleri kontrol edilmeli)
```sql
SELECT * FROM (
  SELECT "TICKETNO"::text AS "Kayıt No",
         CASE "TICKETSUBTYPEID" WHEN 1 THEN 'Alarm' WHEN 2 THEN 'Şikayet' WHEN 3 THEN 'Talep' END AS "Kayıt Türü",
         "STATUS" AS "Durum", "CUSTOMERFULLNAME" AS "Müşteri Adı", "CUSTOMERNO" AS "Müşteri No",
         "LOCATIONNAME" AS "CI Adı", "SUMMARY" AS "Kategori",
         "CREATEDDATE" AS "Açılış Tarihi", "CLOSEDATE" AS "Kapanış Tarihi",
         "TICKETSOLUTIONCAUSEDESC" AS "Kök Sebep", "SOLUTION" AS "Çözüm Açıklaması"
    FROM elysion_customdata_fix."T_SOL_INCIDENT_TICKETS"
   WHERE "TICKETTYPEID" = 1 AND "TICKETSUBTYPEID" IN (1,2,3) AND "CREATEDDATE" >= TIMESTAMP '2026-01-01 00:00:00'
  UNION ALL
  SELECT "WFINSTANCEID"::text, "TICKETTYPE_DESC", "STATUS", "CUSTOMERNAME_DESC", "CUSTOMERNO",
         "CINAME_DESC", "CATEGORY_DESC", "CREATEDDATE", "CLOSEDATE", "ROOTCAUSE_DESC", "CLOSEDESC"
    FROM elysion_soxdata_octopuscorp."T_OCT_CORPORATE_MAIN"
   WHERE "CREATEDDATE" >= TIMESTAMP '2026-01-01 00:00:00'
) t
```

## Doğrulanacaklar
- Yeni tabloda kayıt numarası sütunu belirsiz: `WFINSTANCEID` varsayıldı (`PROBLEMNO` alternatif).
- Yeni tabloda tür: `TICKETTYPE_DESC` metni "alarm / şikayet / talep" içermiyorsa CASE ile eşlenmeli.
- Eski tabloda kök sebep sayısal (`ROOTCAUSEID`); metin için `TICKETSOLUTIONCAUSEDESC` varsayıldı. CI adı için `LOCATIONNAME` varsayıldı.
- Durum değerleri ("kapal/closed/cozul/resolved/tamam/done" içermeli) ve eski/yeni arasında çakışan kayıtlar.
