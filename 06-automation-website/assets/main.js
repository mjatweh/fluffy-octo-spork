(function () {
  const S = window.SITE || {};
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ── Email + booking ─────────────────────────── */
  const mailto = "mailto:" + S.email + "?subject=" + encodeURIComponent(S.emailSubject || "Free automation call") +
    "&body=" + encodeURIComponent("Hi,\n\nI'd like to book a free call.\n\nBusiness name:\nWhat we do:\nBest time to reach me:\nPhone:\n\nThe task that eats the most time in our business is:\n");
  document.querySelectorAll("[data-email]").forEach((el) => { el.textContent = S.email; el.href = mailto; });
  document.querySelectorAll("[data-mailto]").forEach((el) => { el.href = mailto; });

  const slot = document.getElementById("book-widget");
  if (slot) {
    if (S.calendlyUrl) {
      const css = document.createElement("link");
      css.rel = "stylesheet"; css.href = "https://assets.calendly.com/assets/external/widget.css";
      document.head.appendChild(css);
      const url = S.calendlyUrl + (S.calendlyUrl.includes("?") ? "&" : "?") + "hide_gdpr_banner=1&primary_color=ff5a1f";
      slot.innerHTML = '<div class="calendly-inline-widget" data-url="' + url + '"></div>';
      const js = document.createElement("script");
      js.src = "https://assets.calendly.com/assets/external/widget.js"; js.async = true;
      document.body.appendChild(js);
    } else {
      slot.innerHTML =
        '<div class="book-fallback"><div class="big">📅</div>' +
        "<h3>Pick a time that suits you</h3>" +
        "<p>Send us a quick note with two or three times that work. We reply the same business day to confirm.</p>" +
        '<p><a class="btn btn-lg" href="' + mailto + '">Email us to book <span class="arrow">→</span></a></p>' +
        '<p>or write to <a class="email" href="' + mailto + '">' + S.email + "</a></p></div>";
    }
  }

  /* ── Header + mobile nav ─────────────────────── */
  const header = document.querySelector(".site-header");
  const sticky = document.querySelector(".sticky-cta");
  const book = document.getElementById("book");
  const onScroll = () => {
    const y = window.scrollY;
    header && header.classList.toggle("scrolled", y > 30);
    if (sticky) {
      const bookTop = book ? book.getBoundingClientRect().top : 1e9;
      sticky.classList.toggle("show", y > 600 && bookTop > window.innerHeight * 0.6);
    }
  };
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  const toggle = document.querySelector(".nav-toggle");
  toggle && toggle.addEventListener("click", () => {
    const open = document.body.classList.toggle("nav-open");
    toggle.setAttribute("aria-expanded", open);
  });
  document.querySelectorAll(".nav a").forEach((a) => a.addEventListener("click", () => document.body.classList.remove("nav-open")));

  /* ── Reveal on scroll ────────────────────────── */
  const io = "IntersectionObserver" in window ? new IntersectionObserver((entries) => {
    entries.forEach((e) => { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } });
  }, { threshold: 0.12 }) : null;
  document.querySelectorAll(".reveal").forEach((el) => (io ? io.observe(el) : el.classList.add("in")));

  /* ── Counters ────────────────────────────────── */
  const countIO = "IntersectionObserver" in window ? new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      if (!e.isIntersecting) return;
      const el = e.target, end = +el.dataset.count, suffix = el.dataset.suffix || "";
      countIO.unobserve(el);
      if (reduce) { el.textContent = end + suffix; return; }
      const t0 = performance.now(), dur = 1400;
      const tick = (t) => {
        const p = Math.min(1, (t - t0) / dur);
        el.textContent = Math.round(end * (1 - Math.pow(1 - p, 3))) + suffix;
        if (p < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });
  }, { threshold: 0.5 }) : null;
  document.querySelectorAll("[data-count]").forEach((el) => countIO && countIO.observe(el));

  /* ── Rotating word in hero ───────────────────── */
  document.querySelectorAll(".rotator").forEach((r) => {
    const words = [...r.children];
    let i = 0;
    words[0].classList.add("on");
    if (reduce) return;
    setInterval(() => {
      words[i].classList.remove("on");
      i = (i + 1) % words.length;
      words[i].classList.add("on");
    }, 2200);
  });

  /* ── Typing answer (case study) ──────────────── */
  document.querySelectorAll("[data-type]").forEach((el) => {
    const text = el.dataset.type;
    if (reduce || !io) { el.textContent = text; return; }
    const obs = new IntersectionObserver((en) => {
      if (!en[0].isIntersecting) return;
      obs.disconnect();
      el.classList.add("typing");
      let n = 0;
      const step = () => { el.textContent = text.slice(0, ++n); if (n < text.length) setTimeout(step, 18); else el.classList.remove("typing"); };
      step();
    }, { threshold: 0.6 });
    obs.observe(el);
  });

  /* ── "Sound familiar?" checklist ─────────────── */
  const pains = document.querySelectorAll(".pain");
  const result = document.querySelector(".pain-result");
  if (pains.length && result) {
    const count = result.querySelector(".count");
    const msg = result.querySelector("[data-msg]");
    const update = () => {
      const n = document.querySelectorAll('.pain[aria-pressed="true"]').length;
      count.textContent = n;
      result.classList.toggle("show", n > 0);
      msg.textContent = n === 1
        ? "That's one job a computer could be doing for your team every single day."
        : n < 4
          ? "Those are " + n + " jobs a computer could be doing for your team. Each one adds up to hours, every week."
          : n + " out of " + pains.length + ". Your team is doing a lot of work by hand that software can now handle. Let's talk about it.";
    };
    pains.forEach((p) => p.addEventListener("click", () => {
      p.setAttribute("aria-pressed", p.getAttribute("aria-pressed") !== "true");
      update();
    }));
  }

  /* ── Hidden-cost calculator ──────────────────── */
  const calc = document.querySelector(".calc");
  if (calc) {
    const fmt = (n) => "$" + Math.round(n).toLocaleString("en-US");
    const inputs = calc.querySelectorAll("input[type=range]");
    const run = () => {
      const v = {};
      inputs.forEach((i) => {
        v[i.name] = +i.value;
        const out = calc.querySelector('output[for="' + i.id + '"]');
        if (out) out.textContent = (i.dataset.prefix || "") + (+i.value).toLocaleString("en-US") + (i.dataset.suffix || "");
        i.style.setProperty("--p", ((i.value - i.min) / (i.max - i.min)) * 100 + "%");
      });
      const yearlyHours = v.people * v.hours * 50;
      const yearlyCost = yearlyHours * v.rate;
      calc.querySelector("[data-money]").textContent = fmt(yearlyCost);
      calc.querySelector("[data-hours]").textContent = yearlyHours.toLocaleString("en-US");
      calc.querySelector("[data-half]").textContent = fmt(yearlyCost / 2);
      calc.querySelector("[data-weeks]").textContent = Math.round(yearlyHours / 2 / 40).toLocaleString("en-US");
    };
    inputs.forEach((i) => i.addEventListener("input", run));
    run();
  }

  /* ── Footer year ─────────────────────────────── */
  document.querySelectorAll("[data-year]").forEach((el) => (el.textContent = new Date().getFullYear()));
})();
