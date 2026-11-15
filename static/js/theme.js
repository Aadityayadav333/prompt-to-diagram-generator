/* Runs in <head> before first paint so the chosen theme never flashes. */
(function () {
  var t = null;
  try { t = localStorage.getItem("df.theme"); } catch (e) { /* storage may be blocked */ }
  if (!t) t = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", t);
})();
