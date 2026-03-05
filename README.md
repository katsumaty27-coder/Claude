# ジョブカン勤怠自動入力ツール

平日の勤怠時間を **9:00～17:00** で自動入力するツールです。
2つのアプローチを提供しています。

---

## 方法1: Tampermonkeyユーザースクリプト（推奨）

ブラウザ拡張機能を使って、ジョブカンのページ上にボタンを追加します。

### セットアップ

1. ブラウザに [Tampermonkey](https://www.tampermonkey.net/) をインストール
2. Tampermonkeyの管理画面を開く
3. 「新規スクリプト」をクリック
4. `jobcan_autofill.user.js` の内容を貼り付けて保存

### 使い方

- ジョブカンの従業員ページ (`https://ssl.jobcan.jp/employee`) にアクセス
- 画面右上に「勤怠自動入力」パネルが表示されます
- **「平日を一括入力」** ボタン: 勤怠表の平日に9:00～17:00を一括入力
- **「この日の時間を入力」** ボタン: 打刻修正ページで個別入力

### カスタマイズ

スクリプト冒頭の `CONFIG` で時間を変更できます:

```javascript
const CONFIG = {
  startTime: "9:00",   // 出勤時間
  endTime: "17:00",    // 退勤時間
};
```

---

## 方法2: Python + Selenium スクリプト

コマンドラインから自動実行するスクリプトです。

### セットアップ

```bash
pip install selenium webdriver-manager
```

### 環境変数の設定

```bash
export JOBCAN_EMAIL="your_email@example.com"
export JOBCAN_PASSWORD="your_password"
export JOBCAN_CLIENT_ID="your_company_id"  # 会社IDが必要な場合
```

### 使い方

```bash
# 今月の平日を自動入力
python jobcan_autofill_selenium.py

# 対象日を確認（ドライラン）
python jobcan_autofill_selenium.py --dry-run

# 特定の月を指定
python jobcan_autofill_selenium.py --year 2026 --month 3

# 時間をカスタマイズ
python jobcan_autofill_selenium.py --start-time 8:30 --end-time 17:30

# ヘッドレスモード（ブラウザ非表示）
python jobcan_autofill_selenium.py --headless

# id.jobcan.jp 経由でログイン
python jobcan_autofill_selenium.py --login-method id
```

### オプション一覧

| オプション | 説明 | デフォルト |
|------------|------|-----------|
| `--year` | 対象年 | 今年 |
| `--month` | 対象月 | 今月 |
| `--start-time` | 出勤時間 | 9:00 |
| `--end-time` | 退勤時間 | 17:00 |
| `--dry-run` | 対象日の確認のみ | - |
| `--headless` | ブラウザ非表示で実行 | - |
| `--login-method` | ログイン方法 (employee/id) | employee |

---

## 重要な注意事項

- **セレクタの調整が必要です**: ジョブカンの画面構成は会社設定やアップデートにより異なる場合があります。実際のページのDOM構造をブラウザの開発者ツール (F12) で確認し、セレクタを調整してください。
- **祝日判定**: 簡易的な祝日判定を含んでいますが、振替休日や特別な休日は含まれていません。必要に応じてカスタマイズしてください。
- **自己責任**: 勤怠データの自動入力は会社の規定に従って使用してください。
