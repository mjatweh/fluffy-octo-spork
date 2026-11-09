# Builds the three pages from shared header/footer so they stay in sync.
import sys, pathlib
OUT = pathlib.Path(sys.argv[1])
I = lambda d: f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{d}</svg>'
ICON = {
 "money": I('<rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/><path d="M6 10v4M18 10v4"/>'),
 "link": I('<path d="M10 14a4 4 0 0 0 5.66 0l3-3a4 4 0 0 0-5.66-5.66l-1 1"/><path d="M14 10a4 4 0 0 0-5.66 0l-3 3a4 4 0 0 0 5.66 5.66l1-1"/>'),
 "chat": I('<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12Z"/><path d="M8 11h.01M12 11h.01M16 11h.01"/>'),
 "doc": I('<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>'),
 "mail": I('<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>'),
 "chart": I('<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>'),
 "bot": I('<rect x="4" y="8" width="16" height="12" rx="3"/><path d="M12 4v4M9 14h.01M15 14h.01M2 13v2M22 13v2"/>'),
 "cog": I('<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z"/>'),
 "puzzle": I('<path d="M4 7h3a2 2 0 1 1 4 0h3v3a2 2 0 1 1 0 4v3h-3a2 2 0 1 0-4 0H4v-3a2 2 0 1 0 0-4Z"/>'),
 "shield": I('<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6Z"/><path d="m9 12 2 2 4-4"/>'),
 "cal": I('<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>'),
}
TOOLS = ["QuickBooks Desktop","QuickBooks Online","Microsoft 365","Outlook","Excel","Gmail","Google Workspace","Sage","Xero","Salesforce","HubSpot","Slack","Teams","Shopify","DocuSign","SharePoint","Dropbox","Custom APIs","Legacy software"]

def head(title, desc, cur):
    nav = "".join(f'<a href="{h}"{" aria-current=\"page\"" if h==cur else ""}>{t}</a>' for h,t in [("index.html","Home"),("services.html","Services"),("about.html","About")])
    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <meta name="description" content="{desc}">
  <meta property="og:title" content="{title}">
  <meta property="og:description" content="{desc}">
  <meta property="og:type" content="website">
  <meta name="theme-color" content="#050505">
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='16' fill='%2339ff14'/%3E%3Crect x='22' y='22' width='20' height='20' rx='5' fill='%23000'/%3E%3C/svg%3E">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Unbounded:wght@700;800&family=Inter:wght@400;600;700;800&family=JetBrains+Mono:wght@400;600;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="assets/styles.css">
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="site-header">
  <div class="wrap">
    <a class="logo" href="index.html"><span class="logo-mark"><i></i></span><span>LVNT<span class="neon">.AI</span></span></a>
    <button class="nav-toggle" aria-label="Menu" aria-expanded="false"><span></span><span></span><span></span></button>
    <nav class="nav" aria-label="Main">{nav}<a class="btn" href="#book" data-book>Book a call</a></nav>
  </div>
</header>
<main id="main">
'''

BOOK = '''
<section id="book">
  <div class="wrap">
    <div class="book-grid">
      <div class="box reveal">
        <span class="tag"><span class="dot"></span>Free 30-minute call</span>
        <h2>Let's build <span class="glow">your</span> automation.</h2>
        <p style="font-size:1.08rem">Tell us how your business runs. We'll show you what to automate first and how we'd build it for you. No obligation, no jargon.</p>
        <ul class="agenda">
          <li><span class="t">00:00</span><span>How your business runs today</span></li>
          <li><span class="t">00:10</span><span>Where the hours go, and what AI can take over</span></li>
          <li><span class="t">00:25</span><span>A clear next step, built around you</span></li>
        </ul>
      </div>
      <div class="box cal reveal d1" id="cal"></div>
    </div>
  </div>
</section>
</main>
'''

def foot():
    return '''
<footer class="site-footer">
  <div class="wrap foot">
    <a class="logo" href="index.html"><span class="logo-mark"><i></i></span><span>LVNT<span class="neon">.AI</span></span></a>
    <nav aria-label="Footer"><a href="index.html">Home</a><a href="services.html">Services</a><a href="about.html">About</a><a href="#book" data-book>Book a call</a><a data-email href="#">email</a></nav>
    <span class="mono" style="font-size:.85rem">© <span data-year></span> LVNT AI · Custom AI automation</span>
  </div>
