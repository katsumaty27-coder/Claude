#!/usr/bin/env python3
"""
取得済みの不動産取引価格データから、分析レポート(HTML)を生成するスクリプト。

data/YYYYQ#/transaction_prices_YYYYQ#.json を読み込み、以下の分析を行う:
  1. 区別 ㎡単価
  2. 予算2億円以内で狙える面積帯(3LDK以上・70㎡以上)
  3. 築年数と価格(㎡単価)の関係
  4. 間取り別の価格分布
  5. リノベーション有無による価格差
  6. 地区(町丁目)レベルの粒度(港区の例)
  7. 対象セグメントの取引件数(流動性)

出力: reports/report_<quarter>.html (自己完結HTML、外部依存なし)
"""

import json
import re
import statistics
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"

# 対象ワード(固定順 = カラースロット順)
WARD_ORDER = ["千代田区", "中央区", "港区", "新宿区", "文京区", "渋谷区", "品川区", "目黒区"]

# 検討スコープ: ファミリー向け間取りの判定用
FAMILY_FLOORPLAN_RE = re.compile(r"３ＬＤＫ|４ＬＤＫ|５ＬＤＫ")
BUDGET_YEN = 200_000_000  # 2億円

# --- 検証済みデフォルトパレット(dataviz skill references/palette.md) ---
CATEGORICAL = [
    ("#2a78d6", "#3987e5"),  # 1 blue
    ("#eb6834", "#d95926"),  # 2 orange
    ("#1baf7a", "#199e70"),  # 3 aqua
    ("#eda100", "#c98500"),  # 4 yellow
    ("#e87ba4", "#d55181"),  # 5 magenta
    ("#008300", "#008300"),  # 6 green
    ("#4a3aa7", "#9085e9"),  # 7 violet
    ("#e34948", "#e66767"),  # 8 red
]
WARD_COLOR = {ward: CATEGORICAL[i] for i, ward in enumerate(WARD_ORDER)}

FLOORPLAN_ORDER = ["１Ｒ", "１Ｋ", "１ＤＫ", "１ＬＤＫ", "２ＤＫ", "２ＬＤＫ", "３ＬＤＫ", "４ＬＤＫ"]
FLOORPLAN_COLOR = {fp: CATEGORICAL[i] for i, fp in enumerate(FLOORPLAN_ORDER)}
OTHER_GRAY = ("#898781", "#898781")


# ---------------------------------------------------------------------------
# データ読み込み・前処理
# ---------------------------------------------------------------------------

def load_quarter(quarter_dir: Path):
    files = list(quarter_dir.glob("transaction_prices_*.json"))
    if not files:
        return []
    with open(files[0], encoding="utf-8") as f:
        return json.load(f)


