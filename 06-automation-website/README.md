# TailorWired website

Black and neon-green, box-grid design. Three pages: `index.html` (home), `services.html`, `about.html`.
Plain HTML/CSS/JS: no install, no build needed to view it.

## Turn on Calendly (5 minutes)

1. Go to https://calendly.com/signup and choose **Sign up with Google** using your TailorWired email (or whichever Google account holds your calendar).
2. Connect that Google calendar when asked.
3. Create an event: **One-on-One**, name "TailorWired: Free AI Automation Call", **30 min**, location **Google Meet** (or phone).
4. Copy the event link (e.g. `https://calendly.com/tailorwired/30min`).
5. Paste it into `assets/config.js` → `calendlyUrl: "..."` and save/commit.

That's it: every "Book a call" button then opens Calendly in a pop-up, and the booking box at the bottom of each
page shows your live calendar in the site's colors. Until then, those buttons open a pre-filled email to you.

## Put it online at tailorwired.com

1. **Register the domain**: buy `tailorwired.com` at Cloudflare Registrar, Namecheap or GoDaddy (~$10-15/year).
2. **Turn on publishing**: repo Settings → Pages → Source: **GitHub Actions**, then merge this branch to `master`.
   The site goes live at `https://mjatweh.github.io/fluffy-octo-spork/` (`.github/workflows/website.yml`).
3. **Connect the domain**: Settings → Pages → Custom domain → `tailorwired.com` → Save. At your registrar, add the
   DNS records GitHub shows (four `A` records for `@` and a `CNAME` for `www` → `mjatweh.github.io`). Tick
   **Enforce HTTPS** once it appears (can take up to an hour).
4. **Email**: set up `michael@tailorwired.com` (Google Workspace, ~$7/month) and put it in `assets/config.js`.
   The site currently shows `michael.atweh@lvnt.ai` so booking emails still reach you.

Only the site files are published; `marketing/`, `_src/` and `.md` files stay in the repo.

## Editing

- Email and Calendly: `assets/config.js`.
- Colors: top of `assets/styles.css` (`--neon`, `--bg`).
- Text: the pages are generated from `_src/build.py` (shared header, footer and booking box). Edit the text there,
  then run `python3 _src/build.py .` from this folder. Small one-off text edits can also go straight into the `.html`.

## Marketing

`marketing/LAUNCH-PLAN.md` (strategy, channels, 30-day plan) and `marketing/LAUNCH-KIT.md` (ready-to-post copy).
