"""
ジョブカン勤怠自動入力スクリプト (Python + Selenium)

平日の勤怠時間を 9:00～17:00 で自動入力します。

使い方:
    1. pip install selenium webdriver-manager
    2. 環境変数を設定:
       export JOBCAN_EMAIL="your_email@example.com"
       export JOBCAN_PASSWORD="your_password"
       export JOBCAN_CLIENT_ID="your_company_id"  # 会社IDが必要な場合
    3. python jobcan_autofill_selenium.py

オプション:
    --year YYYY     対象年（デフォルト: 今年）
    --month MM      対象月（デフォルト: 今月）
    --start-time HH:MM  出勤時間（デフォルト: 9:00）
    --end-time HH:MM    退勤時間（デフォルト: 17:00）
    --dry-run       実際に入力せずに対象日を表示
    --headless      ヘッドレスモードで実行
"""

import argparse
import calendar
import os
import sys
import time
from datetime import date, datetime

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import Select, WebDriverWait
except ImportError:
    print("Error: selenium が必要です。以下のコマンドでインストールしてください:")
    print("  pip install selenium webdriver-manager")
    sys.exit(1)

try:
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:
    ChromeDriverManager = None

# ============================================
# 設定
# ============================================
JOBCAN_LOGIN_URL = "https://ssl.jobcan.jp/login/pc-employee"
JOBCAN_ID_LOGIN_URL = "https://id.jobcan.jp/users/sign_in"
JOBCAN_EMPLOYEE_URL = "https://ssl.jobcan.jp/employee"
JOBCAN_ADIT_MODIFY_URL = "https://ssl.jobcan.jp/employee/adit/modify/"

# 日本の祝日（固定祝日の簡易版）
def get_japanese_holidays(year):
    """日本の祝日を返す（簡易版 - 固定祝日のみ）"""
    holidays = {
        date(year, 1, 1),    # 元日
        date(year, 2, 11),   # 建国記念の日
        date(year, 2, 23),   # 天皇誕生日
        date(year, 3, 20),   # 春分の日（概算）
        date(year, 4, 29),   # 昭和の日
        date(year, 5, 3),    # 憲法記念日
        date(year, 5, 4),    # みどりの日
        date(year, 5, 5),    # こどもの日
        date(year, 8, 11),   # 山の日
        date(year, 9, 23),   # 秋分の日（概算）
        date(year, 11, 3),   # 文化の日
        date(year, 11, 23),  # 勤労感謝の日
    }

    # 第2月曜日の祝日
    # 成人の日（1月第2月曜）
    holidays.add(get_nth_weekday(year, 1, 0, 2))
    # 海の日（7月第3月曜）
    holidays.add(get_nth_weekday(year, 7, 0, 3))
    # 敬老の日（9月第3月曜）
    holidays.add(get_nth_weekday(year, 9, 0, 3))
    # スポーツの日（10月第2月曜）
    holidays.add(get_nth_weekday(year, 10, 0, 2))

    return holidays


def get_nth_weekday(year, month, weekday, n):
    """指定月のn番目の指定曜日の日付を返す (weekday: 0=月曜)"""
    cal = calendar.Calendar(firstweekday=0)
    month_days = cal.itermonthdates(year, month)
    count = 0
    for d in month_days:
        if d.month == month and d.weekday() == weekday:
            count += 1
            if count == n:
                return d
    return None


def get_weekdays(year, month):
    """指定月の平日（祝日を除く）リストを返す"""
    holidays = get_japanese_holidays(year)
    weekdays = []
    cal = calendar.Calendar()
    for d in cal.itermonthdates(year, month):
        if d.month != month:
            continue
        # 平日（月～金）かつ祝日でない
        if d.weekday() < 5 and d not in holidays:
            weekdays.append(d)
    return weekdays