def to_float(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def building_age(building_year: str, report_year: int):
    if not building_year or "年" not in building_year:
        return None
    try:
        year = int(building_year.replace("年", "").strip())
        return report_year - year
    except ValueError:
        return None


def unit_price_man(trade_price_yen, area_sqm):
    """万円/㎡"""
    if area_sqm is None or area_sqm == 0:
        return None
    return (trade_price_yen / 10000) / area_sqm


def enrich(records, report_year):
    """数値フィールドを付加"""
    out = []
    for r in records:
        area = to_float(r.get("Area"))
        price = to_float(r.get("TradePrice"))
        if area is None or price is None or area <= 0:
            continue
        rec = dict(r)
        rec["_area"] = area
        rec["_price_man"] = price / 10000
        rec["_unit_price_man"] = unit_price_man(price, area)
        rec["_age"] = building_age(r.get("BuildingYear", ""), report_year)
        out.append(rec)
    return out


def is_family_scope(rec):
    fp = rec.get("FloorPlan", "")
    return bool(FAMILY_FLOORPLAN_RE.search(fp)) and rec["_area"] >= 70


def median(values):
    values = [v for v in values if v is not None]
    if not values:
        return None
    return statistics.median(values)


# ---------------------------------------------------------------------------
# SVG プリミティブ (dataviz skillのmark specに準拠)
# ---------------------------------------------------------------------------

def nice_max(value, headroom=1.15):
    v = value * headroom
    if v <= 0:
        return 1
    import math
    magnitude = 10 ** math.floor(math.log10(v))
    for mult in (1, 2, 2.5, 5, 10):
        step = magnitude * mult
        if step >= v:
            return step
    return v


def rounded_top_bar_path(x, y, w, h, r=4):
    r = max(0, min(r, w / 2, h))
    if h <= 0:
        return ""
    return (
        f"M{x:.1f},{y + h:.1f} L{x:.1f},{y + r:.1f} "
        f"Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} "
        f"L{x + w - r:.1f},{y:.1f} "
        f"Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f} "
        f"L{x + w:.1f},{y + h:.1f} Z"
    )


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def bar_chart(categories, values, colors, *, width=760, height=340,
              value_fmt=lambda v: f"{v:,.0f}", y_suffix="", n_labels=None,
              bar_cap=56):
    """1カテゴリ1本の縦棒グラフ。x軸ラベル=カテゴリ名(色と冗長なので凡例は省略)。"""
    margin = {"top": 24, "right": 20, "bottom": 56, "left": 64}
    plot_w = width - margin["left"] - margin["right"]
    plot_h = height - margin["top"] - margin["bottom"]

    valid_values = [v for v in values if v is not None]
    vmax = nice_max(max(valid_values) if valid_values else 1)

    n = len(categories)
    slot_w = plot_w / n
    bar_w = min(bar_cap, slot_w * 0.55)

    def ys(v):
        return margin["top"] + plot_h * (1 - v / vmax)

    parts = [f'<svg viewBox="0 0 {width} {height}" class="chart-svg" role="img" '
             f'aria-label="棒グラフ">']

    # gridlines + y-axis ticks
    steps = 4
    for i in range(steps + 1):
        v = vmax * i / steps
        y = ys(v)
        parts.append(f'<line x1="{margin["left"]}" y1="{y:.1f}" x2="{width - margin["right"]}" '
                      f'y2="{y:.1f}" class="gridline" />')
        parts.append(f'<text x="{margin["left"] - 8}" y="{y + 4:.1f}" class="axis-label" '
                      f'text-anchor="end">{v:,.0f}{y_suffix}</text>')

    # baseline
    y0 = ys(0)
    parts.append(f'<line x1="{margin["left"]}" y1="{y0:.1f}" x2="{width - margin["right"]}" '
                  f'y2="{y0:.1f}" class="baseline" />')

    for i, (cat, val, color) in enumerate(zip(categories, values, colors)):
        cx = margin["left"] + slot_w * i + slot_w / 2
        x = cx - bar_w / 2
        n_label = f"（n={n_labels[i]}）" if n_labels else ""
        if val is None:
            parts.append(f'<text x="{cx:.1f}" y="{y0 - 8:.1f}" class="axis-label" '
                          f'text-anchor="middle">データなし</text>')
        else:
            h = plot_h * (val / vmax)
            y = y0 - h
            path = rounded_top_bar_path(x, y, bar_w, h)
            light, dark = color
            parts.append(
                f'<path d="{path}" fill="{light}" class="bar-mark" '
                f'data-light="{light}" data-dark="{dark}" '
                f'data-tooltip="{esc(cat)}: {esc(value_fmt(val))}{y_suffix}{n_label}" />'
            )
            parts.append(f'<text x="{cx:.1f}" y="{y - 6:.1f}" class="value-label" '
                          f'text-anchor="middle">{esc(value_fmt(val))}</text>')
        parts.append(f'<text x="{cx:.1f}" y="{y0 + 20:.1f}" class="axis-label" '
                      f'text-anchor="middle">{esc(cat)}</text>')
        if n_labels:
            parts.append(f'<text x="{cx:.1f}" y="{y0 + 34:.1f}" class="axis-label-sub" '
                          f'text-anchor="middle">n={n_labels[i]}</text>')

    parts.append("</svg>")
    return "".join(parts)


def grouped_bar_chart(categories, series, *, width=760, height=360,
                       value_fmt=lambda v: f"{v:,.0f}", y_suffix=""):
    """series = [(label, color, [values...]), ...] 複数系列の比較棒グラフ"""
    margin = {"top": 24, "right": 20, "bottom": 56, "left": 64}
    plot_w = width - margin["left"] - margin["right"]
    plot_h = height - margin["top"] - margin["bottom"]

    all_vals = [v for _, _, vals in series for v in vals if v is not None]
    vmax = nice_max(max(all_vals) if all_vals else 1)

    n = len(categories)
    slot_w = plot_w / n
    n_series = len(series)
    group_w = min(slot_w * 0.72, 24 * n_series + 4 * (n_series - 1))
    bar_w = (group_w - 4 * (n_series - 1)) / n_series

    def ys(v):
        return margin["top"] + plot_h * (1 - v / vmax)

    parts = [f'<svg viewBox="0 0 {width} {height}" class="chart-svg" role="img" '
             f'aria-label="グループ棒グラフ">']

    steps = 4
    for i in range(steps + 1):
        v = vmax * i / steps
        y = ys(v)
        parts.append(f'<line x1="{margin["left"]}" y1="{y:.1f}" x2="{width - margin["right"]}" '
                      f'y2="{y:.1f}" class="gridline" />')
        parts.append(f'<text x="{margin["left"] - 8}" y="{y + 4:.1f}" class="axis-label" '
                      f'text-anchor="end">{v:,.0f}{y_suffix}</text>')

    y0 = ys(0)
    parts.append(f'<line x1="{margin["left"]}" y1="{y0:.1f}" x2="{width - margin["right"]}" '
                  f'y2="{y0:.1f}" class="baseline" />')

    for gi, cat in enumerate(categories):
        gx0 = margin["left"] + slot_w * gi + (slot_w - group_w) / 2
        for si, (label, color, values) in enumerate(series):
            val = values[gi]
            x = gx0 + si * (bar_w + 4)
            cx = x + bar_w / 2
            if val is None:
                continue
            h = plot_h * (val / vmax)
            y = y0 - h
            path = rounded_top_bar_path(x, y, bar_w, h)
            light, dark = color
            parts.append(
                f'<path d="{path}" fill="{light}" class="bar-mark" '
                f'data-light="{light}" data-dark="{dark}" '
                f'data-tooltip="{esc(cat)} / {esc(label)}: {esc(value_fmt(val))}{y_suffix}" />'
            )
        cx_group = gx0 + group_w / 2
        parts.append(f'<text x="{cx_group:.1f}" y="{y0 + 20:.1f}" class="axis-label" '
                      f'text-anchor="middle">{esc(cat)}</text>')

    parts.append("</svg>")

    legend = '<div class="legend">'
    for label, color, _ in series:
        light, dark = color
        legend += (f'<span class="legend-item"><span class="legend-swatch" '
                   f'data-light="{light}" data-dark="{dark}" '
                   f'style="background:{light}"></span>{esc(label)}</span>')
    legend += "</div>"

    return "".join(parts) + legend


def strip_plot(categories, groups, colors, *, width=760, height=360,
                y_suffix="㎡", value_fmt=lambda v: f"{v:,.0f}"):
    """groups = [[values...], ...] 区ごとの個別ドット + 中央値ティック"""
    margin = {"top": 24, "right": 20, "bottom": 56, "left": 64}
    plot_w = width - margin["left"] - margin["right"]
    plot_h = height - margin["top"] - margin["bottom"]

    all_vals = [v for g in groups for v in g]
    if not all_vals:
        vmax, vmin = 1, 0
    else:
        vmax = nice_max(max(all_vals))
        vmin = 0

    n = len(categories)
    slot_w = plot_w / n

    def ys(v):
        return margin["top"] + plot_h * (1 - (v - vmin) / (vmax - vmin))

    parts = [f'<svg viewBox="0 0 {width} {height}" class="chart-svg" role="img" '
             f'aria-label="散布ストリップ図">']

    steps = 4
    for i in range(steps + 1):
        v = vmin + (vmax - vmin) * i / steps
        y = ys(v)
        parts.append(f'<line x1="{margin["left"]}" y1="{y:.1f}" x2="{width - margin["right"]}" '
                      f'y2="{y:.1f}" class="gridline" />')
        parts.append(f'<text x="{margin["left"] - 8}" y="{y + 4:.1f}" class="axis-label" '
                      f'text-anchor="end">{v:,.0f}{y_suffix}</text>')

    y0 = ys(vmin)
    parts.append(f'<line x1="{margin["left"]}" y1="{y0:.1f}" x2="{width - margin["right"]}" '
                  f'y2="{y0:.1f}" class="baseline" />')

    import random
    rng = random.Random(42)

    for i, (cat, vals, color) in enumerate(zip(categories, groups, colors)):
        cx = margin["left"] + slot_w * i + slot_w / 2
        light, dark = color
        if not vals:
            parts.append(f'<text x="{cx:.1f}" y="{(y0 + margin["top"]) / 2:.1f}" '
                          f'class="axis-label" text-anchor="middle">データなし</text>')
        else:
            jitter_span = min(36, slot_w * 0.5)
            for v in vals:
                jx = cx + (rng.random() - 0.5) * jitter_span
                jy = ys(v)
                parts.append(
                    f'<circle cx="{jx:.1f}" cy="{jy:.1f}" r="5" fill="{light}" '
                    f'class="dot-mark" data-light="{light}" data-dark="{dark}" '
                    f'data-tooltip="{esc(cat)}: {esc(value_fmt(v))}{y_suffix}" />'
                )
            med = statistics.median(vals)
            my = ys(med)
            parts.append(f'<line x1="{cx - 22:.1f}" y1="{my:.1f}" x2="{cx + 22:.1f}" y2="{my:.1f}" '
                          f'class="median-tick" data-tooltip="{esc(cat)} 中央値: '
                          f'{esc(value_fmt(med))}{y_suffix}" />')
        parts.append(f'<text x="{cx:.1f}" y="{y0 + 20:.1f}" class="axis-label" '
                      f'text-anchor="middle">{esc(cat)}</text>')
        parts.append(f'<text x="{cx:.1f}" y="{y0 + 34:.1f}" class="axis-label-sub" '
                      f'text-anchor="middle">n={len(vals)}</text>')

    parts.append("</svg>")
    return "".join(parts)


def line_chart(x_categories, series, *, width=760, height=380,
                value_fmt=lambda v: f"{v:,.0f}", y_suffix="", label_top_n=2):
    """series = [(label, color, [values...]), ...] 複数系列の時系列推移。
    値がないx点は None を許容(線を切る)。上位/下位 label_top_n 本のみ
    終端に直接ラベルし、残りは凡例+ホバーで確認する(収束による重なりを回避)。
    """
    margin = {"top": 24, "right": 88, "bottom": 44, "left": 64}
    plot_w = width - margin["left"] - margin["right"]
    plot_h = height - margin["top"] - margin["bottom"]

    all_vals = [v for _, _, vals in series for v in vals if v is not None]
    vmax = nice_max(max(all_vals)) if all_vals else 1
    vmin = 0

    n = len(x_categories)

    def sx(i):
        return margin["left"] + (plot_w * i / (n - 1) if n > 1 else plot_w / 2)

    def sy(v):
        return margin["top"] + plot_h * (1 - (v - vmin) / (vmax - vmin))

    parts = [f'<svg viewBox="0 0 {width} {height}" class="chart-svg" role="img" '
             f'aria-label="時系列推移グラフ">']

    steps = 4
    for i in range(steps + 1):
        v = vmax * i / steps
        y = sy(v)
        parts.append(f'<line x1="{margin["left"]}" y1="{y:.1f}" x2="{width - margin["right"]}" '
                      f'y2="{y:.1f}" class="gridline" />')
        parts.append(f'<text x="{margin["left"] - 8}" y="{y + 4:.1f}" class="axis-label" '
                      f'text-anchor="end">{v:,.0f}{y_suffix}</text>')

    y0 = sy(vmin)
    parts.append(f'<line x1="{margin["left"]}" y1="{y0:.1f}" x2="{width - margin["right"]}" '
                  f'y2="{y0:.1f}" class="baseline" />')

    for i, cat in enumerate(x_categories):
        parts.append(f'<text x="{sx(i):.1f}" y="{height - margin["bottom"] + 20:.1f}" '
                      f'class="axis-label" text-anchor="middle">{esc(cat)}</text>')

    # 終端値でソートし、上位/下位のみ直接ラベル
    ends = [(label, vals[-1]) for label, _, vals in series if vals and vals[-1] is not None]
    ends.sort(key=lambda t: t[1])
    label_set = set(l for l, _ in ends[:label_top_n]) | set(l for l, _ in ends[-label_top_n:])

    for label, color, values in series:
        light, dark = color
        pts = [(sx(i), sy(v)) for i, v in enumerate(values) if v is not None]
        if len(pts) >= 2:
            d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
            parts.append(f'<path d="{d}" fill="none" stroke="{light}" stroke-width="2" '
                          f'stroke-linejoin="round" stroke-linecap="round" '
                          f'class="line-mark" data-light="{light}" data-dark="{dark}" />')
        for i, v in enumerate(values):
            if v is None:
                continue
            px, py = sx(i), sy(v)
            parts.append(
                f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4" fill="{light}" '
                f'class="dot-mark" data-light="{light}" data-dark="{dark}" '
                f'data-tooltip="{esc(label)} {esc(x_categories[i])}: {esc(value_fmt(v))}{y_suffix}" />'
            )
        if label in label_set and pts:
            lx, ly = pts[-1]
            parts.append(f'<text x="{lx + 8:.1f}" y="{ly + 4:.1f}" class="line-end-label" '
                          f'data-light="{light}" data-dark="{dark}">{esc(label)}</text>')

    parts.append("</svg>")

    legend = '<div class="legend">'
    for label, color, _ in series:
        light, dark = color
        legend += (f'<span class="legend-item"><span class="legend-swatch" '
                   f'data-light="{light}" data-dark="{dark}" '
                   f'style="background:{light}"></span>{esc(label)}</span>')
    legend += "</div>"

    return "".join(parts) + legend


def scatter_chart(points, color, *, width=760, height=380, x_label="", y_label=""):
    """points = [(x, y, tooltip), ...] 単色散布図"""
    margin = {"top": 24, "right": 20, "bottom": 56, "left": 64}
    plot_w = width - margin["left"] - margin["right"]
    plot_h = height - margin["top"] - margin["bottom"]

    xs = [p[0] for p in points]
    ys_ = [p[1] for p in points]
    xmax = nice_max(max(xs)) if xs else 1
    ymax = nice_max(max(ys_)) if ys_ else 1
    xmin, ymin = 0, 0

    def sx(v):
        return margin["left"] + plot_w * (v - xmin) / (xmax - xmin)

    def sy(v):
        return margin["top"] + plot_h * (1 - (v - ymin) / (ymax - ymin))

    parts = [f'<svg viewBox="0 0 {width} {height}" class="chart-svg" role="img" '
             f'aria-label="散布図">']

    steps = 4
    for i in range(steps + 1):
        v = ymax * i / steps
        y = sy(v)
        parts.append(f'<line x1="{margin["left"]}" y1="{y:.1f}" x2="{width - margin["right"]}" '
                      f'y2="{y:.1f}" class="gridline" />')
        parts.append(f'<text x="{margin["left"] - 8}" y="{y + 4:.1f}" class="axis-label" '
                      f'text-anchor="end">{v:,.0f}</text>')
    for i in range(steps + 1):
        v = xmax * i / steps
        x = sx(v)
        parts.append(f'<text x="{x:.1f}" y="{height - margin["bottom"] + 20:.1f}" '
                      f'class="axis-label" text-anchor="middle">{v:,.0f}</text>')

    y0 = sy(ymin)
    x0 = sx(xmin)
    parts.append(f'<line x1="{margin["left"]}" y1="{y0:.1f}" x2="{width - margin["right"]}" '
                  f'y2="{y0:.1f}" class="baseline" />')
    parts.append(f'<line x1="{x0:.1f}" y1="{margin["top"]}" x2="{x0:.1f}" '
                  f'y2="{height - margin["bottom"]}" class="baseline" />')

    light, dark = color
    for x, y, tip in points:
        px, py = sx(x), sy(y)
        parts.append(
            f'<circle cx="{px:.1f}" cy="{py:.1f}" r="5" fill="{light}" '
            f'class="dot-mark" data-light="{light}" data-dark="{dark}" '
            f'data-tooltip="{esc(tip)}" />'
        )

    parts.append(f'<text x="{(margin["left"] + width - margin["right"]) / 2:.1f}" '
                  f'y="{height - 6}" class="axis-title" text-anchor="middle">{esc(x_label)}</text>')
    parts.append(f'<text x="14" y="{(margin["top"] + height - margin["bottom"]) / 2:.1f}" '
                  f'class="axis-title" text-anchor="middle" '
                  f'transform="rotate(-90 14 {(margin["top"] + height - margin["bottom"]) / 2:.1f})">'
                  f'{esc(y_label)}</text>')

    parts.append("</svg>")
    return "".join(parts)


def stat_tile(label, value, sub=""):
    return (f'<div class="stat-tile"><div class="stat-label">{esc(label)}</div>'
            f'<div class="stat-value">{esc(value)}</div>'
            f'<div class="stat-sub">{esc(sub)}</div></div>')


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def main():
    quarter_dirs = sorted(DATA_DIR.glob("*Q*"))
    if not quarter_dirs:
        print("No data found in data/", file=sys.stderr)
        sys.exit(1)

    quarter_labels = [d.name for d in quarter_dirs]
    latest_label = quarter_labels[-1]

    # --- 全四半期を読み込み、四半期別・プール(全期間)の両方を作る ---
    per_quarter_mansion = {}
    pooled_mansion = []
    total_raw_count = 0

    for d in quarter_dirs:
        label = d.name
        year = int(label.split("Q")[0])
        raw = load_quarter(d)
        total_raw_count += len(raw)
        records = enrich(raw, year)
        mansion_q = [r for r in records if r.get("Type") == "中古マンション等"]
        for r in mansion_q:
            r["_quarter_label"] = label
        per_quarter_mansion[label] = mansion_q
        pooled_mansion.extend(mansion_q)

    mansion = pooled_mansion  # セクション②〜⑥はプール(全期間)を使う
    family_scope = [r for r in mansion if is_family_scope(r)]

    period_label = f"{quarter_labels[0]}〜{quarter_labels[-1]}（{len(quarter_labels)}四半期）"

    sections_html = []

    # --- 概要 stat tiles ---
    stats = "".join([
        stat_tile("対象期間", period_label),
        stat_tile("総取引件数", f"{total_raw_count:,}"),
        stat_tile("中古マンション等", f"{len(mansion):,}"),
        stat_tile("3LDK以上・70㎡以上", f"{len(family_scope):,}",
                   f"{len(quarter_labels)}四半期の累計"),
    ])

    # --- 1. 区別 ㎡単価の時系列推移 ---
    line_series_1 = []
    for w in WARD_ORDER:
        values = []
        for label in quarter_labels:
            vals = [r["_unit_price_man"] for r in per_quarter_mansion[label]
                    if r["city_name"] == w]
            values.append(median(vals))
        line_series_1.append((w, WARD_COLOR[w], values))
    chart1 = line_chart(
        quarter_labels, line_series_1,
        value_fmt=lambda v: f"{v:,.0f}", y_suffix="万円/㎡",
    )
    sections_html.append(("sec1", "① 区別 ㎡単価の推移(中央値)",
        f"中古マンション等・全間取り対象。{period_label}の四半期ごとの中央値をつないだ推移。",
        chart1))

    # --- 2. 予算2億円で狙える面積帯 ---
    budget_by_ward = {}
    for w in WARD_ORDER:
        vals = [r["_area"] for r in family_scope
                if r["city_name"] == w and (to_float(r.get("TradePrice")) or 0) <= BUDGET_YEN]
        budget_by_ward[w] = vals
    chart2 = strip_plot(
        WARD_ORDER,
        [budget_by_ward[w] for w in WARD_ORDER],
        [WARD_COLOR[w] for w in WARD_ORDER],
        y_suffix="㎡",
    )
    sections_html.append(("sec2", "② 2億円以内で狙える面積帯(3LDK以上・70㎡以上)",
        f"{period_label}の累計。各点が1取引、横棒が区ごとの中央値。同じ予算でも区によって狙える広さが大きく異なる。",
        chart2))

    # --- 3. 築年数と価格の関係 ---
    scatter_pts = []
    for r in family_scope:
        if r["_age"] is None or r["_unit_price_man"] is None:
            continue
        tip = f"{r['city_name']}{r.get('DistrictName','')} 築{r['_age']}年 {r['_unit_price_man']:,.0f}万円/㎡"
        scatter_pts.append((r["_age"], r["_unit_price_man"], tip))
    chart3 = scatter_chart(
        scatter_pts, CATEGORICAL[0],
        x_label="築年数(年)", y_label="㎡単価(万円/㎡)",
    )
    sections_html.append(("sec3", "③ 築年数と価格(㎡単価)の関係",
        f"{period_label}累計、3LDK以上・70㎡以上のセグメント。築年数は各取引が発生した四半期時点での年数。",
        chart3))

    # --- 4. 間取り別の価格分布 ---
    fp_values = []
    fp_counts = []
    fp_categories = FLOORPLAN_ORDER + ["その他"]
    fp_colors = [FLOORPLAN_COLOR[fp] for fp in FLOORPLAN_ORDER] + [OTHER_GRAY]
    for fp in FLOORPLAN_ORDER:
        vals = [r["_unit_price_man"] for r in mansion if r.get("FloorPlan") == fp]
        fp_values.append(median(vals))
        fp_counts.append(len(vals))
    other_vals = [r["_unit_price_man"] for r in mansion if r.get("FloorPlan") not in FLOORPLAN_ORDER]
    fp_values.append(median(other_vals))
    fp_counts.append(len(other_vals))
    chart4 = bar_chart(
        fp_categories, fp_values, fp_colors,
        value_fmt=lambda v: f"{v:,.0f}", y_suffix="万円/㎡", n_labels=fp_counts,
        bar_cap=40,
    )
    sections_html.append(("sec4", "④ 間取り別の価格分布(㎡単価・中央値)",
        f"対象9区の中古マンション等 {period_label}累計 全{len(mansion):,}件。"
        f"「その他」はワンルーム系・複合間取り・不明を含む。",
        chart4))

    # --- 5. リノベーション有無の価格差 ---
    reno_target_fps = ["１Ｋ", "２ＬＤＫ", "３ＬＤＫ", "１ＬＤＫ"]
    series = []
    for label, key in [("未改装", "未改装"), ("改装済み", "改装済み")]:
        vals = []
        for fp in reno_target_fps:
            v = median([r["_unit_price_man"] for r in mansion
                        if r.get("FloorPlan") == fp and r.get("Renovation") == key])
            vals.append(v)
        color = CATEGORICAL[0] if key == "未改装" else CATEGORICAL[1]
        series.append((label, color, vals))
    chart5 = grouped_bar_chart(
        reno_target_fps, series,
        value_fmt=lambda v: f"{v:,.0f}", y_suffix="万円/㎡",
    )
    sections_html.append(("sec5", "⑤ リノベーション有無による価格差(間取り別・㎡単価中央値)",
        f"{period_label}累計。同じ間取りで比較することで、単純な広さの違いによる誤差を避けている。"
        f"「不明」区分(未記載)は除外。",
        chart5))

    # --- 6. 地区(町丁目)レベルの粒度: 港区の例 ---
    minato = [r for r in mansion if r["city_name"] == "港区"]
    from collections import Counter
    district_counts = Counter(r.get("DistrictName", "") for r in minato).most_common()
    top_districts = [d for d, _ in district_counts[:7]]
    other_districts = [d for d, _ in district_counts[7:]]
    dist_categories = top_districts + (["その他"] if other_districts else [])
    dist_colors = [CATEGORICAL[i % len(CATEGORICAL)] for i in range(len(top_districts))] + \
                  ([OTHER_GRAY] if other_districts else [])
    dist_values = []
    dist_ns = []
    for d in top_districts:
        vals = [r["_unit_price_man"] for r in minato if r.get("DistrictName") == d]
        dist_values.append(median(vals))
        dist_ns.append(len(vals))
    if other_districts:
        vals = [r["_unit_price_man"] for r in minato if r.get("DistrictName") in other_districts]
        dist_values.append(median(vals))
        dist_ns.append(len(vals))
    chart6 = bar_chart(
        dist_categories, dist_values, dist_colors,
        value_fmt=lambda v: f"{v:,.0f}", y_suffix="万円/㎡", n_labels=dist_ns,
        bar_cap=40,
    )
    sections_html.append(("sec6", "⑥ 地区(町丁目)レベルの粒度 — 港区の例",
        f"{period_label}累計。同じ港区内でも地区によって水準が異なる。件数の少ない地区は参考値。",
        chart6))

    # --- 7. 対象セグメントの取引件数(流動性)の推移 ---
    line_series_7 = []
    for w in WARD_ORDER:
        values = []
        for label in quarter_labels:
            count = sum(1 for r in per_quarter_mansion[label]
                        if r["city_name"] == w and is_family_scope(r))
            values.append(count)
        line_series_7.append((w, WARD_COLOR[w], values))
    chart7 = line_chart(
        quarter_labels, line_series_7,
        value_fmt=lambda v: f"{v:.0f}", y_suffix="件",
    )
    sections_html.append(("sec7", "⑦ 対象セグメントの取引件数(流動性)の推移",
        "3LDK以上・70㎡以上、四半期ごとの件数。区によっては月1件未満の水準で上下も激しく、"
        "単一四半期では判断が難しいことが分かる。",
        chart7))

    html = render_html(period_label, stats, sections_html)

    REPORTS_DIR.mkdir(exist_ok=True)
    # 固定ファイル名にすることで、データ更新のたびに同じパスが上書きされる
    # (過去の版が見たければ git log で辿れる)。GitHub Pages等で常に
    # 最新を指す1つのURLとして公開する前提の設計。
    out_path = REPORTS_DIR / "report.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote {out_path}")


