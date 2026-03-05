// ==UserScript==
// @name         ジョブカン勤怠自動入力
// @namespace    https://ssl.jobcan.jp/
// @version      2.0
// @description  平日の勤怠時間を9:00～17:00で自動入力（出勤簿→打刻修正→出勤簿のループ）
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
    startTime: "9:00",  // 出勤時間
    endTime: "17:00",   // 退勤時間
    remarks: "調整",     // 備考欄に入力する文字列
    delayMs: 2000,       // ページ遷移後の待機時間(ms)
  };

  // ============================================
  // セレクタ定義（実際のページに合わせて修正してください）
  // ============================================
  const SELECTORS = {
    // --- 出勤簿ページ ---
    // 勤怠テーブル全体
    attendanceTable: "#search-result",
    // テーブル内の各日付の行
    attendanceRows: "tr",
    // 各行内の日付セル（例: "1(月)", "2(火)" のようなテキストを含むセル）
    dateCell: "td:first-child",
    // 各行内の打刻修正リンク（鉛筆アイコンやリンク）
    editLink: 'a[href*="adit/modify"], a.edit-link',

    // --- 打刻修正ページ ---
    // 時間入力フィールド（出勤・退勤の順で複数ある想定）
    timeInputs: 'input[name="time"]',
    // 打刻種別セレクト（出勤・退勤を選ぶドロップダウン）
    typeSelects: 'select[name="adit_item"]',
    // 打刻種別の値
    typeValueStart: "work_start",  // 出勤の<option>のvalue
    typeValueEnd: "work_end",      // 退勤の<option>のvalue
    // 備考入力フィールド
    remarksInput: 'input[name="notice"], textarea[name="notice"], input[name="memo"], textarea[name="memo"]',
    // 保存ボタン
    saveButton: 'input[type="submit"], button[type="submit"], .btn-primary',
  };

  // ============================================
  // 状態管理（localStorage でページ遷移をまたいで保持）
  // ============================================
  const STORAGE_KEY = "jobcan_autofill_state";

  function getState() {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY)) || null;
    } catch {
      return null;
    }
  }

  function setState(state) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }

  function clearState() {
    localStorage.removeItem(STORAGE_KEY);
  }

  // ============================================
  // 出勤簿ページの処理
  // ============================================

  // 出勤簿テーブルから平日（未入力）の日付リストを取得
  function readWeekdays() {
    const table = document.querySelector(SELECTORS.attendanceTable);
    if (!table) {
      console.warn("[自動入力] 勤怠テーブルが見つかりません。セレクタを確認: ", SELECTORS.attendanceTable);
      return [];
    }

    const rows = table.querySelectorAll(SELECTORS.attendanceRows);
    const weekdays = [];

    rows.forEach((row) => {
      const dateCell = row.querySelector(SELECTORS.dateCell);
      if (!dateCell) return;

      const text = dateCell.textContent.trim();

      // "1(月)" や "15(金)" のような形式を想定
      const match = text.match(/(\d{1,2})\s*[\(（]([日月火水木金土])[\)）]/);
      if (!match) return;

      const day = parseInt(match[1], 10);
      const dayOfWeek = match[2];

      // 土日はスキップ
      if (dayOfWeek === "土" || dayOfWeek === "日") return;

      // 編集リンクを取得
      const editLink = row.querySelector(SELECTORS.editLink);
      if (!editLink) return;

      weekdays.push({
        day,
        dayOfWeek,
        editUrl: editLink.href,
        row,
      });
    });

    // 日付の昇順（古い順）にソート
    weekdays.sort((a, b) => a.day - b.day);
    return weekdays;
  }

  // ============================================
  // 打刻修正ページの処理
  // ============================================

  function fillAndSave() {
    return new Promise((resolve, reject) => {
      setTimeout(() => {
        try {
          // --- 時間入力 ---
          const timeInputs = document.querySelectorAll(SELECTORS.timeInputs);
          const typeSelects = document.querySelectorAll(SELECTORS.typeSelects);

          if (timeInputs.length < 2 || typeSelects.length < 2) {
            reject(new Error(
              `入力フィールドが不足: time=${timeInputs.length}, select=${typeSelects.length}\n` +
              `セレクタを確認: timeInputs="${SELECTORS.timeInputs}", typeSelects="${SELECTORS.typeSelects}"`
            ));
            return;
          }

          // 出勤
          typeSelects[0].value = SELECTORS.typeValueStart;
          triggerChange(typeSelects[0]);
          timeInputs[0].value = CONFIG.startTime;
          triggerChange(timeInputs[0]);

          // 退勤
          typeSelects[1].value = SELECTORS.typeValueEnd;
          triggerChange(typeSelects[1]);
          timeInputs[1].value = CONFIG.endTime;
          triggerChange(timeInputs[1]);

          // --- 備考入力 ---
          const remarksInput = document.querySelector(SELECTORS.remarksInput);
          if (remarksInput) {
            remarksInput.value = CONFIG.remarks;
            triggerChange(remarksInput);
          } else {
            console.warn("[自動入力] 備考フィールドが見つかりません。セレクタを確認: ", SELECTORS.remarksInput);
          }

          // --- 保存 ---
          const saveBtn = document.querySelector(SELECTORS.saveButton);
          if (!saveBtn) {
            reject(new Error("保存ボタンが見つかりません。セレクタを確認: " + SELECTORS.saveButton));
            return;
          }

          saveBtn.click();
          resolve();
        } catch (e) {
          reject(e);
        }
      }, CONFIG.delayMs);
    });
  }

  function triggerChange(element) {
    element.dispatchEvent(new Event("change", { bubbles: true }));
    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("blur", { bubbles: true }));
  }

  // ============================================
  // メインフロー制御
  // ============================================

  async function startAutoFill() {
    const weekdays = readWeekdays();
    if (weekdays.length === 0) {
      showNotification("対象の平日が見つかりませんでした", "error");
      return;
    }

    // 処理対象の日付リスト（URLのみ保存）をstateに保存
    const pending = weekdays.map((w) => ({
      day: w.day,
      dayOfWeek: w.dayOfWeek,
      editUrl: w.editUrl,
    }));

    setState({
      mode: "processing",
      pending,        // 未処理リスト
      currentIndex: 0,
      total: pending.length,
      returnUrl: window.location.href,  // 出勤簿ページのURL
    });

    showNotification(`${pending.length}日分の平日を検出。自動入力を開始します...`);

    // 最初の打刻修正ページへ遷移
    setTimeout(() => {
      window.location.href = pending[0].editUrl;
    }, 1500);
  }

  function resumeAutoFill() {
    const state = getState();
    if (!state || state.mode !== "processing") return;

    const path = window.location.pathname;

    // --- 打刻修正ページにいる場合 ---
    if (path.includes("/adit/modify") || path.includes("/edit")) {
      const current = state.pending[state.currentIndex];
      showNotification(
        `[${state.currentIndex + 1}/${state.total}] ${current.day}日(${current.dayOfWeek}) を入力中...`
      );

      fillAndSave()
        .then(() => {
          state.currentIndex++;

          if (state.currentIndex >= state.pending.length) {
            // 全日程完了
            clearState();
            showNotification("全平日の入力が完了しました！", "success");
            setTimeout(() => {
              window.location.href = state.returnUrl;
            }, 2000);
          } else {
            // 出勤簿ページに戻る（→ 次の日の処理へ）
            setState(state);
            setTimeout(() => {
              window.location.href = state.returnUrl;
            }, CONFIG.delayMs);
          }
        })
        .catch((err) => {
          console.error("[自動入力] エラー:", err);
          showNotification(`エラー: ${err.message}`, "error");
          clearState();
        });
      return;
    }

    // --- 出勤簿ページに戻ってきた場合 ---
    if (path === "/employee" || path === "/employee/" || path.includes("/employee/attendance")) {
      const nextIndex = state.currentIndex;
      if (nextIndex >= state.pending.length) {
        clearState();
        showNotification("全平日の入力が完了しました！", "success");
        return;
      }

      const next = state.pending[nextIndex];
      showNotification(
        `[${nextIndex + 1}/${state.total}] 次: ${next.day}日(${next.dayOfWeek})へ移動中...`
      );

      setTimeout(() => {
        window.location.href = next.editUrl;
      }, CONFIG.delayMs);
    }
  }

  // ============================================
  // 停止機能
  // ============================================
  function stopAutoFill() {
    const state = getState();
    clearState();
    if (state) {
      showNotification(
        `自動入力を停止しました (${state.currentIndex}/${state.total} 完了)`, "warn"
      );
    }
  }

  // ============================================
  // UI
  // ============================================

  function createControlPanel() {
    const panel = document.createElement("div");
    panel.id = "jobcan-autofill-panel";
    panel.style.cssText = `
      position: fixed; top: 10px; right: 10px; z-index: 9999;
      background: #fff; border: 2px solid #4CAF50; border-radius: 8px;
      padding: 14px; box-shadow: 0 4px 12px rgba(0,0,0,0.15);
      font-family: sans-serif; font-size: 13px; min-width: 240px;
    `;

    const title = document.createElement("div");
    title.textContent = "勤怠自動入力 v2.0";
    title.style.cssText = "font-weight: bold; margin-bottom: 6px; color: #333; font-size: 14px;";
    panel.appendChild(title);

    const info = document.createElement("div");
    info.textContent = `出勤 ${CONFIG.startTime} / 退勤 ${CONFIG.endTime} / 備考「${CONFIG.remarks}」`;
    info.style.cssText = "margin-bottom: 10px; color: #666; font-size: 11px;";
    panel.appendChild(info);

    const state = getState();

    if (state && state.mode === "processing") {
      // 実行中の場合: 停止ボタンを表示
      const statusText = document.createElement("div");
      statusText.textContent = `実行中: ${state.currentIndex}/${state.total} 完了`;
      statusText.style.cssText = "margin-bottom: 8px; color: #2196F3; font-weight: bold;";
      panel.appendChild(statusText);

      const stopBtn = createButton("停止", "#f44336", stopAutoFill);
      panel.appendChild(stopBtn);
    } else {
      // 出勤簿ページの場合: 開始ボタンを表示
      const path = window.location.pathname;
      if (path === "/employee" || path === "/employee/" || path.includes("/employee/attendance")) {
        const startBtn = createButton("平日を一括入力（開始）", "#4CAF50", () => {
          startBtn.disabled = true;
          startBtn.textContent = "読み取り中...";
          startAutoFill();
        });
        panel.appendChild(startBtn);

        // プレビューボタン
        const previewBtn = createButton("対象日をプレビュー", "#607D8B", () => {
          const weekdays = readWeekdays();
          if (weekdays.length === 0) {
            showNotification("対象の平日が見つかりません", "error");
            return;
          }
          const list = weekdays.map((w) => `${w.day}日(${w.dayOfWeek})`).join(", ");
          showNotification(`対象: ${list}（計${weekdays.length}日）`);
        });
        panel.appendChild(previewBtn);
      }
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
    btn.addEventListener("mouseenter", () => { btn.style.opacity = "0.85"; });
    btn.addEventListener("mouseleave", () => { btn.style.opacity = "1"; });
    btn.addEventListener("click", onClick);
    return btn;
  }

  function showNotification(message, type = "info") {
    const colors = {
      info: "#333",
      success: "#4CAF50",
      error: "#f44336",
      warn: "#FF9800",
    };
    const notification = document.createElement("div");
    notification.textContent = message;
    notification.style.cssText = `
      position: fixed; bottom: 20px; right: 20px; z-index: 10000;
      background: ${colors[type] || colors.info}; color: #fff;
      padding: 12px 20px; border-radius: 6px; font-size: 14px;
      font-family: sans-serif; box-shadow: 0 4px 12px rgba(0,0,0,0.3);
      max-width: 400px;
    `;
    document.body.appendChild(notification);
    setTimeout(() => {
      notification.style.opacity = "0";
      notification.style.transition = "opacity 0.3s ease";
      setTimeout(() => notification.remove(), 300);
    }, 4000);
  }

  // ============================================
  // 初期化
  // ============================================
  function init() {
    createControlPanel();

    // 実行中のstateがあれば自動再開
    const state = getState();
    if (state && state.mode === "processing") {
      setTimeout(resumeAutoFill, CONFIG.delayMs);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
