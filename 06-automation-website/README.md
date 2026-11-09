# LVNT AI website

Black and neon-green, box-grid design. Three pages: `index.html` (home), `services.html`, `about.html`.
Plain HTML/CSS/JS: no install, no build needed to view it.

## Turn on Calendly (5 minutes)

1. Go to https://calendly.com/signup and choose **Sign up with Google** using `michael.atweh@lvnt.ai`.
2. Connect that Google calendar when asked.
3. Create an event: **One-on-One**, name "AI Automation Call", **30 min**, location **Google Meet** (or phone).
4. Copy the event link (e.g. `https://calendly.com/michael-atweh/ai-automation-call`).
5. Paste it into `assets/config.js` → `calendlyUrl: "..."` and save/commit.

That's it: every "Book a call" button then opens Calendly in a pop-up, and the booking box at the bottom of each
page shows your live calendar in the site's colors. Until then, those buttons open a pre-filled email to you.

## Put it online

Repo **Settings → Pages → Source: GitHub Actions**, then merge to `master`. It publishes automatically
(`.github/workflows/website.yml`) to `https://mjatweh.github.io/fluffy-octo-spork/`. Add your own domain under
Settings → Pages → Custom domain.

## Editing

- Email and Calendly: `assets/config.js`.
- Colors: top of `assets/styles.css` (`--neon`, `--bg`).
- Text: the pages are generated from `_src/build.py` (shared header, footer and booking box). Edit the text there,
  then run `python3 _src/build.py .` from this folder. Small one-off text edits can also go straight into the `.html`.