def render_html(period_label, stats_html, sections):
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    section_html = ""
    for sec_id, title, note, chart_svg in sections:
        section_html += f"""
    <section class="card" id="{sec_id}">
      <h2>{esc(title)}</h2>
      <p class="note">{esc(note)}</p>
      <div class="chart-wrap">{chart_svg}</div>
    </section>"""

    return f"""<!doctype html>
<title>マンション価格ウォッチ</title>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {{
    color-scheme: light;
    --surface-1: #fcfcfb;
    --page: #f9f9f7;
    --text-primary: #0b0b0b;
    --text-secondary: #52514e;
    --muted: #898781;
    --grid: #e1e0d9;
    --baseline: #c3c2b7;
    --border: rgba(11,11,11,0.10);
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      color-scheme: dark;
      --surface-1: #1a1a19;
      --page: #0d0d0d;
      --text-primary: #ffffff;
      --text-secondary: #c3c2b7;
      --muted: #898781;
      --grid: #2c2c2a;
      --baseline: #383835;
      --border: rgba(255,255,255,0.10);
    }}
  }}
  :root[data-theme="dark"] {{
    color-scheme: dark;
    --surface-1: #1a1a19;
    --page: #0d0d0d;
    --text-primary: #ffffff;
    --text-secondary: #c3c2b7;
    --muted: #898781;
    --grid: #2c2c2a;
    --baseline: #383835;
    --border: rgba(255,255,255,0.10);
  }}

  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: var(--page);
    color: var(--text-primary);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    line-height: 1.6;
  }}
  .wrap {{ max-width: 880px; margin: 0 auto; padding: 32px 20px 80px; }}
  h1 {{ font-size: 1.5rem; margin: 0 0 4px; }}
  .subtitle {{ color: var(--text-secondary); margin: 0 0 28px; font-size: 0.9rem; }}
  .stats-row {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 12px; margin-bottom: 32px;
  }}
  .stat-tile {{
    background: var(--surface-1); border: 1px solid var(--border);
    border-radius: 10px; padding: 14px 16px;
  }}
  .stat-label {{ font-size: 0.78rem; color: var(--text-secondary); }}
  .stat-value {{ font-size: 1.5rem; font-weight: 600; margin-top: 2px;
    font-variant-numeric: tabular-nums; }}
  .stat-sub {{ font-size: 0.72rem; color: var(--muted); margin-top: 2px; min-height: 1em; }}

  .card {{
    background: var(--surface-1); border: 1px solid var(--border);
    border-radius: 12px; padding: 20px 20px 8px; margin-bottom: 20px;
  }}
  .card h2 {{ font-size: 1.05rem; margin: 0 0 6px; }}
  .note {{ font-size: 0.82rem; color: var(--text-secondary); margin: 0 0 12px; max-width: 66ch; }}
  .chart-wrap {{ overflow-x: auto; }}
  .chart-svg {{ width: 100%; height: auto; display: block; min-width: 480px; }}

  .gridline {{ stroke: var(--grid); stroke-width: 1; }}
  .baseline {{ stroke: var(--baseline); stroke-width: 1; }}
  .axis-label {{ font-size: 11px; fill: var(--muted); font-variant-numeric: tabular-nums; }}
  .axis-label-sub {{ font-size: 9.5px; fill: var(--muted); font-variant-numeric: tabular-nums; }}
  .axis-title {{ font-size: 11px; fill: var(--text-secondary); }}
  .value-label {{ font-size: 11px; fill: var(--text-primary); font-weight: 600;
    font-variant-numeric: tabular-nums; }}
  .median-tick {{ stroke: var(--text-primary); stroke-width: 2; }}
  .bar-mark, .dot-mark {{ cursor: pointer; transition: opacity 0.1s; }}
  .bar-mark:hover, .dot-mark:hover {{ opacity: 0.75; }}
  .dot-mark {{ stroke: var(--surface-1); stroke-width: 2; }}
  .line-mark {{ opacity: 0.92; }}
  .line-end-label {{ font-size: 11px; font-weight: 600; fill: var(--text-primary); }}

  .legend {{ display: flex; gap: 16px; flex-wrap: wrap; padding: 4px 0 16px; }}
  .legend-item {{ display: flex; align-items: center; gap: 6px; font-size: 0.8rem; color: var(--text-secondary); }}
  .legend-swatch {{ width: 10px; height: 10px; border-radius: 2px; display: inline-block; }}

  footer {{ color: var(--muted); font-size: 0.78rem; margin-top: 32px; max-width: 66ch; }}

  #tooltip {{
    position: fixed; pointer-events: none; z-index: 10;
    background: var(--text-primary); color: var(--surface-1);
    font-size: 0.78rem; padding: 6px 10px; border-radius: 6px;
    max-width: 260px; opacity: 0; transition: opacity 0.08s;
  }}
</style>

<div class="wrap">
  <h1>東京23区 マンション価格分析レポート</h1>
  <p class="subtitle">対象期間: {esc(period_label)} ／ 生成日時: {esc(generated)} ／
    データ出典: 国土交通省 不動産情報ライブラリ(不動産取引価格情報)</p>

  <div class="stats-row">{stats_html}</div>
  {section_html}

  <footer>
    対象9区: 千代田区・中央区・港区・新宿区・文京区・渋谷区・品川区・目黒区(麻布台ヒルズ勤務・車通勤20〜25分圏)。
    予算上限2億円、ファミリー向け(3LDK以上・70㎡以上)を軸に集計。
    最寄駅・駅距離のデータはこのAPIエンドポイントには含まれないため、駅距離分析は今回対象外。
    ②〜⑥は対象期間全体をプールした集計、①・⑦は四半期ごとの時系列推移。
    最新四半期は買主アンケートの回収が完了しておらず件数が少なめに出ることがある点に注意。
  </footer>
</div>

<div id="tooltip"></div>
<script>
  const tooltip = document.getElementById('tooltip');
  document.addEventListener('mousemove', (e) => {{
    const target = e.target.closest('[data-tooltip]');
    if (!target) {{ tooltip.style.opacity = 0; return; }}
    tooltip.textContent = target.getAttribute('data-tooltip');
    tooltip.style.opacity = 1;
    let x = e.clientX + 14, y = e.clientY + 14;
    tooltip.style.left = x + 'px';
    tooltip.style.top = y + 'px';
  }});
  document.addEventListener('mouseleave', () => {{ tooltip.style.opacity = 0; }});

  // ダークモード時に色付きマークを data-dark に差し替え
  function applyThemeColors() {{
    const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const themeAttr = document.documentElement.getAttribute('data-theme');
    const dark = themeAttr ? themeAttr === 'dark' : isDark;
    document.querySelectorAll('[data-light]').forEach(el => {{
      const color = dark ? el.getAttribute('data-dark') : el.getAttribute('data-light');
      if (el.tagName === 'circle') {{
        el.setAttribute('fill', color);
      }} else if (el.tagName === 'path' && el.classList.contains('line-mark')) {{
        el.setAttribute('stroke', color);
      }} else if (el.classList.contains('legend-swatch')) {{
        el.style.background = color;
      }} else {{
        el.setAttribute('fill', color);
      }}
    }});
  }}
  applyThemeColors();
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', applyThemeColors);
</script>
"""


if __name__ == "__main__":
    main()
