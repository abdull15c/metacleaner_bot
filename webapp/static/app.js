(function () {
  const tg = window.Telegram && window.Telegram.WebApp;
  if (tg) {
    tg.ready();
    tg.expand();
    if (tg.themeParams && tg.themeParams.bg_color) {
      document.body.style.background = tg.themeParams.bg_color;
    }
  }

  const pick = document.getElementById("pick");
  const fileInput = document.getElementById("file");
  const fname = document.getElementById("fname");
  const fsize = document.getElementById("fsize");
  const form = document.getElementById("up-form");
  const submit = document.getElementById("submit");
  const errEl = document.getElementById("err");
  const statusEl = document.getElementById("status");
  const barWrap = document.getElementById("bar-wrap");
  const bar = document.getElementById("bar");
  const doneActions = document.getElementById("done-actions");
  const btnDownload = document.getElementById("btn-download");
  const btnBot = document.getElementById("btn-bot");
  const botUser = typeof window.__TG_BOT__ === "string" ? window.__TG_BOT__.trim() : "";

  let lastJobUuid = null;
  let lastInitData = "";

  function initData() {
    if (!tg || !tg.initData) {
      return "";
    }
    return tg.initData;
  }

  function showErr(msg) {
    errEl.textContent = msg || "";
    errEl.hidden = !msg;
  }

  function fmtMb(bytes) {
    if (!bytes && bytes !== 0) return "";
    return (bytes / (1024 * 1024)).toFixed(2) + " МБ";
  }

  function showToast(message, type="info") {
    const el = document.createElement("div");
    el.style.background = type === "error" ? "#ef4444" : (type === "success" ? "#10b981" : "#374151");
    el.style.color = "white";
    el.style.padding = "10px 15px";
    el.style.borderRadius = "8px";
    el.style.fontSize = "0.9rem";
    el.style.boxShadow = "0 4px 6px rgba(0,0,0,0.1)";
    el.style.transition = "opacity 0.3s ease";
    el.textContent = message;
    
    const toastContainer = document.getElementById("toast-container");
    if (toastContainer) {
      toastContainer.appendChild(el);
      setTimeout(() => { el.style.opacity = "0"; }, 2500);
      setTimeout(() => { el.remove(); }, 3000);
    }
  }

  // --- Drag & Drop ---
  const dropZone = document.getElementById("drop-zone");
  const fileMetaContainer = document.getElementById("file-meta-container");
  const btnClear = document.getElementById("btn-clear");
  const btnReset = document.getElementById("btn-reset");

  if (dropZone) {
    dropZone.addEventListener("click", () => fileInput.click());
    
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
      dropZone.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) { e.preventDefault(); e.stopPropagation(); }

    ['dragenter', 'dragover'].forEach(eventName => {
      dropZone.addEventListener(eventName, () => {
        dropZone.style.background = "rgba(59, 130, 246, 0.05)";
        dropZone.style.borderColor = "var(--tg-theme-button-color, #3b82f6)";
      }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
      dropZone.addEventListener(eventName, () => {
        dropZone.style.background = "";
        dropZone.style.borderColor = "var(--tg-theme-hint-color, #ccc)";
      }, false);
    });

    dropZone.addEventListener("drop", (e) => {
      let dt = e.dataTransfer;
      let files = dt.files;
      if (files.length) {
        fileInput.files = files;
        handleFileSelection(files[0]);
      }
    }, false);
    
    document.addEventListener("paste", (e) => {
      if (e.clipboardData.files.length > 0) {
        let file = e.clipboardData.files[0];
        if (file.type.startsWith("video/")) {
          const dt = new DataTransfer();
          dt.items.add(file);
          fileInput.files = dt.files;
          handleFileSelection(file);
        }
      }
    });
  }

  fileInput.addEventListener("change", function () {
    if (this.files && this.files[0]) {
      handleFileSelection(this.files[0]);
    }
  });

  function handleFileSelection(f) {
    if (!f.type.startsWith("video/") && !f.name.match(/\.(mp4|mkv|mov|avi|webm|m4v)$/i)) {
      showToast("Пожалуйста, выберите видеофайл", "error");
      return;
    }
    fname.textContent = f.name;
    fsize.textContent = fmtMb(f.size);
    if (dropZone) dropZone.style.display = "none";
    if (fileMetaContainer) fileMetaContainer.style.display = "flex";
    submit.disabled = false;
    showErr("");
    if (doneActions) doneActions.hidden = true;
  }
  
  if (btnClear) {
    btnClear.addEventListener("click", () => {
      fileInput.value = "";
      if (dropZone) dropZone.style.display = "flex";
      if (fileMetaContainer) fileMetaContainer.style.display = "none";
      submit.disabled = true;
    });
  }

  if (btnReset) {
    btnReset.addEventListener("click", () => {
      if (btnClear) btnClear.click();
      statusEl.textContent = "";
      errEl.hidden = true;
      if (doneActions) doneActions.hidden = true;
      form.style.display = "block";
    });
  }

  // --- Tabs ---
  const tabUpload = document.getElementById("tab-upload");
  const tabHistory = document.getElementById("tab-history");
  const contentUpload = document.getElementById("upload-tab-content");
  const contentHistory = document.getElementById("history-tab-content");
  const historyList = document.getElementById("history-list");
  const btnRefreshHistory = document.getElementById("btn-refresh-history");

  function switchTab(tab) {
    if (tab === "upload") {
      if (tabUpload) {
        tabUpload.classList.add("active");
        tabUpload.style.borderBottomColor = "var(--tg-theme-button-color, #3b82f6)";
        tabUpload.style.color = "var(--tg-theme-text-color, #000)";
      }
      if (tabHistory) {
        tabHistory.classList.remove("active");
        tabHistory.style.borderBottomColor = "transparent";
        tabHistory.style.color = "var(--tg-theme-hint-color, #888)";
      }
      if (contentUpload) contentUpload.style.display = "block";
      if (contentHistory) contentHistory.style.display = "none";
    } else {
      if (tabHistory) {
        tabHistory.classList.add("active");
        tabHistory.style.borderBottomColor = "var(--tg-theme-button-color, #3b82f6)";
        tabHistory.style.color = "var(--tg-theme-text-color, #000)";
      }
      if (tabUpload) {
        tabUpload.classList.remove("active");
        tabUpload.style.borderBottomColor = "transparent";
        tabUpload.style.color = "var(--tg-theme-hint-color, #888)";
      }
      if (contentHistory) contentHistory.style.display = "block";
      if (contentUpload) contentUpload.style.display = "none";
      loadHistory();
    }
  }
  
  if (tabUpload) tabUpload.addEventListener("click", () => switchTab("upload"));
  if (tabHistory) tabHistory.addEventListener("click", () => switchTab("history"));
  if (btnRefreshHistory) btnRefreshHistory.addEventListener("click", loadHistory);
  
  async function loadHistory() {
    try {
      if (!lastInitData && tg.initData) lastInitData = tg.initData;
      if (!lastInitData) return;
      
      const r = await fetch("/api/webapp/jobs", {
        headers: { "X-Telegram-Init-Data": lastInitData },
      });
      if (!r.ok) throw new Error();
      const data = await r.json();
      
      if (!data.jobs || data.jobs.length === 0) {
        if (historyList) historyList.innerHTML = `<div style="text-align: center; padding: 30px; color: var(--tg-theme-hint-color, #888);">История пуста</div>`;
        return;
      }
      
      if (historyList) historyList.innerHTML = "";
      data.jobs.forEach(j => {
        const div = document.createElement("div");
        div.className = "history-item " + j.status;
        
        let icon = "❓";
        if (j.status === "done") icon = "✅";
        else if (j.status === "failed" || j.status === "cancelled") icon = "❌";
        else icon = "🔄";
        
        let statusText = j.status;
        if (j.status === "done") statusText = "Готово";
        else if (j.status === "failed") statusText = "Ошибка";
        else if (j.status === "pending") statusText = "В очереди";
        else if (j.status === "processing") statusText = "Обработка";
        
        let actionHtml = "";
        if (j.status === "done" && j.result_download_available) {
          actionHtml = `<button class="hi-action dl" onclick="window.downloadResult('${j.uuid}', '${lastInitData}')">Скачать</button>`;
        }
        
        let dateStr = new Date(j.created_at).toLocaleDateString("ru-RU", {day:"numeric", month:"short", hour:"2-digit", minute:"2-digit"});
        
        div.innerHTML = `
          <div class="hi-icon">${icon}</div>
          <div class="hi-content">
            <div class="hi-title">${j.original_filename || "video.mp4"}</div>
            <div class="hi-meta">
              <span>${dateStr}</span>
              <span>${statusText}</span>
            </div>
          </div>
          <div>${actionHtml}</div>
        `;
        if (historyList) historyList.appendChild(div);
      });
    } catch (e) {
      if (historyList) historyList.innerHTML = `<div style="text-align: center; padding: 30px; color: #ef4444;">Не удалось загрузить историю</div>`;
    }
  }

  const detailMap = {
    invalid_init_data: "Не удалось подтвердить вход Telegram. Закройте приложение и откройте снова из бота.",
    processing_disabled: "Обработка отключена.",
    maintenance: "Техобслуживание. Попробуйте позже.",
    banned: "Доступ ограничен.",
    active_job_exists: "Уже есть активная задача. Дождитесь или отмените в боте: /cancel",
    daily_limit: "Дневной лимит исчерпан.",
    unsupported_format: "Формат не поддерживается.",
    file_too_large: "Файл слишком большой.",
    empty_file: "Пустой файл.",
    queue_unavailable: "Очередь недоступна. Попробуйте позже.",
    save_failed: "Не удалось сохранить файл.",
  };

  async function downloadResult(jobUuid, idata) {
    const r = await fetch("/api/webapp/result/" + encodeURIComponent(jobUuid), {
      headers: { "X-Telegram-Init-Data": idata },
    });
    if (!r.ok) {
      statusEl.textContent = "Не удалось скачать файл (истёк срок или файл удалён).";
      return;
    }
    const blob = await r.blob();
    const cd = r.headers.get("Content-Disposition");
    let name = "video_clean.mp4";
    if (cd) {
      const m = cd.match(/filename\*?=(?:UTF-8'')?["']?([^"';]+)/i);
      if (m) {
        try {
          name = decodeURIComponent(m[1].trim());
        } catch (_) {
          name = m[1].trim();
        }
      }
    }
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.click();
    URL.revokeObjectURL(url);
    if (tg) tg.HapticFeedback.notificationOccurred("success");
  }

  if (btnDownload) {
    btnDownload.addEventListener("click", function () {
      if (lastJobUuid && lastInitData) {
        downloadResult(lastJobUuid, lastInitData);
      }
    });
  }

  if (btnBot && botUser) {
    btnBot.addEventListener("click", function () {
      const url = "https://t.me/" + botUser;
      if (tg && tg.openTelegramLink) {
        tg.openTelegramLink(url);
      } else {
        window.open(url, "_blank");
      }
    });
  }

  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    const idata = initData();
    if (!idata) {
      showErr("Откройте страницу через кнопку в Telegram.");
      return;
    }
    const f = fileInput.files && fileInput.files[0];
    if (!f) return;

    showErr("");
    submit.disabled = true;
    if (doneActions) doneActions.hidden = true;
    barWrap.hidden = false;
    bar.style.width = "15%";
    statusEl.textContent = "Загрузка…";

    const fd = new FormData();
    fd.append("init_data", idata);
    fd.append("file", f);

    try {
      const xhr = new XMLHttpRequest();
      const done = new Promise(function (resolve, reject) {
        xhr.upload.onprogress = function (ev) {
          if (ev.lengthComputable) {
            const p = Math.min(95, 15 + (ev.loaded / ev.total) * 80);
            bar.style.width = p + "%";
          }
        };
        xhr.onload = function () {
          resolve({ status: xhr.status, body: xhr.responseText });
        };
        xhr.onerror = function () {
          reject(new Error("network"));
        };
      });
      xhr.open("POST", "/api/webapp/upload");
      xhr.send(fd);
      const res = await done;
      bar.style.width = "100%";

      if (res.status !== 200) {
        let detail = "upload_failed";
        try {
          const j = JSON.parse(res.body);
          detail = j.detail || detail;
        } catch (_) {}
        showErr(detailMap[detail] || "Ошибка загрузки.");
        submit.disabled = false;
        return;
      }

      const data = JSON.parse(res.body);
      const jobUuid = data.job_uuid;
      lastJobUuid = jobUuid;
      lastInitData = idata;
      statusEl.textContent = "В очереди…";

      const poll = async function () {
        const r = await fetch("/api/webapp/job/" + encodeURIComponent(jobUuid), {
          headers: { "X-Telegram-Init-Data": idata },
        });
        if (!r.ok) {
          statusEl.textContent = "Не удалось получить статус.";
          return;
        }
        const j = await r.json();
        const st = j.status;
        const labels = {
          pending: "В очереди…",
          downloading: "Скачивание…",
          processing: "Обработка…",
          sending: "Отправка в бот или подготовка ссылки…",
          done: "Готово.",
          failed: "Ошибка: " + (j.error_message || st),
          cancelled: "Отменено",
        };
        statusEl.textContent = labels[st] || st;
        
        if (st === "done" || st === "failed" || st === "cancelled") {
            if (st === "done") {
              if (tg) tg.HapticFeedback.notificationOccurred("success");
              const big = j.processed_size_bytes && j.telegram_send_limit_bytes && j.processed_size_bytes > j.telegram_send_limit_bytes;
              const note = big ? " Файл большой — скачайте здесь или по ссылке из бота." : " Результат также отправлен в чат бота.";
              statusEl.textContent = (labels.done || "Готово.") + note;
              if (doneActions && j.result_download_available) {
                doneActions.hidden = false;
              }
              showToast("Видео успешно обработано!", "success");
            } else {
              if (tg) tg.HapticFeedback.notificationOccurred("error");
              statusEl.textContent = labels[st] || st;
              showToast(labels[st] || "Произошла ошибка при обработке", "error");
            }
            submit.disabled = false;
            return;
        }
        setTimeout(poll, 2000);
      };
      poll();
    } catch (_) {
      showErr("Сеть недоступна.");
      submit.disabled = false;
    }
  });
})();

window.downloadResult = async function(jobUuid, idata) {
  const r = await fetch("/api/webapp/result/" + encodeURIComponent(jobUuid), {
    headers: { "X-Telegram-Init-Data": idata },
  });
  if (!r.ok) {
    const toastContainer = document.getElementById("toast-container");
    if (toastContainer) {
      const el = document.createElement("div");
      el.style.background = "#ef4444";
      el.style.color = "white";
      el.style.padding = "10px 15px";
      el.style.borderRadius = "8px";
      el.textContent = "Файл недоступен (истёк срок хранения).";
      toastContainer.appendChild(el);
      setTimeout(() => el.remove(), 3000);
    }
    return;
  }
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "video_clean.mp4";
  a.click();
  URL.revokeObjectURL(url);
};