</footer>
<div class="sticky-cta"><a class="btn btn-lg" href="#book" data-book>Book a free call <span class="arr">→</span></a></div>
<script src="assets/config.js"></script>
<script src="assets/main.js"></script>
</body>
</html>
'''

def marquee():
    chips = "".join(f'<span class="chip"><b>+</b> {t}</span>' for t in TOOLS)
    return f'<div class="marquee" aria-label="Systems we connect to"><div class="marquee-track">{chips}{chips}</div></div>'

def page(name, title, desc, body):
    (OUT / name).write_text(head(title, desc, name) + body + BOOK + foot())

# ───────── HOME ─────────
home = f'''
<section class="hero">
  <div class="wrap">
    <span class="tag"><span class="dot"></span>AI automation · built to fit you</span>
    <h1><span class="line"><span>AI automation</span></span><span class="line"><span>built around</span></span><span class="line"><span class="glow">your business.</span></span></h1>
    <p class="lead">Automate your <span class="typed mono" data-words="invoices|data entry|inbox|reports|follow-ups|paperwork|scheduling"></span><br>
      Every company runs differently, so we don't sell one-size-fits-all software. <b>We design, build and run AI automations around your exact workflows and the systems you already use.</b></p>
    <div class="ctas">
      <a class="btn btn-lg" href="#book" data-book>Book a free call <span class="arr">→</span></a>
      <a class="btn btn-ghost btn-lg" href="#build">Build your automation</a>
    </div>
    <ul class="hero-meta"><li>Custom-built, never off-the-shelf</li><li>Works with your current software</li><li>Live in weeks, not months</li></ul>

    <div class="bento" style="margin-top:64px">
      <div class="box s7 term reveal">
        <div class="term-head"><i></i><i></i><i></i><span>automation.run · live</span></div>
        <div class="term-lines">
          <div class="cmd">$ run invoice-automation --client=yours</div>
          <div>→ 14 new emails with invoices found</div>
          <div>→ reading PDFs · extracting vendor, amount, due date</div>
          <div>→ matching to purchase orders</div>
          <div>→ posting drafts to QuickBooks</div>
          <div class="ok">✓ 14 bills ready for one-click approval</div>
          <div class="ok">✓ weekly cash report sent to owner</div>
          <div class="cmd">$ <span class="typed-static">idle · next run 07:00</span></div>
        </div>
      </div>
      <div class="box s5 reveal d1">
        <span class="k">// how it connects</span>
        <h3>Your systems in. Finished work out.</h3>
        <p>We connect AI to the tools you already run on and let it do the repetitive part.</p>
        <div class="flow"><div class="node">Email</div><div class="wire"></div><div class="node ai">AI</div><div class="wire"></div><div class="node">QuickBooks</div></div>
        <div class="flow"><div class="node">PDFs</div><div class="wire"></div><div class="node ai">AI</div><div class="wire"></div><div class="node">CRM</div></div>
      </div>
    </div>
  </div>
</section>

{marquee()}

