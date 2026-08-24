#!/usr/bin/env python3
"""
ARENA DASHBOARD — realtime, chạy local.

    python3 app.py

Rồi mở http://localhost:8787

Không cần cài gì thêm (chỉ dùng thư viện chuẩn của Python 3).
"""
import json, os, sys, datetime, threading, http.server, socketserver, urllib.parse, collections, traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine import (Api, compute, customers, build_price_table, price_per_min,
                    HOURS, OPEN_M, CLOSE_M, PEAK_S, PEAK_E, DOW_VI, merge)

# ══════════════════════════════════════════════════════════════
#  CẤU HÌNH — sửa ở đây
# ══════════════════════════════════════════════════════════════
BASE_URL = "https://api.quanlysan.vn/api"

HUBS = {
    # "Tên hiển thị": {"token": "...", "shop_id": 0000},
    "Arena.03": {"token": os.environ.get("ARENA03_TOKEN", ""), "shop_id": 6097},
    # Bỏ dấu # ở 2 dòng dưới khi xin được token:
    # "Arena.01": {"token": os.environ.get("ARENA01_TOKEN", ""), "shop_id": 5981},
    # "Arena.02": {"token": os.environ.get("ARENA02_TOKEN", ""), "shop_id": 5980},
}

PORT = int(os.environ.get("PORT", 8787))
REFRESH_SEC = 120          # dashboard tự làm mới sau bao nhiêu giây
CACHE_TTL = 90             # giữ cache bao lâu trước khi gọi lại API
DEFAULT_DAYS = 28          # cửa sổ phân tích mặc định
# ══════════════════════════════════════════════════════════════

_cache, _lock = {}, threading.Lock()


def cached(key, ttl, fn):
    now = datetime.datetime.now().timestamp()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    val = fn()
    with _lock:
        _cache[key] = (now, val)
    return val


def load(hub, days):
    cfg = HUBS[hub]
    api = Api(BASE_URL, cfg["token"])
    today = datetime.date.today()
    d2, d1 = today, today - datetime.timedelta(days=days - 1)
    hist2 = today - datetime.timedelta(days=1)
    hist1 = hist2 - datetime.timedelta(days=days - 1)

    def pull():
        sched = api.schedule(str(hist1), str(hist2))
        con = api.contracts(str(hist1), str(hist2))
        con90 = api.contracts(str(today - datetime.timedelta(days=89)), str(today))
        today_s = api.schedule(str(today), str(today))
        fwd = api.schedule(str(today), str(today + datetime.timedelta(days=6)))
        try:
            rep = api.report_money(cfg["shop_id"], str(hist1), str(hist2))
            rep = rep[0] if rep else []
        except Exception:
            rep = []
        try:
            cancel = api.report_cancel(cfg["shop_id"], str(hist1), str(hist2))
            cancel = cancel[0] if cancel else {}
        except Exception:
            cancel = {}
        return {"sched": sched, "con": con, "con90": con90, "today": today_s,
                "fwd": fwd, "rep": rep, "cancel": cancel,
                "range": (str(hist1), str(hist2)), "pulled": datetime.datetime.now().isoformat()}

    return cached(f"{hub}:{days}", CACHE_TTL, pull)


# ───────────────────────── helpers ─────────────────────────
def vnd(x):
    try:
        return f"{round(x):,}".replace(",", ".") + "đ"
    except Exception:
        return "—"


def num(x):
    return f"{round(x):,}".replace(",", ".")


def short(x):
    x = x or 0
    if abs(x) >= 1_000_000_000:
        return f"{x/1_000_000_000:.2f} tỷ"
    if abs(x) >= 1_000_000:
        return f"{x/1_000_000:.1f}tr"
    if abs(x) >= 1000:
        return f"{x/1000:.0f}k"
    return f"{x:.0f}"


def hm(m):
    return f"{int(m)//60:02d}:{int(m)%60:02d}"


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def heat_class(p):
    if p >= 85: return "h5"
    if p >= 65: return "h4"
    if p >= 40: return "h3"
    if p >= 15: return "h2"
    if p > 0:   return "h1"
    return "h0"


# ───────────────────────── render ─────────────────────────
def kpi(label, val, note="", tone=""):
    return (f'<div class="kpi {tone}"><span class="kl">{esc(label)}</span>'
            f'<p class="kv">{val}</p><span class="kn">{esc(note)}</span></div>')


