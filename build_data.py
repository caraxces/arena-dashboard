#!/usr/bin/env python3
"""Kéo dữ liệu và đóng gói thành payload JSON nhúng vào dashboard."""
import sys, os, json, datetime, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine import Api, build_price_table, price_per_min, OPEN_M, CLOSE_M

BASE = "https://api.quanlysan.vn/api"
HUBS = {
    "Arena.01": {"token": os.environ.get("ARENA01_TOKEN", ""), "shop_id": 5981,
                 "courts": 6, "area": "Liên Chiểu", "addr": "40 Hoàng Văn Thái"},
    "Arena.02": {"token": os.environ.get("ARENA02_TOKEN", ""), "shop_id": 5980,
                 "courts": 9, "area": "Sơn Trà", "addr": "25 Hồ Hán Thương"},
    "Arena.03": {"token": os.environ.get("ARENA03_TOKEN", ""), "shop_id": 6097,
                 "courts": 8, "area": "Liên Chiểu", "addr": "38 Hoàng Văn Thái"},
}
OPEN_H = 19          # 05:00–24:00
MONTHS_BACK = 7
HISTORY_DAYS = int(os.environ.get("HISTORY_DAYS", 200))
FORWARD_DAYS = 14


def mask(p):
    p = (p or "").strip()
    return p[:4] + "***" + p[-2:] if len(p) > 6 else (p or "—")


def build_hub(name, cfg):
    api = Api(BASE, cfg["token"])
    today = datetime.date.today()
    d0 = today - datetime.timedelta(days=HISTORY_DAYS)
    dz = today + datetime.timedelta(days=FORWARD_DAYS)
    sch = api.schedule(str(d0), str(dz))
    con = api.contracts(str(d0), str(dz))

    fields = sch.get("getScheduleFields") or []
    if not fields:
        return None
    fidx = {f["fieldId"]: i for i, f in enumerate(fields)}
    ptab = build_price_table(fields)

    # lưới giá: [loại 0=ngày,1=cố định][thứ 0..6][giờ 5..23] -> đồng/giờ
    grid = []
    for fixed in (False, True):
        g = []
        for wd in range(7):
            ref = today - datetime.timedelta(days=(today.weekday() - wd) % 7)
            g.append([round(price_per_min(ptab, ref, h * 60 + 30, fixed) * 60) for h in range(24)])
        grid.append(g)

    bk = []
    for b in sch.get("getScheduleBookeds") or []:
        d = datetime.date.fromisoformat(b["bookedDay"][:10])
        s, e = max(b["startTime"], OPEN_M), min(b["endTime"], CLOSE_M)
        if e <= s or b["fieldId"] not in fidx:
            continue
        bk.append([(d - d0).days, fidx[b["fieldId"]], s, e, b.get("bookedType") or 2])

    ok = [c for c in con if c.get("status") in (1, 2)]
    cmap, cust, rows = {}, [], []
    for c in ok:
        ph = (c.get("customerPhone") or "").strip()
        key = ph or f"#{c.get('customerID')}"
        if key not in cmap:
            cmap[key] = len(cust)
            cust.append([c.get("customerName") or "—", mask(ph)])
        try:
            md = datetime.datetime.fromisoformat(c["minDate"][:19])
            cd = datetime.datetime.fromisoformat(c["createDate"][:19])
            lead = round((md - cd).total_seconds() / 3600, 1)
            di = (md.date() - d0).days
        except Exception:
            continue
        rows.append([di, cmap[key], round(c.get("totalMoneyHire") or 0),
                     c.get("contractType") or 2, lead])

    return {
        "hub": name, "shopId": cfg["shop_id"],
        "d0": str(d0), "today": (today - d0).days, "nDays": (dz - d0).days + 1,
        "open": sch.get("openingTime") or OPEN_M,
        "close": sch.get("closeTime") or CLOSE_M,
        "minTime": sch.get("minTime") or 60,
        "fields": [f["fieldName"] for f in fields],
        "fieldIds": [f["fieldId"] for f in fields],
        "priceGrid": grid,
        "priceRules": [{"dows": sorted(p["dows"]), "s": p["s"], "e": p["e"],
                        "c": round(p["custom"] * 60), "f": round(p["fixed"] * 60)}
                       for p in ptab],
        "bk": bk, "cust": cust, "con": rows,
    }


def month_spans(n, today):
    """[(nhãn, từ, đến, số ngày trong kỳ, đủ tháng?)] — n tháng gần nhất."""
    out, y, m = [], today.year, today.month
    for _ in range(n):
        first = datetime.date(y, m, 1)
        nxt = datetime.date(y + (m == 12), 1 if m == 12 else m + 1, 1)
        last = min(nxt - datetime.timedelta(days=1), today)
        out.append(("%02d/%s" % (m, str(y)[2:]), str(first), str(last),
                    (last - first).days + 1, last == nxt - datetime.timedelta(days=1)))
        m -= 1
        if m == 0: y, m = y - 1, 12
    return list(reversed(out))


