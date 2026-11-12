# Catch Up

An all-in-one learning platform and school management system for A-level and first and second year university students in Zambia.

- **Verified teachers only.** Teachers apply with their TCZ registration, degree and ID, and choose the subjects they specialise in. An admin approves them before they can publish or be paid.
- **Monthly subscriptions with mobile money.** Students pay per course per month (K80 by default) with MTN MoMo, Airtel Money or Zamtel Money through pawaPay. They type their PIN on the phone prompt and get an in-app notification and an email receipt.
- **A 50/50 split.** Every payment goes into a ledger. The payment fee comes off first, then the teacher gets 50% and the platform 50%. Courses published by platform admins keep 100% for the platform. Teacher payouts are batched monthly and paid to mobile money after an admin approves them.
- **A full teacher toolkit.** Teachers upload PowerPoint, Word, PDF, Excel, HTML and images. Word and PowerPoint files are also turned into a page that reads well on any phone. Teachers also get class groups, timetabled live sessions with meeting links, attendance registers and check-in codes, quizzes and problem sets with automatic marking, written work marked by hand, weighted gradebooks with CSV export, announcements, and booking requests for extra lessons.
- **Continuous assessment that gates progress.** A teacher can make an assessment required, or require a pass, before the next lesson opens.
- **Four portals:** students, parents, teachers and the admin control room. Each has its own sign-in page and dashboard. Parents link to a child with the child's invite code, follow their progress and attendance, get alerts, and can pay for their courses.
- **Schools and universities.** A school sets up its own space with join codes for teachers and students, private courses, timetables, registers and a school dashboard.
- **Data science in the services layer** (`apps/analytics/services.py`, numpy only):
  - Dropout-risk scoring with logistic regression. The model is retrained nightly and only saved when it beats chance on held-out data.
  - Course recommendations from collaborative filtering combined with level and subject matching.
  - Revenue forecasting with Holt's linear trend and an 80% band.
  - Detection of unusual payment activity.
  - A study coach that writes plain-language tips.
- **Front end:** server-rendered Django templates with CSS, plus small TypeScript "islands" (charts, tabs, payment polling, timers, uploads with progress, network detection). On phones there is a LinkedIn-style bottom navigation bar and book-style course covers, and animations are gentle and respect reduced-motion settings.

---

## Run it on Windows with VS Code

You need Python 3.12 or newer. Node 20 or newer is only needed if you change the TypeScript.

```powershell
cd catchup
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py seed_catchup        # subjects, verified placeholder teachers, 6 courses
python manage.py seed_demo           # optional: demo students, parents, payments, classes, grades
python manage.py createsuperuser     # your own admin
python manage.py runserver
```

Open http://localhost:8000. In VS Code, pick the `.venv` interpreter, then press F5 ("Django: runserver"). On macOS or Linux, use `python3 -m venv .venv` and `source .venv/bin/activate`.

**Demo accounts** (after `seed_demo`; the password is `CatchUp-demo-2026`, or whatever you set in `DEMO_PASSWORD`):

| Portal | Email |
|---|---|
| Student | student@demo.catchup |
| Parent | parent@demo.catchup |
| School admin | school@demo.catchup |
| Teacher | mwila.banda@catchup.example (password is `SEED_ACCOUNT_PASSWORD`, or the one printed by `seed_catchup`) |
| Admin control room | admin@catchup.example (same) |

The demo runs in payment simulator mode. A "Demo phone" panel on the payment page stands in for the prompt on the customer's phone, and phone numbers ending in 13 are rejected so you can see the failure path.

### TypeScript front end

The compiled `static/js/app.js` is committed, so you don't need Node to run or deploy the site. To change the TypeScript:

```powershell
cd frontend
npm install
npm run watch     # rebuilds on save; or: npm run build  (type-checks, then builds minified)
npm run katex     # only if you upgrade KaTeX: copies maths fonts into static/vendor/katex
```

The source is in `frontend/src/`: `main.ts` (page behaviour), `charts.ts` (dependency-free SVG charts) and `types.ts` (the API shapes, which mirror `apps/analytics/api.py`).

### Tests

```powershell
python manage.py test
```

