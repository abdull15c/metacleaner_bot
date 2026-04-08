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

  pick.addEventListener("click", function () {
    fileInput.click();
  });

  fileInput.addEventListener("change", function () {
    const f = fileInput.files && fileInput.files[0];
    fname.textContent = f ? f.name : "Файл не выбран";
    fsize.textContent = f ? fmtMb(f.size) : "";
    submit.disabled = !f;
    showErr("");
    if (doneActions) doneActions.hidden = true;
  });

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
        if (st === "done") {
          if (tg) tg.HapticFeedback.notificationOccurred("success");
          const big =
            j.processed_size_bytes &&
            j.telegram_send_limit_bytes &&
            j.processed_size_bytes > j.telegram_send_limit_bytes;
          const note = big
            ? " Файл большой — скачайте здесь или по ссылке из бота."
            : " Результат также отправлен в чат бота.";
          statusEl.textContent = (labels.done || "Готово.") + note;
          if (doneActions && j.result_download_available) {
            doneActions.hidden = false;
          }
          return;
        }
        if (st === "failed" || st === "cancelled") {
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
