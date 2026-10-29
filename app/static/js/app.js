(function () {
  "use strict";
  var root = document.documentElement;

  // Жарық / қараңғы тақырып
  var toggle = document.querySelector("[data-theme-toggle]");
  if (toggle) {
    toggle.addEventListener("click", function () {
      var next = root.dataset.theme === "dark" ? "light" : "dark";
      root.dataset.theme = next;
      try { localStorage.setItem("theme", next); } catch (e) { /* жеке режим */ }
    });
  }

  // Аспан: тәулік уақытына қарай күн немесе түн
  var hour = new Date().getHours();
  var night = hour < 6 || hour >= 19;
  var forced = new URLSearchParams(location.search).get("sky");  // ?sky=day / ?sky=night — көрсету үшін
  if (forced === "day" || forced === "night") night = forced === "night";
  document.querySelectorAll("[data-sky]").forEach(function (sky) {
    if (!sky.dataset.time) sky.dataset.time = night ? "night" : "day";
  });

  // Тірі сағат
  var DAYS = ["жексенбі", "дүйсенбі", "сейсенбі", "сәрсенбі", "бейсенбі", "жұма", "сенбі"];
  var MONTHS = ["қаңтар", "ақпан", "наурыз", "сәуір", "мамыр", "маусым", "шілде", "тамыз", "қыркүйек", "қазан", "қараша", "желтоқсан"];
  var clocks = document.querySelectorAll("[data-clock]");
  var dates = document.querySelectorAll("[data-date]");
  function tick() {
    var now = new Date();
    var hh = String(now.getHours()).padStart(2, "0");
    var mm = String(now.getMinutes()).padStart(2, "0");
    clocks.forEach(function (el) { el.textContent = hh + ":" + mm; });
    dates.forEach(function (el) {
      el.textContent = now.getDate() + " " + MONTHS[now.getMonth()] + ", " + DAYS[now.getDay()];
    });
  }
  if (clocks.length || dates.length) { tick(); setInterval(tick, 10000); }

  // Сандарды 0-ден санау анимациясы
  function countUp(el) {
    var target = parseFloat(el.dataset.count);
    var decimals = parseInt(el.dataset.decimals || "0", 10);
    if (isNaN(target)) return;
    var start = performance.now();
    var duration = 1400;
    function frame(t) {
      var p = Math.min((t - start) / duration, 1);
      var eased = 1 - Math.pow(1 - p, 3);
      var value = target * eased;
      el.textContent = decimals ? value.toFixed(decimals) : Math.round(value).toLocaleString("ru-RU");
      if (p < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }

  // Карточкалардың біртіндеп пайда болуы
  var items = document.querySelectorAll("main .card, main .tile, main .station-banner");
  var counters = document.querySelectorAll("[data-count]");
  if (!("IntersectionObserver" in window)) {
    items.forEach(function (el) { el.classList.add("reveal", "is-in"); });
    counters.forEach(countUp);
    return;
  }
  var groups = new Map();
  items.forEach(function (el) {
    var parent = el.parentElement;
    var index = groups.get(parent) || 0;
    groups.set(parent, index + 1);
    el.style.setProperty("--d", Math.min(index, 8) * 70 + "ms");
    el.classList.add("reveal");
  });
  var observer = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (!entry.isIntersecting) return;
      entry.target.classList.add("is-in");
      entry.target.querySelectorAll("[data-count]").forEach(countUp);
      observer.unobserve(entry.target);
    });
  }, { threshold: 0.08 });
  items.forEach(function (el) { observer.observe(el); });
  // Қауіпсіздік: бақылаушы іске қоспаса да, мазмұн көрінбей қалмасын
  setTimeout(function () {
    items.forEach(function (el) {
      if (!el.classList.contains("is-in")) {
        el.classList.add("is-in");
        el.querySelectorAll("[data-count]").forEach(countUp);
      }
    });
  }, 2500);
  counters.forEach(function (el) { if (!el.closest(".reveal")) countUp(el); });
})();
