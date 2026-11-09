(function () {
  const S = window.SITE || {};
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const $ = (q, el = document) => el.querySelector(q);
  const $$ = (q, el = document) => [...el.querySelectorAll(q)];

  /* ── Booking: Calendly pop-up + inline, or email fallback ── */
  const mailto = (extra) => "mailto:" + S.email + "?subject=" + encodeURIComponent(S.emailSubject || "Book a call") +
    "&body=" + encodeURIComponent("Hi,\n\nI'd like to book a call about AI automation.\n\nCompany:\nWhat we do:\nBest times for a call:\nPhone:\n" + (extra || ""));
  $$("[data-email]").forEach((a) => { a.textContent = S.email; a.href = mailto(); });

  let calReady = null;
  const loadCalendly = () => calReady || (calReady = new Promise((res) => {
    const css = document.createElement("link");
    css.rel = "stylesheet"; css.href = "https://assets.calendly.com/assets/external/widget.css";
    document.head.appendChild(css);
    const js = document.createElement("script");
    js.src = "https://assets.calendly.com/assets/external/widget.js"; js.async = true; js.onload = res;
    document.body.appendChild(js);
  }));
  const calUrl = S.calendlyUrl ? S.calendlyUrl + (S.calendlyUrl.includes("?") ? "&" : "?") +
    "hide_gdpr_banner=1&background_color=0e0f0e&text_color=f2f5f0&primary_color=39ff14" : "";

  if (calUrl) {
    loadCalendly();
    $$("[data-book]").forEach((b) => b.addEventListener("click", (e) => {
      if (!window.Calendly) return; // falls back to scrolling to #book
      e.preventDefault();
      window.Calendly.initPopupWidget({ url: calUrl });
    }));
  }

  const slot = $("#cal");
  if (slot) {
    if (calUrl) {
      slot.innerHTML = '<div class="calendly-inline-widget" data-url="' + calUrl + '"></div>';
      loadCalendly().then(() => window.Calendly && window.Calendly.initInlineWidget({ url: calUrl, parentElement: slot.firstChild }));
    } else {
      slot.innerHTML = '<div class="cal-fallback"><span class="k">// booking</span><h3>Pick a time that works for you</h3>' +
        '<p>Send us two or three times. We confirm the same business day.</p>' +
        '<p><a class="btn btn-lg" id="mail-book" href="' + mailto() + '">Email us to book <span class="arr">→</span></a></p>' +
        '<p class="email">' + S.email + "</p></div>";
    }
  }

  /* ── Header, mobile nav, sticky CTA ─────────────── */
  const header = $(".site-header"), sticky = $(".sticky-cta"), book = $("#book");
  const onScroll = () => {
    header && header.classList.toggle("scrolled", scrollY > 20);
    if (sticky) sticky.classList.toggle("show", scrollY > 500 && (!book || book.getBoundingClientRect().top > innerHeight * .7));
  };
  addEventListener("scroll", onScroll, { passive: true }); onScroll();
  const toggle = $(".nav-toggle");
  toggle && toggle.addEventListener("click", () => toggle.setAttribute("aria-expanded", document.body.classList.toggle("nav-open")));
  $$(".nav a").forEach((a) => a.addEventListener("click", () => document.body.classList.remove("nav-open")));

  /* ── Reveal on scroll ───────────────────────────── */
  const io = "IntersectionObserver" in window && new IntersectionObserver((es) => es.forEach((e) => {
    if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
  }), { threshold: .1 });
  $$(".reveal").forEach((el) => (io ? io.observe(el) : el.classList.add("in")));

  /* ── Spotlight that follows the cursor on boxes ── */
  $$(".box").forEach((b) => b.addEventListener("pointermove", (e) => {
    const r = b.getBoundingClientRect();
    b.style.setProperty("--mx", e.clientX - r.left + "px");
    b.style.setProperty("--my", e.clientY - r.top + "px");
  }));

  /* ── Typed word in hero ─────────────────────────── */
  const typed = $(".typed");
  if (typed) {
    const words = typed.dataset.words.split("|");
    if (reduce) typed.textContent = words[0];
    else {
      let w = 0, i = 0, del = false;
      const tick = () => {
        const word = words[w];
        typed.textContent = word.slice(0, i);
        if (!del && i === word.length) { del = true; return setTimeout(tick, 1600); }
        if (del && i === 0) { del = false; w = (w + 1) % words.length; }
        i += del ? -1 : 1;
        setTimeout(tick, del ? 35 : 75);
      };
      tick();
    }
  }

  /* ── Terminal box: an automation running ────────── */
  const term = $(".term-lines");
  if (term) {
    const lines = $$("div", term);
    if (reduce) lines.forEach((l) => l.classList.add("on"));
    else {
      let n = 0;
      const step = () => {
        if (n < lines.length) { lines[n++].classList.add("on"); setTimeout(step, 650); }
        else setTimeout(() => { lines.forEach((l) => l.classList.remove("on")); n = 0; setTimeout(step, 600); }, 3500);
      };
      setTimeout(step, 900);
    }
  }

  /* ── Build-your-automation configurator ─────────── */
  const builder = $(".builder");
  if (builder) {
    const list = $(".bp-list", builder), count = $("[data-bp-count]", builder), cta = $("[data-bp-cta]", builder);
    const recipes = {
      "Invoices & bills": "Read incoming bills and invoices, code them and post them to {sys}, ready to approve",
      "Data entry": "Stop retyping: sync records between {sys} automatically",
      "Email & inbox": "Sort the inbox, draft replies and file attachments, with {sys} kept up to date",
      "Reports": "Build your weekly numbers from {sys} and send a plain-English summary",
      "Quotes & sales": "Draft quotes from your price list, follow up until the customer replies, log it in {sys}",
      "Collections": "Send polite payment reminders on schedule from {sys} and flag the late ones",
      "Documents": "Pull the details out of PDFs, POs and contracts and send them to {sys}",
      "Scheduling": "Book, confirm and remind customers automatically, synced to {sys}",
    };
    const update = () => {
      const sys = $$('[data-group="sys"] [aria-pressed="true"]', builder).map((b) => b.textContent);
      const tasks = $$('[data-group="task"] [aria-pressed="true"]', builder).map((b) => b.textContent);
      const sysText = sys.length ? sys.slice(0, 3).join(", ") + (sys.length > 3 ? " and more" : "") : "your systems";
      list.innerHTML = tasks.length
        ? tasks.map((t) => "<li>" + recipes[t].replace("{sys}", "<b>" + sysText + "</b>") + " <span>// custom-built</span></li>").join("")
        : '<li class="bp-empty" style="border-left-color:var(--line-2)">Pick a few tasks to see your automation plan →</li>';
      count.textContent = tasks.length;
      const extra = "\nOur systems: " + (sys.join(", ") || "-") + "\nTasks to automate: " + (tasks.join(", ") || "-") + "\n";
      if (!S.calendlyUrl) cta.href = mailto(extra);
      const mb = $("#mail-book"); if (mb) mb.href = mailto(extra);
    };
    $$(".opt", builder).forEach((o) => o.addEventListener("click", () => { o.setAttribute("aria-pressed", o.getAttribute("aria-pressed") !== "true"); update(); }));
    update();
  }

  /* ── Cost calculator ────────────────────────────── */
  const calc = $(".calc");
  if (calc) {
    const fmt = (n) => "$" + Math.round(n).toLocaleString("en-US");
    const ins = $$("input[type=range]", calc);
    const run = () => {
      const v = {};
      ins.forEach((i) => {
        v[i.name] = +i.value;
        $('output[for="' + i.id + '"]', calc).textContent = (i.dataset.pre || "") + (+i.value).toLocaleString("en-US") + (i.dataset.suf || "");
        i.style.setProperty("--p", (i.value - i.min) / (i.max - i.min) * 100 + "%");
      });
      const hours = v.people * v.hours * 50;
      $("[data-money]", calc).textContent = fmt(hours * v.rate);
      $("[data-hours]", calc).textContent = hours.toLocaleString("en-US");
    };
    ins.forEach((i) => i.addEventListener("input", run)); run();
  }

  /* ── Typed AI answer (case study) ───────────────── */
  $$("[data-type]").forEach((el) => {
    const text = el.dataset.type;
    if (reduce || !io) { el.textContent = text; return; }
    el.textContent = "";
    const o = new IntersectionObserver((en) => {
      if (!en[0].isIntersecting) return; o.disconnect();
      let n = 0; const s = () => { el.textContent = text.slice(0, ++n); if (n < text.length) setTimeout(s, 16); }; s();
    }, { threshold: .6 });
    o.observe(el);
  });

  $$("[data-year]").forEach((el) => (el.textContent = new Date().getFullYear()));
})();