class JobcanAutoFiller:
    def __init__(self, headless=False):
        self.driver = None
        self.headless = headless

    def setup_driver(self):
        """Chromeドライバーを設定"""
        options = Options()
        if self.headless:
            options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1280,900")

        if ChromeDriverManager:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
        else:
            self.driver = webdriver.Chrome(options=options)

        self.driver.implicitly_wait(10)

    def login_via_employee_page(self, client_id, email, password):
        """従業員ページからログイン"""
        self.driver.get(JOBCAN_LOGIN_URL)
        time.sleep(2)

        wait = WebDriverWait(self.driver, 15)

        # 会社IDが必要な場合
        if client_id:
            try:
                client_input = wait.until(
                    EC.presence_of_element_located((By.ID, "client_id"))
                )
                client_input.clear()
                client_input.send_keys(client_id)
            except Exception:
                pass

        # メールアドレス
        email_input = wait.until(
            EC.presence_of_element_located((By.ID, "email"))
        )
        email_input.clear()
        email_input.send_keys(email)

        # パスワード
        password_input = self.driver.find_element(By.ID, "password")
        password_input.clear()
        password_input.send_keys(password)

        # ログインボタン
        login_btn = self.driver.find_element(
            By.CSS_SELECTOR, 'input[type="submit"], button[type="submit"]'
        )
        login_btn.click()
        time.sleep(3)

        # ログイン成功確認
        if "/employee" in self.driver.current_url:
            print("ログイン成功")
            return True
        else:
            print(f"ログイン失敗: 現在のURL = {self.driver.current_url}")
            return False

    def login_via_id_page(self, email, password):
        """id.jobcan.jp からログイン"""
        self.driver.get(JOBCAN_ID_LOGIN_URL)
        time.sleep(2)

        wait = WebDriverWait(self.driver, 15)

        email_input = wait.until(
            EC.presence_of_element_located((By.ID, "user_email"))
        )
        email_input.clear()
        email_input.send_keys(email)

        password_input = self.driver.find_element(By.ID, "user_password")
        password_input.clear()
        password_input.send_keys(password)

        login_btn = self.driver.find_element(By.ID, "login_button")
        login_btn.click()
        time.sleep(3)

        # 勤怠管理ページへ遷移
        self.driver.get(JOBCAN_EMPLOYEE_URL)
        time.sleep(2)

        if "/employee" in self.driver.current_url:
            print("ログイン成功")
            return True
        else:
            print(f"ログイン失敗: 現在のURL = {self.driver.current_url}")
            return False

    def navigate_to_adit_modify(self, target_date):
        """打刻修正ページへ遷移"""
        url = (
            f"{JOBCAN_ADIT_MODIFY_URL}"
            f"?year={target_date.year}"
            f"&month={target_date.month}"
            f"&day={target_date.day}"
        )
        self.driver.get(url)
        time.sleep(2)

    def fill_time_for_date(self, target_date, start_time, end_time):
        """指定日の出退勤時間を入力"""
        self.navigate_to_adit_modify(target_date)

        wait = WebDriverWait(self.driver, 10)

        try:
            # 打刻修正ページの入力フィールドを探す
            # 方法1: input[name="time"] が複数ある場合
            time_inputs = self.driver.find_elements(By.CSS_SELECTOR, 'input[name="time"]')
            type_selects = self.driver.find_elements(
                By.CSS_SELECTOR, 'select[name="adit_item"]'
            )

            if time_inputs and type_selects:
                # 出勤入力
                if len(type_selects) > 0:
                    Select(type_selects[0]).select_by_value("work_start")
                if len(time_inputs) > 0:
                    time_inputs[0].clear()
                    time_inputs[0].send_keys(start_time)

                # 退勤入力
                if len(type_selects) > 1:
                    Select(type_selects[1]).select_by_value("work_end")
                if len(time_inputs) > 1:
                    time_inputs[1].clear()
                    time_inputs[1].send_keys(end_time)

                # 保存ボタンをクリック
                save_btn = self.driver.find_element(
                    By.CSS_SELECTOR,
                    'input[type="submit"], button[type="submit"], .btn-primary'
                )
                save_btn.click()
                time.sleep(2)

                print(f"  {target_date} => {start_time}～{end_time} 入力完了")
                return True

            # 方法2: 別のフォーム構造の場合
            # 開始時間・終了時間が別々のフィールドの場合
            start_input = self.driver.find_elements(
                By.CSS_SELECTOR,
                'input[name*="start_time"], input[name*="work_start"], '
                'input.start-time'
            )
            end_input = self.driver.find_elements(
                By.CSS_SELECTOR,
                'input[name*="end_time"], input[name*="work_end"], '
                'input.end-time'
            )

            if start_input and end_input:
                start_input[0].clear()
                start_input[0].send_keys(start_time)
                end_input[0].clear()
                end_input[0].send_keys(end_time)

                save_btn = self.driver.find_element(
                    By.CSS_SELECTOR,
                    'input[type="submit"], button[type="submit"], .btn-primary'
                )
                save_btn.click()
                time.sleep(2)

                print(f"  {target_date} => {start_time}～{end_time} 入力完了")
                return True

            print(f"  {target_date} => 入力フィールドが見つかりませんでした")
            return False

        except Exception as e:
            print(f"  {target_date} => エラー: {e}")
            return False

    def fill_month(self, year, month, start_time, end_time, dry_run=False):
        """指定月の平日を一括入力"""
        weekdays = get_weekdays(year, month)

        print(f"\n{'='*50}")
        print(f"対象: {year}年{month}月")
        print(f"出勤時間: {start_time} / 退勤時間: {end_time}")
        print(f"平日数: {len(weekdays)}日")
        print(f"{'='*50}")

        if dry_run:
            print("\n[ドライラン] 対象日一覧:")
            for d in weekdays:
                weekday_names = ["月", "火", "水", "木", "金", "土", "日"]
                print(f"  {d} ({weekday_names[d.weekday()]})")
            print(f"\n合計: {len(weekdays)}日")
            return

        print("\n入力開始...")
        success = 0
        fail = 0
        for d in weekdays:
            if self.fill_time_for_date(d, start_time, end_time):
                success += 1
            else:
                fail += 1

        print(f"\n完了: 成功={success}日, 失敗={fail}日")

    def close(self):
        """ブラウザを閉じる"""
        if self.driver:
            self.driver.quit()


