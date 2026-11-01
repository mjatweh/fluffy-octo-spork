# Automation website (LVNT AI)

Three pages, plain HTML/CSS/JS. No build step, nothing to install.

| File | What it is |
|---|---|
| `index.html` | Home: hero, "sound familiar?" checklist, cost calculator, services, before/after, case study, how it works, FAQ, booking |
| `services.html` | Ten services in detail, industries, tools we connect, process |
| `about.html` | Company story (no individual bios), values, fit check |
| `assets/config.js` | **The only file you normally edit**: email and Calendly link |
| `assets/styles.css`, `assets/main.js` | Design and animations |

## Turn on Calendly (2 minutes)

1. Sign up at https://calendly.com with `michael.atweh@lvnt.ai` and connect that calendar.
2. Create a 30-minute event called "Free automation call". Copy its link.
3. Paste it into `assets/config.js` → `calendlyUrl: "https://calendly.com/..."`.

Until then every "Book a call" button opens a pre-filled email to you, so nothing looks broken.

## See it on your computer

Double-click `index.html`, or run `python3 -m http.server` in this folder and open http://localhost:8000.

## Put it online

**GitHub Pages (free, already wired up):** repo Settings → Pages → Source: **GitHub Actions**. Every change merged to
`main` publishes automatically (`.github/workflows/website.yml`). Your address will be
`https://mjatweh.github.io/fluffy-octo-spork/`. To use your own domain (e.g. `lvnt.ai` or a new one), add it under
Settings → Pages → Custom domain and follow the DNS steps shown there.

**Netlify (alternative):** drag this folder onto https://app.netlify.com/drop.

## Changing things

- **Brand name**: search-and-replace `LVNT` across the three `.html` files.
- **Text**: edit the `.html` files directly; every section has a comment like `<!-- CASE STUDY -->`.
- **Colors**: top of `assets/styles.css` (`--orange`, `--blue`, `--sun`, ...).
- **Case study**: on the home page, anonymized ("an industrial finishing company in the Carolinas"). Get the client's OK before naming them, and add real numbers (hours saved, etc.) once you have them.