There are 50 tests. They cover:
- the money split and that a payment is never counted twice
- monthly access and renewals
- parents linking to a child and paying for them
- teacher verification gating
- upload validation, including disguised files
- assessment auto-marking and lesson gating
- tutor marking and the gradebook
- attendance check-in
- school sign-up and join codes
- portal role checks
- a sweep that renders every page as every kind of user

---

## Deploy on Render

1. Push this folder to a GitHub repository. `.gitignore` already leaves out `.env`, `db.sqlite3`, `media/` and `node_modules`.
2. In Render, choose **New > Blueprint**, pick the repository, and Render reads `render.yaml`. It creates:
   - the web service, with a 5 GB disk at `/var/data` for uploads
   - a Postgres database
   - a shared settings group
   - four cron jobs: class and renewal reminders every 15 minutes, settling pending payments every 10 minutes, nightly model training, and monthly payout batches
3. Fill in the values Render asks for:
   - `SITE_URL`: your Render URL or your own domain
   - `DJANGO_SUPERUSER_EMAIL` and `DJANGO_SUPERUSER_PASSWORD`: your admin account
   - `SEED_ACCOUNT_PASSWORD`
   - the email settings (for Gmail: `smtp.gmail.com`, port 587, your address and a Google **App Password**)
4. Deploy. `build.sh` installs packages, collects static files, migrates, adds the starter catalogue, creates your admin and runs Django's deployment checks.
5. Sign in at `/control/login/` with your admin account.

**Going live with real money:**
1. Open a pawaPay merchant account and test it in their sandbox.
2. Set `PAYMENT_PROVIDER=pawapay`, `PAWAPAY_API_TOKEN=...`, and `PAYMENT_FEE_PERCENT` to your contracted fee.
3. Remove `ALLOW_PAYMENT_SIMULATOR`, and set `PAWAPAY_SANDBOX=false` when you're approved.
4. In the pawaPay dashboard, set the callback URL to `https://YOUR-DOMAIN/payments/callback/pawapay/`.

Never run `seed_demo` on the live database. It refuses to run unless `DEBUG` is on.

**Uploads.** The Render disk works out of the box. If you outgrow it, set the `AWS_*` variables for S3 or Cloudflare R2 and uploads go there instead.

---

## How the money works

| Step | Example: K80 subscription, 3% fee |
|---|---|
| Student approves on the phone | K80.00 received |
| Payment fee | K2.40 |
| Teacher (50% of the rest, rounded down to the ngwee) | K38.80 |
| Platform | K38.80 |

The ledger stores amounts in ngwee (integers), so totals always add up exactly. Teachers see their balance on the **Earnings** page. On the 1st of each month, `create_payouts` prepares payouts for balances above `PAYOUT_MINIMUM`. An admin approves them in the Django admin, and they're sent to the teacher's mobile money number.

## Project layout

```
apps/
  accounts/     users, roles (student, parent, tutor, admin), tutor verification, parent links
  courses/      courses, modules, lessons, uploaded materials (docx/pptx/pdf/html), monthly access
  payments/     mobile money checkout, pawaPay and simulator providers, callbacks
  ledger/       50/50 split, tutor earnings, monthly payouts
  classroom/    class groups, sessions, attendance, assessments, marking, gradebook, bookings
  schools/      schools and universities, join codes, school dashboard
  portal/       the four sign-in portals, parent and admin dashboards, tutor directory
  analytics/    machine learning and data science (services.py), JSON API for the dashboards
  notifications/ in-app notifications and email
  core/         home, dashboards, pages, seed commands
frontend/       TypeScript source (builds to static/js/app.js)
templates/      Django templates
static/         CSS, compiled JS, images, KaTeX
```

## Settings reference

Every setting is an environment variable; see `.env.example`. The most important ones:

| Variable | Default | Meaning |
|---|---|---|
| `COURSE_PRICE_ZMW` | 80.00 | Default monthly price for new courses |
| `MIN_COURSE_PRICE` / `MAX_COURSE_PRICE` | 50 / 500 | Range teachers can set |
| `ACCESS_PERIOD_DAYS` | 30 | Days of access each payment adds |
| `RENEWAL_WINDOW_DAYS` | 7 | How early a student can renew |
| `TUTOR_SHARE_PERCENT` | 50 | Teacher share after fees |
| `PAYMENT_FEE_PERCENT` | 0 | Payment provider fee, taken first |
| `PAYOUT_MINIMUM` | 100 | Smallest balance paid out monthly |
