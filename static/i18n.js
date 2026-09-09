/* VersoCon i18n runtime — lightweight, no dependencies.
 * Usage:
 *   <span data-i18n="key">…</span>                       → replaces children (textContent)
 *   <label data-i18n-text="key">…<input/></label>        → replaces text nodes only
 *   <p data-i18n-html="key">…</p>                        → innerHTML (trusted, app strings)
 *   <input data-i18n-attr="placeholder:ph.key;title:t.key" />
 *   window.IC.t("key", {name:"x"}) → "Caricato: x …"
 *   IC.setLang("fr") → load + apply + persist
 * Fallback chain: current lang → en → it → key itself.
 */
(() => {
  "use strict";

  const SUPPORTED = ["it", "en", "es", "fr", "de", "pt", "zh", "ja"];
  const STORE_KEY = "vscon_lang";
  const dicts = {};   // lang -> object
  let cur = "it";     // applied language
  let enDict = null;
  let itDict = null;

  function pickInitial() {
    const saved = localStorage.getItem(STORE_KEY);
    if (saved && SUPPORTED.includes(saved)) return saved;
    const q = new URLSearchParams(location.search).get("lang");
    if (q && SUPPORTED.includes(q)) return q;
    const nav = (navigator.language || "").split("-")[0].toLowerCase();
    if (nav && SUPPORTED.includes(nav)) return nav;
    return "it";
  }

  async function load(lang) {
    if (dicts[lang]) return dicts[lang];
    try {
      const r = await fetch("i18n/" + lang + ".json", { cache: "no-store" });
      if (!r.ok) throw new Error("HTTP " + r.status);
      const j = await r.json();
      dicts[lang] = j;
      if (lang === "en") enDict = j;
      if (lang === "it") itDict = j;
      return j;
    } catch (e) {
      return null;
    }
  }

  function rawLookup(key) {
    const d = dicts[cur];
    if (d && d[key] != null) return d[key];
    if (enDict && enDict[key] != null) return enDict[key];
    if (itDict && itDict[key] != null) return itDict[key];
    return key;
  }

  window.IC = {
    supported: SUPPORTED,
    get lang() { return cur; },
    t(key, params) {
      let s = rawLookup(key);
      if (params && typeof s === "string") {
        for (const k of Object.keys(params)) {
          s = s.split("{" + k + "}").join(String(params[k]));
        }
      }
      return s;
    },
    async setLang(lang) {
      if (!SUPPORTED.includes(lang)) lang = "it";
      cur = lang;
      await load(lang);
      localStorage.setItem(STORE_KEY, lang);
      apply();
      const sel = document.getElementById("langSel");
      if (sel) sel.value = lang;
      document.dispatchEvent(new CustomEvent("vscon:lang", { detail: { lang } }));
    },
    apply,
    init: initI18n,
  };

  function replaceTextNodes(el, text) {
    let first = null;
    [...el.childNodes].forEach((n) => {
      if (n.nodeType === Node.TEXT_NODE) {
        if (first) el.removeChild(n);
        else first = n;
      }
    });
    if (first) {
      first.nodeValue = text;
    } else {
      el.prepend(document.createTextNode(text));
    }
  }

  function apply() {
    document.documentElement.lang = cur;
    document.title = rawLookup("app_title");
    document.querySelectorAll("[data-i18n]").forEach((el) => {
      el.textContent = rawLookup(el.getAttribute("data-i18n"));
    });
    document.querySelectorAll("[data-i18n-text]").forEach((el) => {
      replaceTextNodes(el, rawLookup(el.getAttribute("data-i18n-text")));
    });
    document.querySelectorAll("[data-i18n-html]").forEach((el) => {
      el.innerHTML = rawLookup(el.getAttribute("data-i18n-html"));
    });
    document.querySelectorAll("[data-i18n-attr]").forEach((el) => {
      el.getAttribute("data-i18n-attr").split(";").forEach((pair) => {
        const [attr, key] = pair.split(":").map((s) => s.trim());
        if (attr && key) el.setAttribute(attr, rawLookup(key));
      });
    });
  }

  const NAMES = {
    it: "Italiano", en: "English", es: "Español", fr: "Français",
    de: "Deutsch", pt: "Português", zh: "中文", ja: "日本語",
  };

  async function initI18n() {
    cur = pickInitial();
    await load(cur);
    await load("en"); // ensure fallback loaded
    if (cur !== "it") await load("it");

    const sel = document.getElementById("langSel");
    if (sel) {
      sel.innerHTML = SUPPORTED.map(
        (l) => `<option value="${l}">${NAMES[l]}</option>`
      ).join("");
      sel.value = cur;
      sel.addEventListener("change", () => { IC.setLang(sel.value); });
    }
    apply();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => IC.init());
  } else {
    IC.init();
  }
})();
