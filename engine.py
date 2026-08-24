"""Arena — engine tính metrics từ Mewin Partner API."""
import json, urllib.request, datetime, collections, statistics, time

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126 Safari/537.36"
OPEN_M, CLOSE_M = 300, 1440          # 05:00 -> 24:00
HOURS = list(range(5, 24))
PEAK_S, PEAK_E = 1020, 1260          # 17:00-21:00
DOW_VI = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]


class Api:
    def __init__(self, base, token, timeout=120):
        self.base, self.token, self.timeout = base.rstrip("/"), token, timeout

    def _call(self, path, body=None, method="POST"):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            self.base + path, data=data, method=method,
            headers={"Accept": "application/json", "Content-Type": "application/json",
                     "Authorization": self.token, "User-Agent": UA})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.load(r)

    def shops(self):
        return self._call("/Partner/GetShops", {"generalSearch": "", "status": -111}).get("value") or []

    def schedule(self, d1, d2):
        return self._call("/Partner/GetScheduleView", {"fromDate": d1, "toDate": d2}).get("value") or {}

    def contracts(self, d1, d2):
        return self._call("/Partner/GetContractScheduleBookedDatatable",
                          {"generalSearch": "", "status": -111, "fromDate": d1, "toDate": d2,
                           "paymentStatus": -111, "source": -111, "isRenew": -111}).get("value") or []

    def report_money(self, shop_id, d1, d2):
        return self._call("/Partner/Report/GetTimeAndPriceContractV2",
                          {"shopID": shop_id, "dateTimes": [{"fromDate": d1, "toDate": d2}]}).get("value") or []

    def report_cancel(self, shop_id, d1, d2):
        return self._call("/Partner/Report/GetOverviewCancelContractV2",
                          {"shopID": shop_id, "dateTimes": [{"fromDate": d1, "toDate": d2}]}).get("value") or []


# ---------- bảng giá ----------
def build_price_table(fields):
    """[(set(dow), start, end, price_per_min_custom, price_per_min_fixed)]"""
    out = []
    seen = set()
    for f in fields:
        for r in f.get("getScheduleWeeklyRenters") or []:
            for w in r.get("getScheduleWeekly") or []:
                try:
                    dows = set(json.loads(w.get("dayOfWeeks") or "[]"))
                except Exception:
                    dows = set()
                n = w.get("numberOfMinute") or 60
                key = (tuple(sorted(dows)), w.get("startTime"), w.get("endTime"),
                       w.get("customPrice"), w.get("fixedPrice"), r.get("fieldRentersID"))
                if key in seen:
                    continue
                seen.add(key)
                out.append({
                    "dows": dows, "s": w.get("startTime") or 0, "e": w.get("endTime") or 0,
                    "custom": (w.get("customPrice") or 0) / n,
                    "fixed": (w.get("fixedPrice") or 0) / n,
                    "renter": r.get("fieldRentersID"),
                    "renter_name": r.get("fieldRentersName"),
                    "unit_min": n,
                })
    return out


def price_per_min(ptab, date, minute, fixed=False, renter=None):
    """Rule có khung giờ cụ thể thắng; rule mặc định (dow=-111 hoặc s==e==0) là fallback."""
    dow = date.weekday() + 2
    specific, fallback = None, None
    for p in ptab:
        if renter is not None and p["renter"] != renter:
            continue
        val = p["fixed"] if fixed else p["custom"]
        if not val:
            val = p["custom"] or p["fixed"]
        if not val:
            continue
        all_days = (-111 in p["dows"]) or not p["dows"]
        if p["s"] == p["e"]:                      # rule mặc định, không giới hạn giờ
            if all_days or dow in p["dows"]:
                fallback = val if fallback is None else max(fallback, val)
            continue
        if (all_days or dow in p["dows"]) and p["s"] <= minute < p["e"]:
            specific = val if specific is None else max(specific, val)
    return specific if specific is not None else (fallback or 0.0)


def listed_value(ptab, date, s, e, fixed=False):
    return sum(price_per_min(ptab, date, m, fixed) for m in range(max(s, OPEN_M), min(e, CLOSE_M)))


# ---------- metrics ----------
def merge(ivs):
    m = []
    for s, e in sorted(ivs):
        if m and s <= m[-1][1]:
            m[-1] = (m[-1][0], max(m[-1][1], e))
        else:
            m.append((s, e))
    return m


