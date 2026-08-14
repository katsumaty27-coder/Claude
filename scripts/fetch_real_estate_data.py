#!/usr/bin/env python3
"""
不動産情報ライブラリ API から対象エリアの取引価格データを定期取得するスクリプト

このデータは国交省が四半期単位で集計・公開しているため(個々の取引に
月の情報は付与されない)、取得の粒度は四半期固定。年4回程度の実行を想定。
過去分の一括取得には backfill_historical_data.py を使う。
"""

import os
import sys
import json
import requests
from datetime import datetime
from pathlib import Path

# 対象市区町村コード (東京都=13)
TARGET_CITIES = {
    13101: "千代田区",
    13102: "中央区",
    13103: "港区",
    13104: "新宿区",
    13105: "文京区",
    13107: "渋谷区",
    13108: "品川区",
    13109: "目黒区",
}

# データが確実に存在する可能性が高い区(最新四半期を探すためのプローブ用)
PROBE_CITY_CODE = 13103  # 港区

# 最新四半期を探す際に遡る最大四半期数(=3年分)
MAX_LOOKBACK_QUARTERS = 12

# API 設定
API_BASE_URL = "https://www.reinfolib.mlit.go.jp/ex-api/external/XIT001"
API_KEY = os.environ.get("MLIT_API_KEY")

DATA_DIR = Path(__file__).parent.parent / "data"


def fetch_transaction_data(year, quarter, city_code):
    """
    指定年度・四半期・市区町村コードの不動産取引価格データを取得
    """
    if not API_KEY:
        raise ValueError("MLIT_API_KEY environment variable not set")

    headers = {
        "Ocp-Apim-Subscription-Key": API_KEY,
    }

    params = {
        "area": "13",  # 東京都
        "city": city_code,
        "year": year,
        "quarter": quarter,
        "priceClassification": "01",  # 01: 取引価格
    }

    response = requests.get(API_BASE_URL, headers=headers, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def step_quarter_back(year, quarter):
    """四半期を1つ過去にずらす"""
    quarter -= 1
    if quarter < 1:
        quarter = 4
        year -= 1
    return year, quarter


def step_quarter_forward(year, quarter):
    """四半期を1つ未来にずらす"""
    quarter += 1
    if quarter > 4:
        quarter = 1
        year += 1
    return year, quarter


def find_latest_available_quarter(start_year, start_quarter):
    """
    プローブ用の区に対して、データが取得できる最新の四半期を
    新しい方から遡って探す。データ公開には数ヶ月〜半年以上の
    タイムラグがあるため、直近の四半期は404になることが多い。
    """
    year, quarter = start_year, start_quarter

    for _ in range(MAX_LOOKBACK_QUARTERS):
        print(f"Probing {year}Q{quarter}...", file=sys.stderr)
        try:
            result = fetch_transaction_data(year, quarter, PROBE_CITY_CODE)
            if result.get("data"):
                print(f"  -> Found data at {year}Q{quarter}", file=sys.stderr)
                return year, quarter
            print(f"  -> Empty response, trying earlier quarter", file=sys.stderr)
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else "?"
            print(f"  -> HTTP {status}, trying earlier quarter", file=sys.stderr)

        year, quarter = step_quarter_back(year, quarter)

    return None, None


def quarter_data_exists(year, quarter):
    output_dir = DATA_DIR / f"{year}Q{quarter}"
    output_file = output_dir / f"transaction_prices_{year}Q{quarter}.json"
    return output_file.exists()


def fetch_and_save_quarter(year, quarter):
    """
    指定四半期について対象9区すべてのデータを取得し、data/YYYYQ#/ に保存する。
    その四半期がまだ公開されていない(全区404)場合は None を返す。
    戻り値: 保存したレコード数、または未公開の場合は None
    """
    output_dir = DATA_DIR / f"{year}Q{quarter}"
    all_results = []
    any_success = False

    for city_code, city_name in TARGET_CITIES.items():
        print(f"Fetching data for {city_name} ({year}Q{quarter})...", file=sys.stderr)

        try:
            result = fetch_transaction_data(year, quarter, city_code)
            any_success = True

            if "data" in result:
                for record in result.get("data", []):
                    record["city_name"] = city_name
                    record["city_code"] = city_code
                    all_results.append(record)

            print(f"  ✓ {len(result.get('data', []))} records", file=sys.stderr)

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else "?"
            print(f"  ✗ HTTP Error {status}: {e}", file=sys.stderr)
            continue
        except requests.exceptions.RequestException as e:
            print(f"  ✗ Error: {e}", file=sys.stderr)
            continue

    if not any_success:
        # 9区すべてが失敗 = その四半期はまだ公開されていない
        return None

    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / f"transaction_prices_{year}Q{quarter}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print(f"\nSaved {len(all_results)} records to {output_file}", file=sys.stderr)

    summary = {
        "fetch_date": datetime.now().isoformat(),
        "year": year,
        "quarter": quarter,
        "total_records": len(all_results),
        "by_city": {},
    }

    for record in all_results:
        city = record["city_name"]
        summary["by_city"].setdefault(city, 0)
        summary["by_city"][city] += 1

    summary_file = output_dir / f"summary_{year}Q{quarter}.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"Saved summary to {summary_file}", file=sys.stderr)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    return len(all_results)


def main():
    if not API_KEY:
        print("Error: MLIT_API_KEY environment variable not set", file=sys.stderr)
        sys.exit(1)

    now = datetime.now()
    current_quarter = (now.month - 1) // 3 + 1
    print(f"Current date: {now.strftime('%Y-%m-%d')}, Current Q: {current_quarter}", file=sys.stderr)

    # データ公開にタイムラグがあるため、直近の四半期から遡って
    # 実際にデータが存在する最新の四半期を探す
    probe_year, probe_quarter = step_quarter_back(now.year, current_quarter)
    year, quarter = find_latest_available_quarter(probe_year, probe_quarter)

    if year is None:
        print(
            f"Error: No data found within the last {MAX_LOOKBACK_QUARTERS} quarters",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Using {year}Q{quarter} for all target cities", file=sys.stderr)
    result = fetch_and_save_quarter(year, quarter)

    if result is None:
        print(f"Error: {year}Q{quarter} turned out to be unavailable", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
