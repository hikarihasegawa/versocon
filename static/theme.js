/* Tema dell'interfaccia: "pro" (dashboard sobria, predefinito) o "manga".
 *
 * - la classe `theme-pro` su <html> attiva il tema Pro (variabili in style.css);
 * - la scelta è ricordata in localStorage (`versocon.theme`);
 * - viene applicata subito (script in <head>) per evitare il flash iniziale;
 * - il pulsante #themeToggle commuta e aggiorna label/aria-pressed.
 */
(function () {
  "use strict";
  var KEY = "versocon.theme";
  var root = document.documentElement;

  function savedTheme() {
    try {
      return localStorage.getItem(KEY);
    } catch (e) {
      return null;
    }
  }

  function label(name) {
    var hasT = window.IC && typeof IC.t === "function";
    if (hasT) return IC.t(name === "pro" ? "theme.pro" : "theme.manga");
    return name === "pro" ? "Pro" : "Manga";
  }

  function applyTheme(name) {
    root.classList.toggle("theme-pro", name === "pro");
    root.dataset.theme = name;
    var btn = document.getElementById("themeToggle");
    if (!btn) return;
    btn.setAttribute("aria-pressed", name === "pro" ? "true" : "false");
    var labelEl = document.getElementById("themeLabel");
    if (labelEl) labelEl.textContent = label(name);
    document.dispatchEvent(new CustomEvent("vscon:theme", { detail: { theme: name } }));
  }

  function currentTheme() {
    var t = savedTheme();
    return t === "manga" ? "manga" : "pro";
  }

  applyTheme(currentTheme());

  document.addEventListener("DOMContentLoaded", function () {
    applyTheme(currentTheme());
    var btn = document.getElementById("themeToggle");
    if (btn) {
      btn.addEventListener("click", function () {
        var next = root.dataset.theme === "pro" ? "manga" : "pro";
        try {
          localStorage.setItem(KEY, next);
        } catch (e) {
          /* modalità privata: la scelta vale solo per questa sessione */
        }
        applyTheme(next);
      });
    }
    document.addEventListener("vscon:lang", function () {
      applyTheme(currentTheme());
    });
  });
})();