def compute(sched, contracts, min_time=60):
    fields = sched.get("getScheduleFields") or []
    bookings = sched.get("getScheduleBookeds") or []
    ptab = build_price_table(fields)
    names = {f["fieldId"]: f["fieldName"] for f in fields}
    live = [b for b in bookings if b.get("bookedType") != 4]
    locks = [b for b in bookings if b.get("bookedType") == 4]
    days = sorted({b["bookedDay"][:10] for b in bookings}) or []
    nd, nc = max(len(days), 1), max(len(names), 1)

    grid = collections.Counter()      # (fieldId, hour) -> minutes
    byhour = collections.Counter()
    bydow_hour = collections.Counter()
    dow_days = collections.Counter()
    per_court = collections.Counter()
    per_court_peak = collections.Counter()
    per_court_bk = collections.Counter()
    listed_rev = 0.0
    listed_by_hour = collections.Counter()

    for d in days:
        dow_days[datetime.date.fromisoformat(d).weekday()] += 1

    for b in live:
        d = datetime.date.fromisoformat(b["bookedDay"][:10])
        s, e = max(b["startTime"], OPEN_M), min(b["endTime"], CLOSE_M)
        if e <= s:
            continue
        fid = b["fieldId"]
        per_court[fid] += e - s
        per_court_bk[fid] += 1
        per_court_peak[fid] += max(0, min(e, PEAK_E) - max(s, PEAK_S))
        fixed = b.get("bookedType") in (1, 5)
        for m in range(s, e):
            h = m // 60
            grid[(fid, h)] += 1
            byhour[h] += 1
            bydow_hour[(d.weekday(), h)] += 1
            v = price_per_min(ptab, d, m, fixed)
            listed_rev += v
            listed_by_hour[h] += v

    # mảnh vụn trong khung giờ vàng
    g = collections.defaultdict(list)
    for b in live:
        g[(b["bookedDay"][:10], b["fieldId"])].append((b["startTime"], b["endTime"]))
    frag_interior, frag_edge, frag_by_court = [], [], collections.Counter()
    for d in days:
        for fid in names:
            cur, gaps = PEAK_S, []
            for s, e in merge(g.get((d, fid), [])):
                if e <= PEAK_S or s >= PEAK_E + 60:
                    continue
                if s > cur:
                    gaps.append((cur, min(s, PEAK_E + 60), True))
                cur = max(cur, e)
            if cur < PEAK_E + 60:
                gaps.append((cur, PEAK_E + 60, False))
            for s, e, between in gaps:
                ln = e - s
                if 0 < ln < min_time:
                    rec = {"day": d, "field": names[fid], "s": s, "e": e, "len": ln}
                    if between and s > PEAK_S:
                        frag_interior.append(rec); frag_by_court[fid] += 1
                    else:
                        frag_edge.append(rec)

    # tiền thật từ hợp đồng
    ok = [c for c in contracts if c.get("status") in (1, 2)]
    money = sum(c.get("totalMoneyHire") or 0 for c in ok)
    disc = sum(c.get("totalMoneyDiscount") or 0 for c in ok)
    svc = sum(c.get("totalMoneyService") or 0 for c in ok)
    debt = sum(c.get("finalTotalMustPay") or 0 for c in ok)
    sold_h = sum(per_court.values()) / 60

    cap_day = nc * (CLOSE_M - OPEN_M)
    return {
        "fields": names, "days": days, "nd": nd, "nc": nc, "ptab": ptab,
        "grid": grid, "byhour": byhour, "bydow_hour": bydow_hour, "dow_days": dow_days,
        "per_court": per_court, "per_court_peak": per_court_peak, "per_court_bk": per_court_bk,
        "listed_rev": listed_rev, "listed_by_hour": listed_by_hour,
        "frag_interior": frag_interior, "frag_edge": frag_edge, "frag_by_court": frag_by_court,
        "locks": len(locks), "sold_hours": sold_h,
        "occ": sum(per_court.values()) / (cap_day * nd) * 100 if nd else 0,
        "money": money, "discount": disc, "service": svc, "debt": debt,
        "realized_per_hour": (money / sold_h) if sold_h else 0,
        "realization": (money / listed_rev * 100) if listed_rev else 0,
        "n_contracts": len(ok),
    }


def customers(contracts):
    ok = [c for c in contracts if c.get("status") in (1, 2)]
    ph = [c for c in ok if c.get("customerPhone")]
    cu = collections.defaultdict(lambda: {"n": 0, "rev": 0.0, "name": "", "first": None, "last": None})
    for c in ph:
        k = c["customerPhone"].strip()
        x = cu[k]
        x["n"] += 1
        x["rev"] += c.get("totalMoneyHire") or 0
        x["name"] = c.get("customerName") or x["name"]
        d = (c.get("createDate") or "")[:10]
        if d:
            x["first"] = min(x["first"] or d, d)
            x["last"] = max(x["last"] or d, d)
    lead = []
    for c in ok:
        try:
            cd = datetime.datetime.fromisoformat(c["createDate"][:19])
            md = datetime.datetime.fromisoformat(c["minDate"][:19])
            h = (md - cd).total_seconds() / 3600
            if -24 < h < 24 * 120:
                lead.append(h)
        except Exception:
            pass
    lead.sort()
    revs = sorted((x["rev"] for x in cu.values()), reverse=True)
    tot = sum(revs) or 1
    top10 = sum(revs[:max(1, len(revs) // 10)]) / tot * 100
    freq = collections.Counter(min(x["n"], 10) for x in cu.values())

    def pct(p):
        return lead[int(len(lead) * p / 100)] if lead else 0

    return {
        "n_contracts": len(ok), "with_phone": len(ph),
        "phone_rate": len(ph) / len(ok) * 100 if ok else 0,
        "unique": len(cu),
        "repeat": sum(1 for x in cu.values() if x["n"] > 1),
        "repeat_rate": (sum(1 for x in cu.values() if x["n"] > 1) / len(cu) * 100) if cu else 0,
        "ltv_median": statistics.median(revs) if revs else 0,
        "ltv_mean": statistics.mean(revs) if revs else 0,
        "top10_share": top10, "freq": dict(sorted(freq.items())),
        "lead_p": {p: pct(p) for p in (10, 25, 50, 75, 90)},
        "lead_under2h": (sum(1 for h in lead if h < 2) / len(lead) * 100) if lead else 0,
        "lead_under24h": (sum(1 for h in lead if h < 24) / len(lead) * 100) if lead else 0,
        "fixed": sum(1 for c in ok if c.get("contractType") == 1),
        "flex": sum(1 for c in ok if c.get("contractType") == 2),
        "top": sorted(({"phone": k, **v} for k, v in cu.items()), key=lambda x: -x["rev"])[:20],
        "type_rev": {t: sum(c.get("totalMoneyHire") or 0 for c in ok if c.get("contractType") == t)
                     for t in (1, 2, 3)},
    }
