// =========================
// Footer year
// =========================
(function initYear(){
  const y = document.getElementById("year");
  if (y) y.textContent = new Date().getFullYear();
})();

// =========================
// Reveal on scroll
// =========================
(function initReveal(){
  const els = Array.from(document.querySelectorAll(".reveal"));
  if (!els.length) return;

  const io = new IntersectionObserver((entries) => {
    for (const e of entries) {
      if (e.isIntersecting) e.target.classList.add("is-in");
    }
  }, { threshold: 0.12 });

  els.forEach(el => io.observe(el));
})();

// =========================
// Background slider
// =========================
(function initBackgroundSlider(){
  const imgEl = document.getElementById("bgImg");
  const prevBtn = document.getElementById("prevBtn");
  const nextBtn = document.getElementById("nextBtn");
  if (!imgEl) return;

  // 你把这里换成你 images 文件夹里真实存在的图片即可
  const BG_IMAGES = [
    "./images/qishen.jpg",
    // "./images/xxx.jpg",
    // "./images/yyy.jpg",
  ];

  let idx = Math.max(0, BG_IMAGES.indexOf(imgEl.getAttribute("src")));
  if (idx < 0) idx = 0;

  function setBg(newIdx){
    if (!BG_IMAGES.length) return;
    idx = (newIdx + BG_IMAGES.length) % BG_IMAGES.length;

    imgEl.style.opacity = "0";
    setTimeout(() => {
      imgEl.src = BG_IMAGES[idx];
      imgEl.onload = () => {
        imgEl.style.opacity = "1";
      };
      // 如果缓存直接命中 onload 不触发，兜底一下
      setTimeout(() => { imgEl.style.opacity = "1"; }, 120);
    }, 120);
  }

  if (prevBtn) prevBtn.addEventListener("click", () => setBg(idx - 1));
  if (nextBtn) nextBtn.addEventListener("click", () => setBg(idx + 1));
})();

