// ==UserScript==
// @name         ジョブカン勤怠自動入力
// @namespace    https://ssl.jobcan.jp/
// @version      1.0
// @description  平日の勤怠時間を9:00～17:00で自動入力するスクリプト
// @match        https://ssl.jobcan.jp/employee/*
// @match        https://ssl.jobcan.jp/employee
// @grant        none
// ==/UserScript==

(function () {
  "use strict";

  // ============================================
  // 設定
  // ============================================
  const CONFIG = {
    startTime: "9:00", // 出勤時間
    endTime: "17:00", // 退勤時間
    // 自動入力ボタンの表示位置
    buttonStyle: {
      position: "fixed",
      top: "10px",
      right: "10px",
      zIndex: "9999",
    },
  };

  // 平日かどうか判定 (0=日曜, 6=土曜)
  function isWeekday(date) {
    const day = date.getDay();
    return day !== 0 && day !== 6;
  }

  // 日本の祝日判定（簡易版 - 必要に応じて拡張してください）
  function isJapaneseHoliday(date) {
    const holidays = getJapaneseHolidays(date.getFullYear());
    const dateStr = formatDate(date);
    return holidays.includes(dateStr);
  }

  function formatDate(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, "0");
    const d = String(date.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
  }

  // 日本の祝日リスト生成（固定祝日のみ - 振替休日等は含まない簡易版）
  function getJapaneseHolidays(year) {
    return [
      `${year}-01-01`, // 元日
      `${year}-01-13`, // 成人の日（第2月曜 - 簡易的に固定）
      `${year}-02-11`, // 建国記念の日
      `${year}-02-23`, // 天皇誕生日
      `${year}-03-20`, // 春分の日（概算）
      `${year}-04-29`, // 昭和の日
      `${year}-05-03`, // 憲法記念日
      `${year}-05-04`, // みどりの日
      `${year}-05-05`, // こどもの日
      `${year}-07-21`, // 海の日（第3月曜 - 簡易的に固定）
      `${year}-08-11`, // 山の日
      `${year}-09-16`, // 敬老の日（第3月曜 - 簡易的に固定）
      `${year}-09-23`, // 秋分の日（概算）
      `${year}-10-14`, // スポーツの日（第2月曜 - 簡易的に固定）
      `${year}-11-03`, // 文化の日
      `${year}-11-23`, // 勤労感謝の日
    ];
  }

  // ============================================
  // 勤怠入力ページの自動入力
  // ============================================

  // 打刻修正ページ (/employee/adit/modify/) での自動入力
  function fillAditModifyPage() {
    // 時間入力フィールドを探す
    const timeInputs = document.querySelectorAll('input[name="time"]');
    const typeSelects = document.querySelectorAll('select[name="adit_item"]');

    if (timeInputs.length >= 2 && typeSelects.length >= 2) {
      // 出勤
      typeSelects[0].value = "work_start";
      timeInputs[0].value = CONFIG.startTime;

      // 退勤
      typeSelects[1].value = "work_end";
      timeInputs[1].value = CONFIG.endTime;

      triggerChange(typeSelects[0]);
      triggerChange(timeInputs[0]);
      triggerChange(typeSelects[1]);
      triggerChange(timeInputs[1]);
    }
  }

  // 勤怠表ページでの一括自動入力
  function fillAttendanceTable() {
    // ジョブカンの勤怠表のテーブル行を取得
    const table = document.querySelector("#search-result");
    if (!table) return { filled: 0, skipped: 0 };

    const rows = table.querySelectorAll("tr");
    let filled = 0;
    let skipped = 0;

    rows.forEach((row) => {
      // 日付セルから日付を取得
      const dateCell = row.querySelector("td.date, td:first-child");
      if (!dateCell) return;

      const dateText = dateCell.textContent.trim();
      // "3/1(月)" のようなフォーマットを想定
      const dayMatch = dateText.match(
        /(\d{1,2})\/(\d{1,2})\s*[\(（]([日月火水木金土])[\)）]/
      );
      if (!dayMatch) return;

      const dayOfWeek = dayMatch[3];
      // 土日はスキップ
      if (dayOfWeek === "土" || dayOfWeek === "日") {
        skipped++;
        return;
      }

      // 既に入力済みの場合はスキップ
      const startInput = row.querySelector(
        'input[name*="start"], input.start-time, input[data-field="start"]'
      );
      const endInput = row.querySelector(
        'input[name*="end"], input.end-time, input[data-field="end"]'
      );

      if (startInput && endInput) {
        if (startInput.value && endInput.value) {
          skipped++;
          return;
        }
        startInput.value = CONFIG.startTime;
        endInput.value = CONFIG.endTime;
        triggerChange(startInput);
        triggerChange(endInput);
        filled++;
      }
    });

    return { filled, skipped };
  }

  // 変更イベントを発火させる
  function triggerChange(element) {
    element.dispatchEvent(new Event("change", { bubbles: true }));
    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("blur", { bubbles: true }));
  }

  // ============================================
  // UI（操作ボタン）の作成
  // ============================================
  function createControlPanel() {
    const panel = document.createElement("div");
    panel.id = "jobcan-autofill-panel";
    panel.style.cssText = `
      position: fixed;
      top: 10px;
      right: 10px;
      z-index: 9999;
      background: #fff;
      border: 2px solid #4CAF50;
      border-radius: 8px;
      padding: 12px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.15);
      font-family: sans-serif;
      font-size: 13px;
      min-width: 220px;
    `;

    const title = document.createElement("div");
    title.textContent = "勤怠自動入力";
    title.style.cssText =
      "font-weight: bold; margin-bottom: 8px; color: #333; font-size: 14px;";
    panel.appendChild(title);

    // 時間設定表示
    const timeInfo = document.createElement("div");
    timeInfo.textContent = `出勤: ${CONFIG.startTime} / 退勤: ${CONFIG.endTime}`;
    timeInfo.style.cssText =
      "margin-bottom: 10px; color: #666; font-size: 12px;";
    panel.appendChild(timeInfo);

    // 自動入力ボタン（打刻修正ページ用）
    if (window.location.pathname.includes("/adit/modify")) {
      const fillBtn = createButton("この日の時間を入力", "#4CAF50", () => {
        fillAditModifyPage();
        showNotification("入力完了しました");
      });
      panel.appendChild(fillBtn);
    }

    // 一括入力ボタン（勤怠表ページ用）
    if (
      window.location.pathname.includes("/employee/attendance") ||
      window.location.pathname === "/employee" ||
      window.location.pathname === "/employee/"
    ) {
      const bulkBtn = createButton("平日を一括入力", "#2196F3", () => {
        const result = fillAttendanceTable();
        showNotification(
          `入力: ${result.filled}日 / スキップ: ${result.skipped}日`
        );
      });
      panel.appendChild(bulkBtn);
    }

    // 閉じるボタン
    const closeBtn = document.createElement("span");
    closeBtn.textContent = "×";
    closeBtn.style.cssText = `
      position: absolute; top: 4px; right: 8px;
      cursor: pointer; color: #999; font-size: 16px;
    `;
    closeBtn.addEventListener("click", () => panel.remove());
    panel.appendChild(closeBtn);

    document.body.appendChild(panel);
  }

  function createButton(text, color, onClick) {
    const btn = document.createElement("button");
    btn.textContent = text;
    btn.style.cssText = `
      display: block; width: 100%; padding: 8px 12px;
      margin-bottom: 6px; border: none; border-radius: 4px;
      background: ${color}; color: #fff; cursor: pointer;
      font-size: 13px; font-weight: bold;
    `;
    btn.addEventListener("mouseenter", () => {
      btn.style.opacity = "0.85";
    });
    btn.addEventListener("mouseleave", () => {
      btn.style.opacity = "1";
    });
    btn.addEventListener("click", onClick);
    return btn;
  }

  function showNotification(message) {
    const notification = document.createElement("div");
    notification.textContent = message;
    notification.style.cssText = `
      position: fixed; bottom: 20px; right: 20px; z-index: 10000;
      background: #333; color: #fff; padding: 12px 20px;
      border-radius: 6px; font-size: 14px; font-family: sans-serif;
      box-shadow: 0 4px 12px rgba(0,0,0,0.3);
      animation: fadeIn 0.3s ease;
    `;
    document.body.appendChild(notification);
    setTimeout(() => {
      notification.style.opacity = "0";
      notification.style.transition = "opacity 0.3s ease";
      setTimeout(() => notification.remove(), 300);
    }, 3000);
  }

  // ============================================
  // 初期化
  // ============================================
  // ページ読み込み完了後に実行
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", createControlPanel);
  } else {
    createControlPanel();
  }
})();
