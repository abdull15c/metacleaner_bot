(function () {
  const tg = window.Telegram && window.Telegram.WebApp;
  if (tg) {
    tg.ready();
    tg.expand();
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
  window.getTelegramInitData = initData;

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
  window.showWebappToast = showToast;

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
        dropZone.classList.add("dragover");
      }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
      dropZone.addEventListener(eventName, () => {
        dropZone.classList.remove("dragover");
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
      barWrap.hidden = true;
      bar.style.width = "0%";
      if (doneActions) doneActions.hidden = true;
      form.style.display = "block";
    });
  }

  // --- Tabs ---
  const tabUpload = document.getElementById("tab-upload");
  const tabDownload = document.getElementById("tab-download");
  const tabHistory = document.getElementById("tab-history");
  const contentUpload = document.getElementById("upload-tab-content");
  const contentDownload = document.getElementById("download-tab-content");
  const contentHistory = document.getElementById("history-tab-content");
  const historyList = document.getElementById("history-list");
  const btnRefreshHistory = document.getElementById("btn-refresh-history");

  function resetTabs() {
      if(tabUpload) tabUpload.classList.remove("active");
      if(tabDownload) tabDownload.classList.remove("active");
      if(tabHistory) tabHistory.classList.remove("active");
      if(contentUpload) contentUpload.style.display = "none";
      if(contentDownload) contentDownload.style.display = "none";
      if(contentHistory) contentHistory.style.display = "none";
  }

  function switchTab(tab) {
    resetTabs();
    if (tab === "upload") {
      if (tabUpload) {
        tabUpload.classList.add("active");
      }
      if (contentUpload) contentUpload.style.display = "block";
    } else if (tab === "download") {
      if (tabDownload) {
        tabDownload.classList.add("active");
      }
      if (contentDownload) contentDownload.style.display = "block";
    } else {
      if (tabHistory) {
        tabHistory.classList.add("active");
      }
      if (contentHistory) contentHistory.style.display = "block";
      loadHistory();
    }
  }
  
  if (tabUpload) tabUpload.addEventListener("click", () => switchTab("upload"));
  if (tabDownload) tabDownload.addEventListener("click", () => switchTab("download"));
  if (tabHistory) tabHistory.addEventListener("click", () => switchTab("history"));
  if (btnRefreshHistory) btnRefreshHistory.addEventListener("click", loadHistory);
  
  async function loadHistory() {
    try {
      if (!lastInitData) lastInitData = initData();
      if (!lastInitData) {
        if (historyList) historyList.innerHTML = `<div style="text-align: center; padding: 30px; color: var(--tg-theme-hint-color, #888);">Откройте приложение через Telegram, чтобы увидеть историю.</div>`;
        return;
      }
      
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
        
        let dateStr = new Date(j.created_at).toLocaleDateString("ru-RU", {day:"numeric", month:"short", hour:"2-digit", minute:"2-digit"});

        const iconEl = document.createElement("div");
        iconEl.className = "hi-icon";
        iconEl.textContent = icon;

        const contentEl = document.createElement("div");
        contentEl.className = "hi-content";

        const titleEl = document.createElement("div");
        titleEl.className = "hi-title";
        titleEl.textContent = j.original_filename || "video.mp4";

        const metaEl = document.createElement("div");
        metaEl.className = "hi-meta";
        const dateEl = document.createElement("span");
        dateEl.textContent = dateStr;
        const statusTextEl = document.createElement("span");
        statusTextEl.textContent = statusText;
        metaEl.append(dateEl, statusTextEl);
        contentEl.append(titleEl, metaEl);

        const actionEl = document.createElement("div");
        if (j.status === "done" && j.result_download_available) {
          const btn = document.createElement("button");
          btn.className = "hi-action dl";
          btn.type = "button";
          btn.textContent = "Скачать";
          btn.addEventListener("click", () => window.downloadResult(j.uuid, lastInitData));
          actionEl.appendChild(btn);
        }

        div.append(iconEl, contentEl, actionEl);
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

let downloadJobUuid = null;
let downloadPollInterval = null;
let availableDownloadFormats = [];
let selectedDownloadKind = "video";

const dlUrlInput = document.getElementById('download-url');
const btnGetInfo = document.getElementById('btn-get-info');
const btnStartDownload = document.getElementById('btn-start-download');
const dlStep1 = document.getElementById('download-step-1');
const dlStep2 = document.getElementById('download-step-2');
const dlStep3 = document.getElementById('download-step-3');
const dlStep4 = document.getElementById('download-step-4');
const formatOptions = document.getElementById('format-options');
const formatSelect = document.getElementById('dl-format');
const metadataOption = document.getElementById('metadata-option');
const mediaSwitchButtons = document.querySelectorAll('.media-switch-btn');

function currentInitData() {
    return typeof window.getTelegramInitData === "function" ? window.getTelegramInitData() : "";
}

function showDownloadError(message) {
    if (typeof window.showWebappToast === "function") {
        window.showWebappToast(message, "error");
    } else {
        alert(message);
    }
}

function formatKind(format) {
    if (format.kind) return format.kind;
    return String(format.id || "").startsWith("mp3_") || String(format.id || "").startsWith("m4a_") ? "audio" : "video";
}

function selectDownloadFormat(formatId) {
    if (formatSelect) formatSelect.value = formatId;
    if (formatOptions) {
        formatOptions.querySelectorAll(".format-card").forEach(card => {
            card.classList.toggle("active", card.dataset.formatId === formatId);
        });
    }
}

function renderDownloadFormats(kind = selectedDownloadKind) {
    selectedDownloadKind = kind;
    mediaSwitchButtons.forEach(btn => btn.classList.toggle("active", btn.dataset.kind === kind));
    if (metadataOption) {
        metadataOption.classList.toggle("is-audio", kind === "audio");
    }
    if (btnStartDownload) {
        btnStartDownload.textContent = kind === "audio" ? "Скачать аудио" : "Скачать видео";
    }
    if (!formatOptions || !formatSelect) return;

    formatOptions.innerHTML = "";
    formatSelect.innerHTML = "";

    const filtered = availableDownloadFormats.filter(f => formatKind(f) === kind);
    if (filtered.length === 0) {
        const empty = document.createElement("div");
        empty.className = "format-empty";
        empty.textContent = "Нет доступных вариантов для этого типа.";
        formatOptions.appendChild(empty);
        return;
    }
    filtered.forEach((f, index) => {
        const opt = document.createElement('option');
        opt.value = f.id;
        opt.textContent = f.label;
        formatSelect.appendChild(opt);

        const card = document.createElement("button");
        card.type = "button";
        card.className = "format-card";
        card.dataset.formatId = f.id;
        const main = document.createElement("span");
        main.className = "format-main";
        main.textContent = f.label;
        const sub = document.createElement("span");
        sub.className = "format-sub";
        sub.textContent = f.description || f.ext || "";
        card.append(main, sub);
        card.addEventListener("click", () => selectDownloadFormat(f.id));
        formatOptions.appendChild(card);

        if (index === 0) selectDownloadFormat(f.id);
    });
}

mediaSwitchButtons.forEach(btn => {
    btn.addEventListener("click", () => renderDownloadFormats(btn.dataset.kind));
});

if (btnGetInfo) {
    btnGetInfo.addEventListener('click', async () => {
        const url = dlUrlInput.value.trim();
        if (!url) return;
        
        btnGetInfo.disabled = true;
        btnGetInfo.textContent = "Получение...";
        
        try {
            const idata = currentInitData();
            if (!idata) {
                showDownloadError("Откройте приложение через Telegram.");
                btnGetInfo.disabled = false;
                btnGetInfo.textContent = "Получить информацию";
                return;
            }
            const resp = await fetch('/api/webapp/download/info', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Telegram-Init-Data': idata
                },
                body: JSON.stringify({ url })
            });
            
            const data = await resp.json();
            
            if (!resp.ok || !data.supported) {
                alert(data.error || "Платформа не поддерживается или произошла ошибка.");
                btnGetInfo.disabled = false;
                btnGetInfo.textContent = "Получить информацию";
                return;
            }
            
            document.getElementById('dl-thumb').src = data.thumbnail || '';
            document.getElementById('dl-title').textContent = data.title;
            
            const min = Math.floor(data.duration_sec / 60);
            const sec = data.duration_sec % 60;
            document.getElementById('dl-platform').textContent = `${data.platform.toUpperCase()} • ${min}:${sec.toString().padStart(2, '0')}`;
            
            availableDownloadFormats = Array.isArray(data.formats) ? data.formats : [];
            renderDownloadFormats("video");
            
            dlStep1.style.display = 'none';
            dlStep2.style.display = 'block';
        } catch (e) {
            alert("Ошибка сети");
        }
        
        btnGetInfo.disabled = false;
        btnGetInfo.textContent = "Получить информацию";
    });
}

if (document.getElementById('btn-dl-back')) {
    document.getElementById('btn-dl-back').addEventListener('click', () => {
        dlStep2.style.display = 'none';
        dlStep1.style.display = 'block';
    });
}

if (btnStartDownload) {
    btnStartDownload.addEventListener('click', async () => {
        const url = dlUrlInput.value.trim();
        const format = formatSelect ? formatSelect.value : "";
        const clean_metadata = document.getElementById('dl-clean-metadata').checked;
        if (!format) {
            showDownloadError("Выберите качество или формат.");
            return;
        }
        
        dlStep2.style.display = 'none';
        dlStep3.style.display = 'block';
        
        try {
            const idata = currentInitData();
            if (!idata) {
                showDownloadError("Откройте приложение через Telegram.");
                dlStep3.style.display = 'none';
                dlStep2.style.display = 'block';
                return;
            }
            const resp = await fetch('/api/webapp/download/start', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Telegram-Init-Data': idata
                },
                body: JSON.stringify({ url, format, clean_metadata })
            });
            
            const data = await resp.json();
            
            if (!resp.ok) {
                alert(data.detail || "Ошибка");
                dlStep3.style.display = 'none';
                dlStep2.style.display = 'block';
                return;
            }
            
            downloadJobUuid = data.job_id;
            pollDownloadJob();
        } catch (e) {
            alert("Ошибка сети");
            dlStep3.style.display = 'none';
            dlStep2.style.display = 'block';
        }
    });
}