<section>
  <div class="wrap">
    <div class="head reveal">
      <span class="tag"><span class="dot"></span>What we automate</span>
      <h2>If it's repetitive, <span class="glow">it's automatable.</span></h2>
      <p>Every automation is designed for your business: your rules, your systems, your way of working.</p>
    </div>
    <div class="bento">
      <a class="box s6 reveal" href="services.html#finance" style="text-decoration:none"><div class="ico">{ICON["money"]}</div><span class="k">01 · finance &amp; back office</span><h3>Invoices, bills, collections and month-end, on autopilot.</h3><p>Bills read and posted to QuickBooks or Sage, payment reminders sent on schedule, books always current.</p></a>
      <a class="box s3 reveal d1" href="services.html#integration" style="text-decoration:none"><div class="ico">{ICON["link"]}</div><span class="k">02 · integration</span><h3>Systems that finally talk.</h3><p>Type it once. It shows up everywhere.</p></a>
      <a class="box s3 reveal d2" href="services.html#assistant" style="text-decoration:none"><div class="ico">{ICON["chat"]}</div><span class="k">03 · AI assistant</span><h3>Ask your data anything.</h3><p>Answers from your own numbers in seconds.</p></a>
      <a class="box s3 reveal" href="services.html#documents" style="text-decoration:none"><div class="ico">{ICON["doc"]}</div><span class="k">04 · documents</span><h3>Paperwork, processed.</h3><p>POs, contracts and forms read and filed.</p></a>
      <a class="box s3 reveal d1" href="services.html#inbox" style="text-decoration:none"><div class="ico">{ICON["mail"]}</div><span class="k">05 · inbox</span><h3>An inbox that sorts itself.</h3><p>Sorted, drafted, followed up.</p></a>
      <a class="box s6 reveal d2" href="services.html#agents" style="text-decoration:none"><div class="ico">{ICON["bot"]}</div><span class="k">06 · custom AI agents</span><h3>Digital team members for the jobs nobody wants.</h3><p>AI agents that follow your rules, do the work and ask a person before anything important.</p></a>
      <a class="box s4 reveal" href="services.html#sales" style="text-decoration:none"><div class="ico">{ICON["chart"]}</div><span class="k">07 · sales &amp; reporting</span><h3>Quotes out faster. Reports that build themselves.</h3></a>
      <a class="box s4 reveal d1" href="services.html#operations" style="text-decoration:none"><div class="ico">{ICON["cal"]}</div><span class="k">08 · operations</span><h3>Scheduling, inventory and job tracking, handled.</h3></a>
      <div class="box s4 neon-box reveal d2"><span class="k">// not on the list?</span><h3>We build it anyway.</h3><p>Most of our work is something nobody sells off the shelf.</p><a class="btn" href="#book" data-book>Tell us about it <span class="arr">→</span></a></div>
    </div>
  </div>
</section>