def main():
    parser = argparse.ArgumentParser(
        description="ジョブカン勤怠自動入力スクリプト"
    )
    parser.add_argument("--year", type=int, default=date.today().year,
                        help="対象年（デフォルト: 今年）")
    parser.add_argument("--month", type=int, default=date.today().month,
                        help="対象月（デフォルト: 今月）")
    parser.add_argument("--start-time", default="9:00",
                        help="出勤時間（デフォルト: 9:00）")
    parser.add_argument("--end-time", default="17:00",
                        help="退勤時間（デフォルト: 17:00）")
    parser.add_argument("--dry-run", action="store_true",
                        help="実際に入力せずに対象日を表示")
    parser.add_argument("--headless", action="store_true",
                        help="ヘッドレスモードで実行")
    parser.add_argument("--login-method", choices=["employee", "id"],
                        default="employee",
                        help="ログイン方法 (employee: 従業員ページ, id: id.jobcan.jp)")

    args = parser.parse_args()

    # 認証情報を環境変数から取得
    email = os.environ.get("JOBCAN_EMAIL")
    password = os.environ.get("JOBCAN_PASSWORD")
    client_id = os.environ.get("JOBCAN_CLIENT_ID", "")

    if not email or not password:
        print("エラー: 環境変数 JOBCAN_EMAIL と JOBCAN_PASSWORD を設定してください")
        print("")
        print("例:")
        print('  export JOBCAN_EMAIL="your_email@example.com"')
        print('  export JOBCAN_PASSWORD="your_password"')
        sys.exit(1)

    filler = JobcanAutoFiller(headless=args.headless)

    try:
        filler.setup_driver()

        # ログイン
        if args.login_method == "id":
            if not filler.login_via_id_page(email, password):
                sys.exit(1)
        else:
            if not filler.login_via_employee_page(client_id, email, password):
                sys.exit(1)

        # 勤怠入力
        filler.fill_month(
            args.year, args.month,
            args.start_time, args.end_time,
            dry_run=args.dry_run
        )

    finally:
        filler.close()


if __name__ == "__main__":
    main()