def render_main(hub, days):
    D = load(hub, days)
    sched, con, con90 = D["sched"], D["con"], D["con90"]
    m = compute(sched, con)
    cu = customers(con90)
    names, nd, nc = m["fields"], m["nd"], m["nc"]
    ptab = m["ptab"]
    order = sorted(names, key=lambda f: names[f])
    today = datetime.date.today()

    rep_money = sum(x.get("totalMoneyHire") or 0 for x in (D["rep"] or []))
    rep_min = sum(x.get("totalTimeMinute") or 0 for x in (D["rep"] or []))
    money = rep_money or m["listed_rev"]
    per_h = (money / m["sold_hours"]) if m["sold_hours"] else 0
    realization = (rep_money / m["listed_rev"] * 100) if (rep_money and m["listed_rev"]) else 0

    # ---- doanh thu niêm yết theo sân & theo (sân,giờ) ----
    rev_court = collections.Counter()
    rev_court_hour = collections.Counter()
    for b in sched.get("getScheduleBookeds") or []:
        if b.get("bookedType") == 4:
            continue
        d = datetime.date.fromisoformat(b["bookedDay"][:10])
        fixed = b.get("bookedType") in (1, 5)
        for mm in range(max(b["startTime"], OPEN_M), min(b["endTime"], CLOSE_M)):
            v = price_per_min(ptab, d, mm, fixed)
            rev_court[b["fieldId"]] += v
            rev_court_hour[(b["fieldId"], mm // 60)] += v

    # ---- lịch hôm nay ----
    tv = D["today"]
    tnames = {f["fieldId"]: f["fieldName"] for f in (tv.get("getScheduleFields") or [])} or names
    tbook = collections.defaultdict(list)
    for b in tv.get("getScheduleBookeds") or []:
        tbook[b["fieldId"]].append((b["startTime"], b["endTime"], b.get("bookedType")))
    now_m = datetime.datetime.now().hour * 60 + datetime.datetime.now().minute
    busy_now = sum(1 for f in tnames for s, e, _ in tbook.get(f, []) if s <= now_m < e)

    # ---- cơ hội: giờ vàng còn trống 7 ngày tới ----
    fv = D["fwd"]
    fb = collections.defaultdict(list)
    for b in fv.get("getScheduleBookeds") or []:
        fb[(b["bookedDay"][:10], b["fieldId"])].append((b["startTime"], b["endTime"]))
    opp, opp_val, opp_h = [], 0.0, 0.0
    for i in range(7):
        d = today + datetime.timedelta(days=i)
        for fid in order:
            cur = PEAK_S
            free = []
            for s, e in merge(fb.get((str(d), fid), [])):
                if e <= PEAK_S or s >= PEAK_E:
                    continue
                if s > cur:
                    free.append((cur, min(s, PEAK_E)))
                cur = max(cur, e)
            if cur < PEAK_E:
                free.append((cur, PEAK_E))
            for s, e in free:
                if e - s < 60:
                    continue
                if d == today and e * 1 <= now_m:
                    continue
                val = sum(price_per_min(ptab, d, x) for x in range(s, e))
                opp.append({"d": d, "f": names.get(fid, fid), "s": s, "e": e, "v": val})
                opp_val += val
                opp_h += (e - s) / 60
    opp.sort(key=lambda o: (o["d"], o["s"]))

    cap_h = nc * (CLOSE_M - OPEN_M) / 60 * nd
    idle_h = cap_h - m["sold_hours"]
    frag_i = m["frag_interior"]
    frag_val = sum(sum(price_per_min(ptab, datetime.date.fromisoformat(f["day"]), x)
                       for x in range(f["s"], f["e"])) for f in frag_i)
    cancel = D["cancel"] or {}
    n_cancel = (cancel.get("contractFixTerm") or 0) + (cancel.get("contractFlexible") or 0)

    H = []
    A = H.append

    # ═══ KPI ═══
    A('<section class="band"><div class="kpis">')
    A(kpi("Occupancy kỳ", f'{m["occ"]:.1f}%', f'{days} ngày · {nc} sân', "accent"))
    A(kpi("Doanh thu sân", short(money), f'{m["sold_hours"]:.0f} giờ-sân bán được'))
    A(kpi("Thực thu / giờ-sân", vnd(per_h), f'niêm yết {vnd(m["listed_rev"]/m["sold_hours"] if m["sold_hours"] else 0)}'))
    A(kpi("Price realization", f'{realization:.1f}%' if realization else "—",
          "thu về / giá niêm yết", "warn" if realization and realization < 95 else ""))
    A(kpi("Đang chơi lúc này", f'{busy_now}/{len(tnames)}', f'{hm(now_m)} hôm nay', "live"))
    A(kpi("Giờ-sân trống", num(idle_h), f'trần cơ hội {short(idle_h*per_h)}'))
    A('</div></section>')

    # ═══ LỊCH HÔM NAY ═══
    A('<section class="band"><div class="sh"><h2>Lịch hôm nay <span class="live-dot"></span></h2>'
      f'<p>{today.strftime("%d/%m/%Y")} · {DOW_VI[today.weekday()]} · vạch đỏ là thời điểm hiện tại</p></div>')
    A('<div class="scroll"><table class="grid"><thead><tr><th class="stick">Sân</th>')
    for h in HOURS:
        A(f'<th>{h:02d}</th>')
    A('</tr></thead><tbody>')
    for fid in sorted(tnames, key=lambda f: tnames[f]):
        A(f'<tr><td class="stick">{esc(tnames[fid])}</td>')
        for h in HOURS:
            filled = 0
            for s, e, bt in tbook.get(fid, []):
                filled += max(0, min(e, (h+1)*60) - max(s, h*60))
            cls = heat_class(filled / 60 * 100)
            nowc = " nowcol" if h == now_m // 60 else ""
            A(f'<td class="{cls}{nowc}"></td>')
        A('</tr>')
    A('</tbody></table></div>')
    A('<div class="legend"><span><i class="sw h0"></i>trống</span><span><i class="sw h2"></i>một phần</span>'
      '<span><i class="sw h5"></i>kín</span></div></section>')

    # ═══ CƠ HỘI BÁN NGAY ═══
    A('<section class="band"><div class="sh"><h2>Giờ vàng còn trống — 7 ngày tới</h2>'
      f'<p>Khoảng trống ≥60 phút trong khung 17–21h. Đây là hàng bán được ngay, không phải thống kê quá khứ.</p></div>')
    A('<div class="kpis tight">')
    A(kpi("Slot trống", f'{len(opp)}', "khung ≥60 phút", "warn"))
    A(kpi("Giờ-sân", f'{opp_h:.0f}', "trong giờ vàng"))
    A(kpi("Giá trị", short(opp_val), "nếu bán hết", "accent"))
    A('</div>')
    if opp:
        byday = collections.OrderedDict()
        for o in opp:
            k = o["d"]
            b = byday.setdefault(k, {"n": 0, "h": 0.0, "v": 0.0})
            b["n"] += 1; b["h"] += (o["e"]-o["s"])/60; b["v"] += o["v"]
        A('<div class="two"><div><h3>Tổng hợp theo ngày</h3>'
          '<table class="mini"><thead><tr><th>Ngày</th><th>Slot</th><th>Giờ</th><th>Giá trị</th>'
          '</tr></thead><tbody>')
        mx = max(b["v"] for b in byday.values()) or 1
        for d, b in byday.items():
            A(f'<tr><td>{d.strftime("%d/%m")} {DOW_VI[d.weekday()]}</td><td class="n">{b["n"]}</td>'
              f'<td class="n">{b["h"]:.0f}</td><td class="n">{short(b["v"])}</td>'
              f'<td class="barcell"><i style="width:{b["v"]/mx*100:.0f}%"></i></td></tr>')
        A('</tbody></table></div>')
        A('<div><h3>Slot lớn nhất — gọi khách ngay</h3>'
          '<p class="fine">Sắp theo giá trị. Đây là danh sách để team booking chủ động chào, '
          'thay vì ngồi đợi tin nhắn tới.</p>'
          '<table class="mini"><thead><tr><th>Ngày</th><th>Sân</th><th>Khung giờ</th><th>Giá trị</th>'
          '</tr></thead><tbody>')
        for o in sorted(opp, key=lambda x: -x["v"])[:12]:
            A(f'<tr><td>{o["d"].strftime("%d/%m")} {DOW_VI[o["d"].weekday()]}</td><td>{esc(o["f"])}</td>'
              f'<td class="n">{hm(o["s"])}–{hm(o["e"])}</td><td class="n">{vnd(o["v"])}</td></tr>')
        A('</tbody></table></div></div>')
    else:
        A('<p class="fine">Giờ vàng đã kín hết 7 ngày tới.</p>')
    A('</section>')

    # ═══ HEATMAP SÂN × GIỜ ═══
    A('<section class="band"><div class="sh"><h2>Occupancy theo sân × khung giờ</h2>'
      f'<p>Bình quân {days} ngày. Mỗi ô là một khung 60 phút. Đây là bản đồ chi tiết nhất — '
      'ô càng nhạt càng là chỗ đang mất tiền.</p></div>')
    A('<div class="scroll"><table class="grid"><thead><tr><th class="stick">Sân</th>')
    for h in HOURS:
        A(f'<th>{h:02d}</th>')
    A('<th>TB</th></tr></thead><tbody>')
    for fid in order:
        A(f'<tr><td class="stick">{esc(names[fid])}</td>')
        for h in HOURS:
            p = m["grid"][(fid, h)] / (60 * nd) * 100
            A(f'<td class="{heat_class(p)}" title="{names[fid]} {h:02d}h — {p:.0f}%">{p:.0f}</td>')
        tot = m["per_court"][fid] / ((CLOSE_M - OPEN_M) * nd) * 100
        A(f'<td class="tot n">{tot:.0f}%</td>')
    A('</tr>')
    A('<tr class="foot-row"><td class="stick">TB</td>')
    for h in HOURS:
        p = m["byhour"][h] / (nc * 60 * nd) * 100
        A(f'<td class="{heat_class(p)}">{p:.0f}</td>')
    A(f'<td class="tot n">{m["occ"]:.0f}%</td></tr>')
    A('</tbody></table></div></section>')

    # ═══ HEATMAP THỨ × GIỜ ═══
    A('<section class="band"><div class="sh"><h2>Occupancy theo thứ × khung giờ</h2>'
      '<p>Cùng dữ liệu, cắt theo ngày trong tuần — để biết nên chạy khuyến mãi vào thứ mấy.</p></div>')
    A('<div class="scroll"><table class="grid"><thead><tr><th class="stick">Thứ</th>')
    for h in HOURS:
        A(f'<th>{h:02d}</th>')
    A('</tr></thead><tbody>')
    for w in range(7):
        ndw = m["dow_days"][w] or 1
        A(f'<tr><td class="stick">{DOW_VI[w]}</td>')
        for h in HOURS:
            p = m["bydow_hour"][(w, h)] / (nc * 60 * ndw) * 100
            A(f'<td class="{heat_class(p)}">{p:.0f}</td>')
        A('</tr>')
    A('</tbody></table></div></section>')

    # ═══ THEO KHUNG GIỜ ═══
    A('<section class="band"><div class="sh"><h2>Chi tiết theo khung giờ 60 phút</h2>'
      '<p>Cột <em>trần cơ hội</em> = doanh thu nếu lấp kín khung đó, quy về một tháng. '
      'Đây là bảng để quyết định đổ tiền marketing vào giờ nào.</p></div>')
    A('<div class="scroll"><table><thead><tr><th>Khung</th><th>Occ.</th><th>Giờ-sân bán</th>'
      '<th>Doanh thu kỳ</th><th>Giá niêm yết</th><th>Giờ-sân trống/tháng</th>'
      '<th>Trần cơ hội/tháng</th></tr></thead><tbody>')
    for h in HOURS:
        sold = m["byhour"][h] / 60
        caph = nc * nd
        p = sold / caph * 100 if caph else 0
        rev = m["listed_by_hour"][h]
        list_rate = (rev / sold) if sold else price_per_min(ptab, today, h * 60 + 30) * 60
        idle_mo = (caph - sold) / nd * 30
        cls = "row-peak" if PEAK_S <= h * 60 < PEAK_E else ("row-dead" if p < 15 else "")
        A(f'<tr class="{cls}"><td class="n">{h:02d}:00–{h+1:02d}:00</td><td class="n">{p:.1f}%</td>'
          f'<td class="n">{sold:.0f}</td><td class="n">{short(rev)}</td>'
          f'<td class="n">{vnd(list_rate)}</td><td class="n">{idle_mo:,.0f}</td>'
          f'<td class="n">{short(idle_mo*list_rate)}</td></tr>')
    A('</tbody></table></div>')
    A('<div class="legend"><span><i class="sw row-peak-sw"></i>giờ vàng 17–21h</span>'
      '<span><i class="sw row-dead-sw"></i>occupancy &lt;15%</span></div></section>')

    # ═══ THEO SÂN ═══
    rank = sorted(order, key=lambda f: m["per_court_peak"][f])
    A('<section class="band"><div class="sh"><h2>Chi tiết theo sân</h2>'
      '<p>Cột <em>thứ tự gán</em> là bảng tra cho nhân viên: khi khách không chọn sân, '
      'gán từ trên xuống — bán sân khó bán trước, giữ sân dễ bán lại.</p></div>')
    A('<div class="scroll"><table><thead><tr><th>Thứ tự gán</th><th>Sân</th><th>fieldID</th>'
      '<th>Occ. cả ngày</th><th>Occ. giờ vàng</th><th>Lượt đặt</th><th>Giờ bán</th>'
      '<th>Doanh thu</th><th>Mảnh vụn gây ra</th></tr></thead><tbody>')
    for i, fid in enumerate(rank, 1):
        allp = m["per_court"][fid] / ((CLOSE_M - OPEN_M) * nd) * 100
        pkp = m["per_court_peak"][fid] / ((PEAK_E - PEAK_S) * nd) * 100
        A(f'<tr><td class="n rankcell">{i}</td><td><strong>{esc(names[fid])}</strong></td>'
          f'<td class="n dim">{fid}</td><td class="n">{allp:.1f}%</td><td class="n">{pkp:.1f}%</td>'
          f'<td class="n">{m["per_court_bk"][fid]}</td><td class="n">{m["per_court"][fid]/60:.0f}</td>'
          f'<td class="n">{short(rev_court[fid])}</td>'
          f'<td class="n">{m["frag_by_court"][fid]}</td></tr>')
    A('</tbody></table></div></section>')

    # ═══ PRICING ═══
    A('<section class="band"><div class="sh"><h2>Bảng giá &amp; thất thoát giá</h2>'
      '<p>Bảng giá lấy trực tiếp từ cấu hình trên G-Sport. '
      '<em>Price realization</em> so tiền thực thu với tiền lẽ ra thu được nếu bán đúng giá niêm yết.</p></div>')
    A('<div class="kpis tight">')
    A(kpi("Giá niêm yết bình quân", vnd(m["listed_rev"]/m["sold_hours"] if m["sold_hours"] else 0), "/giờ-sân"))
    A(kpi("Thực thu bình quân", vnd(per_h), "/giờ-sân"))
    A(kpi("Realization", f'{realization:.1f}%' if realization else "—",
          "gần 100% = không rò rỉ giá", "accent" if realization >= 95 else "warn"))
    A(kpi("Giảm giá ghi nhận", short(m["discount"]), f'{m["discount"]/money*100:.1f}% doanh thu' if money else ""))
    A('</div>')
    seen, rows = set(), []
    for pr in ptab:
        if pr["s"] == pr["e"]:
            lbl = "Mặc định (khung không có quy tắc riêng)"
        else:
            lbl = f'{hm(pr["s"])}–{hm(pr["e"])}'
        dws = "Cả tuần" if (-111 in pr["dows"] or len(pr["dows"]) >= 7) else \
              " ".join(DOW_VI[d-2] for d in sorted(pr["dows"]) if 2 <= d <= 8)
        k = (lbl, dws)
        if k in seen:
            continue
        seen.add(k)
        rows.append((pr["s"], lbl, dws, pr["custom"]*60, pr["fixed"]*60))
    A('<div class="scroll"><table><thead><tr><th>Khung giờ</th><th>Áp dụng</th>'
      '<th>Giá lịch ngày</th><th>Giá lịch cố định</th></tr></thead><tbody>')
    for _, lbl, dws, cst, fxd in sorted(rows):
        A(f'<tr><td class="n">{esc(lbl)}</td><td>{esc(dws)}</td>'
          f'<td class="n">{vnd(cst) if cst else "—"}</td><td class="n">{vnd(fxd) if fxd else "—"}</td></tr>')
    A('</tbody></table></div></section>')

    # ═══ MẢNH VỤN ═══
    A('<section class="band"><div class="sh"><h2>Mảnh vụn lịch trong giờ vàng</h2>'
      f'<p>Khoảng trống dưới {sched.get("minTime") or 60} phút — hệ thống không cho đặt, nên là hàng chết. '
      'Chỉ loại <em>kẹt giữa</em> là do xếp lịch sai và tránh được.</p></div>')
    A('<div class="kpis tight">')
    A(kpi("Kẹt giữa hai booking", f'{len(frag_i)}', "tránh được bằng quy tắc dán sát mép", "warn"))
    A(kpi("Sát mép cửa sổ", f'{len(m["frag_edge"])}', "do khách chọn giờ, khó tránh"))
    A(kpi("Giá trị kẹt", short(frag_val), f'trong {days} ngày'))
    A(kpi("Quy đổi / tháng", short(frag_val/nd*30), "một hub"))
    A('</div>')
    if frag_i:
        A('<div class="scroll"><table><thead><tr><th>Ngày</th><th>Sân</th><th>Khoảng kẹt</th><th>Phút</th>'
          '</tr></thead><tbody>')
        for f in frag_i[:25]:
            dd = datetime.date.fromisoformat(f["day"])
            A(f'<tr><td>{dd.strftime("%d/%m")} {DOW_VI[dd.weekday()]}</td><td>{esc(f["field"])}</td>'
              f'<td class="n">{hm(f["s"])}–{hm(f["e"])}</td><td class="n">{f["len"]}</td></tr>')
        A('</tbody></table></div>')
    A('</section>')

    # ═══ KHÁCH HÀNG ═══
    A('<section class="band"><div class="sh"><h2>Khách hàng — 90 ngày</h2>'
      '<p>Ghép theo số điện thoại. Cửa sổ 90 ngày để đủ mẫu cho hành vi quay lại.</p></div>')
    A('<div class="kpis">')
    A(kpi("Khách unique", f'{cu["unique"]:,}'.replace(",", "."), f'{cu["n_contracts"]:,} hợp đồng'.replace(",", ".")))
    A(kpi("Tỉ lệ quay lại", f'{cu["repeat_rate"]:.1f}%', f'{cu["repeat"]} khách đặt >1 lần', "accent"))
    A(kpi("LTV trung vị", vnd(cu["ltv_median"]), f'trung bình {vnd(cu["ltv_mean"])}'))
    A(kpi("Top 10% khách", f'{cu["top10_share"]:.1f}%', "doanh thu đến từ nhóm này", "warn"))
    A(kpi("Có số điện thoại", f'{cu["phone_rate"]:.1f}%', "khoá nối CRM",
          "" if cu["phone_rate"] > 90 else "warn"))
    A(kpi("Huỷ trong kỳ", f'{n_cancel}', f'{days} ngày'))
    A('</div>')

    A('<div class="two">')
    A('<div><h3>Khách đặt trước bao lâu</h3><p class="fine">Phân vị thời gian từ lúc tạo đơn tới giờ chơi. '
      'Càng ngắn thì tốc độ trả lời tin nhắn càng quyết định doanh thu.</p><table class="mini"><tbody>')
    for p, v in cu["lead_p"].items():
        A(f'<tr><td>p{p}</td><td class="n">{v:.1f} giờ</td></tr>')
    A(f'<tr class="hi"><td>Đặt gấp &lt;2h</td><td class="n">{cu["lead_under2h"]:.1f}%</td></tr>')
    A(f'<tr class="hi"><td>Trong vòng 24h</td><td class="n">{cu["lead_under24h"]:.1f}%</td></tr>')
    A('</tbody></table></div>')

    A('<div><h3>Tần suất đặt / khách</h3><p class="fine">Số hợp đồng mỗi khách trong 90 ngày (10 = từ 10 trở lên).</p>'
      '<table class="mini"><tbody>')
    mx = max(cu["freq"].values()) if cu["freq"] else 1
    for k, v in cu["freq"].items():
        A(f'<tr><td>{k}{"+" if k==10 else ""} lần</td><td class="n">{v}</td>'
          f'<td class="barcell"><i style="width:{v/mx*100:.0f}%"></i></td></tr>')
    A('</tbody></table></div>')
    A('</div>')

    A('<h3 style="margin-top:2rem">Top 20 khách theo doanh thu</h3>')
    A('<div class="scroll"><table><thead><tr><th>#</th><th>Khách</th><th>Điện thoại</th>'
      '<th>Số lần</th><th>Doanh thu 90 ngày</th><th>TB/lần</th><th>Lần cuối</th></tr></thead><tbody>')
    for i, t in enumerate(cu["top"], 1):
        ph = t["phone"]
        mask = ph[:4] + "***" + ph[-2:] if len(ph) > 6 else ph
        A(f'<tr><td class="n dim">{i}</td><td><strong>{esc(t["name"])}</strong></td>'
          f'<td class="n">{esc(mask)}</td><td class="n">{t["n"]}</td>'
          f'<td class="n">{vnd(t["rev"])}</td><td class="n">{vnd(t["rev"]/t["n"])}</td>'
          f'<td class="n dim">{esc(t["last"] or "—")}</td></tr>')
    A('</tbody></table></div>')
    A(f'<p class="fine">Cố định {cu["fixed"]} HĐ ({short(cu["type_rev"].get(1,0))}) · '
      f'Linh hoạt {cu["flex"]} HĐ ({short(cu["type_rev"].get(2,0))}). '
      'Số điện thoại được che một phần; bản đầy đủ nằm trong G-Sport.</p>')
    A('</section>')

    A(f'<p class="stamp">Dữ liệu kéo lúc {D["pulled"][11:19]} · cửa sổ phân tích '
      f'{D["range"][0]} → {D["range"][1]} · nguồn Mewin Partner API</p>')
    return "".join(H)


CSS = """
:root{
 --ink:#0C1512;--ink2:#3D4B45;--dim:#6B7A72;--bg:#EDF0EC;--card:#F6F8F5;
 --line:#C9D2CB;--line2:#DDE3DC;--court:#1B6B4F;--peak:#A8481A;--peak-w:#F7E7DC;
 --cool:#2A6483;--on:#F6F8F5;
 --h0:#E4E9E4;--h1:#D3E4DA;--h2:#A9CFBD;--h3:#6FB496;--h4:#3C9070;--h5:#1B6B4F;
 --hi0:var(--ink2);--hi1:var(--ink2);--hi2:var(--ink);--hi3:#0C1512;--hi4:#F6F8F5;--hi5:#F6F8F5;
 --fd:"Be Vietnam Pro",-apple-system,"Segoe UI",system-ui,sans-serif;
 --fm:"IBM Plex Mono",ui-monospace,SFMono-Regular,Consolas,monospace;
}
@media(prefers-color-scheme:dark){:root{
 --ink:#E3E9E2;--ink2:#A9B6AE;--dim:#7C8A82;--bg:#0B120F;--card:#121B17;
 --line:#29352E;--line2:#1D2721;--court:#4FAE84;--peak:#DE8B57;--peak-w:#2A1B12;
 --cool:#6FAAC9;--on:#08110D;
 --h0:#151E19;--h1:#1B3A2C;--h2:#245442;--h3:#2F7458;--h4:#3E9770;--h5:#58BC92;
 --hi0:var(--ink2);--hi1:var(--ink2);--hi2:#E3E9E2;--hi3:#E3E9E2;--hi4:#08110D;--hi5:#08110D;
}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--fd);
 font-size:15px;line-height:1.5;-webkit-font-smoothing:antialiased}
.wrap{max-width:1400px;margin:0 auto;padding:0 20px 80px}
header.top{padding:28px 0 0}
.brand{font-size:12px;letter-spacing:.2em;text-transform:uppercase;color:var(--dim);margin:0 0 8px}
h1{font-size:34px;font-weight:800;letter-spacing:-.03em;margin:0 0 4px;line-height:1.05}
.sub{color:var(--ink2);margin:0}
.bar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:18px 0 0;
 padding:12px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.bar a{font-family:var(--fd);font-size:13px;font-weight:600;text-decoration:none;color:var(--ink2);
 border:1px solid var(--line);padding:6px 12px;border-radius:2px}
.bar a.on{background:var(--court);color:var(--on);border-color:var(--court)}
.bar .grow{flex:1}
.tick{font-family:var(--fm);font-size:12px;color:var(--dim)}
.live-dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--peak);
 margin-left:8px;vertical-align:middle;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}
@media(prefers-reduced-motion:reduce){.live-dot{animation:none}}
.band{margin:38px 0 0;padding-top:26px;border-top:1px solid var(--line2)}
.band:first-of-type{border-top:0;padding-top:14px}
.sh{margin-bottom:16px}
.sh h2{font-size:20px;font-weight:800;letter-spacing:-.02em;margin:0 0 3px}
.sh p{margin:0;color:var(--ink2);font-size:14px;max-width:70ch}
h3{font-size:15px;font-weight:600;margin:0 0 4px}
em{font-style:italic}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));
 gap:1px;background:var(--line2);border:1px solid var(--line2)}
.kpis.tight{grid-template-columns:repeat(auto-fit,minmax(150px,1fr))}
.kpi{background:var(--bg);padding:14px 16px 16px}
.kpi .kl{font-size:11px;font-weight:600;letter-spacing:.09em;text-transform:uppercase;color:var(--dim)}
.kpi .kv{font-family:var(--fm);font-size:25px;font-weight:600;letter-spacing:-.02em;
 margin:4px 0 2px;font-variant-numeric:tabular-nums}
.kpi .kn{font-size:12.5px;color:var(--ink2);line-height:1.35;display:block}
.kpi.accent .kv{color:var(--court)}
.kpi.warn .kv{color:var(--peak)}
.kpi.live .kv{color:var(--peak)}
.scroll{overflow-x:auto;border:1px solid var(--line2)}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{text-align:left;padding:8px 11px;border-bottom:1px solid var(--line2);white-space:nowrap}
th{font-size:11px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;
 color:var(--dim);background:var(--card);border-bottom:1px solid var(--line);position:sticky;top:0}
td.n{font-family:var(--fm);font-variant-numeric:tabular-nums}
td.dim{color:var(--dim)}
tbody tr:last-child td{border-bottom:0}
tr.row-peak td{background:var(--peak-w)}
tr.row-dead td{opacity:.62}
.rankcell{font-weight:600;color:var(--court)}
table.grid td{padding:0;height:26px;min-width:26px;text-align:center;
 font-family:var(--fm);font-size:10.5px;border:1px solid var(--bg)}
table.grid th{min-width:26px;text-align:center;padding:6px 2px;font-size:10.5px}
table.grid .stick{position:sticky;left:0;background:var(--card);z-index:2;
 text-align:left;padding:0 10px;font-family:var(--fd);font-size:12.5px;font-weight:600;min-width:74px}
table.grid td.tot{background:var(--card);font-weight:600;padding:0 8px}
.foot-row td{border-top:2px solid var(--line)}
.nowcol{outline:2px solid var(--peak);outline-offset:-2px}
.h0{background:var(--h0);color:var(--hi0)}.h1{background:var(--h1);color:var(--hi1)}
.h2{background:var(--h2);color:var(--hi2)}.h3{background:var(--h3);color:var(--hi3)}
.h4{background:var(--h4);color:var(--hi4)}.h5{background:var(--h5);color:var(--hi5)}
.legend{display:flex;flex-wrap:wrap;gap:16px;margin-top:10px;font-size:12.5px;color:var(--dim)}
.legend span{display:inline-flex;align-items:center;gap:6px}
.sw{width:12px;height:12px;display:inline-block;border:1px solid var(--line)}
.row-peak-sw{background:var(--peak-w)}.row-dead-sw{background:var(--h1);opacity:.62}
.two{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:28px;margin-top:8px}
table.mini{font-size:13.5px;border:1px solid var(--line2)}
table.mini td{padding:6px 11px}
table.mini th{padding:6px 11px;position:static}
table.mini tr.hi td{font-weight:600;background:var(--card)}
.barcell{width:45%}
.barcell i{display:block;height:9px;background:var(--court);opacity:.65}
.fine{font-size:12.5px;color:var(--dim);margin:8px 0 0;max-width:75ch}
.stamp{font-family:var(--fm);font-size:11.5px;color:var(--dim);margin-top:34px;
 padding-top:12px;border-top:1px solid var(--line2)}
.err{border:1px solid var(--peak);background:var(--peak-w);color:var(--peak);
 padding:16px;margin-top:24px;font-size:14px}
.err pre{white-space:pre-wrap;font-family:var(--fm);font-size:11.5px;margin:8px 0 0}
@media(max-width:700px){h1{font-size:26px}.wrap{padding:0 13px 50px}.kpi .kv{font-size:21px}}
"""

SHELL = """<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Arena Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;600;800&family=IBM+Plex+Mono:wght@500;600&display=swap">
<style>%(css)s</style></head><body><div class="wrap">
<header class="top">
  <p class="brand">arena by lona&amp;co</p>
  <h1>Bảng điều khiển vận hành</h1>
  <p class="sub">Occupancy, giá, sân và khách hàng — đọc thẳng từ Mewin Partner API.</p>
  <nav class="bar">%(nav)s<span class="grow"></span>
    <span class="tick" id="tick">cập nhật lúc %(now)s</span></nav>
</header>
<main id="main">%(main)s</main></div>
<script>
const RS=%(refresh)d, Q=location.search;
let busy=false;
async function tick(){
  if(busy||document.hidden) return;
  busy=true;
  try{
    const r=await fetch('/partial'+Q,{cache:'no-store'});
    if(r.ok){
      document.getElementById('main').innerHTML=await r.text();
      document.getElementById('tick').textContent=
        'cập nhật lúc '+new Date().toLocaleTimeString('vi-VN');
    }
  }catch(e){
    document.getElementById('tick').textContent='mất kết nối — đang thử lại';
  }finally{ busy=false; }
}
setInterval(tick, RS*1000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)tick();});
</script></body></html>"""


def nav_html(hub, days):
    out = []
    for h in HUBS:
        cls = " class=\"on\"" if h == hub else ""
        out.append(f'<a href="/?hub={urllib.parse.quote(h)}&days={days}"{cls}>{esc(h)}</a>')
    out.append('<span style="width:14px"></span>')
    for d in (7, 28, 90):
        cls = " class=\"on\"" if d == days else ""
        out.append(f'<a href="/?hub={urllib.parse.quote(hub)}&days={d}"{cls}>{d} ngày</a>')
    return "".join(out)


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, ctype="text/html; charset=utf-8", code=200):
        b = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        hub = q.get("hub", [next(iter(HUBS))])[0]
        if hub not in HUBS:
            hub = next(iter(HUBS))
        try:
            days = max(1, min(365, int(q.get("days", [DEFAULT_DAYS])[0])))
        except ValueError:
            days = DEFAULT_DAYS

        if u.path not in ("/", "/partial"):
            self._send("404", code=404)
            return
        try:
            main = render_main(hub, days)
        except Exception:
            main = ('<div class="err"><strong>Không lấy được dữ liệu.</strong> '
                    'Kiểm tra token và kết nối mạng, rồi tải lại trang.'
                    f'<pre>{esc(traceback.format_exc()[-1500:])}</pre></div>')
        if u.path == "/partial":
            self._send(main)
            return
        self._send(SHELL % {
            "css": CSS, "nav": nav_html(hub, days), "main": main,
            "now": datetime.datetime.now().strftime("%H:%M:%S"),
            "refresh": REFRESH_SEC,
        })


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    missing = [h for h, c in HUBS.items() if not c["token"]]
    if missing:
        print("!! Chưa có token cho:", ", ".join(missing))
        print("   Đặt biến môi trường, ví dụ:  export ARENA03_TOKEN='...'\n")
    print(f"  Arena Dashboard  →  http://localhost:{PORT}")
    print(f"  Tự làm mới mỗi {REFRESH_SEC}s · Ctrl+C để dừng\n")
    with Server(("127.0.0.1", PORT), Handler) as s:
        try:
            s.serve_forever()
        except KeyboardInterrupt:
            print("\n  Đã dừng.")


if __name__ == "__main__":
    main()