// =========================
// Calendar (Mon-start)
// =========================
(function initCalendar(){
  const timeEl = document.getElementById("calTime");
  const dateEl = document.getElementById("calDate");
  const subEl  = document.getElementById("calSub");
  const monthEl = document.getElementById("calMonth");
  const gridEl = document.getElementById("calGrid");
  const prevBtn = document.getElementById("calPrev");
  const nextBtn = document.getElementById("calNext");
  const todayBtn = document.getElementById("calToday");

  if (!timeEl || !dateEl || !monthEl || !gridEl) return;

  // remove sub line content
  if (subEl) subEl.textContent = "";

  const now = new Date();
  let viewYear = now.getFullYear();
  let viewMonth = now.getMonth(); // 0-11
  let selected = null; // {y,m,d}

  const fmtTime = new Intl.DateTimeFormat(undefined, {
    hour: "2-digit", minute: "2-digit", second: "2-digit",
    hour12: false
  });
  const fmtDate = new Intl.DateTimeFormat(undefined, {
    weekday: "short", month: "short", day: "2-digit", year: "numeric"
  });
  const fmtMonth = new Intl.DateTimeFormat(undefined, {
    month: "long", year: "numeric"
  });

  function tick(){
    const d = new Date();
    timeEl.textContent = fmtTime.format(d);
    dateEl.textContent = fmtDate.format(d);
  }
  tick();
  setInterval(tick, 1000);

  function daysInMonth(y, m){
    return new Date(y, m + 1, 0).getDate();
  }

  // JS getDay(): Sun=0..Sat=6
  // We want Mon=0..Sun=6
  function monStartIndex(y, m, day){
    const js = new Date(y, m, day).getDay();
    return (js + 6) % 7;
  }

  function isSame(a, b){
    return a && b && a.y === b.y && a.m === b.m && a.d === b.d;
  }

  function render(){
    monthEl.textContent = fmtMonth.format(new Date(viewYear, viewMonth, 1));
    gridEl.innerHTML = "";

    const today = new Date();
    const todayKey = { y: today.getFullYear(), m: today.getMonth(), d: today.getDate() };

    const firstIdx = monStartIndex(viewYear, viewMonth, 1);
    const dim = daysInMonth(viewYear, viewMonth);

    // previous month days to fill
    const prevMonth = viewMonth === 0 ? 11 : viewMonth - 1;
    const prevYear = viewMonth === 0 ? viewYear - 1 : viewYear;
    const dimPrev = daysInMonth(prevYear, prevMonth);

    // 6 rows * 7 = 42 cells
    for (let i = 0; i < 42; i++){
      const cell = document.createElement("button");
      cell.className = "cal__cell";
      cell.type = "button";

      let y = viewYear, m = viewMonth, d = 1;

      if (i < firstIdx){
        // previous month
        d = dimPrev - (firstIdx - 1 - i);
        y = prevYear;
        m = prevMonth;
        cell.classList.add("is-other");
      } else if (i >= firstIdx + dim){
        // next month
        d = i - (firstIdx + dim) + 1;
        y = viewMonth === 11 ? viewYear + 1 : viewYear;
        m = viewMonth === 11 ? 0 : viewMonth + 1;
        cell.classList.add("is-other");
      } else {
        d = i - firstIdx + 1;
      }

      const key = { y, m, d };
      cell.textContent = String(d);

      if (isSame(key, todayKey)) cell.classList.add("is-today");
      if (isSame(key, selected)) cell.classList.add("is-selected");

      cell.addEventListener("click", () => {
        selected = key;
        render();
      });

      gridEl.appendChild(cell);
    }
  }

  function goPrev(){
    if (viewMonth === 0){ viewMonth = 11; viewYear--; }
    else viewMonth--;
    render();
  }

  function goNext(){
    if (viewMonth === 11){ viewMonth = 0; viewYear++; }
    else viewMonth++;
    render();
  }

  function goToday(){
    const t = new Date();
    viewYear = t.getFullYear();
    viewMonth = t.getMonth();
    selected = { y: viewYear, m: viewMonth, d: t.getDate() };
    render();
  }

  if (prevBtn) prevBtn.addEventListener("click", goPrev);
  if (nextBtn) nextBtn.addEventListener("click", goNext);
  if (todayBtn) todayBtn.addEventListener("click", goToday);

  render();
})();

// =========================
// Projects carousel
// =========================
(function initProjectsCarousel(){
  const wrap = document.getElementById("projCarousel");
  if (!wrap) return;

  const items = Array.from(wrap.querySelectorAll(".projItem"));
  const prevBtn = document.getElementById("projPrev");
  const nextBtn = document.getElementById("projNext");
  const counter = document.getElementById("projCounter");

  if (!items.length){
    if (prevBtn) prevBtn.style.display = "none";
    if (nextBtn) nextBtn.style.display = "none";
    if (counter) counter.style.display = "none";
    return;
  }

  let idx = 0;

  function render(){
    items.forEach((el, i) => el.classList.toggle("is-active", i === idx));
    if (counter) counter.textContent = `${idx + 1} / ${items.length}`;

    const hideNav = items.length <= 1;
    if (prevBtn) prevBtn.style.display = hideNav ? "none" : "";
    if (nextBtn) nextBtn.style.display = hideNav ? "none" : "";
    if (counter) counter.style.display = hideNav ? "none" : "";
  }

  function prev(){
    idx = (idx - 1 + items.length) % items.length;
    render();
  }

  function next(){
    idx = (idx + 1) % items.length;
    render();
  }

  if (prevBtn) prevBtn.addEventListener("click", prev);
  if (nextBtn) nextBtn.addEventListener("click", next);

  // Optional: keyboard arrow navigation
  window.addEventListener("keydown", (e) => {
    const tag = (document.activeElement && document.activeElement.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea") return;
    if (e.key === "ArrowLeft") prev();
    if (e.key === "ArrowRight") next();
  });

  render();
})();