function pollDownloadJob() {
    if (downloadPollInterval) clearInterval(downloadPollInterval);
    
    downloadPollInterval = setInterval(async () => {
        try {
            const idata = currentInitData();
            if (!idata) {
                clearInterval(downloadPollInterval);
                showDownloadError("Сессия Telegram недоступна. Откройте приложение заново из бота.");
                dlStep3.style.display = 'none';
                dlStep1.style.display = 'block';
                return;
            }
            const resp = await fetch(`/api/webapp/download/job/${downloadJobUuid}`, {
                headers: { 'X-Telegram-Init-Data': idata }
            });
            
            if (resp.ok) {
                const data = await resp.json();
                const statusText = document.getElementById('dl-status-text');
                if (statusText) {
                    const labels = {
                        pending: "В очереди...",
                        downloading: "Скачиваем файл...",
                        processing: "Очищаем метаданные...",
                        done: "Готово",
                        failed: "Ошибка скачивания",
                        cancelled: "Отменено"
                    };
                    statusText.textContent = labels[data.status] || "Обрабатываем...";
                }
                
                if (data.status === 'done') {
                    clearInterval(downloadPollInterval);
                    dlStep3.style.display = 'none';
                    dlStep4.style.display = 'block';
                    
                    const btnDlFile = document.getElementById('btn-download-file');
                    btnDlFile.onclick = (e) => {
                        e.preventDefault();
                        window.downloadResult(downloadJobUuid, currentInitData(), true, data.title);
                    };
                } else if (data.status === 'failed' || data.status === 'cancelled') {
                    clearInterval(downloadPollInterval);
                    alert("Ошибка скачивания: " + data.status);
                    dlStep3.style.display = 'none';
                    dlStep1.style.display = 'block';
                }
            } else {
                clearInterval(downloadPollInterval);
                showDownloadError("Не удалось получить статус скачивания.");
                dlStep3.style.display = 'none';
                dlStep1.style.display = 'block';
            }
        } catch (e) {
            clearInterval(downloadPollInterval);
            showDownloadError("Сеть недоступна. Попробуйте ещё раз.");
            dlStep3.style.display = 'none';
            dlStep1.style.display = 'block';
        }
    }, 3000);
}

if (document.getElementById('btn-dl-again')) {
    document.getElementById('btn-dl-again').addEventListener('click', () => {
        dlUrlInput.value = '';
        dlStep4.style.display = 'none';
        dlStep1.style.display = 'block';
    });
}

window.downloadResult = async function(jobUuid, idata, isSiteDownload = false, customTitle = null) {
  const endpoint = isSiteDownload ? `/api/webapp/download/result/` : `/api/webapp/result/`;
  const r = await fetch(endpoint + encodeURIComponent(jobUuid), {
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
  let filename = customTitle ? customTitle + ".mp4" : "video_clean.mp4";
  const cd = r.headers.get("Content-Disposition");
  if (cd) {
    const m = cd.match(/filename\*?=(?:UTF-8'')?["']?([^"';]+)/i);
    if (m) {
      try { filename = decodeURIComponent(m[1].trim()); }
      catch (_) { filename = m[1].trim(); }
    }
  }
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
};
