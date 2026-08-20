/* DBYT frontend logic */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);

  // Elements
  const tabYoutube = $("tab-youtube");
  const tabUpload = $("tab-upload");
  const panelYoutube = $("panel-youtube");
  const panelUpload = $("panel-upload");
  const urlInput = $("youtube-url");
  const statusDot = $("status-dot");
  const statusText = $("status-text");
  const metaHint = $("video-meta-hint");
  const projectName = $("project-name");
  const targetLang = $("target-lang");
  const engine = $("engine");
  const keepBg = $("keep-bg");
  const preserveEmotions = $("preserve-emotions");
  const wordLevel = $("word-level");
  const lipSync = $("lip-sync");
  const startBtn = $("start-btn");
  const ctaText = $("cta-text");
  const jobStatus = $("job-status");
  const jobTitle = $("job-title");
  const jobBadge = $("job-badge");
  const jobFill = $("job-fill");
  const jobMessage = $("job-message");
  const downloadBtn = $("download-btn");
  const dropzone = $("dropzone");
  const fileInput = $("file-input");
  const uploadProgress = $("upload-progress");
  const uploadFill = $("upload-fill");
  const uploadStatusText = $("upload-status-text");

  let currentMode = "youtube";
  let uploadId = null;
  let uploadedName = null;
  let pollTimer = null;
  let urlCheckTimer = null;

  /* ---------- Tabs ---------- */
  function setMode(mode) {
    currentMode = mode;
    const y = mode === "youtube";
    tabYoutube.classList.toggle("active", y);
    tabUpload.classList.toggle("active", !y);
    tabYoutube.setAttribute("aria-selected", y);
    tabUpload.setAttribute("aria-selected", !y);
    panelYoutube.classList.toggle("hidden", !y);
    panelUpload.classList.toggle("hidden", y);
  }
  tabYoutube.addEventListener("click", () => setMode("youtube"));
  tabUpload.addEventListener("click", () => setMode("upload"));

  /* ---------- YouTube URL validation + auto-fill ---------- */
  function setLinkStatus(state, text) {
    statusDot.className = "status-dot";
    statusText.className = "status-text";
    if (state) {
      statusDot.classList.add(state);
      statusText.classList.add(state);
    }
    statusText.textContent = text || "";
  }

  function looksLikeYouTube(url) {
    return /(youtube\.com|youtu\.be|youtube-nocookie\.com)/i.test(url || "");
  }

  async function validateUrl() {
    const url = urlInput.value.trim();
    if (!url) {
      setLinkStatus("", "");
      metaHint.textContent = "الصق رابط الفيديو وسيتم التحقق منه وتعبئة الاسم تلقائياً.";
      metaHint.className = "hint";
      return;
    }
    if (!looksLikeYouTube(url)) {
      setLinkStatus("invalid", "رابط غير صحيح");
      metaHint.textContent = "هذا لا يبدو رابط يوتيوب صالحاً.";
      metaHint.className = "hint";
      return;
    }

    setLinkStatus("checking", "جارٍ التحقق...");
    metaHint.textContent = "جارٍ جلب معلومات الفيديو...";
    metaHint.className = "hint";

    try {
      const res = await fetch("/api/youtube/info", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      const data = await res.json();
      if (data.valid) {
        setLinkStatus("valid", "رابط صحيح ✓");
        metaHint.textContent =
          `${data.title || "فيديو"} — ${data.channel ? "القناة: " + data.channel : ""}`;
        metaHint.className = "hint success";
        if (data.suggested_project_name && !projectName.value.trim()) {
          projectName.value = data.suggested_project_name;
        }
      } else {
        setLinkStatus("invalid", "رابط غير صحيح");
        metaHint.textContent = data.error || "تعذر جلب الفيديو.";
        metaHint.className = "hint";
      }
    } catch (e) {
      setLinkStatus("invalid", "خطأ");
      metaHint.textContent = "تعذر الاتصال بالخادم.";
      metaHint.className = "hint";
    }
  }

  urlInput.addEventListener("input", () => {
    clearTimeout(urlCheckTimer);
    setLinkStatus("checking", "جارٍ التحقق...");
    urlCheckTimer = setTimeout(validateUrl, 700);
  });

  /* ---------- Upload ---------- */
  dropzone.addEventListener("click", () => fileInput.click());
  dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  });
  dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
    if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
  });
  fileInput.addEventListener("change", () => {
    if (fileInput.files.length) handleFile(fileInput.files[0]);
  });

  async function handleFile(file) {
    uploadProgress.classList.remove("hidden");
    uploadStatusText.textContent = "جارٍ رفع " + file.name + "...";
    uploadFill.style.width = "0%";
    if (!projectName.value.trim()) {
      projectName.value = file.name.replace(/\.[^.]+$/, "").replace(/[^\w\s-]/g, "");
    }
    uploadedName = file.name;

    const form = new FormData();
    form.append("file", file);
    try {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/upload");
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          const pct = Math.round((e.loaded / e.total) * 100);
          uploadFill.style.width = pct + "%";
        }
      };
      const result = await new Promise((resolve, reject) => {
        xhr.onload = () => {
          try { resolve(JSON.parse(xhr.responseText)); }
          catch { reject(new Error(xhr.responseText)); }
        };
        xhr.onerror = () => reject(new Error("Upload failed"));
        xhr.send(form);
      });
      uploadId = result.upload_id;
      uploadStatusText.textContent = "تم رفع الملف ✓";
      uploadFill.style.width = "100%";
    } catch (e) {
      uploadStatusText.textContent = "فشل الرفع: " + e.message;
    }
  }

  /* ---------- Start dubbing ---------- */
  startBtn.addEventListener("click", startDubbing);

  async function startDubbing() {
    if (currentMode === "youtube") {
      const url = urlInput.value.trim();
      if (!url || !looksLikeYouTube(url)) {
        metaHint.textContent = "يرجى إدخال رابط يوتيوب صالح أولاً.";
        metaHint.className = "hint";
        return;
      }
    } else if (!uploadId) {
      uploadStatusText.textContent = "يرجى رفع ملف فيديو أولاً.";
      return;
    }

    const payload = {
      source: currentMode,
      target_language: targetLang.value,
      engine: engine.value,
      keep_background: keepBg.checked,
      preserve_emotions: preserveEmotions.checked,
      granularity: wordLevel.checked ? "word" : "segment",
      lip_sync: lipSync.checked,
      project_name: projectName.value.trim() || null,
    };
    if (currentMode === "youtube") payload.youtube_url = urlInput.value.trim();
    else payload.upload_id = uploadId;

    startBtn.disabled = true;
    ctaText.textContent = "⏳ جارٍ بدء المعالجة...";
    jobStatus.classList.remove("hidden");
    jobTitle.textContent = projectName.value.trim() || "المشروع";
    jobBadge.textContent = "قيد الانتظار";
    jobBadge.className = "job-badge";
    jobFill.style.width = "2%";
    jobMessage.textContent = "جارٍ إرسال الطلب...";
    downloadBtn.classList.add("hidden");

    try {
      const res = await fetch("/api/dub", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "فشل بدء المهمة");
      pollJob(data.job_id);
    } catch (e) {
      jobBadge.textContent = "خطأ";
      jobBadge.className = "job-badge error";
      jobMessage.textContent = e.message;
      resetCta();
    }
  }

  function resetCta() {
    startBtn.disabled = false;
    ctaText.textContent = "🎙️ ابدأ الدوبلاج الآن";
  }

  async function pollJob(jobId) {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(async () => {
      try {
        const res = await fetch("/api/status/" + jobId);
        const j = await res.json();
        jobFill.style.width = (j.progress || 0) + "%";
        jobMessage.textContent = j.message || "";
        jobBadge.textContent = statusLabel(j.status);
        jobBadge.className = "job-badge " +
          (j.status === "done" ? "done" : j.status === "error" ? "error" : "");

        if (j.status === "done") {
          clearInterval(pollTimer);
          downloadBtn.classList.remove("hidden");
          downloadBtn.href = j.output_url;
          resetCta();
        } else if (j.status === "error") {
          clearInterval(pollTimer);
          jobMessage.textContent = j.error || "حدث خطأ.";
          resetCta();
        }
      } catch (e) {
        jobMessage.textContent = "تعذر الاتصال بالخادم أثناء المعالجة.";
      }
    }, 2000);
  }

  function statusLabel(s) {
    return {
      queued: "قيد الانتظار",
      downloading: "جارٍ التحميل",
      transcribing: "نسخ الكلام",
      translating: "الترجمة",
      synthesizing: "توليد الصوت",
      mixing: "دمج الصوت",
      lip_syncing: "مزامنة الشفاه",
      done: "اكتمل ✓",
      error: "خطأ",
    }[s] || s;
  }
})();
