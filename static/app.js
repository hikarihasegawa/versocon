/* VersoCon frontend */
(() => {
  "use strict";

  const $ = (s) => document.querySelector(s);

  const dropCard = $("#dropCard");
  const dropzone = $("#dropzone");
  const fileInput = $("#fileInput");
  const fileList = $("#fileList");
  const controlsCard = $("#controlsCard");
  const btnConvert = $("#btnConvert");
  const btnZip = $("#btnZip");
  const resultsCard = $("#resultsCard");
  const resultsList = $("#resultsList");
  const btnResultsZip = $("#btnResultsZip");
  const toast = $("#toast");
  const qualityInput = $("#quality");
  const qualityVal = $("#qualityVal");
  const maxSideInput = $("#maxSide");

  const ACCEPT_RE = /\.(heic|heif|jpe?g|png|webp|bmp|tiff?|gif)$/i;

  let files = [];       // [File]
  let results = [];     // [{name, download, ...}]
  let fmt = "jpeg";

  /* ---------- sakura petals ---------- */
  (function petals() {
    const host = $("#petals");
    const n = 18;
    for (let i = 0; i < n; i++) {
      const p = document.createElement("div");
      p.className = "petal";
      const dur = 9 + Math.random() * 10;
      p.style.left = Math.random() * 100 + "vw";
      p.style.animationDuration = dur + "s";
      p.style.animationDelay = -Math.random() * dur + "s";
      p.style.setProperty("--sway", (Math.random() * 120 - 60).toFixed(0) + "px");
      p.style.setProperty("--o", (0.35 + Math.random() * 0.5).toFixed(2));
      const s = 8 + Math.random() * 10;
      p.style.width = s + "px";
      p.style.height = s + "px";
      host.appendChild(p);
    }
  })();

  /* ---------- helpers ---------- */
  let toastTimer = 0;
  function showToast(msg, kind) {
    toast.textContent = msg;
    toast.classList.remove("ok", "err", "warn");
    if (kind) toast.classList.add(kind);
    toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("show"), 3200);
  }

  const fmtBytes = (n) => {
    if (n < 1024) return n + " B";
    if (n < 1048576) return (n / 1024).toFixed(1) + " KB";
    return (n / 1048576).toFixed(2) + " MB";
  };

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  /* ---------- queue ---------- */
  function addFiles(list) {
    for (const f of list) {
      if (!ACCEPT_RE.test(f.name)) {
        showToast(`Formato non supportato: ${f.name}`, "err");
        continue;
      }
      if (files.some((x) => x.name === f.name && x.size === f.size)) continue;
      files.push(f);
    }
    renderQueue();
  }

  function renderQueue() {
    if (files.length === 0) {
      fileList.hidden = true;
      controlsCard.hidden = true;
      dropCard.classList.remove("has-files");
      return;
    }
    fileList.hidden = false;
    controlsCard.hidden = false;
    dropCard.classList.add("has-files");
    fileList.innerHTML = files
      .map(
        (f, i) => `
      <li class="file" data-i="${i}">
        <span class="ficon">🖼</span>
        <span class="fname" title="${esc(f.name)}">${esc(f.name)}</span>
        <span class="fsize">${fmtBytes(f.size)}</span>
        <button class="rm" title="Rimuovi" aria-label="Rimuovi">✕</button>
      </li>`
      )
      .join("");
  }

  fileList.addEventListener("click", (e) => {
    const btn = e.target.closest(".rm");
    if (!btn) return;
    const li = btn.closest("[data-i]");
    files.splice(+li.dataset.i, 1);
    renderQueue();
  });

  /* ---------- format selection ---------- */
  document.querySelectorAll(".seg-btn").forEach((b) => {
    b.addEventListener("click", () => {
      document.querySelectorAll(".seg-btn").forEach((x) => {
        x.classList.remove("active");
        x.setAttribute("aria-checked", "false");
      });
      b.classList.add("active");
      b.setAttribute("aria-checked", "true");
      fmt = b.dataset.fmt;
      const q = qualityInput, w = q.closest(".ctl");
      const noQ = fmt === "png" || fmt === "gif";
      q.disabled = noQ;
      w.style.opacity = noQ ? ".45" : "1";
      results = [];
      renderResults();
    });
  });

  /* ---------- quality & size ---------- */
  qualityInput.addEventListener("input", () => {
    qualityVal.textContent = qualityInput.value;
  });

  /* ---------- convert ---------- */
  btnConvert.addEventListener("click", async () => {
    if (!files.length) return showToast("Nessun file in coda.", "err");
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    fd.append("fmt", fmt);
    if (fmt !== "png" && fmt !== "gif" && qualityInput.value) fd.append("quality", qualityInput.value);
    const ms = (maxSideInput.value || "").trim();
    if (ms && +ms > 0) fd.append("max_side", ms);

    btnConvert.disabled = true;
    btnConvert.textContent = "Convertendo…";
    try {
      const res = await fetch("/api/convert", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) {
        const detail = (data && data.detail && data.detail !== "All files failed to convert")
          ? `: ${data.detail}` : "";
        throw new Error(`Conversione fallita${detail}`);
      }
      results = data.results;
      renderResults();
      showToast(`${results.filter((r) => !r.error).length} file convertiti ✓`, "ok");
    } catch (err) {
      showToast(err.message || String(err), "err");
    } finally {
      btnConvert.disabled = false;
      btnConvert.textContent = "Converti";
    }
  });

  function renderResults() {
    const ok = results.filter((r) => !r.error);
    if (!results.length) {
      resultsCard.hidden = true;
      btnZip.hidden = true;
      return;
    }
    resultsCard.hidden = false;
    resultsList.innerHTML = results
      .map((r) => {
        if (r.error) {
          return `<li class="file"><span class="ficon">⚠</span><span class="fname">${esc(r.name)}</span><span class="ferr">${esc(r.error)}</span></li>`;
        }
        return `<li class="file"><span class="ficon">✓</span>
          <span class="fname">${esc(r.name)}</span>
          ${r.src_size ? `<span class="fsize muted">${fmtBytes(r.src_size)} → </span>` : ""}
          <span class="fsize">${fmtBytes(r.size)}</span>
          ${r.saved_pct != null ? `<span class="fsaved">-${r.saved_pct}%</span>` : ""}
          <a href="${r.download}" download>Scarica</a></li>`;
      })
      .join("");
    btnZip.hidden = ok.length < 2;
    btnResultsZip.hidden = ok.length < 2;
  }

  function downloadResultsZip() {
    const names = results.filter((r) => !r.error).map((r) => r.name).join(",");
    if (!names) return;
    window.location.href = `/api/download?names=${encodeURIComponent(names)}`;
  }

  btnZip.addEventListener("click", downloadResultsZip);
  btnResultsZip.addEventListener("click", downloadResultsZip);

  /* ---------- drag & drop / picker ---------- */
  dropzone.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", () => {
    addFiles([...fileInput.files]);
    fileInput.value = "";
  });

  ["dragenter", "dragover"].forEach((ev) =>
    dropCard.addEventListener(ev, (e) => {
      e.preventDefault();
      dropCard.classList.add("dragover");
    })
  );
  ["dragleave", "drop"].forEach((ev) =>
    dropCard.addEventListener(ev, (e) => {
      e.preventDefault();
      if (ev === "drop") {
        dropCard.classList.remove("dragover");
        if (e.dataTransfer && e.dataTransfer.files) addFiles([...e.dataTransfer.files]);
      } else if (e.target === dropCard || !dropCard.contains(e.relatedTarget)) {
        dropCard.classList.remove("dragover");
      }
    })
  );

  /* ---------- tabs ---------- */
  const tabPhotos = $("#tabPhotos");
  const tabPdf = $("#tabPdf");
  const tabCompress = $("#tabCompress");
  const tabVideo = $("#tabVideo");
  const tabExtra = $("#tabExtra");
  const TABS = { photos: tabPhotos, pdf: tabPdf, compress: tabCompress, video: tabVideo, extra: tabExtra };
  document.querySelectorAll(".tabs .tab").forEach((b) => {
    b.addEventListener("click", () => {
      document.querySelectorAll(".tabs .tab").forEach((x) => {
        x.classList.remove("active");
        x.setAttribute("aria-selected", "false");
      });
      b.classList.add("active");
      b.setAttribute("aria-selected", "true");
      const t = b.dataset.tab;
      for (const k in TABS) TABS[k].hidden = k !== t;
      results = [];
      renderResults();
    });
  });

   /* ---------- PDF sub-tabs ---------- */
  document.querySelectorAll("#tabPdf .subtabs .subtab").forEach((b) => {
    b.addEventListener("click", () => {
      document.querySelectorAll("#tabPdf .subtabs .subtab").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      const s = b.dataset.sub;
      document.querySelectorAll("#tabPdf .subpane").forEach((p) => {
        p.hidden = (p.id !== "sub" + s);
      });
    });
  });

  /* ---------- Compress: sub-tabs (Immagine / PDF) ---------- */
  const cImgPane = $("#cimg");
  const cPdfPane = $("#cpdf");
  document.querySelectorAll("#tabCompress .subtabs .subtab").forEach((b) => {
    b.addEventListener("click", () => {
      document.querySelectorAll("#tabCompress .subtabs .subtab").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      const s = b.dataset.csub;
      cImgPane.hidden = s !== "image";
      cPdfPane.hidden = s !== "pdf";
    });
  });

  /* ---------- PDF -> immagini ---------- */
  const pdfFmt = $("#pdfFmt");
  const pdfQ = $("#pdfQ");
  const pdfQVal = $("#pdfQVal");
  const pdfDpi = $("#pdfDpi");
  const pdfDpiVal = $("#pdfDpiVal");
  const btnPdfConvert = $("#btnPdfConvert");
  const btnPdfZip = $("#btnPdfZip");
  let pdfFile = null;

  function syncPdfQuality() {
    const hideQ = pdfFmt.value === "png";
    pdfQ.disabled = hideQ;
    pdfQ.parentElement.style.opacity = hideQ ? ".45" : "1";
  }
  pdfFmt.addEventListener("change", syncPdfQuality);
  pdfQ.addEventListener("input", () => (pdfQVal.textContent = pdfQ.value));
  pdfDpi.addEventListener("input", () => (pdfDpiVal.textContent = pdfDpi.value || "150"));

  $("input#pdfIn").addEventListener("change", function () {
    pdfFile = this.files[0] || null;
    this.value = "";
  });

  btnPdfConvert.addEventListener("click", async () => {
    if (!pdfFile) return showToast("Scegli prima un PDF.", "err");
    const fd = new FormData();
    fd.append("file", pdfFile);
    fd.append("fmt", pdfFmt.value);
    if (pdfFmt.value !== "png" && pdfQ.value) fd.append("quality", pdfQ.value);
    if (pdfDpi.value) fd.append("dpi", pdfDpi.value);

    btnPdfConvert.disabled = true;
    btnPdfConvert.textContent = "Convertendo…";
    try {
      const res = await fetch("/api/convert-pdf-to-images", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error((data && data.detail) || "Errore");
      results = data.results;
      renderResults();
      showToast(`${results.length} pagine convertite ✓`, "ok");
    } catch (err) {
      showToast(err.message || String(err), "err");
    } finally {
      btnPdfConvert.disabled = false;
      btnPdfConvert.textContent = "Converti";
    }
  });

  btnPdfZip.addEventListener("click", () => {
    const names = results.filter((r) => !r.error).map((r) => r.name).join(",");
    window.location.href = `/api/download?names=${encodeURIComponent(names)}`;
  });

  /* ---------- Immagini -> PDF ---------- */
  const imgToPdfListEl = $("#imgToPdfList");
  const btnImgToPdf = $("#btnImgToPdf");
  const imgToPdfMaxSide = $("#imgToPdfMaxSide");
  let imgToPdfFiles = [];
  const IMG_PDF_EXT_RE = /\.(jpe?g|png|webp|bmp|tiff?)$/i;

  $("input#imgToPdfIn").addEventListener("change", function () {
    const added = [...this.files];
    this.value = "";
    for (const f of added) {
      if (!IMG_PDF_EXT_RE.test(f.name)) {
        showToast(`Formato non supportato: ${f.name}`, "err");
        continue;
      }
      if (imgToPdfFiles.some((x) => x.name === f.name && x.size === f.size)) continue;
      imgToPdfFiles.push(f);
    }
    imgToPdfFiles = imgToPdfFiles.slice(0, 50);
    renderImgToPdf();
  });

  function renderImgToPdf() {
    if (!imgToPdfFiles.length) {
      imgToPdfListEl.hidden = true;
      return;
    }
    imgToPdfListEl.hidden = false;
    imgToPdfListEl.innerHTML = imgToPdfFiles
      .map(
        (f, i) => `<li class="file" data-i="${i}"><span class="ficon">${i + 1}</span>
          <span class="fname">${esc(f.name)}</span><span class="fsize">${fmtBytes(f.size)}</span>
          <button class="rm" title="Rimuovi">✕</button></li>`
      )
      .join("");
    imgToPdfListEl.onclick = (e) => {
      const btn = e.target.closest(".rm");
      if (!btn) return;
      const li = btn.closest("[data-i]");
      imgToPdfFiles.splice(+li.dataset.i, 1);
      renderImgToPdf();
    };
  }

  btnImgToPdf.addEventListener("click", async () => {
    if (!imgToPdfFiles.length) return showToast("Nessuna immagine in coda.", "err");
    const fd = new FormData();
    imgToPdfFiles.forEach((f) => fd.append("files", f));
    const ms = (imgToPdfMaxSide.value || "").trim();
    if (ms && +ms > 0) fd.append("max_side", ms);

    btnImgToPdf.disabled = true;
    btnImgToPdf.textContent = "Creando…";
    try {
      const res = await fetch("/api/convert-images-to-pdf", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error((data && data.detail) || "Errore");
      results = data.results;
      renderResults();
      showToast(`PDF creato con ${data.images} pagine ✓`, "ok");
    } catch (err) {
      showToast(err.message || String(err), "err");
    } finally {
      btnImgToPdf.disabled = false;
      btnImgToPdf.textContent = "Crea PDF";
    }
  });

  /* ---------- PDF -> testo (estrazione + OCR) ---------- */
  const txtPdfIn = $("input#txtPdfIn");
  const txtOcrSel = $("#txtOcr");
  const txtLang = $("#txtLang");
  const txtOcrStatus = $("#txtOcrStatus");
  const btnTxtExtract = $("#btnTxtExtract");
  const txtResult = $("#txtResult");
  const txtPreview = $("#txtPreview");
  const txtCopy = $("#txtCopy");
  const txtDownload = $("#txtDownload");
  let txtFile = null;
  let lastText = "";

  txtPdfIn.addEventListener("change", function () {
    txtFile = this.files[0] || null;
    this.value = "";
  });

  btnTxtExtract.addEventListener("click", async () => {
    if (!txtFile) return showToast("Scegli prima un PDF.", "err");
    const fd = new FormData();
    fd.append("file", txtFile);
    fd.append("ocr", txtOcrSel.value);
    fd.append("lang", txtLang.value);

    btnTxtExtract.disabled = true;
    btnTxtExtract.textContent = "Estragendo…";
    try {
      const res = await fetch("/api/pdf-to-text", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error((data && data.detail) || "Errore");
      lastText = data.text || "";
      txtPreview.textContent = lastText || "(nessun testo estratto)";
      txtResult.hidden = false;
      txtDownload.href = data.results[0].download;
      txtDownload.textContent = `⬇ Scarica ${data.results[0].name}`;
      if (data.warning) showToast(data.warning, "warn");
      showToast(`Testo estratto (${(data.pages || []).length} pagine) ✓`, "ok");
    } catch (err) {
      showToast(err.message || String(err), "err");
    } finally {
      btnTxtExtract.disabled = false;
      btnTxtExtract.textContent = "Estrai testo";
    }
  });

  txtCopy.addEventListener("click", async (e) => {
    e.preventDefault();
    if (!lastText) return showToast("Niente da copiare.", "err");
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(lastText);
      } else {
        const ta = document.createElement("textarea");
        ta.value = lastText;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
      }
      showToast("Testo copiato ✓", "ok");
    } catch (err) {
      showToast("Copia non riuscita.", "err");
    }
  });

  /* ---------- Video -> mp4/webm ---------- */
  const videoIn = $("input#videoIn");
  const videoFmt = $("#videoFmt");
  const videoCrf = $("#videoCrf");
  const videoStatus = $("#videoStatus");
  const btnVideoConvert = $("#btnVideoConvert");
  let videoFile = null;

  videoIn.addEventListener("change", function () {
    videoFile = this.files[0] || null;
    this.value = "";
  });

  btnVideoConvert.addEventListener("click", async () => {
    if (!videoFile) return showToast("Scegli prima un video.", "err");
    const fd = new FormData();
    fd.append("file", videoFile);
    fd.append("fmt", videoFmt.value);
    if (videoCrf.value) fd.append("crf", videoCrf.value);
    btnVideoConvert.disabled = true;
    btnVideoConvert.textContent = "Trascodando…";
    try {
      const res = await fetch("/api/convert-video", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error((data && data.detail) || "Errore");
      results = data.results;
      renderResults();
      showToast("Video convertito ✓", "ok");
    } catch (err) {
      showToast(err.message || String(err), "err");
    } finally {
      btnVideoConvert.disabled = false;
      btnVideoConvert.textContent = "Converti";
    }
  });

  function downloadBlobResponse(res, fallbackName) {
    return res.blob().then((blob) => {
      const cd = res.headers.get("Content-Disposition") || "";
      const m = /filename\*?="?([^";]+)"?/.exec(cd);
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = (m && m[1]) || fallbackName || "download";
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 4000);
      return true;
    });
  }

  /* ---------- Extra: merge / split / rename ---------- */
  const xsubs = { merge: $("#xmerge"), split: $("#xsplit"), rename: $("#xrename") };
  document.querySelectorAll('[data-xsub]').forEach((b) => {
    b.addEventListener("click", () => {
      document.querySelectorAll('[data-xsub]').forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      const t = b.dataset.xsub;
      for (const k in xsubs) xsubs[k].hidden = k !== t;
    });
  });

  /* --- Unisci PDF --- */
  const mergeIn = $("input#mergeIn");
  const mergeListEl = $("#mergeList");
  const btnMerge = $("#btnMerge");
  let mergeFiles = [];
  mergeIn.addEventListener("change", function () {
    for (const f of [...this.files]) {
      if (!f.name.toLowerCase().endsWith(".pdf")) { showToast(`Non è un PDF: ${f.name}`, "err"); continue; }
      if (mergeFiles.some((x) => x.name === f.name && x.size === f.size)) continue;
      mergeFiles.push(f);
    }
    mergeFiles = mergeFiles.slice(0, 40);
    this.value = "";
    renderMergeList();
  });
  function renderMergeList() {
    if (!mergeFiles.length) { mergeListEl.hidden = true; return; }
    mergeListEl.hidden = false;
    mergeListEl.innerHTML = mergeFiles
      .map((f, i) => `<li class="file" data-i="${i}"><span class="ficon">${i + 1}</span>
        <span class="fname">${esc(f.name)}</span><span class="fsize">${fmtBytes(f.size)}</span>
        <button class="rm" title="Rimuovi">✕</button></li>`)
      .join("");
    mergeListEl.onclick = (e) => {
      const btn = e.target.closest(".rm");
      if (!btn) return;
      const li = btn.closest("[data-i]");
      mergeFiles.splice(+li.dataset.i, 1);
      renderMergeList();
    };
  }
  btnMerge.addEventListener("click", async () => {
    if (mergeFiles.length < 2) return showToast("Serve almeno 2 PDF da unire.", "err");
    const fd = new FormData();
    mergeFiles.forEach((f) => fd.append("files", f));
    btnMerge.disabled = true; btnMerge.textContent = "Unendo…";
    try {
      const res = await fetch("/api/merge-pdfs", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error((data && data.detail) || "Errore");
      results = data.results;
      renderResults();
      showToast(`PDF unito: ${data.pages} pagine da ${data.inputs} file ✓`, "ok");
    } catch (err) {
      showToast(err.message || String(err), "err");
    } finally {
      btnMerge.disabled = false; btnMerge.textContent = "Unisci";
    }
  });

  /* --- Estrai pagine --- */
  const splitIn = $("input#splitIn");
  const splitStart = $("#splitStart");
  const splitEnd = $("#splitEnd");
  const btnSplit = $("#btnSplit");
  let splitFile = null;
  splitIn.addEventListener("change", function () { splitFile = this.files[0] || null; this.value = ""; });
  btnSplit.addEventListener("click", async () => {
    if (!splitFile) return showToast("Scegli prima un PDF.", "err");
    const fd = new FormData();
    fd.append("file", splitFile);
    if (splitStart.value) fd.append("start", splitStart.value);
    if (splitEnd.value) fd.append("end", splitEnd.value);
    btnSplit.disabled = true; btnSplit.textContent = "Estraggo…";
    try {
      const res = await fetch("/api/split-pdf", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error((data && data.detail) || "Errore");
      results = data.results;
      renderResults();
      showToast(`Estratto: ${data.pages} di ${data.total_pages_source} pagine ✓`, "ok");
    } catch (err) {
      showToast(err.message || String(err), "err");
    } finally {
      btnSplit.disabled = false; btnSplit.textContent = "Estrai";
    }
  });

  /* --- Rinomina --- */
  const renameMode = $("#renameMode");
  const renameValue = $("#renameValue");
  const renameValueLabel = $("#renameValueLabel");
  const renameNumRow = $("#renameNumRow");
  const renameStart = $("#renameStart");
  const renameStep = $("#renameStep");
  const renameSep = $("#renameSep");
  const renameIn = $("input#renameIn");
  const renameListEl = $("#renameList");
  const renamePreviewEl = $("#renamePreview");
  const btnRename = $("#btnRename");
  const btnRenamePreview = $("#btnRenamePreview");
  let renameFiles = [];
  renameIn.addEventListener("change", function () {
    for (const f of [...this.files]) {
      if (renameFiles.some((x) => x.name === f.name && x.size === f.size)) continue;
      renameFiles.push(f);
    }
    renameFiles = renameFiles.slice(0, 500);
    this.value = "";
    renameListEl.hidden = !renameFiles.length;
    renameListEl.innerHTML = renameFiles
      .map((f) => `<li class="file"><span class="fname">${esc(f.name)}</span><span class="fsize">${fmtBytes(f.size)}</span></li>`)
      .join("");
    btnRenamePreview.hidden = !renameFiles.length;
  });
  function renameLabelFor(mode) {
    if (mode === "prefix") return "Prefisso";
    if (mode === "suffix") return "Suffisso";
    if (mode === "find") return "Testo da sostituire";
    return "Base nome";
  }
  renameMode.addEventListener("change", () => {
    renameValueLabel.textContent = renameLabelFor(renameMode.value);
    renameNumRow.hidden = renameMode.value !== "number";
  });
  function buildRenameForm() {
    const fd = new FormData();
    renameFiles.forEach((f) => fd.append("files", f));
    fd.append("mode", renameMode.value);
    fd.append("value", renameValue.value || "");
    if (renameMode.value === "number") {
      fd.append("start", renameStart.value || "1");
      fd.append("step", renameStep.value || "1");
      fd.append("sep", renameSep.value || "-");
    }
    return fd;
  }
  btnRenamePreview.addEventListener("click", async () => {
    if (!renameFiles.length) return showToast("Scegli prima i file.", "err");
    const names = renameFiles.map((f) => f.name);
    const fd = new FormData();
    names.forEach((n) => fd.append("names", n));
    fd.append("mode", renameMode.value);
    fd.append("value", renameValue.value || "");
    if (renameMode.value === "number") {
      fd.append("start", renameStart.value || "1");
      fd.append("step", renameStep.value || "1");
      fd.append("sep", renameSep.value || "-");
    }
    try {
      const res = await fetch("/api/rename-preview", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error((data && data.detail) || "Errore");
      renamePreviewEl.hidden = false;
      renamePreviewEl.innerHTML = data.mapping
        .map((m) => `<li class="file renameprev"><span class="fname">${esc(m.from)} → <b>${esc(m.to)}</b></span></li>`)
        .join("");
    } catch (err) {
      showToast(err.message || String(err), "err");
    }
  });
  btnRename.addEventListener("click", async () => {
    if (!renameFiles.length) return showToast("Scegli prima i file.", "err");
    btnRename.disabled = true; btnRename.textContent = "Rinominando…";
    try {
      const res = await fetch("/api/rename-batch", { method: "POST", body: buildRenameForm() });
      if (!res.ok) {
        let msg = "Errore";
        try { const j = await res.json(); msg = (j && j.detail) || msg; } catch (_) {}
        throw new Error(msg);
      }
      await downloadBlobResponse(res, "versocon_renamed.zip");
      showToast("ZIP rinomina pronto ✓", "ok");
    } catch (err) {
      showToast(err.message || String(err), "err");
    } finally {
      btnRename.disabled = false; btnRename.textContent = "Rinomina (ZIP)";
    }
  });

  /* ---------- Comprimi: immagine ---------- */
  let cImgFile = null;
  const cImgMode = $("#cImgMode");
  const cImgModeRowT = $("#cImgTargetRow");
  const cImgModeRowQ = $("#cImgQualityRow");
  const cImgTarget = $("#cImgTarget");
  const cImgTargetVal = $("#cImgTargetVal");
  const cImgQ = $("#cImgQ");
  const cImgQVal = $("#cImgQVal");
  const cImgMaxSide = $("#cImgMaxSide");
  const btnCImg = $("#btnCImg");

  function syncCImgMode() {
    const isT = cImgMode.value === "target";
    cImgModeRowT.hidden = !isT;
    cImgModeRowQ.hidden = isT;
  }
  cImgMode.addEventListener("change", syncCImgMode);
  syncCImgMode();
  cImgTarget.addEventListener("input", () => (cImgTargetVal.textContent = cImgTarget.value || "500"));
  cImgQ.addEventListener("input", () => (cImgQVal.textContent = cImgQ.value || "80"));
  $("input#cImgIn").addEventListener("change", function () {
    cImgFile = this.files[0] || null;
    this.value = "";
  });
  btnCImg.addEventListener("click", async () => {
    if (!cImgFile) return showToast("Scegli prima un'immagine.", "err");
    const fd = new FormData();
    fd.append("file", cImgFile);
    fd.append("fmt", $("#cImgFmt").value);
    if (cImgMode.value === "target") {
      fd.append("target_bytes", (parseInt(cImgTarget.value, 10) || 0) * 1024);
    } else {
      fd.append("quality", cImgQ.value);
    }
    const ms = parseInt(cImgMaxSide.value, 10);
    if (ms > 0) fd.append("max_side", ms);
    btnCImg.disabled = true;
    btnCImg.textContent = "Comprimendo…";
    try {
      const res = await fetch("/api/compress-image", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error((data && data.detail) || "Errore");
      results = data.results;
      renderResults();
      showToast("Immagine compressa ✓", "ok");
    } catch (err) {
      showToast(err.message || String(err), "err");
    } finally {
      btnCImg.disabled = false;
      btnCImg.textContent = "Comprimi immagine";
    }
  });

  /* ---------- Comprimi: PDF ---------- */
  let cPdfFile = null;
  const cPdfLevel = $("#cPdfLevel");
  const btnCPdf = $("#btnCPdf");
  $("input#cPdfIn").addEventListener("change", function () {
    cPdfFile = this.files[0] || null;
    this.value = "";
  });
  btnCPdf.addEventListener("click", async () => {
    if (!cPdfFile) return showToast("Scegli prima un PDF.", "err");
    const fd = new FormData();
    fd.append("file", cPdfFile);
    fd.append("level", cPdfLevel.value);
    btnCPdf.disabled = true;
    btnCPdf.textContent = "Comprimendo…";
    try {
      const res = await fetch("/api/compress-pdf", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error((data && data.detail) || "Errore");
      results = data.results;
      renderResults();
      showToast("PDF compresso ✓", "ok");
    } catch (err) {
      showToast(err.message || String(err), "err");
    } finally {
      btnCPdf.disabled = false;
      btnCPdf.textContent = "Comprimi PDF";
    }
  });

  /* ---------- Editor PDF ---------- */
  let edPdfFile = null;
  let edSigFile = null;
  let edPdfDoc = null;
  let edCurPage = 1;
  let edPageCount = 0;
  let edSigBox = { x: 50, y: 80, w: 30, rot: 0, op: 100 };
  const edAction = $("#edAction");
  const edStatus = $("#edStatus");
  const btnEdApply = $("#btnEdApply");
  const edDownload = $("#edDownload");
  const edPreview = document.getElementById("edPreview");
  const edPageEl = document.getElementById("edPage");
  const edCanvas = document.getElementById("edCanvas");
  const edSigOverlay = document.getElementById("edSigOverlay");
  const edSigImag = document.getElementById("edSigImag");
  const edPageEmpty = document.getElementById("edPageEmpty");
  const edPgLabel = document.getElementById("edPgLabel");
  const edPgSel = document.getElementById("edPgSel");
  const edPgPrev = document.getElementById("edPgPrev");
  const edPgNext = document.getElementById("edPgNext");

  if (window.pdfjsLib) {
    window.pdfjsLib.GlobalWorkerOptions.workerSrc = "vendor/pdfjs/pdf.worker.min.js";
  }

  let overlayBound = false;
  function bindOverlayOnce() {
    if (overlayBound) return;
    overlayBound = true;
    bindOverlayGestures(edSigOverlay, edPageEl, (pct) => {
      edSigBox.x = pct.x; edSigBox.y = pct.y; edSigBox.w = pct.w;
    });
  }

  function   applySigBoxToDom() {
    edSigOverlay.hidden = !edSigFile;
    if (!edSigFile) return;
    edSigOverlay.style.left = edSigBox.x + "%";
    edSigOverlay.style.top = edSigBox.y + "%";
    edSigOverlay.style.width = edSigBox.w + "%";
    edSigOverlay.style.height = "";
    edSigOverlay.style.setProperty("--rot", (edSigBox.rot || 0) + "deg");
    edSigImag.style.opacity = edSigBox.op / 100;
  }

  function setEmpty(msg) {
    edPageEmpty.hidden = !msg;
    if (msg) edPageEmpty.querySelector("p").textContent = msg;
  }

  let edRenderToken = 0;

  async function renderEdPage() {
    if (!edPdfDoc) return;
    const token = ++edRenderToken;
    const page = await edPdfDoc.getPage(edCurPage);
    if (token !== edRenderToken) return;
    setEmpty("");
    const vp1 = page.getViewport({ scale: 1 });
    const dpr = window.devicePixelRatio || 1;
    const targetCss = Math.min(1280, Math.max(360, edPageEl.clientWidth - 8 || 900));
    const scale = targetCss / vp1.width;
    const vp2 = page.getViewport({ scale: scale });
    edCanvas.width  = Math.floor(vp2.width  * dpr);
    edCanvas.height = Math.floor(vp2.height * dpr);
    const ctx = edCanvas.getContext("2d");
    ctx.clearRect(0, 0, edCanvas.width, edCanvas.height);
    edCanvas.hidden = false;
    try {
      await page.render({ canvasContext: ctx, viewport: vp2 }).promise;
    } catch (e) {
      if (token === edRenderToken) {
        setEmpty("Errore nel render della pagina: " + (e && e.message ? e.message : e));
        edCanvas.hidden = true;
        showToast("Render pagina fallito", "err");
      }
    }
  }

  async function loadEdPreview(file) {
    if (!file) {
      if (edPdfDoc) { try { edPdfDoc.destroy(); } catch (e) {} edPdfDoc = null; }
      edPreview.hidden = true;
      edPageCount = 0; edSigFile = null; edSigBox = { x: 50, y: 80, w: 30, rot: 0, op: 100 };
      applySigBoxToDom();
      return;
    }
    if (!window.pdfjsLib) {
      showToast("pdf.js non caricato", "err");
      edPreview.hidden = false;
      setEmpty("Anteprima non disponibile — pdf.js non caricato");
      edCanvas.hidden = true;
      return;
    }
    edPreview.hidden = false;
    if (edPdfDoc) { try { edPdfDoc.destroy(); } catch (e) {} edPdfDoc = null; }
    bindOverlayOnce();
    edStatus.textContent = "Anteprima in caricamento…";
    edPageCount = 0; edCurPage = 1;
    edPgSel.innerHTML = "";
    setEmpty("Caricamento pagina…");
    try {
      const buf = await file.arrayBuffer();
      edPdfDoc = await window.pdfjsLib.getDocument({ data: buf }).promise;
      edPageCount = edPdfDoc.numPages;
      edCurPage = 1;
      syncPager();
      edPgSel.innerHTML = "";
      for (let i = 1; i <= edPageCount; i++) {
        const o = document.createElement("option");
        o.value = i; o.textContent = i;
        edPgSel.appendChild(o);
      }
      edPgSel.value = "1";
      edStatus.textContent = `Caricato: ${file.name} (${fmtBytes(file.size)} · ${edPageCount} pp.)`;
      await renderEdPage();
    } catch (e) {
      edStatus.textContent = "⚠ Errore anteprima: " + (e.message || e);
      setEmpty("Errore anteprima: " + (e.message || e));
    }
    applySigBoxToDom();
  }

  function syncPager() {
    if (edPgLabel) edPgLabel.textContent = edPageCount ? `${edCurPage} / ${edPageCount}` : "-";
    if (edPgSel && edPgSel.options.length) edPgSel.value = String(edCurPage);
    if (edPgPrev) edPgPrev.disabled = !edPageCount || edCurPage <= 1;
    if (edPgNext) edPgNext.disabled = !edPageCount || edCurPage >= edPageCount;
  }

  edPgPrev.addEventListener("click", () => { if (edCurPage > 1) { edCurPage--; syncPager(); renderEdPage(); } });
  edPgNext.addEventListener("click", () => { if (edCurPage < edPageCount) { edCurPage++; syncPager(); renderEdPage(); } });
  edPgSel.addEventListener("change", () => { edCurPage = +edPgSel.value; syncPager(); renderEdPage(); });

  function bindOverlayGestures(overlay, pageHost, onBoxChange) {
    const getBox = () => {
      const pr = pageHost.getBoundingClientRect();
      const b = overlay.getBoundingClientRect();
      const cx = (b.left + b.width / 2 - pr.left) / pr.width * 100;
      const cy = (b.top + b.height / 2 - pr.top) / pr.height * 100;
      const w = (b.width / pr.width) * 100;
      return { x: Math.round(cx * 10) / 10, y: Math.round(cy * 10) / 10, w: Math.max(1, Math.round(w * 10) / 10) };
    };
    const clampB = (b) => {
      b.x = Math.max(0, Math.min(100, b.x));
      b.y = Math.max(0, Math.min(100, b.y));
      b.w = Math.max(1, Math.min(100, b.w));
      return b;
    };
    let drag = null;
    overlay.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      const h = e.target && e.target.dataset ? e.target.dataset.h : null;
      drag = h ? { mode: "resize", h, start: e, b: getBox() } : { mode: "move", start: e, b: getBox() };
      overlay.setPointerCapture(e.pointerId);
      e.preventDefault();
    });
    overlay.addEventListener("pointermove", (e) => {
      if (!drag) return;
      const pr = pageHost.getBoundingClientRect();
      const dx = (e.clientX - drag.start.clientX) / pr.width * 100;
      const dy = (e.clientY - drag.start.clientY) / pr.height * 100;
      let nb = { x: drag.b.x, y: drag.b.y, w: drag.b.w };
      if (drag.mode === "move") {
        nb.x += dx; nb.y += dy;
      } else if (drag.h === "nw" || drag.h === "sw") {
        nb.w = drag.b.w - dx;
      } else if (drag.h === "ne" || drag.h === "se") {
        nb.w = drag.b.w + dx;
      }
      nb.w = Math.max(1, nb.w);
      nb = clampB(nb);
      overlay.style.left = nb.x + "%";
      overlay.style.top = nb.y + "%";
      overlay.style.width = nb.w + "%";
      if (onBoxChange) onBoxChange(nb);
    });
    const end = (e) => {
      if (!drag) return;
      drag = null;
      try { overlay.releasePointerCapture(e.pointerId); } catch (err) {}
    };
    overlay.addEventListener("pointerup", end);
    overlay.addEventListener("pointercancel", end);
  }

  $("input#edPdfIn").addEventListener("change", function () {
    edPdfFile = this.files[0] || null;
    edSigBox = { x: 50, y: 80, w: 30, rot: 0, op: 100 };
    loadEdPreview(edPdfFile);
  });
  $("input#edSigImg").addEventListener("change", function () {
    const f = this.files[0] || null;
    if (f) {
      edSigFile = f;
      const u = URL.createObjectURL(f);
      edSigImag.src = u;
    } else {
      edSigFile = null;
    }
    applySigBoxToDom();
  });
  const edBlocks = {
    rotate: document.getElementById("edBlock-rotate"),
    delete: document.getElementById("edBlock-delete"),
    reorder: document.getElementById("edBlock-reorder"),
    watermark: document.getElementById("edBlock-watermark"),
    signature: document.getElementById("edBlock-signature"),
  };
  let inkPadOpen = false;
  function syncEdBlock() {
    const act = edAction.value;
    for (const [k, el] of Object.entries(edBlocks)) {
      if (el) el.hidden = (k !== act);
    }
    const pad = document.getElementById("edSignPad");
    if (pad) pad.hidden = (act !== "signature" || !inkPadOpen);
  }
  edAction.addEventListener("change", syncEdBlock);
  syncEdBlock();
  const pairs = [
    ["edWmSize", "edWmSizeVal", (v) => v],
    ["edWmOpacity", "edWmOpVal", (v) => v],
    ["edSigRot", "edSigRotVal", (v) => (+v) + "°"],
    ["edSigOpacity", "edSigOpVal", (v) => v],
  ];
  for (const [id, labelId, fmt] of pairs) {
    const el = document.getElementById(id);
    const lab = document.getElementById(labelId);
    if (el && lab) {
      el.addEventListener("input", () => {
        lab.textContent = fmt(el.value);
        if (id === "edSigRot") {
          edSigBox.rot = +el.value;
          edSigOverlay.style.setProperty("--rot", edSigBox.rot + "deg");
        } else if (id === "edSigOpacity") {
          edSigBox.op = +el.value;
          edSigImag.style.opacity = edSigBox.op / 100;
        }
      });
    }
  }
  const btnSigReset = document.getElementById("btnSigResetPos");
  if (btnSigReset) btnSigReset.addEventListener("click", () => {
    edSigBox.x = 50; edSigBox.y = 80; edSigBox.rot = 0;
    const r = document.getElementById("edSigRot"); if (r) { r.value = "0"; }
    const rv = document.getElementById("edSigRotVal"); if (rv) rv.textContent = "0°";
    applySigBoxToDom();
  });

  /* ---------- InkPad (firma mano) ---------- */
  const inkPad = document.getElementById("inkPad");
  const inkCtx = inkPad ? inkPad.getContext("2d") : null;
  let inkDrawing = false;
  let inkLast = null;
  let inkStrokes = [];
  let inkColor = "#1a1a2e";
  let inkSize = 4;
  function inkWhite() {
    inkCtx.fillStyle = "#fff";
    inkCtx.fillRect(0, 0, inkPad.width, inkPad.height);
    inkStrokes = [];
  }
  function inkPoint(e) {
    const r = inkPad.getBoundingClientRect();
    return {
      x: (e.clientX - r.left) / r.width * inkPad.width,
      y: (e.clientY - r.top) / r.height * inkPad.height,
    };
  }
  function inkStroke(st) {
    inkCtx.strokeStyle = st.c; inkCtx.lineWidth = st.s;
    inkCtx.lineCap = "round"; inkCtx.lineJoin = "round";
    inkCtx.beginPath();
    st.points.forEach((p, idx) => { if (idx === 0) inkCtx.moveTo(p.x, p.y); else inkCtx.lineTo(p.x, p.y); });
    inkCtx.stroke();
  }
  if (inkPad) {
    inkWhite();
    inkPad.addEventListener("pointerdown", (e) => {
      inkDrawing = true;
      inkLast = inkPoint(e);
      inkPad.setPointerCapture(e.pointerId);
      const p = inkLast;
      inkLast = null;
      inkCtx.beginPath();
      inkCtx.moveTo(p.x, p.y); inkCtx.lineTo(p.x + 0.1, p.y + 0.1);
      inkCtx.strokeStyle = inkColor; inkCtx.lineWidth = inkSize;
      inkCtx.lineCap = "round"; inkCtx.lineJoin = "round";
      inkCtx.stroke();
      inkStrokes.push({ points: [p], c: inkColor, s: inkSize });
    });
    inkPad.addEventListener("pointermove", (e) => {
      if (!inkDrawing) return;
      const p = inkPoint(e);
      const prev = inkStrokes[inkStrokes.length - 1];
      if (prev) {
        const lp = prev.points[prev.points.length - 1];
        inkCtx.beginPath(); inkCtx.moveTo(lp.x, lp.y); inkCtx.lineTo(p.x, p.y);
        inkCtx.strokeStyle = prev.c; inkCtx.lineWidth = prev.s;
        inkCtx.lineCap = "round"; inkCtx.lineJoin = "round";
        inkCtx.stroke();
        prev.points.push(p);
      }
    });
    const inkEnd = (e) => {
      inkDrawing = false;
      try { inkPad.releasePointerCapture(e.pointerId); } catch (err) {}
    };
    inkPad.addEventListener("pointerup", inkEnd);
    inkPad.addEventListener("pointercancel", inkEnd);
    const cEl = document.getElementById("inkColor");
    if (cEl) cEl.addEventListener("input", () => { inkColor = cEl.value; });
    const sEl = document.getElementById("inkSize");
    if (sEl) sEl.addEventListener("input", () => { inkSize = +sEl.value; });
    const clearEl = document.getElementById("inkClear");
    if (clearEl) clearEl.addEventListener("click", inkWhite);
    const undoEl = document.getElementById("inkUndo");
    if (undoEl) undoEl.addEventListener("click", () => {
      if (!inkStrokes.length) return;
      inkStrokes = inkStrokes.slice(0, -1);
      inkWhite();
      inkStrokes.forEach(inkStroke);
    });
    const okEl = document.getElementById("inkOk");
    if (okEl) okEl.addEventListener("click", async () => {
      if (!inkStrokes.length) return showToast("Disegna prima una firma.", "err");
      let pngBlob;
      try {
        pngBlob = await new Promise((res, rej) =>
          inkPad.toBlob((b) => (b ? res(b) : rej(new Error("pad vuoto"))), "image/png"));
      } catch (e) { return showToast("Niente da esportare dal pad.", "err"); }
      const name = "firma_disegnata_" + Date.now() + ".png";
      edSigFile = new File([pngBlob], name, { type: "image/png" });
      const u = URL.createObjectURL(pngBlob);
      edSigImag.src = u;
      applySigBoxToDom();
      showToast("Firma creata ✓ — trascinala dove serve.", "ok");
    });
  }
  const btnInkOpen = document.getElementById("btnInkOpen");
  if (btnInkOpen) btnInkOpen.addEventListener("click", () => {
    inkPadOpen = !inkPadOpen;
    syncEdBlock();
  });

  /* ---------- Firma da testo (4 stili font, backend) ---------- */
  const edTxtName = document.getElementById("edTxtName");
  const edTxtStyle = document.getElementById("edTxtStyle");
  const btnTxtSign = document.getElementById("btnTxtSign");
  (async () => {
    try {
      const r = await fetch("/api/signature-styles");
      const d = await r.json();
      if (!edTxtStyle) return;
      edTxtStyle.innerHTML = (d.styles || [])
        .map((s) => `<option value="${s.key}">${s.label}</option>`)
        .join("");
    } catch (_) {}
  })();
  if (btnTxtSign) {
    btnTxtSign.addEventListener("click", async () => {
      const name = ((edTxtName && edTxtName.value) || "").trim();
      if (!name) return showToast("Scrivi il nome da firmare.", "err");
      btnTxtSign.disabled = true;
      try {
        const fd = new FormData();
        fd.append("name", name);
        if (edTxtStyle) fd.append("style", edTxtStyle.value);
        fd.append("color", (document.getElementById("edTxtColor") || {}).value || "#000000");
        const r = await fetch("/api/signature-generate", { method: "POST", body: fd });
        if (!r.ok) {
          let msg = "Generazione firma fallita.";
          try { const d = await r.json(); if (d && d.detail) msg = d.detail; } catch (_) {}
          throw new Error(msg);
        }
        const blob = await r.blob();
        edSigFile = new File([blob], "firma_" + name.replace(/\s+/g, "_") + ".png", { type: "image/png" });
        if (edSigImag) {
          const u = URL.createObjectURL(blob);
          if (edSigImag.src && edSigImag.src.startsWith("blob:")) URL.revokeObjectURL(edSigImag.src);
          edSigImag.src = u;
        }
        applySigBoxToDom();
        showToast("Firma creata ✓ — trascinala dove serve.", "ok");
      } catch (err) {
        showToast(err.message || String(err), "err");
      } finally {
        btnTxtSign.disabled = false;
      }
    });
  }

  function pagesToPayload(raw) {
    const v = (raw || "").trim();
    const low = v.toLowerCase();
    if (low === "" || low === "tutte" || low === "all" || low === "*") return v === "" ? "" : low;
    const nums = v.split(",").map((s) => s.trim()).filter(Boolean).map(Number);
    if (nums.some((n) => !Number.isInteger(n) || n < 1)) {
      throw new Error("Pagine invalide: usa es. 1,3 oppure \"tutte\"");
    }
    return JSON.stringify(nums);
  }
  function orderToPayload(raw) {
    const v = (raw || "").trim();
    if (!v) throw new Error("Indica il nuovo ordine, es. 3,1,2");
    const nums = v.split(",").map((s) => s.trim()).filter(Boolean).map(Number);
    if (nums.some((n) => !Number.isInteger(n) || n < 1)) {
      throw new Error("Ordine invalide: usa es. 3,1,2");
    }
    return JSON.stringify(nums);
  }

  btnEdApply.addEventListener("click", async () => {
    if (!edPdfFile) return showToast("Scegli prima un PDF.", "err");
    const act = edAction.value;
    edDownload.hidden = true;
    const fd = new FormData();
    fd.append("file", edPdfFile);
    fd.append("action", act);
    try {
      if (act === "rotate") {
        fd.append("pages", pagesToPayload($("#edRotPages").value));
        fd.append("angle", $("#edRotAngle").value);
      } else if (act === "delete") {
        fd.append("pages", pagesToPayload($("#edDelPages").value));
      } else if (act === "reorder") {
        fd.append("order", orderToPayload($("#edReOrder").value));
      } else if (act === "watermark") {
        fd.append("wm_text", $("#edWmText").value);
        fd.append("wm_corner", $("#edWmCorner").value);
        fd.append("wm_size", $("#edWmSize").value);
        fd.append("wm_opacity", (+$("#edWmOpacity").value) / 100);
        fd.append("wm_rotate", $("#edWmRotate").value);
      } else if (act === "signature") {
        if (!edSigFile) throw new Error("Carica o disegna prima la firma.");
        fd.append("signature", edSigFile);
        fd.append("sig_page", $("#edSigPage").value);
        // nuovo posizionamento libero (percentuali) + rotazione + opacità
        fd.append("sig_pos_x", String(edSigBox.x));
        fd.append("sig_pos_y", String(edSigBox.y));
        fd.append("sig_w_pct", String(edSigBox.w));
        fd.append("sig_rot", String(edSigBox.rot || 0));
        fd.append("sig_opacity", String(edSigBox.op || 100));
      }
    } catch (e) {
      return showToast(e.message || String(e), "err");
    }
    btnEdApply.disabled = true;
    btnEdApply.textContent = "Applico…";
    try {
      const r = await fetch("/api/pdf-edit", { method: "POST", body: fd });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error((data && data.detail) || "Errore");
      const res = data.results && data.results[0];
      edDownload.href = res.download;
      edDownload.download = res.name;
      edDownload.hidden = false;
      edStatus.textContent = `✓ ${res.name} (${fmtBytes(res.size)})`;
      showToast("PDF modificato ✓", "ok");
    } catch (err) {
      showToast(err.message || String(err), "err");
    } finally {
      btnEdApply.disabled = false;
      btnEdApply.textContent = "Applica";
    }
  });

  /* ---------- Ko-fi (supporto, URL da config globale) ---------- */
  let kofiUrl = null;
  const btnKofi = $("#btnKofi");
  if (btnKofi) {
    btnKofi.addEventListener("click", async () => {
      // 1) backend: webbrowser aperto dal sistema (funziona anche su pywebview)
      try {
        const r = await fetch("/api/support", { method: "POST" });
        if (r.ok) return;
      } catch (_) {}
      // 2) fallback: browser predefinito via JS
      if (kofiUrl) {
        window.open(kofiUrl, "_blank", "noopener,noreferrer");
        return;
      }
      showToast("Link di supporto non configurato.", "warn");
    });
  }

  /* ---------- boot ---------- */
  fetch("/api/config")
    .then((r) => r.json())
    .then((cfg) => {
      if (cfg.support && cfg.support.kofi_url) kofiUrl = cfg.support.kofi_url;
      if (cfg.video && cfg.video.ffmpeg_available === false) {
        videoStatus.textContent = "⚠ ffmpeg non rilevato: il transcode video restituirà un errore 503. Installalo per l'uso.";
      } else if (cfg.video && cfg.video.ffmpeg_available) {
        videoStatus.textContent = "✓ ffmpeg rilevato.";
      }
      if (txtOcrStatus) {
        if (cfg.ocr && cfg.ocr.available) {
          txtOcrStatus.textContent = "✓ OCR attivo — lingue: " + (cfg.ocr.languages || []).join(", ");
        } else {
          txtOcrStatus.textContent = "⚠ OCR non disponibile (Tesseract mancante). Estrezioni solo testo nativo.";
        }
      }
    })
    .catch(() => {});
})();
