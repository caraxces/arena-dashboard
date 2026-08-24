#!/usr/bin/env python3
"""Kéo dữ liệu Mewin Partner API -> in payload JSON ra stdout (hoặc file arg 1)."""
import json, os, sys, datetime, urllib.request

BASE = "https://api.quanlysan.vn/api"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126 Safari/537.36"
HUBS = [("Arena.03", os.environ.get("ARENA03_TOKEN", ""), 6097),
        ("Arena.01", os.environ.get("ARENA01_TOKEN", ""), 5981),
        ("Arena.02", os.environ.get("ARENA02_TOKEN", ""), 5980)]
HIST, FWD, OPEN_M, CLOSE_M = 200, 14, 300, 1440


def post(tok, path, body):
    r = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
        headers={"Accept": "application/json", "Content-Type": "application/json",
                 "Authorization": tok, "User-Agent": UA})
    with urllib.request.urlopen(r, timeout=240) as f:
        return json.load(f)


def price_rules(fields):
    out, seen = [], set()
    for fd in fields:
        for rt in fd.get("getScheduleWeeklyRenters") or []:
            for w in rt.get("getScheduleWeekly") or []:
                try: dows = set(json.loads(w.get("dayOfWeeks") or "[]"))
                except Exception: dows = set()
                n = w.get("numberOfMinute") or 60
                k = (tuple(sorted(dows)), w.get("startTime"), w.get("endTime"),
                     w.get("customPrice"), w.get("fixedPrice"))
                if k in seen: continue
                seen.add(k)
                out.append({"dows": dows, "s": w.get("startTime") or 0, "e": w.get("endTime") or 0,
                            "c": (w.get("customPrice") or 0) / n, "f": (w.get("fixedPrice") or 0) / n})
    return out


def rate(rules, dow, minute, fixed):
    """Rule có khung giờ cụ thể thắng; rule mặc định (s==e hoặc dow -111) là fallback."""
    spec = fb = None
    for p in rules:
        v = (p["f"] if fixed else p["c"]) or p["c"] or p["f"]
        if not v: continue
        alld = (-111 in p["dows"]) or not p["dows"]
        if p["s"] == p["e"]:
            if alld or dow in p["dows"]: fb = v if fb is None else max(fb, v)
            continue
        if (alld or dow in p["dows"]) and p["s"] <= minute < p["e"]:
            spec = v if spec is None else max(spec, v)
    return spec if spec is not None else (fb or 0.0)


def mask(p):
    p = (p or "").strip()
    return p[:4] + "***" + p[-2:] if len(p) > 6 else (p or "—")


def hub(name, tok, shop):
    today = datetime.date.today()
    d0, dz = today - datetime.timedelta(days=HIST), today + datetime.timedelta(days=FWD)
    sch = post(tok, "/Partner/GetScheduleView", {"fromDate": str(d0), "toDate": str(dz)})["value"]
    con = post(tok, "/Partner/GetContractScheduleBookedDatatable",
               {"generalSearch": "", "status": -111, "fromDate": str(d0), "toDate": str(dz),
                "paymentStatus": -111, "source": -111, "isRenew": -111})["value"] or []
    fields = sch.get("getScheduleFields") or []
    if not fields: return None
    fi = {f["fieldId"]: i for i, f in enumerate(fields)}
    ru = price_rules(fields)
    grid = [[[round(rate(ru, wd + 2, h * 60 + 30, fx) * 60) for h in range(24)]
             for wd in range(7)] for fx in (False, True)]
    bk = []
    for b in sch.get("getScheduleBookeds") or []:
        d = datetime.date.fromisoformat(b["bookedDay"][:10])
        s, e = max(b["startTime"], OPEN_M), min(b["endTime"], CLOSE_M)
        if e > s and b["fieldId"] in fi:
            bk.append([(d - d0).days, fi[b["fieldId"]], s, e, b.get("bookedType") or 2])
    cm, cust, rows = {}, [], []
    for c in [x for x in con if x.get("status") in (1, 2)]:
        ph = (c.get("customerPhone") or "").strip()
        key = ph or ("#%s" % c.get("customerID"))
        if key not in cm:
            cm[key] = len(cust); cust.append([c.get("customerName") or "—", mask(ph)])
        try:
            md = datetime.datetime.fromisoformat(c["minDate"][:19])
            cd = datetime.datetime.fromisoformat(c["createDate"][:19])
        except Exception:
            continue
        rows.append([(md.date() - d0).days, cm[key], round(c.get("totalMoneyHire") or 0),
                     c.get("contractType") or 2, round((md - cd).total_seconds() / 3600, 1)])
    return {"hub": name, "shopId": shop, "d0": str(d0), "today": (today - d0).days,
            "nDays": (dz - d0).days + 1, "open": sch.get("openingTime") or OPEN_M,
            "close": sch.get("closeTime") or CLOSE_M, "minTime": sch.get("minTime") or 60,
            "fields": [f["fieldName"] for f in fields],
            "fieldIds": [f["fieldId"] for f in fields], "priceGrid": grid,
            "bk": bk, "cust": cust, "con": rows}


def main():
    out = {"generated": datetime.datetime.now().replace(microsecond=0).isoformat(), "hubs": []}
    for name, tok, shop in HUBS:
        if not tok:
            print("bỏ qua %s (chưa có token)" % name, file=sys.stderr); continue
        try:
            h = hub(name, tok, shop)
            if h:
                out["hubs"].append(h)
                print("%s: %d lượt đặt · %d HĐ · %d khách" % (name, len(h["bk"]), len(h["con"]), len(h["cust"])), file=sys.stderr)
        except Exception as e:
            print("!! %s: %s" % (name, e), file=sys.stderr)
    if not out["hubs"]: sys.exit("Không lấy được dữ liệu hub nào.")
    js = json.dumps(out, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    blob = '<script id="payload">window.__ARENA__=%s;</script>' % js
    p = sys.argv[1] if len(sys.argv) > 1 else "payload.txt"
    open(p, "w", encoding="utf-8").write(blob)
    print("→ %s (%.0f KB)" % (p, os.path.getsize(p) / 1024), file=sys.stderr)


if __name__ == "__main__":
    main()
