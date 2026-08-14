#!/usr/bin/env python3
"""
不動産情報ライブラリ API から過去分の取引価格データを一括取得するスクリプト。

指定した開始四半期(デフォルト: 2024Q1)から、実際にデータが公開されている
最新の四半期までを順番に取得し、data/YYYYQ#/ に保存する。
一度取得済みの四半期はスキップする(--force で強制再取得)。

通常運用(最新四半期のみを定期取得)には fetch_real_estate_data.py を使う。
これはワンタイムの過去分一括取得専用。
"""

import argparse
import sys
import time
from datetime import datetime

from fetch_real_estate_data import (
    fetch_and_save_quarter,
    find_latest_available_quarter,
    quarter_data_exists,
    step_quarter_back,
    step_quarter_forward,
    API_KEY,
)

# 四半期リクエスト間のウェイト(秒) — APIへの負荷配慮
REQUEST_INTERVAL_SEC = 1.0


def parse_args():
    parser = argparse.ArgumentParser(description="過去分の不動産取引価格データを一括取得")
    parser.add_argument("--start-year", type=int, default=2024)
    parser.add_argument("--start-quarter", type=int, default=1, choices=[1, 2, 3, 4])
    parser.add_argument("--force", action="store_true",
                         help="既に取得済みの四半期も再取得する")
    return parser.parse_args()


def main():
    args = parse_args()

    if not API_KEY:
        print("Error: MLIT_API_KEY environment variable not set", file=sys.stderr)
        sys.exit(1)

    now = datetime.now()
    current_quarter = (now.month - 1) // 3 + 1
    probe_year, probe_quarter = step_quarter_back(now.year, current_quarter)

    print(f"Finding latest available quarter (probing back from {probe_year}Q{probe_quarter})...",
          file=sys.stderr)
    latest_year, latest_quarter = find_latest_available_quarter(probe_year, probe_quarter)

    if latest_year is None:
        print("Error: could not find any available quarter", file=sys.stderr)
        sys.exit(1)

    print(f"Latest available quarter: {latest_year}Q{latest_quarter}", file=sys.stderr)
    print(f"Backfilling from {args.start_year}Q{args.start_quarter} to "
          f"{latest_year}Q{latest_quarter}\n", file=sys.stderr)

    year, quarter = args.start_year, args.start_quarter
    fetched, skipped, unavailable = [], [], []

    while (year, quarter) <= (latest_year, latest_quarter):
        label = f"{year}Q{quarter}"

        if not args.force and quarter_data_exists(year, quarter):
            print(f"=== {label}: already exists, skipping ===", file=sys.stderr)
            skipped.append(label)
        else:
            print(f"=== {label}: fetching ===", file=sys.stderr)
            result = fetch_and_save_quarter(year, quarter)
            if result is None:
                print(f"=== {label}: not available (unpublished) ===", file=sys.stderr)
                unavailable.append(label)
            else:
                fetched.append((label, result))
            time.sleep(REQUEST_INTERVAL_SEC)

        year, quarter = step_quarter_forward(year, quarter)

    print("\n" + "=" * 50, file=sys.stderr)
    print("Backfill summary", file=sys.stderr)
    print("=" * 50, file=sys.stderr)
    print(f"Fetched:     {len(fetched)} quarters", file=sys.stderr)
    for label, count in fetched:
        print(f"  {label}: {count} records", file=sys.stderr)
    print(f"Skipped (already existed): {len(skipped)} quarters -> {', '.join(skipped) or '(none)'}",
          file=sys.stderr)
    print(f"Unavailable (not yet published): {len(unavailable)} quarters -> "
          f"{', '.join(unavailable) or '(none)'}", file=sys.stderr)


if __name__ == "__main__":
    main()
