"""ReportDB tablo kesfi (salt okuma, yalniz veri sozlugu): erisim verilen tablo/gorunumler, sutunlar, istatistik satir sayisi,
bolum anahtarlari ve indeksler. Hicbir tablonun veri satiri okunmaz (COUNT(*) bile yok: istatistik NUM_ROWS kullanilir).

Kullanim (panelden AYRI surec, Oracle giris tetikleyicisinin izin verdigi Windows hesabiyla):
    python -m araclar.reportdb_kesif [--kaynak oracle_reportdb] [--sahip TEMIP ...]
Cikti: var/kesif/<kaynak>-<YYYYMMDD-HHMM>.json ve .md (git disi). Ekrana yalniz ozet yazilir; adres/kullanici/parola yazilmaz.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.config import env_dosyasi_yukle
from app.tampon import oracle

# Oracle'in kendi semalari: kesif disi (yalniz bize verilen is tablolari aranir).
SISTEM = (
    "SYS", "SYSTEM", "XDB", "MDSYS", "CTXSYS", "ORDSYS", "ORDDATA", "ORDPLUGINS", "WMSYS", "OUTLN", "DBSNMP", "APPQOSSYS",
    "OLAPSYS", "EXFSYS", "LBACSYS", "DVSYS", "AUDSYS", "GSMADMIN_INTERNAL", "OJVMSYS", "SI_INFORMTN_SCHEMA", "DBSFWUSER",
    "REMOTE_SCHEDULER_AGENT", "GGSYS", "ANONYMOUS", "XS$NULL", "PUBLIC", "MGMT_VIEW", "SYSMAN", "ORACLE_OCM", "FLOWS_FILES",
)  # fmt: skip
CAGRI_SURESI_MS = 180_000


def _sorgu(cur: Any, sql: str, **binds: Any) -> list[dict[str, Any]]:
    cur.execute(sql, binds)
    adlar = [d[0].lower() for d in cur.description]
    return [dict(zip(adlar, (oracle.deger(v) for v in satir), strict=True)) for satir in cur.fetchall()]


def _sistem_disi(sutun: str) -> str:
    return f"{sutun} NOT IN ({', '.join(repr(s) for s in SISTEM)}) AND {sutun} NOT LIKE 'APEX%'"


def kesfet(kaynak: str, sahipler: list[str]) -> dict[str, Any]:
    ayar = oracle.ayar(kaynak)
    oracledb = oracle._oracledb()
    with ayar._baglan(oracledb) as conn:
        conn.call_timeout = CAGRI_SURESI_MS
        with conn.cursor() as cur:
            # 1) Izinler: dogrudan ve oturumdaki roller uzerinden (nesne bazinda)
            dogrudan = _sorgu(cur, "SELECT OWNER, TABLE_NAME, PRIVILEGE FROM USER_TAB_PRIVS_RECD")
            rol = _sorgu(
                cur,
                "SELECT R.ROLE, R.OWNER, R.TABLE_NAME, R.PRIVILEGE FROM ROLE_TAB_PRIVS R WHERE R.ROLE IN (SELECT ROLE FROM SESSION_ROLES)",
            )
            roller = [r["role"] for r in _sorgu(cur, "SELECT ROLE FROM SESSION_ROLES ORDER BY ROLE")]
            sistem_yetkileri = [r["privilege"] for r in _sorgu(cur, "SELECT PRIVILEGE FROM SESSION_PRIVS ORDER BY PRIVILEGE")]
            # 2) Erisilebilen is nesneleri (tablo/gorunum/mview); sahip bazinda ozet
            nesneler = _sorgu(
                cur,
                "SELECT OWNER, OBJECT_NAME, OBJECT_TYPE, TO_CHAR(LAST_DDL_TIME,'YYYY-MM-DD') AS LAST_DDL FROM ALL_OBJECTS "
                f"WHERE OBJECT_TYPE IN ('TABLE','VIEW','MATERIALIZED VIEW') AND {_sistem_disi('OWNER')} "
                "AND OBJECT_NAME NOT LIKE 'BIN$%' ORDER BY OWNER, OBJECT_NAME",
            )
            izinli = {(r["owner"], r["table_name"]) for r in dogrudan + rol if r["privilege"] in ("SELECT", "READ")}
            if sahipler:
                hedef = [n for n in nesneler if n["owner"] in sahipler]
            else:
                # Rol/dogrudan izin listesinde olmayan erisim (orn. SELECT ANY TABLE) sahip ozetinde gorunur; --sahip ile acilir.
                hedef = [n for n in nesneler if (n["owner"], n["object_name"]) in izinli]
            anahtarlar = sorted({(n["owner"], n["object_name"]) for n in hedef})
            # 3) Ayrinti: sutun, aciklama, istatistik, bolum anahtari, indeks (her biri tek sorguda, sahip bazinda suzulur)
            sutunlar: dict[tuple, list] = defaultdict(list)
            yorum: dict[tuple, str] = {}
            sutun_yorum: dict[tuple, str] = {}
            tablo_bilgi: dict[tuple, dict] = {}
            bolum: dict[tuple, list] = defaultdict(list)
            indeks: dict[tuple, dict] = defaultdict(dict)
            for sahip in sorted({o for o, _ in anahtarlar}):
                adlar = {a for o, a in anahtarlar if o == sahip}

                def al(sql: str, _sahip: str = sahip, _adlar: set = adlar) -> list[dict[str, Any]]:
                    return [r for r in _sorgu(cur, sql, sahip=_sahip) if r.get("table_name", r.get("name")) in _adlar]

                for r in al(
                    "SELECT TABLE_NAME, COLUMN_ID, COLUMN_NAME, DATA_TYPE, DATA_LENGTH, DATA_PRECISION, DATA_SCALE, NULLABLE "
                    "FROM ALL_TAB_COLUMNS WHERE OWNER = :sahip ORDER BY TABLE_NAME, COLUMN_ID"
                ):
                    sutunlar[(sahip, r["table_name"])].append(r)
                for r in al("SELECT TABLE_NAME, COMMENTS FROM ALL_TAB_COMMENTS WHERE OWNER = :sahip AND COMMENTS IS NOT NULL"):
                    yorum[(sahip, r["table_name"])] = r["comments"]
                for r in al("SELECT TABLE_NAME, COLUMN_NAME, COMMENTS FROM ALL_COL_COMMENTS WHERE OWNER = :sahip AND COMMENTS IS NOT NULL"):
                    sutun_yorum[(sahip, r["table_name"], r["column_name"])] = r["comments"]
                for r in al(
                    "SELECT TABLE_NAME, NUM_ROWS, TO_CHAR(LAST_ANALYZED,'YYYY-MM-DD') AS LAST_ANALYZED, PARTITIONED "
                    "FROM ALL_TABLES WHERE OWNER = :sahip"
                ):
                    tablo_bilgi[(sahip, r["table_name"])] = r
                for r in al(
                    "SELECT NAME, COLUMN_NAME, COLUMN_POSITION FROM ALL_PART_KEY_COLUMNS WHERE OWNER = :sahip "
                    "AND OBJECT_TYPE = 'TABLE' ORDER BY NAME, COLUMN_POSITION"
                ):
                    bolum[(sahip, r["name"])].append(r["column_name"])
                for r in al(
                    "SELECT TABLE_NAME, INDEX_NAME, COLUMN_NAME, COLUMN_POSITION FROM ALL_IND_COLUMNS WHERE TABLE_OWNER = :sahip "
                    "ORDER BY TABLE_NAME, INDEX_NAME, COLUMN_POSITION"
                ):
                    indeks[(sahip, r["table_name"])].setdefault(r["index_name"], []).append(r["column_name"])
            sahip_ozeti: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
            for n in nesneler:
                sahip_ozeti[n["owner"]][n["object_type"]] += 1
    tur = {(n["owner"], n["object_name"]): n for n in nesneler}
    tablolar = []
    for anahtar in anahtarlar:
        o, a = anahtar
        b = tablo_bilgi.get(anahtar, {})
        tablolar.append(
            {
                "sahip": o,
                "ad": a,
                "tur": tur.get(anahtar, {}).get("object_type", ""),
                "son_ddl": tur.get(anahtar, {}).get("last_ddl", ""),
                "aciklama": yorum.get(anahtar, ""),
                "satir_istatistik": b.get("num_rows"),
                "istatistik_tarihi": b.get("last_analyzed"),
                "bolumlu": b.get("partitioned") == "YES",
                "bolum_anahtari": bolum.get(anahtar, []),
                "indeksler": indeks.get(anahtar, {}),
                "izin": sorted({r["privilege"] for r in dogrudan + rol if (r["owner"], r["table_name"]) == anahtar}),
                "izin_yolu": sorted(
                    {"dogrudan" for r in dogrudan if (r["owner"], r["table_name"]) == anahtar}
                    | {f"rol:{r['role']}" for r in rol if (r["owner"], r["table_name"]) == anahtar}
                ),
                "sutunlar": [
                    {
                        "ad": s["column_name"],
                        "tip": _tip(s),
                        "bos_olabilir": s["nullable"] == "Y",
                        "aciklama": sutun_yorum.get((o, a, s["column_name"]), ""),
                    }
                    for s in sutunlar.get(anahtar, [])
                ],
            }
        )
    return {
        "kaynak": kaynak,
        "zaman": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M"),
        "roller": roller,
        "sistem_yetkileri": sistem_yetkileri,
        "dogrudan_izin_sayisi": len(dogrudan),
        "rol_izin_sayisi": len(rol),
        "sahip_ozeti": {k: dict(v) for k, v in sorted(sahip_ozeti.items())},
        "tablolar": tablolar,
    }


def _tip(s: dict[str, Any]) -> str:
    t = s["data_type"]
    if t in ("VARCHAR2", "NVARCHAR2", "CHAR", "NCHAR", "RAW"):
        return f"{t}({s['data_length']})"
    if t == "NUMBER" and s["data_precision"] is not None:
        return f"NUMBER({s['data_precision']},{s['data_scale'] or 0})"
    return t


def _md(k: dict[str, Any]) -> str:
    satir = [
        f"# ReportDB tablo keşfi — {k['zaman']}",
        "",
        f"Kaynak `{k['kaynak']}`. Yalnız veri sözlüğü okundu; tablo satırı okunmadı. Satır sayısı Oracle istatistiğidir (tahmini).",
        "",
        f"- Oturum rolleri: {', '.join(k['roller']) or '—'}",
        f"- Sistem yetkileri: {', '.join(k['sistem_yetkileri']) or '—'}",
        f"- Nesne izinleri: doğrudan {k['dogrudan_izin_sayisi']}, rol üzerinden {k['rol_izin_sayisi']}",
        "",
        "## Erişilebilen şemalar (sistem şemaları hariç)",
        "",
        "| Şema | Tablo | Görünüm | MView |",
        "|---|---:|---:|---:|",
    ]
    for o, t in k["sahip_ozeti"].items():
        satir.append(f"| {o} | {t.get('TABLE', 0)} | {t.get('VIEW', 0)} | {t.get('MATERIALIZED VIEW', 0)} |")
    satir += ["", f"## İzin verilen nesneler ({len(k['tablolar'])})", ""]
    satir += ["| Nesne | Tür | Satır (ist.) | Bölüm anahtarı | Sütun | İzin |", "|---|---|---:|---|---:|---|"]
    for t in k["tablolar"]:
        satir.append(
            f"| {t['sahip']}.{t['ad']} | {t['tur']} | {t['satir_istatistik'] if t['satir_istatistik'] is not None else '—'} | "
            f"{', '.join(t['bolum_anahtari']) or '—'} | {len(t['sutunlar'])} | {', '.join(t['izin'])} ({', '.join(t['izin_yolu'])}) |"
        )
    for t in k["tablolar"]:
        satir += ["", f"### {t['sahip']}.{t['ad']} ({t['tur']})", ""]
        if t["aciklama"]:
            satir += [t["aciklama"], ""]
        if t["indeksler"]:
            satir += ["İndeksler: " + "; ".join(f"{a} ({', '.join(c)})" for a, c in t["indeksler"].items()), ""]
        satir += ["| # | Sütun | Tip | Boş | Açıklama |", "|---:|---|---|---|---|"]
        for i, s in enumerate(t["sutunlar"], 1):
            satir.append(f"| {i} | {s['ad']} | {s['tip']} | {'E' if s['bos_olabilir'] else 'H'} | {s['aciklama']} |")
    return "\n".join(satir) + "\n"


def main() -> int:
    env_dosyasi_yukle()
    p = argparse.ArgumentParser(description="ReportDB tablo kesfi (yalniz veri sozlugu)")
    p.add_argument("--kaynak", default="oracle_reportdb")
    p.add_argument("--sahip", action="append", default=[], help="izin listesi yerine bu semanin tum nesneleri (tekrarlanabilir)")
    a = p.parse_args()
    try:
        k = kesfet(a.kaynak, [s.upper() for s in a.sahip])
    except Exception as hata:  # noqa: BLE001 - mesaj maskelenir, ham hata (adres/kullanici) yazilmaz
        mesaj, ipucu = oracle.hata_metni(hata, oracle.ayar(a.kaynak).gizliler())
        print(f"HATA: {mesaj}" + (f" | {ipucu}" if ipucu else ""))
        return 1
    klasor = BACKEND / "var" / "kesif"
    klasor.mkdir(parents=True, exist_ok=True)
    ad = f"{a.kaynak}-{datetime.now().astimezone():%Y%m%d-%H%M}"
    (klasor / f"{ad}.json").write_text(json.dumps(k, ensure_ascii=False, indent=1), encoding="utf-8")
    (klasor / f"{ad}.md").write_text(_md(k), encoding="utf-8")
    print(f"roller={k['roller']} dogrudan_izin={k['dogrudan_izin_sayisi']} rol_izin={k['rol_izin_sayisi']}")
    print("semalar: " + ", ".join(f"{o}({sum(t.values())})" for o, t in k["sahip_ozeti"].items()))
    print(f"izinli nesne: {len(k['tablolar'])}")
    for t in k["tablolar"]:
        print(f"  {t['sahip']}.{t['ad']} [{t['tur']}] satir~{t['satir_istatistik']} sutun={len(t['sutunlar'])} bolum={t['bolum_anahtari']}")
    print(f"cikti: var/kesif/{ad}.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