<section id="build">
  <div class="wrap">
    <div class="head reveal">
      <span class="tag"><span class="dot"></span>Customizable by design</span>
      <h2>Build <span class="glow">your</span> automation.</h2>
      <p>Pick the systems you use and the work you want gone. This is how every project starts: with your business, not our product.</p>
    </div>
    <div class="builder">
      <div class="box reveal">
        <span class="step-label">Step 1 · your systems</span>
        <div class="opts" data-group="sys">
          <button class="opt" aria-pressed="true">QuickBooks</button><button class="opt" aria-pressed="false">Sage</button><button class="opt" aria-pressed="false">Excel</button><button class="opt" aria-pressed="true">Outlook</button><button class="opt" aria-pressed="false">Gmail</button><button class="opt" aria-pressed="false">Salesforce</button><button class="opt" aria-pressed="false">HubSpot</button><button class="opt" aria-pressed="false">Shopify</button><button class="opt" aria-pressed="false">Industry software</button>
        </div>
        <span class="step-label">Step 2 · work to automate</span>
        <div class="opts" data-group="task">
          <button class="opt" aria-pressed="true">Invoices &amp; bills</button><button class="opt" aria-pressed="false">Data entry</button><button class="opt" aria-pressed="false">Email &amp; inbox</button><button class="opt" aria-pressed="true">Reports</button><button class="opt" aria-pressed="false">Quotes &amp; sales</button><button class="opt" aria-pressed="false">Collections</button><button class="opt" aria-pressed="false">Documents</button><button class="opt" aria-pressed="false">Scheduling</button>
        </div>
      </div>
      <div class="box blueprint reveal d1" aria-live="polite">
        <span class="step-label">Your automation plan · <span data-bp-count>0</span> workflows</span>
        <div class="bp-title">Custom-built for your business</div>
        <ul class="bp-list"></ul>
        <a class="btn" href="#book" data-book data-bp-cta>Book a call to build this <span class="arr">→</span></a>
      </div>
    </div>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="head reveal">
      <span class="tag"><span class="dot"></span>Why custom</span>
      <h2>Off-the-shelf makes you change. <span class="glow">Custom fits.</span></h2>
    </div>
    <div class="bento">
      <div class="box s6 reveal"><span class="k">// off-the-shelf software</span><h3>You adapt to the tool.</h3>
        <ul class="ticks bad"><li>Switch systems and migrate years of data</li><li>Retrain the whole team</li><li>Pay for features you'll never use</li><li>Still miss the steps that make you different</li></ul></div>
      <div class="box s6 neon-box reveal d1"><span class="k">// LVNT custom automation</span><h3>The automation adapts to you.</h3>
        <ul class="ticks"><li>Built on the systems you already have</li><li>Your team keeps working the way they know</li><li>Designed around your exact rules and steps</li><li>Grows with you, one workflow at a time</li></ul></div>
    </div>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="head reveal">
      <span class="tag"><span class="dot"></span>Proof</span>
      <h2>Told to switch systems. <span class="glow">They didn't.</span></h2>
    </div>
    <div class="bento">
      <div class="box s7 reveal">
        <span class="k">// case study · manufacturing · carolinas</span>
        <h3>An established industrial finishing company wanted AI on its books.</h3>
        <p>Their IT provider said the only route was a costly move from QuickBooks Desktop to QuickBooks Online, losing features and retraining the office. We built a custom connection to the system they already had instead. No migration. No new subscription.</p>
        <div class="ask"><div class="q">Which customers are more than 60 days past due?</div><div class="a" data-type="Here are the customers over 60 days, sorted by amount owed, with the oldest invoice for each. Want me to draft reminder emails?"></div></div>
      </div>
      <div class="box s5 calc reveal d1" id="cost">
        <span class="k">// what manual work costs you</span>
        <div class="field"><label for="people">People on admin work <output for="people"></output></label><input type="range" id="people" name="people" min="1" max="50" value="5"></div>
        <div class="field"><label for="hours">Hours each per week on repetitive tasks <output for="hours"></output></label><input type="range" id="hours" name="hours" min="1" max="30" value="8" data-suf=" h"></div>
        <div class="field"><label for="rate">Cost per hour <output for="rate"></output></label><input type="range" id="rate" name="rate" min="15" max="120" value="35" data-pre="$"></div>
        <div class="big glow" data-money>$0</div>
        <p style="margin:0">a year · <span data-hours>0</span> hours of your team's time. Your inputs, your math.</p>
      </div>
    </div>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="head reveal">
      <span class="tag"><span class="dot"></span>How it works</span>
      <h2>From call to <span class="glow">live automation.</span></h2>
    </div>
    <div class="steps">
      <div class="box reveal"><h3>Discovery call</h3><p>30 minutes, free. We learn how you work and where the hours go.</p></div>
      <div class="box reveal d1"><h3>Custom blueprint</h3><p>A written plan for your business: what we'll automate, how, and a fixed price.</p></div>
      <div class="box reveal d2"><h3>Build &amp; connect</h3><p>We build it on your systems while your business keeps running.</p></div>
      <div class="box reveal d3"><h3>Run &amp; improve</h3><p>We train your team, monitor it and keep adding what you need next.</p></div>
    </div>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="head center reveal"><span class="tag"><span class="dot"></span>FAQ</span><h2>Quick answers.</h2></div>
    <div class="faq reveal d1">
      <details><summary>What exactly does "custom" mean?</summary><div class="ans">We don't resell a fixed product. We map how your business actually works, then design and build automations around your steps, your rules and your software. Two clients never get the same build.</div></details>
      <details><summary>Do we have to replace our software?</summary><div class="ans">Almost never. We build on what you already use, including older desktop programs like QuickBooks Desktop.</div></details>
      <details><summary>What does it cost?</summary><div class="ans">It depends on what we build, so after the free call you get a written blueprint with a fixed price per workflow. You choose what to go ahead with.</div></details>
      <details><summary>How fast is it live?</summary><div class="ans">Usually within a few weeks of agreeing the blueprint. We ship one workflow at a time so you see results early.</div></details>
      <details><summary>Is our data safe?</summary><div class="ans">Each automation only gets the access it needs, you can see everything that runs, and anything that sends money or messages customers can require a person's approval.</div></details>
    </div>
  </div>
