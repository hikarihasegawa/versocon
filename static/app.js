/* VersoCon frontend */
(() => {
  "use strict";

  const $ = (s) => document.querySelector(s);
  const IC = window.IC || { t: (k) => k };

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
  let bootCfg = null;   // last /api/config, to re-render i18n-dependent status lines

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
    // i messaggi lunghi (avvisi) restano visibili il tempo di leggerli
    const ms = Math.min(12000, Math.max(3200, String(msg).length * 55));
    toastTimer = setTimeout(() => toast.classList.remove("show"), ms);
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
          showToast(IC.t("dyn.fmt_unsupported", { name: f.name }), "err");
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
        <button class="rm" data-rm aria-label="${IC.t("list.remove")}">✕</button>
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
    if (!files.length) return showToast(IC.t("dyn.no_files"), "err");
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    fd.append("fmt", fmt);
    if (fmt !== "png" && fmt !== "gif" && qualityInput.value) fd.append("quality", qualityInput.value);
    const ms = (maxSideInput.value || "").trim();
    if (ms && +ms > 0) fd.append("max_side", ms);

    btnConvert.disabled = true;
    btnConvert.textContent = IC.t("btn.converting");
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
      showToast(IC.t("dyn.n_files_converted", { n: results.filter((r) => !r.error).length }), "ok");
    } catch (err) {
      showToast(err.message || String(err), "err");
    } finally {
      btnConvert.disabled = false;
      btnConvert.textContent = IC.t("btn.convert");
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
          <a href="${r.download}" download>${esc(IC.t("dyn.download"))}</a></li>`;
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
  const TABS = { photos: tabPhotos, pdf: tabPdf, compress: tabCompress, video: tabVideo };
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
      const shell = document.querySelector(".shell");
      if (shell) shell.classList.toggle("wide", s === "pdf-edit");
    });
  });

  /* ---------- Compress: sub-tabs (Immagine / PDF / Rinomina) ---------- */
  const cPanes = {
    image: $("#cimg"),
    pdf: $("#cpdf"),
    rename: $("#crename"),
  };
  document.querySelectorAll("#tabCompress .subtabs .subtab").forEach((b) => {
    b.addEventListener("click", () => {
      document.querySelectorAll("#tabCompress .subtabs .subtab").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      const s = b.dataset.csub;
      for (const k in cPanes) cPanes[k].hidden = s !== k;
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
    if (!pdfFile) return showToast(IC.t("dyn.pick_pdf_first"), "err");
    const fd = new FormData();
    fd.append("file", pdfFile);
    fd.append("fmt", pdfFmt.value);
    if (pdfFmt.value !== "png" && pdfQ.value) fd.append("quality", pdfQ.value);
    if (pdfDpi.value) fd.append("dpi", pdfDpi.value);

    btnPdfConvert.disabled = true;
    btnPdfConvert.textContent = IC.t("btn.converting");
    try {
      const res = await fetch("/api/convert-pdf-to-images", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error((data && data.detail) || "Errore");
      results = data.results;
      renderResults();
      showToast(IC.t("dyn.n_pages_converted", { n: results.length }), "ok");
    } catch (err) {
      showToast(err.message || String(err), "err");
    } finally {
      btnPdfConvert.disabled = false;
      btnPdfConvert.textContent = IC.t("btn.convert");
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
        showToast(IC.t("dyn.fmt_unsupported", { name: f.name }), "err");
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
          <button class="rm" data-rm aria-label="${IC.t("list.remove")}">✕</button></li>`
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
    if (!imgToPdfFiles.length) return showToast(IC.t("dyn.no_images"), "err");
    const fd = new FormData();
    imgToPdfFiles.forEach((f) => fd.append("files", f));
    const ms = (imgToPdfMaxSide.value || "").trim();
    if (ms && +ms > 0) fd.append("max_side", ms);

    btnImgToPdf.disabled = true;
    btnImgToPdf.textContent = IC.t("btn.creating");
    try {
      const res = await fetch("/api/convert-images-to-pdf", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error((data && data.detail) || "Errore");
      results = data.results;
      renderResults();
      showToast(IC.t("dyn.pdf_created", { n: data.images }), "ok");
    } catch (err) {
      showToast(err.message || String(err), "err");
    } finally {
      btnImgToPdf.disabled = false;
      btnImgToPdf.textContent = IC.t("btn.img2pdf");
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
    if (!txtFile) return showToast(IC.t("dyn.pick_pdf_first"), "err");
    const fd = new FormData();
    fd.append("file", txtFile);
    fd.append("ocr", txtOcrSel.value);
    fd.append("lang", txtLang.value);

    btnTxtExtract.disabled = true;
    btnTxtExtract.textContent = IC.t("btn.extracing");
    try {
      const res = await fetch("/api/pdf-to-text", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error((data && data.detail) || "Errore");
      lastText = data.text || "";
      txtPreview.textContent = lastText || IC.t("dyn.no_text");
      txtResult.hidden = false;
      txtDownload.href = data.results[0].download;
      txtDownload.textContent = IC.t("dyn.download_named", { name: data.results[0].name });
      // un toast solo: l'avviso, se c'è, non va coperto da quello di successo
      if (data.warning) showToast(data.warning, "warn");
      else showToast(IC.t("dyn.text_extracted", { n: (data.pages || []).length }), "ok");
    } catch (err) {
      showToast(err.message || String(err), "err");
    } finally {
      btnTxtExtract.disabled = false;
      btnTxtExtract.textContent = IC.t("btn.extract");
    }
  });

  txtCopy.addEventListener("click", async (e) => {
    e.preventDefault();
    if (!lastText) return showToast(IC.t("dyn.nothing_to_copy"), "err");
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
      showToast(IC.t("dyn.text_copied"), "ok");
    } catch (err) {
      showToast(IC.t("dyn.copy_failed"), "err");
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
    if (!videoFile) return showToast(IC.t("dyn.pick_video_first"), "err");
    const fd = new FormData();
    fd.append("file", videoFile);
    fd.append("fmt", videoFmt.value);
    if (videoCrf.value) fd.append("crf", videoCrf.value);
    btnVideoConvert.disabled = true;
    btnVideoConvert.textContent = IC.t("btn.transcoding");
    try {
      const res = await fetch("/api/convert-video", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error((data && data.detail) || "Errore");
      results = data.results;
      renderResults();
      showToast(IC.t("dyn.video_converted"), "ok");
    } catch (err) {
      showToast(err.message || String(err), "err");
    } finally {
      btnVideoConvert.disabled = false;
      btnVideoConvert.textContent = IC.t("btn.convert");
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

  /* ---------- Extra: merge / split / rename (pannelli ora dentro PDF / Comprimi; i binding restano per-id) ---------- */

  /* --- Unisci PDF --- */
  const mergeIn = $("input#mergeIn");
  const mergeListEl = $("#mergeList");
  const btnMerge = $("#btnMerge");
  let mergeFiles = [];
  mergeIn.addEventListener("change", function () {
    for (const f of [...this.files]) {
      if (!f.name.toLowerCase().endsWith(".pdf")) { showToast(IC.t("dyn.not_pdf", { name: f.name }), "err"); continue; }
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
        <button class="rm" data-rm aria-label="${IC.t("list.remove")}">✕</button></li>`)
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
    if (mergeFiles.length < 2) return showToast(IC.t("dyn.need_2_pdfs"), "err");
    const fd = new FormData();
    mergeFiles.forEach((f) => fd.append("files", f));
    btnMerge.disabled = true; btnMerge.textContent = IC.t("btn.merging");
    try {
      const res = await fetch("/api/merge-pdfs", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error((data && data.detail) || "Errore");
      results = data.results;
      renderResults();
      showToast(IC.t("dyn.pdf_merged", { pages: data.pages, inputs: data.inputs }), "ok");
    } catch (err) {
      showToast(err.message || String(err), "err");
    } finally {
      btnMerge.disabled = false; btnMerge.textContent = IC.t("btn.merge");
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
    if (!splitFile) return showToast(IC.t("dyn.pick_pdf_first"), "err");
    const fd = new FormData();
    fd.append("file", splitFile);
    if (splitStart.value) fd.append("start", splitStart.value);
    if (splitEnd.value) fd.append("end", splitEnd.value);
    btnSplit.disabled = true; btnSplit.textContent = IC.t("btn.extracting_pages");
    try {
      const res = await fetch("/api/split-pdf", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error((data && data.detail) || "Errore");
      results = data.results;
      renderResults();
      showToast(IC.t("dyn.pages_extracted", { n: data.pages, total: data.total_pages_source }), "ok");
    } catch (err) {
      showToast(err.message || String(err), "err");
    } finally {
      btnSplit.disabled = false; btnSplit.textContent = IC.t("btn.extract");
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
    if (mode === "prefix") return IC.t("cp.rn.label_prefix");
    if (mode === "suffix") return IC.t("cp.rn.label_suffix");
    if (mode === "find") return IC.t("cp.rn.label_find");
    return IC.t("cp.rn.label_num");
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
    if (!renameFiles.length) return showToast(IC.t("dyn.pick_files_first"), "err");
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
    if (!renameFiles.length) return showToast(IC.t("dyn.pick_files_first"), "err");
    btnRename.disabled = true; btnRename.textContent = IC.t("btn.renaming");
    try {
      const res = await fetch("/api/rename-batch", { method: "POST", body: buildRenameForm() });
      if (!res.ok) {
        let msg = "Errore";
        try { const j = await res.json(); msg = (j && j.detail) || msg; } catch (_) {}
        throw new Error(msg);
      }
      await downloadBlobResponse(res, "versocon_renamed.zip");
      showToast(IC.t("dyn.rename_zip_ready"), "ok");
    } catch (err) {
      showToast(err.message || String(err), "err");
    } finally {
      btnRename.disabled = false; btnRename.textContent = IC.t("btn.crn");
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
    if (!cImgFile) return showToast(IC.t("dyn.pick_image_first"), "err");
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
    btnCImg.textContent = IC.t("btn.compressing");
    try {
      const res = await fetch("/api/compress-image", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error((data && data.detail) || "Errore");
      results = data.results;
      renderResults();
      showToast(IC.t("dyn.image_compressed"), "ok");
    } catch (err) {
      showToast(err.message || String(err), "err");
    } finally {
      btnCImg.disabled = false;
      btnCImg.textContent = IC.t("btn.cimg_convert");
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
    if (!cPdfFile) return showToast(IC.t("dyn.pick_pdf_first"), "err");
    const fd = new FormData();
    fd.append("file", cPdfFile);
    fd.append("level", cPdfLevel.value);
    btnCPdf.disabled = true;
    btnCPdf.textContent = IC.t("btn.compressing");
    try {
      const res = await fetch("/api/compress-pdf", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error((data && data.detail) || "Errore");
      results = data.results;
      renderResults();
      showToast(IC.t("dyn.pdf_compressed"), "ok");
    } catch (err) {
      showToast(err.message || String(err), "err");
    } finally {
      btnCPdf.disabled = false;
      btnCPdf.textContent = IC.t("btn.cpdf");
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
  const edSessionNote = $("#edSessionNote");
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
  const edZoomIn = document.getElementById("edZoomIn");
  const edZoomOut = document.getElementById("edZoomOut");
  const edZoomFit = document.getElementById("edZoomFit");
  const edZoomLabel = document.getElementById("edZoomLabel");
  const edPageWrap = edPageEl.parentElement;

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

  /* ---------- Editor v2: layer disegno (penna) + rettangoli redazione ---------- */
  const edInkLayer = document.getElementById("edInkLayer");
  const edRectLayer = document.getElementById("edRectLayer");
  let edInkStrokes = [];
  let edRedactRects = [];
  let edInkColor = "#e2382c";
  let edInkW = 2;
  let edRectDraft = null;

  function layerSize(layer) {
    const dpr = window.devicePixelRatio || 1;
    const w = Math.max(1, Math.round((edPageEl.clientWidth || 0) * dpr));
    const h = Math.max(1, Math.round((edPageEl.clientHeight || 0) * dpr));
    if (layer.width !== w) layer.width = w;
    if (layer.height !== h) layer.height = h;
  }
  function pctPoint(layer, e) {
    const r = layer.getBoundingClientRect();
    const cl = (v) => Math.max(0, Math.min(100, v));
    return [cl((e.clientX - r.left) / r.width * 100), cl((e.clientY - r.top) / r.height * 100)];
  }
  function redrawInk() {
    if (!edInkLayer) return;
    layerSize(edInkLayer);
    const ctx = edInkLayer.getContext("2d");
    const sx = edInkLayer.width / 100, sy = edInkLayer.height / 100;
    const lw = Math.max(1, edInkW * (edInkLayer.width / 600));
    ctx.clearRect(0, 0, edInkLayer.width, edInkLayer.height);
    ctx.strokeStyle = ctx.fillStyle = edInkColor;
    ctx.lineWidth = lw; ctx.lineCap = ctx.lineJoin = "round";
    edInkStrokes.forEach((st) => {
      if (st.length === 1) {
        ctx.beginPath();
        ctx.arc(st[0][0] * sx, st[0][1] * sy, lw / 2, 0, Math.PI * 2);
        ctx.fill();
        return;
      }
      ctx.beginPath();
      st.forEach((p, i) => i ? ctx.lineTo(p[0] * sx, p[1] * sy) : ctx.moveTo(p[0] * sx, p[1] * sy));
      ctx.stroke();
    });
  }
  function redrawRects() {
    if (!edRectLayer) return;
    layerSize(edRectLayer);
    const ctx = edRectLayer.getContext("2d");
    const sx = edRectLayer.width / 100, sy = edRectLayer.height / 100;
    const fill = (document.getElementById("edRedactFill") || {}).value || "#000000";
    ctx.clearRect(0, 0, edRectLayer.width, edRectLayer.height);
    const all = edRectDraft ? edRedactRects.concat([edRectDraft]) : edRedactRects;
    ctx.fillStyle = fill; ctx.strokeStyle = "#e2382c"; ctx.lineWidth = 1.5; ctx.setLineDash([5, 3]);
    all.forEach((r) => {
      const x = r[0] * sx, y = r[1] * sy, w = r[2] * sx, h = r[3] * sy;
      ctx.globalAlpha = 0.45; ctx.fillRect(x, y, w, h);
      ctx.globalAlpha = 1; ctx.strokeRect(x, y, w, h);
    });
  }
  function syncDrawLayers() {
    const act = edAction.value;
    const redactMode = (document.getElementById("edRedactMode") || {}).value;
    if (edInkLayer) {
      edInkLayer.hidden = act !== "ink";
      edInkLayer.style.pointerEvents = act === "ink" ? "auto" : "none";
      if (act === "ink") redrawInk();
    }
    if (edRectLayer) {
      const on = act === "redact" && redactMode === "rect";
      edRectLayer.hidden = !on;
      edRectLayer.style.pointerEvents = on ? "auto" : "none";
      if (on) redrawRects();
    }
  }
  if (edInkLayer) {
    let drawing = false;
    edInkLayer.addEventListener("pointerdown", (e) => {
      if (edInkLayer.hidden) return;
      drawing = true;
      edInkStrokes.push([pctPoint(edInkLayer, e)]);
      try { edInkLayer.setPointerCapture(e.pointerId); } catch (_) {}
      redrawInk();
    });
    edInkLayer.addEventListener("pointermove", (e) => {
      if (!drawing) return;
      edInkStrokes[edInkStrokes.length - 1].push(pctPoint(edInkLayer, e));
      redrawInk();
    });
    const inkEnd = (e) => {
      drawing = false;
      try { edInkLayer.releasePointerCapture(e.pointerId); } catch (_) {}
    };
    edInkLayer.addEventListener("pointerup", inkEnd);
    edInkLayer.addEventListener("pointercancel", inkEnd);
    const cEl = document.getElementById("edInkColor");
    if (cEl) cEl.addEventListener("input", () => { edInkColor = cEl.value; redrawInk(); });
    const wEl = document.getElementById("edInkWidth");
    if (wEl) wEl.addEventListener("input", () => { edInkW = +wEl.value || 2; redrawInk(); });
    const clr = document.getElementById("btnInkLayerClear");
    if (clr) clr.addEventListener("click", () => { edInkStrokes = []; redrawInk(); });
  }
  if (edRectLayer) {
    let start = null;
    edRectLayer.addEventListener("pointerdown", (e) => {
      if (edRectLayer.hidden) return;
      start = pctPoint(edRectLayer, e);
      edRectDraft = [start[0], start[1], 0, 0];
      try { edRectLayer.setPointerCapture(e.pointerId); } catch (_) {}
      redrawRects();
    });
    edRectLayer.addEventListener("pointermove", (e) => {
      if (!start) return;
      const p = pctPoint(edRectLayer, e);
      edRectDraft = [Math.min(start[0], p[0]), Math.min(start[1], p[1]),
                     Math.abs(p[0] - start[0]), Math.abs(p[1] - start[1])];
      redrawRects();
    });
    const rectEnd = (e) => {
      if (start && edRectDraft && edRectDraft[2] > 0.5 && edRectDraft[3] > 0.5) {
        edRedactRects.push(edRectDraft);
      }
      start = null; edRectDraft = null;
      try { edRectLayer.releasePointerCapture(e.pointerId); } catch (_) {}
      redrawRects();
    };
    edRectLayer.addEventListener("pointerup", rectEnd);
    edRectLayer.addEventListener("pointercancel", rectEnd);
    const modeEl = document.getElementById("edRedactMode");
    if (modeEl) modeEl.addEventListener("change", syncDrawLayers);
    const fillEl = document.getElementById("edRedactFill");
    if (fillEl) fillEl.addEventListener("input", redrawRects);
    const clr = document.getElementById("btnRedactClear");
    if (clr) clr.addEventListener("click", () => { edRedactRects = []; redrawRects(); });
  }
  function edPlaceFromClick(e) {
    const act = edAction.value;
    if (!["note", "text", "stamp"].includes(act)) return;
    if (!edPreview || edPreview.hidden) return;
    if (edSigOverlay && !edSigOverlay.hidden && edSigOverlay.contains(e.target)) return;
    if ((edInkLayer && !edInkLayer.hidden) || (edRectLayer && !edRectLayer.hidden)) return;
    const r = edPageEl.getBoundingClientRect();
    if (!r.width || !r.height) return;
    const x = Math.max(0, Math.min(100, (e.clientX - r.left) / r.width * 100));
    const y = Math.max(0, Math.min(100, (e.clientY - r.top) / r.height * 100));
    const map = { note: ["edNoteX", "edNoteY"], text: ["edTextX", "edTextY"], stamp: ["edStampX", "edStampY"] }[act];
    const xi = document.getElementById(map[0]), yi = document.getElementById(map[1]);
    if (!xi || !yi) return;
    const w = act === "stamp" ? (+(document.getElementById("edStampW") || {}).value || 0) : 0;
    const h = act === "stamp" ? (+(document.getElementById("edStampH") || {}).value || 0) : 0;
    xi.value = Math.max(0, Math.min(100, x - w / 2)).toFixed(1);
    yi.value = Math.max(0, Math.min(100, y - h / 2)).toFixed(1);
  }
  edPageEl.addEventListener("click", edPlaceFromClick);

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
  const ED_ZOOM_STEPS = [0.5, 0.75, 1, 1.25, 1.5, 2, 3];
  let edZoom = 1;

  function fitWidthCss() {
    const avail = edPageWrap ? edPageWrap.clientWidth - 24 : 0;
    return Math.min(1280, Math.max(240, avail || 640));
  }

  function syncZoomUI() {
    if (edZoomLabel) edZoomLabel.textContent = Math.round(edZoom * 100) + "%";
    if (edZoomOut) edZoomOut.disabled = edZoom <= ED_ZOOM_STEPS[0];
    if (edZoomIn) edZoomIn.disabled = edZoom >= ED_ZOOM_STEPS[ED_ZOOM_STEPS.length - 1];
    if (edPageWrap) edPageWrap.classList.toggle("ed-zoomed", edZoom > 1);
  }

  function resetWrapScroll() {
    if (edPageWrap) { edPageWrap.scrollTop = 0; edPageWrap.scrollLeft = 0; }
  }

  function setZoom(z) {
    const min = ED_ZOOM_STEPS[0], max = ED_ZOOM_STEPS[ED_ZOOM_STEPS.length - 1];
    const clamped = Math.max(min, Math.min(max, z));
    if (clamped === edZoom) return;
    edZoom = clamped;
    syncZoomUI();
    renderEdPage();
  }

  function stepZoom(dir) {
    const idx = ED_ZOOM_STEPS.findIndex((s) => (dir > 0 ? s > edZoom + 0.001 : s >= edZoom - 0.001));
    if (idx === -1) return;
    setZoom(dir > 0 ? ED_ZOOM_STEPS[idx] : ED_ZOOM_STEPS[Math.max(0, idx - 1)]);
  }

  async function renderEdPage() {
    if (!edPdfDoc) return;
    const token = ++edRenderToken;
    const page = await edPdfDoc.getPage(edCurPage);
    if (token !== edRenderToken) return;
    setEmpty("");
    const vp1 = page.getViewport({ scale: 1 });
    const dpr = window.devicePixelRatio || 1;
    const scale = (fitWidthCss() / vp1.width) * edZoom;
    const vp2 = page.getViewport({ scale: scale });
    const cssW = Math.round(vp2.width);
    const cssH = Math.round(vp2.height);
    edCanvas.width  = Math.floor(vp2.width  * dpr);
    edCanvas.height = Math.floor(vp2.height * dpr);
    edCanvas.style.width  = cssW + "px";
    edCanvas.style.height = cssH + "px";
    edPageEl.style.width = (cssW + 4) + "px";
    syncDrawLayers();
    const ctx = edCanvas.getContext("2d");
    ctx.clearRect(0, 0, edCanvas.width, edCanvas.height);
    edCanvas.hidden = false;
    try {
      await page.render({ canvasContext: ctx, viewport: vp2 }).promise;
    } catch (e) {
      if (token === edRenderToken) {
        setEmpty(IC.t("dyn.render_err", { msg: (e && e.message ? e.message : e) }));
        edCanvas.hidden = true;
        edPageEl.style.width = "";
        showToast(IC.t("dyn.render_failed"), "err");
      }
    }
  }

  async function loadEdPreview(file) {
    if (!file) {
      if (edPdfDoc) { try { edPdfDoc.destroy(); } catch (e) {} edPdfDoc = null; }
      edPreview.hidden = true;
      edPageCount = 0; edSigFile = null; edSigBox = { x: 50, y: 80, w: 30, rot: 0, op: 100 };
      edPageEl.style.width = "";
      applySigBoxToDom();
      return;
    }
    if (!window.pdfjsLib) {
      showToast(IC.t("dyn.pdfjs_missing"), "err");
      edPreview.hidden = false;
      setEmpty(IC.t("dyn.ed_no_preview"));
      edCanvas.hidden = true;
      return;
    }
    edPreview.hidden = false;
    if (edPdfDoc) { try { edPdfDoc.destroy(); } catch (e) {} edPdfDoc = null; }
    bindOverlayOnce();
    edStatus.textContent = IC.t("dyn.preview_loading");
    edPageCount = 0; edCurPage = 1;
    edPgSel.innerHTML = "";
    setEmpty(IC.t("dyn.ed_page_loading"));
    try {
      const buf = await file.arrayBuffer();
      edPdfDoc = await window.pdfjsLib.getDocument({ data: buf }).promise;
      edPageCount = edPdfDoc.numPages;
      edCurPage = 1;
      syncPager();
      edZoom = 1;
      syncZoomUI();
      resetWrapScroll();
      edPgSel.innerHTML = "";
      for (let i = 1; i <= edPageCount; i++) {
        const o = document.createElement("option");
        o.value = i; o.textContent = i;
        edPgSel.appendChild(o);
      }
      edPgSel.value = "1";
      edStatus.textContent = IC.t("dyn.ed_loaded", { name: file.name, size: fmtBytes(file.size), n: edPageCount });
      await renderEdPage();
    } catch (e) {
      edStatus.textContent = IC.t("dyn.err_preview", { msg: (e && e.message ? e.message : e) });
      setEmpty(IC.t("dyn.err_preview", { msg: (e && e.message ? e.message : e) }));
    }
    applySigBoxToDom();
  }

  function syncPager() {
    if (edPgLabel) edPgLabel.textContent = edPageCount ? `${edCurPage} / ${edPageCount}` : "-";
    if (edPgSel && edPgSel.options.length) edPgSel.value = String(edCurPage);
    if (edPgPrev) edPgPrev.disabled = !edPageCount || edCurPage <= 1;
    if (edPgNext) edPgNext.disabled = !edPageCount || edCurPage >= edPageCount;
  }

  edPgPrev.addEventListener("click", () => { if (edCurPage > 1) { edCurPage--; syncPager(); resetWrapScroll(); renderEdPage(); } });
  edPgNext.addEventListener("click", () => { if (edCurPage < edPageCount) { edCurPage++; syncPager(); resetWrapScroll(); renderEdPage(); } });
  edPgSel.addEventListener("change", () => { edCurPage = +edPgSel.value; syncPager(); resetWrapScroll(); renderEdPage(); });

  if (edZoomIn) edZoomIn.addEventListener("click", () => stepZoom(1));
  if (edZoomOut) edZoomOut.addEventListener("click", () => stepZoom(-1));
  if (edZoomFit) edZoomFit.addEventListener("click", () => setZoom(1));
  if (edPageWrap) edPageWrap.addEventListener("wheel", (e) => {
    if (!e.ctrlKey) return;
    e.preventDefault();
    stepZoom(e.deltaY < 0 ? 1 : -1);
  }, { passive: false });

  let edResizeT = null;
  window.addEventListener("resize", () => {
    if (!edPdfDoc) return;
    clearTimeout(edResizeT);
    edResizeT = setTimeout(() => { renderEdPage(); }, 150);
  });

  let edPan = null;
  if (edPageWrap) {
    edPageWrap.addEventListener("pointerdown", (e) => {
      if (e.button !== 0 || edZoom <= 1) return;
      if (edSigOverlay && edSigOverlay.contains(e.target)) return;
      edPan = { x: e.clientX, y: e.clientY, sl: edPageWrap.scrollLeft, st: edPageWrap.scrollTop };
      edPageWrap.classList.add("ed-panning");
      edPageWrap.setPointerCapture(e.pointerId);
    });
    edPageWrap.addEventListener("pointermove", (e) => {
      if (!edPan) return;
      edPageWrap.scrollLeft = edPan.sl - (e.clientX - edPan.x);
      edPageWrap.scrollTop  = edPan.st - (e.clientY - edPan.y);
      e.preventDefault();
    });
    const edPanEnd = (e) => {
      if (!edPan) return;
      edPan = null;
      edPageWrap.classList.remove("ed-panning");
      try { edPageWrap.releasePointerCapture(e.pointerId); } catch (err) {}
    };
    edPageWrap.addEventListener("pointerup", edPanEnd);
    edPageWrap.addEventListener("pointercancel", edPanEnd);
  }
  syncZoomUI();

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
  const ED_ACTIONS = ["rotate", "delete", "reorder", "watermark", "signature",
    "annotate", "note", "ink", "stamp", "text", "redact", "replace",
    "number", "headerfooter", "insertpage", "extract", "form"];
  const edBlocks = {};
  ED_ACTIONS.forEach((a) => { edBlocks[a] = document.getElementById("edBlock-" + a); });
  let inkPadOpen = false;
  function syncEdBlock() {
    const act = edAction.value;
    for (const [k, el] of Object.entries(edBlocks)) {
      if (el) el.hidden = (k !== act);
    }
    const pad = document.getElementById("edSignPad");
    if (pad) pad.hidden = (act !== "signature" || !inkPadOpen);
    const sigHint = document.getElementById("edHintSig");
    if (sigHint) sigHint.hidden = (act !== "signature");
    syncDrawLayers();
    updateEdToolsActive();
  }
  /* Griglia strumenti (la select #edAction resta come stato, nascosta). */
  const ED_TOOLS = [
    ["pdf.edit.group_pages", ["rotate", "delete", "reorder", "insertpage", "extract"]],
    ["pdf.edit.group_mark", ["annotate", "note", "ink", "stamp"]],
    ["pdf.edit.group_text", ["watermark", "text", "redact", "replace"]],
    ["pdf.edit.group_doc", ["signature", "number", "headerfooter"]],
    ["pdf.edit.group_form", ["form"]],
  ];
  const ED_TOOL_KEY = { watermark: "wm", signature: "sig", headerfooter: "hf" };
  function renderEdTools() {
    const box = document.getElementById("edTools");
    if (!box) return;
    box.setAttribute("aria-label", IC.t("pdf.edit.action"));
    box.innerHTML = ED_TOOLS.map(([group, keys]) =>
      `<h5>${IC.t(group)}</h5>` + keys.map((k) => {
        const label = IC.t("pdf.edit." + (ED_TOOL_KEY[k] || k));
        return `<button class="ed-tool" type="button" data-tool="${k}" aria-pressed="${k === edAction.value}">${label}</button>`;
      }).join("")
    ).join("");
  }
  function updateEdToolsActive() {
    document.querySelectorAll("#edTools .ed-tool").forEach((b) => {
      b.setAttribute("aria-pressed", String(b.getAttribute("data-tool") === edAction.value));
    });
  }
  const edToolsBox = document.getElementById("edTools");
  if (edToolsBox) edToolsBox.addEventListener("click", (e) => {
    const btn = e.target.closest(".ed-tool");
    if (!btn) return;
    edAction.value = btn.getAttribute("data-tool");
    syncEdBlock();
    btn.focus();
  });
  edAction.addEventListener("change", syncEdBlock);
  renderEdTools();
  syncEdBlock();
  const pairs = [
    ["edWmSize", "edWmSizeVal", (v) => v],
    ["edWmOpacity", "edWmOpVal", (v) => v],
    ["edSigRot", "edSigRotVal", (v) => (+v) + "°"],
    ["edSigOpacity", "edSigOpVal", (v) => v],
    ["edAnnoOpacity", "edAnnoOpVal", (v) => v],
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
  const btnSigClear = document.getElementById("btnSigClear");
  if (btnSigClear) btnSigClear.addEventListener("click", () => {
    if (edSigImag.src && edSigImag.src.startsWith("blob:")) URL.revokeObjectURL(edSigImag.src);
    edSigImag.removeAttribute("src");
    edSigFile = null;
    const inp = document.getElementById("edSigImg");
    if (inp) inp.value = "";
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
      if (!inkStrokes.length) return showToast(IC.t("dyn.draw_sign_first"), "err");
      let pngBlob;
      try {
        pngBlob = await new Promise((res, rej) =>
          inkPad.toBlob((b) => (b ? res(b) : rej(new Error("pad vuoto"))), "image/png"));
      } catch (e) { return showToast(IC.t("dyn.no_pad_export"), "err"); }
      const name = "firma_disegnata_" + Date.now() + ".png";
      edSigFile = new File([pngBlob], name, { type: "image/png" });
      const u = URL.createObjectURL(pngBlob);
      edSigImag.src = u;
      applySigBoxToDom();
      showToast(IC.t("dyn.signature_created"), "ok");
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
      if (!name) return showToast(IC.t("dyn.write_name_first"), "err");
      btnTxtSign.disabled = true;
      try {
        const fd = new FormData();
        fd.append("name", name);
        if (edTxtStyle) fd.append("style", edTxtStyle.value);
        fd.append("color", (document.getElementById("edTxtColor") || {}).value || "#000000");
        const r = await fetch("/api/signature-generate", { method: "POST", body: fd });
        if (!r.ok) {
          let msg = IC.t("dyn.sign_gen_failed");
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
        showToast(IC.t("dyn.signature_created"), "ok");
      } catch (err) {
        showToast(err.message || String(err), "err");
      } finally {
        btnTxtSign.disabled = false;
      }
    });
  }

  /* ---------- Compila modulo: elenco campi dal PDF ---------- */
  const btnFormLoad = document.getElementById("btnFormLoad");
  if (btnFormLoad) btnFormLoad.addEventListener("click", async () => {
    if (!edPdfFile) return showToast(IC.t("dyn.pick_pdf_first"), "err");
    const box = document.getElementById("edFormFields");
    btnFormLoad.disabled = true;
    try {
      const fd = new FormData();
      fd.append("file", edPdfFile);
      const r = await fetch("/api/pdf-form-fields", { method: "POST", body: fd });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error((data && data.detail) || IC.t("dyn.generic_error"));
      const fields = data.fields || [];
      box.innerHTML = "";
      if (!fields.length) {
        showToast(IC.t("pdf.edit.form_none"), "warn");
      } else {
        fields.forEach((f) => {
          const lab = document.createElement("label");
          lab.textContent = f.name + (f.page ? " · p." + f.page : "");
          const inp = document.createElement("input");
          inp.type = "text";
          inp.className = "numin";
          inp.setAttribute("data-field", f.name);
          inp.value = f.value || "";
          box.appendChild(lab);
          box.appendChild(inp);
        });
      }
    } catch (err) {
      showToast(err.message || String(err), "err");
    } finally {
      btnFormLoad.disabled = false;
    }
  });

  function pagesToPayload(raw) {
    const v = (raw || "").trim();
    const low = v.toLowerCase();
    if (low === "" || low === "tutte" || low === "all" || low === "*") return v === "" ? "" : low;
    const nums = v.split(",").map((s) => s.trim()).filter(Boolean).map(Number);
    if (nums.some((n) => !Number.isInteger(n) || n < 1)) {
      throw new Error(IC.t("dyn.pages_invalid"));
    }
    return JSON.stringify(nums);
  }
  function orderToPayload(raw) {
    const v = (raw || "").trim();
    if (!v) throw new Error(IC.t("dyn.order_required"));
    const nums = v.split(",").map((s) => s.trim()).filter(Boolean).map(Number);
    if (nums.some((n) => !Number.isInteger(n) || n < 1)) {
      throw new Error(IC.t("dyn.order_invalid"));
    }
    return JSON.stringify(nums);
  }

  btnEdApply.addEventListener("click", async () => {
    if (!edPdfFile) return showToast(IC.t("dyn.pick_pdf_first"), "err");
    const act = edAction.value;
    edDownload.hidden = true;
    edSessionNote.hidden = true;
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
        if (!edSigFile) throw new Error(IC.t("dyn.no_signature"));
        fd.append("signature", edSigFile);
        fd.append("sig_page", $("#edSigPage").value);
        // nuovo posizionamento libero (percentuali) + rotazione + opacità
        fd.append("sig_pos_x", String(edSigBox.x));
        fd.append("sig_pos_y", String(edSigBox.y));
        fd.append("sig_w_pct", String(edSigBox.w));
        fd.append("sig_rot", String(edSigBox.rot || 0));
        fd.append("sig_opacity", String(edSigBox.op || 100));
      } else if (act === "annotate") {
        const needle = $("#edAnnoNeedle").value.trim();
        if (!needle) throw new Error(IC.t("dyn.needle_required"));
        fd.append("needle", needle);
        fd.append("anno_kind", $("#edAnnoKind").value);
        fd.append("page_num", $("#edAnnoPage").value);
        fd.append("color", $("#edAnnoColor").value);
        fd.append("annot_opacity", String((+$("#edAnnoOpacity").value) / 100));
      } else if (act === "note") {
        const txt = $("#edNoteText").value.trim();
        if (!txt) throw new Error(IC.t("dyn.note_text_required"));
        fd.append("page_num", $("#edNotePage").value);
        fd.append("text_body", txt);
        fd.append("note_icon", $("#edNoteIcon").value);
        fd.append("x_pct", $("#edNoteX").value);
        fd.append("y_pct", $("#edNoteY").value);
        fd.append("color", $("#edNoteColor").value);
      } else if (act === "ink") {
        if (!edInkStrokes.length) throw new Error(IC.t("dyn.ink_empty"));
        fd.append("page_num", $("#edInkPage").value);
        fd.append("ink_strokes", JSON.stringify(edInkStrokes));
        fd.append("color", edInkColor);
        fd.append("text_size", String(edInkW));
      } else if (act === "stamp") {
        const txt = $("#edStampText").value.trim();
        if (!txt) throw new Error(IC.t("dyn.note_text_required"));
        fd.append("page_num", $("#edStampPage").value);
        fd.append("text_body", txt);
        fd.append("x_pct", $("#edStampX").value);
        fd.append("y_pct", $("#edStampY").value);
        fd.append("w_pct", $("#edStampW").value);
        fd.append("h_pct", $("#edStampH").value);
        fd.append("anno_rotate", $("#edStampRotate").value);
        fd.append("text_size", $("#edStampSize").value);
        fd.append("color", $("#edStampColor").value);
      } else if (act === "text") {
        const txt = $("#edTextBody").value.trim();
        if (!txt) throw new Error(IC.t("dyn.note_text_required"));
        fd.append("page_num", $("#edTextPage").value);
        fd.append("text_body", txt);
        fd.append("x_pct", $("#edTextX").value);
        fd.append("y_pct", $("#edTextY").value);
        fd.append("text_size", $("#edTextSize").value);
        fd.append("font_family", $("#edTextFont").value);
        fd.append("color", $("#edTextColor").value);
      } else if (act === "redact") {
        if ($("#edRedactMode").value === "rect") {
          if (!edRedactRects.length) throw new Error(IC.t("dyn.redact_rects_empty"));
          fd.append("redact_rects", JSON.stringify(edRedactRects));
          fd.append("page_num", $("#edRedactPage").value);
        } else {
          const needle = $("#edRedactNeedle").value.trim();
          if (!needle) throw new Error(IC.t("dyn.needle_required"));
          fd.append("needle", needle);
        }
        fd.append("redact_fill", $("#edRedactFill").value);
      } else if (act === "replace") {
        const needle = $("#edReplNeedle").value.trim();
        if (!needle) throw new Error(IC.t("dyn.needle_required"));
        fd.append("needle", needle);
        fd.append("replacement", $("#edReplWith").value);
        fd.append("pages", pagesToPayload($("#edReplPages").value));
        fd.append("replace_fill", $("#edReplFill").value);
      } else if (act === "number") {
        fd.append("num_start", $("#edNumStart").value);
        fd.append("num_prefix", $("#edNumPrefix").value);
        fd.append("num_suffix", $("#edNumSuffix").value);
        fd.append("num_digits", $("#edNumDigits").value);
        fd.append("num_position", $("#edNumPos").value);
        fd.append("text_size", $("#edNumSize").value);
        fd.append("hf_margin", $("#edNumMargin").value);
        fd.append("color", $("#edNumColor").value);
        fd.append("pages", pagesToPayload($("#edNumPages").value));
      } else if (act === "headerfooter") {
        const head = $("#edHfHeader").value.trim();
        const foot = $("#edHfFooter").value.trim();
        if (!head && !foot) throw new Error(IC.t("dyn.hf_empty"));
        fd.append("hf_header", head);
        fd.append("hf_footer", foot);
        fd.append("hf_position", $("#edHfPos").value);
        fd.append("hf_size", $("#edHfSize").value);
        fd.append("hf_margin", $("#edHfMargin").value);
        fd.append("color", $("#edHfColor").value);
        fd.append("pages", pagesToPayload($("#edHfPages").value));
      } else if (act === "insertpage") {
        fd.append("insert_at", $("#edInsertAt").value);
        fd.append("insert_count", $("#edInsertCount").value);
      } else if (act === "extract") {
        fd.append("pages", pagesToPayload($("#edExtractPages").value));
      } else if (act === "form") {
        const vals = {};
        document.querySelectorAll("#edFormFields [data-field]").forEach((el) => {
          vals[el.getAttribute("data-field")] = el.value;
        });
        if (!Object.keys(vals).length) throw new Error(IC.t("dyn.form_no_fields"));
        fd.append("form_values", JSON.stringify(vals));
      }
    } catch (e) {
      return showToast(e.message || String(e), "err");
    }
    btnEdApply.disabled = true;
    btnEdApply.textContent = IC.t("btn.applying");
    try {
      const r = await fetch("/api/pdf-edit", { method: "POST", body: fd });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error((data && data.detail) || IC.t("dyn.generic_error"));
      const res = data.results && data.results[0];
      edDownload.href = res.download;
      edDownload.download = res.name;
      edDownload.hidden = false;
      edSessionNote.hidden = false;
      edStatus.textContent = IC.t("dyn.ed_saved", { name: res.name, size: fmtBytes(res.size) });
      showToast(IC.t("dyn.pdf_modified"), "ok");
    } catch (err) {
      showToast(err.message || String(err), "err");
    } finally {
      btnEdApply.disabled = false;
      btnEdApply.textContent = IC.t("btn.apply");
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
      showToast(IC.t("dyn.kofi_unconfigured"), "warn");
    });
  }

  /* ---------- boot ---------- */
  function renderConfigStatus(cfg) {
    if (!cfg) return;
    const appVersion = $("#appVersion");
    if (appVersion && cfg.version) appVersion.textContent = "v" + cfg.version;
    if (cfg.support && cfg.support.kofi_url) kofiUrl = cfg.support.kofi_url;
    if (videoStatus) {
      if (cfg.video && cfg.video.ffmpeg_available === false) {
        videoStatus.textContent = IC.t("dyn.ffmpeg_missing");
      } else if (cfg.video && cfg.video.ffmpeg_available) {
        videoStatus.textContent = IC.t("dyn.ffmpeg_ok");
      }
    }
    if (txtOcrStatus) {
      if (cfg.ocr && cfg.ocr.available) {
        txtOcrStatus.textContent = IC.t("dyn.ocr_ok", { langs: (cfg.ocr.languages || []).join(", ") });
      } else {
        txtOcrStatus.textContent = IC.t("dyn.ocr_off");
      }
    }
  }
  fetch("/api/config")
    .then((r) => r.json())
    .then((cfg) => {
      bootCfg = cfg;
      renderConfigStatus(cfg);
    })
    .catch(() => {});

  /* ---------- Ricontrolla motori esterni (ffmpeg / Tesseract) ---------- */
  async function recheckEngines(btn) {
    btn.disabled = true;
    try {
      const r = await fetch("/api/engines/recheck", { method: "POST" });
      if (!r.ok) throw new Error("HTTP " + r.status);
      const res = await r.json();
      if (bootCfg) {
        bootCfg.video = Object.assign({}, bootCfg.video, res.video || {});
        bootCfg.ocr = res.ocr || bootCfg.ocr;
        renderConfigStatus(bootCfg);
      }
      showToast(IC.t("dyn.recheck_ok"), "ok");
    } catch (_) {
      showToast(IC.t("dyn.recheck_err"), "err");
    } finally {
      btn.disabled = false;
    }
  }
  document.querySelectorAll("[data-recheck]").forEach((btn) => {
    btn.addEventListener("click", () => recheckEngines(btn));
  });

  /* ---------- i18n live refresh ---------- */
  function refreshDynamicI18n() {
    try { renderQueue(); } catch (e) {}
    try { renderImgToPdf(); } catch (e) {}
    try { renderMergeList(); } catch (e) {}
    try { renderResults(); } catch (e) {}
    try { renderEdTools(); } catch (e) {}
    renderConfigStatus(bootCfg);
    const btn = $("#btnConvert");
    if (btn && !btn.disabled) btn.textContent = IC.t("btn.convert");
    if (renameValueLabel) renameValueLabel.textContent = renameLabelFor(renameMode.value);
    document.querySelectorAll("[data-rm]").forEach((b) => {
      b.setAttribute("aria-label", IC.t("list.remove"));
    });
  }
  document.addEventListener("vscon:lang", refreshDynamicI18n);
})();