def daily_series(api, shop_id, d0, dn, chunk=45):
    """Report API nhận list nhiều khoảng ngày → kéo chuỗi theo ngày rất rẻ."""
    out, n = [], (dn - d0).days + 1
    for a in range(0, n, chunk):
        spans = [{"fromDate": str(d0 + datetime.timedelta(days=i)),
                  "toDate":   str(d0 + datetime.timedelta(days=i))}
                 for i in range(a, min(a + chunk, n))]
        try:
            res = api._call("/Partner/Report/GetTimeAndPriceContractV2",
                            {"shopID": shop_id, "dateTimes": spans}).get("value") or []
        except Exception as e:
            print("  !! daily %s: %s" % (shop_id, e)); break
        for i, grp in enumerate(res):
            mf = hf = mv = hv = 0
            for x in (grp or []):
                t = x.get("contractType")
                m = round(x.get("totalMoneyHire") or 0)
                h = round((x.get("totalTimeMinute") or 0) / 60, 2)
                if t == 1 or t == 5: mf += m; hf += h
                else:                mv += m; hv += h
            if mf or hf or mv or hv:
                out.append([a + i, mf, hf, mv, hv])
    return out


def system_report(api, today):
    """Report API nhận shopID nên MỘT token đọc được cả 3 hub."""
    d2 = today - datetime.timedelta(days=1)
    d1 = d2 - datetime.timedelta(days=27)
    spans = month_spans(MONTHS_BACK, today)
    hubs = []
    for name, cfg in HUBS.items():
        try:
            r = api.report_money(cfg["shop_id"], str(d1), str(d2))
            r = r[0] if r else []
            money = sum(x.get("totalMoneyHire") or 0 for x in r)
            mins = sum(x.get("totalTimeMinute") or 0 for x in r)
            by = {x.get("contractType"): {"m": x.get("totalMoneyHire") or 0,
                                          "h": (x.get("totalTimeMinute") or 0) / 60}
                  for x in r if x.get("totalMoneyHire")}
            try:
                c = api.report_cancel(cfg["shop_id"], str(d1), str(d2))
                c = c[0] if c else {}
                cancel = (c.get("contractFixTerm") or 0) + (c.get("contractFlexible") or 0)
            except Exception:
                cancel = None
            series = []
            for lab, a, b, nd, full in spans:
                rr = api.report_money(cfg["shop_id"], a, b)
                rr = rr[0] if rr else []
                mm = sum(x.get("totalMoneyHire") or 0 for x in rr)
                series.append({"label": lab, "m": round(mm), "days": nd, "full": full,
                               "norm": round(mm / nd * 30)})
            hubs.append({"name": name, "shopId": cfg["shop_id"], "courts": cfg["courts"],
                         "area": cfg["area"], "addr": cfg["addr"],
                         "money": round(money), "hours": round(mins / 60, 1),
                         "cap": cfg["courts"] * OPEN_H * 28, "cancel": cancel,
                         "byType": {str(k): v for k, v in by.items()}, "series": series})
        except Exception as e:
            print("  !! report %s: %s" % (name, e))
    dn = today + datetime.timedelta(days=FORWARD_DAYS)
    ds0 = today - datetime.timedelta(days=HISTORY_DAYS)
    daily = {}
    for h in hubs:
        daily[h["name"]] = daily_series(api, h["shopId"], ds0, dn)
        print("  chuỗi ngày %s: %d ngày có số" % (h["name"], len(daily[h["name"]])))
    return {"from": str(d1), "to": str(d2), "days": 28, "openHours": OPEN_H,
            "hubs": hubs, "dailyD0": str(ds0), "dailyN": (dn - ds0).days + 1,
            "today": (today - ds0).days, "daily": daily}


def main():
    out = {"generated": datetime.datetime.now().replace(microsecond=0).isoformat(),
           "hubs": []}
    for name, cfg in HUBS.items():
        if not cfg["token"]:
            print(f"  bỏ qua {name} (chưa có token)")
            continue
        try:
            h = build_hub(name, cfg)
            if h:
                out["hubs"].append(h)
                print(f"  {name}: {len(h['bk'])} lượt đặt · {len(h['con'])} HĐ · "
                      f"{len(h['cust'])} khách · {len(h['fields'])} sân")
        except Exception as e:
            print(f"  !! {name}: {e}")
    if not out["hubs"]:
        sys.exit("Không lấy được dữ liệu hub nào.")
    tok = next((c["token"] for c in HUBS.values() if c["token"]), None)
    if tok:
        out["system"] = system_report(Api(BASE, tok), datetime.date.today())
        print("  toàn hệ thống: %d hub qua Report API" % len(out["system"]["hubs"]))
    p = sys.argv[1] if len(sys.argv) > 1 else "data.json"
    json.dump(out, open(p, "w"), ensure_ascii=False, separators=(",", ":"))
    print(f"→ {p}  ({os.path.getsize(p)/1024:.0f} KB)")


if __name__ == "__main__":
    main()