</section>
'''
page("index.html", "LVNT AI | Custom AI Automation for Your Business",
     "Custom AI automation built around your business and the systems you already use. Invoices, data entry, inbox, reports, documents and more. Book a free call.", home)

# ───────── SERVICES ─────────
def svc(id_, ico, k, title, hook, does, ex, span="s12", cls=""):
    items = "".join(f"<li>{d}</li>" for d in does)
    return f'''<div class="box {span} {cls} reveal" id="{id_}" style="scroll-margin-top:90px">
  <div class="ico">{ICON[ico]}</div><span class="k">{k}</span><h3>{title}</h3><p>{hook}</p>
  <ul class="ticks" style="margin-bottom:18px">{items}</ul>
  <p class="mono" style="font-size:.85rem;margin:0"><span class="neon">example ›</span> {ex}</p></div>'''

services = f'''
<section class="page-hero">
  <div class="wrap">
    <span class="tag"><span class="dot"></span>Services</span>
    <h1>Every automation, <span class="glow">built for you.</span></h1>
    <p class="lead" style="color:var(--muted);font-size:1.2rem;max-width:60ch">We design, build and run custom AI automations and integrations. Pick a starting point below, or bring us the task you'd love to never do again.</p>
    <div class="ctas" style="margin-top:28px"><a class="btn btn-lg" href="#book" data-book>Book a free call <span class="arr">→</span></a></div>
  </div>
</section>
{marquee()}
<section>
  <div class="wrap">
    <div class="bento">
      {svc("finance","money","01 · finance & back office","Finance and accounting automation","Your books, always current, without the typing.",["Bills and receipts read and posted to QuickBooks, Sage or Xero","Invoices created and sent automatically","Payment reminders on your schedule","Month-end and cash reports, built for you"],"A supplier emails an invoice; it's coded, matched to the PO and waiting for one-click approval.","s6")}
      {svc("integration","link","02 · systems integration","Connect everything","Your tools, finally working as one system.",["Two-way sync between accounting, CRM, email and spreadsheets","Legacy and desktop software included","One source of truth for customers, jobs and money","No rip-and-replace"],"A new order creates the customer, the job and the invoice draft, with zero retyping.","s6")}
      {svc("assistant","chat","03 · AI assistant","Your own AI assistant","Ask your business a question. Get the answer.",["Trained on your accounts, documents and processes","Plain-English answers with sources","Access controls by person and role"],"“How did October compare to last year?”","s4")}
      {svc("documents","doc","04 · documents","Document processing","Stop retyping what's already on the page.",["POs, contracts, forms and statements read automatically","Details sent to the right system","Unusual items flagged for review"],"A PDF purchase order becomes a sales order in seconds.","s4")}
      {svc("inbox","mail","05 · email & inbox","Inbox automation","Every email sorted, answered or routed.",["Sorting by customer, job and urgency","Drafted replies for you to approve","Attachments filed automatically"],"A daily summary of what actually needs you.","s4")}
      {svc("sales","chart","06 · sales & reporting","Quotes, follow-up and reporting","Win faster. Know your numbers.",["Quote drafts from your price list and past jobs","Automatic follow-ups until customers reply","Dashboards and weekly reports in plain English"],"Every Monday 7am: cash, sales, overdue and open jobs.","s6")}
      {svc("operations","cal","07 · operations","Operations automation","Scheduling, inventory and jobs, handled.",["Bookings, confirmations and reminders","Low-stock alerts and draft purchase orders","Job status updates without phone calls"],"Stock dips below minimum; a PO is drafted for your approval.","s6")}
      {svc("agents","bot","08 · custom AI agents","Custom AI agents","A digital worker for your specific job.",["Built to your rules and checklists","Research, screening, drafting and checking","Human approval before anything important","Every action logged"],"Each morning an agent screens new opportunities and sends the top three.","s8")}
      <div class="box s4 neon-box reveal"><span class="k">// support</span><h3>Training &amp; ongoing support</h3><p>We train your team, monitor every automation and keep improving it as your business changes.</p><a class="btn" href="#book" data-book>Start with a call <span class="arr">→</span></a></div>
    </div>
  </div>
</section>
<section>
  <div class="wrap">
    <div class="head reveal"><span class="tag"><span class="dot"></span>Industries</span><h2>Built for how <span class="glow">you</span> work.</h2></div>
    <div class="bento">
      <div class="box s3 reveal"><span class="k">manufacturing</span><h3>Orders, purchasing, job costing</h3></div>
      <div class="box s3 reveal d1"><span class="k">construction &amp; trades</span><h3>Estimates, scheduling, billing</h3></div>
      <div class="box s3 reveal d2"><span class="k">real estate</span><h3>Leases, rent roll, owner reports</h3></div>
      <div class="box s3 reveal d3"><span class="k">distribution</span><h3>Order entry, stock, collections</h3></div>
      <div class="box s3 reveal"><span class="k">hospitality</span><h3>Bookings, vendors, daily reports</h3></div>
      <div class="box s3 reveal d1"><span class="k">professional services</span><h3>Intake, documents, invoicing</h3></div>
      <div class="box s3 reveal d2"><span class="k">family offices</span><h3>Statements and consolidated reporting</h3></div>
      <div class="box s3 neon-box reveal d3"><span class="k">yours</span><h3>If it's repetitive, we can build it.</h3></div>
    </div>
  </div>
</section>
'''
page("services.html", "Services | LVNT AI Custom Automation",
     "Custom AI automation and integration: finance, systems integration, AI assistants, documents, inbox, sales, reporting, operations and custom AI agents.", services)

# ───────── ABOUT ─────────
about = f'''
<section class="page-hero">
  <div class="wrap">
    <span class="tag"><span class="dot"></span>About</span>
    <h1>We build AI that <span class="glow">fits the business.</span></h1>
    <p class="lead" style="color:var(--muted);font-size:1.2rem;max-width:60ch">LVNT AI is a team of operators and engineers. We design and build custom AI automations for companies that want the benefits of AI without changing how they run.</p>
  </div>
</section>
<section style="padding-top:20px">
  <div class="wrap">
    <div class="bento">
      <div class="box s7 reveal"><span class="k">// our story</span><h3>Built inside real businesses first.</h3>
        <p>We started by automating operations inside a group of companies across manufacturing, real estate, hospitality and technology. Every one of them ran differently, and every vendor said the same thing: switch your systems.</p>
        <p>So we did the opposite: kept the systems people trusted, connected them, and put AI on the repetitive work in between. That approach became LVNT AI.</p></div>
      <div class="box s5 neon-box reveal d1"><span class="k">// our belief</span><h2 style="font-size:clamp(1.8rem,3.4vw,2.8rem)">Technology should fit your business. Not the other way around.</h2></div>
      <div class="box s4 reveal"><div class="ico">{ICON["puzzle"]}</div><h3>Custom, always</h3><p>No templates. Every build starts from how you actually work.</p></div>
      <div class="box s4 reveal d1"><div class="ico">{ICON["link"]}</div><h3>Your systems stay</h3><p>We connect to what you already run before suggesting anything new.</p></div>
      <div class="box s4 reveal d2"><div class="ico">{ICON["shield"]}</div><h3>You stay in control</h3><p>Clear access, full visibility and human approval where it matters.</p></div>
      <div class="box s4 reveal"><div class="ico">{ICON["cog"]}</div><h3>Small steps, fast</h3><p>One workflow live at a time, so you see results in weeks.</p></div>
      <div class="box s4 reveal d1"><div class="ico">{ICON["chat"]}</div><h3>Plain language</h3><p>No jargon. If we can't explain it simply, we won't build it.</p></div>
      <div class="box s4 reveal d2"><div class="ico">{ICON["bot"]}</div><h3>We stay on</h3><p>Monitoring, support and improvements after go-live.</p></div>
    </div>
  </div>
</section>
<section class="cta-band">
  <div class="wrap">
    <h2>Your business. <span class="glow">Automated.</span></h2>
    <p>One call to see what we'd build for you.</p>
    <a class="btn btn-lg" href="#book" data-book>Book a free call <span class="arr">→</span></a>
  </div>
</section>
'''
page("about.html", "About | LVNT AI", "LVNT AI designs and builds custom AI automations that fit how your business already works.", about)
print("built")
