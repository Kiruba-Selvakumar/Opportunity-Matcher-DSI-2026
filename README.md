# Opportunity Matcher

Students from tier 2 and tier 3 engineering colleges often get little help with placements. An NGO, Barabari Collective, helps them find jobs, training and mentors, but staff match students by hand. This tool ranks the top 5 opportunities for each student using both their skills and their real situation (town, budget, family limits), and explains each match in one line. All data is synthetic for Hackathon 1.

## Architecture blocks

| Block | Name | What it does |
|---|---|---|
| B1 | Data collection | Makes fake raw students and opportunities |
| B2 | Clean and structure | Cleans raw data, parses messy text, checks the schema, splits out personal details |
| B3 | Skill mapping | Maps skill words to a fixed skill list and builds vectors |
| B4 | Matching engine | Scores every pair, applies hard filters and soft penalties |
| B5 | Rank and explain | Picks the top 5 per student and writes a reason for each |
| B6 | Web app | React app with three separate areas (NGO, student, employer), a FastAPI backend, stored resumes with ATS scores, interviews with Meet links and notes, email and WhatsApp, messages, and a SQLite log of decisions |
| Eval | Testing and demo | Keyword baseline, precision at 5, the end to end run |

## Setup

You need Python 3.10 or newer and Node 20.19 or newer.

```bash
make install     # Python packages into .venv, then npm install in web/
make all         # generate data, clean, vectors, score, rank, explain (offline, no keys)
make app         # API on http://localhost:8000 and web app on http://localhost:5173
make test        # pytest
make eval        # label sheet, then precision at 5 and the other metrics
```

`make all` works with no internet and no API keys. If the MiniLM model cannot be downloaded, it falls back to TF-IDF vectors. Use `EMBEDDINGS=tfidf` to force this.

For a containerized test run, copy `.env.example` to `.env`, set `DEMO_PASSWORD`, and leave
`RUN_PIPELINE=1`, `SEED_DEMO=1`, and `SEED_OUTCOMES=1` enabled. Then run:

```bash
docker build -t opportunity-matcher .
docker compose up --build
```

`docker build` only builds the image. `docker compose up --build` builds the image and starts
the application with the runtime environment and persistent `matcher-data` volume. The `.env`
file is loaded at runtime by Compose; it is not copied into the image, is excluded from Git and
the Docker build context, and must never be committed or published. Commit only the
`.env.example` template.

The Docker image is intentionally demo-only: it enables `DEMO_LOGIN`, uses the sample data,
seeds demo accounts and outcomes, and uses the demo password (`secure-demo-2026` unless overridden by
`.env`). Do not use this image or its persistent volume for production data. The Docker Compose
configuration enforces demo mode even if `.env` contains production-style values.

If `DEMO_PASSWORD` is empty or missing, Compose uses `secure-demo-2026` automatically. Any
custom demo password must be at least 10 characters.

The demo container is available at [http://localhost:8010](http://localhost:8010). Google OAuth
uses `http://localhost:8010/api/integrations/google/callback` by default. Add that exact URL to
the Google Cloud OAuth client's authorized redirect URIs, and set `GOOGLE_CLIENT_ID` and
`GOOGLE_CLIENT_SECRET` in the local `.env`. You can override `APP_URL`, `API_URL`, and
`GOOGLE_REDIRECT_URI` in `.env` when using a different local address.

## How matching works

A match is first filtered by hard checks (can the student move there, afford it, speak the language, and does it break a family limit). What is left is scored from 0 to 1:

- **Skills.** Rarer skills count for more, and a skill the employer marks "is a plus" counts half. A close skill counts partly, for example MySQL for SQL (the list is in `data/reference/related_skills.csv`).
- **Small nudges**, each capped: a branch that fits the kind of job, staying in the home state, a low CGPA for a job, long hours, low safety.
- **A fair spread.** When far more students are in play for a listing than it has openings, its score drops a little. A listing that is full closes.
- **What staff accepted.** With at least 5 decisions for a kind of job, a tiny capped nudge of at most 0.03.
- **Training by what it teaches.** A training listing scores by how much of the student's skill gap (what their best jobs ask for and they lack) it closes, so it is recommended for what it adds, not for being short and easy to match.
- **Soft skills stay out of similarity.** "English Communication" and certificates are shared by almost everyone, so they count in coverage but not in how alike two profiles look.
- **Only real fits.** A match below 0.20 is not shown. A student may see fewer than 5 matches, and the page says why.
- **Close the gap.** A job match with missing skills suggests the training or mentor listings that teach them.
- **Within easy reach.** Between two jobs that fit about as well, the one whose missing skills are easy to learn (the student knows a close skill, or an open training teaches it) ranks a little higher, by at most 0.05.
- **Where the student stands.** Each job ranks every student it fits. A student sees "3rd of 40", and is steered a little (at most ±0.03) toward jobs where they stand out.
- **Learned from outcomes.** Once there are 20 staff decisions and employer outcomes (shortlisted, hired, not a fit), a small model learns which kinds of match work and nudges similar ones by at most ±0.06. Settings shows what it has learned.
- **Which one is better?** A student's page puts the top matches side by side and marks the best value in each row.
- **Learning plan.** Upcoming trainings, in date order, that teach what the student's best jobs ask for, with how much each one lifts each job. A mentor appears only for what no course they can take teaches.

Every part can be switched off in `src/matcher/config.py` (`V2` and `V3`), and staff can open "How this score was made" on any match to see each line. There is no ground truth yet, so `make eval` compares the old and new scores and says plainly when it has no human-reviewed labels to judge them with.

## Accounts and the three areas

Everyone signs in at `/login` with a username and password. The NGO admin makes the accounts. Each role then lands in its own area and can reach nothing else. The server checks this on every call, not only the web app.

| Role | Lands on | What they can do |
|---|---|---|
| NGO admin | `/ngo` | The gate. Everything staff can do, plus: approve, reject, post, edit and close listings (jobs, training and mentors); read a student's resume beside the listing and share them with the employer; bulk WhatsApp; WhatsApp messages from employers, made into listings; Settings (email, WhatsApp, Google, Fireflies, scoring, sent messages), accounts and the audit log |
| NGO staff | `/ngo` | The case work. A home page of what needs them; students by program, college and branch; each student's matches (with the score breakdown and a side-by-side comparison), resume and score, learning plan and case notes; bulk resume upload; put interested students forward or decline them; schedule interviews, paste or fetch notes; messages |
| Student | `/student` | See their matches and why, with a learning plan; browse every live listing; show interest and track each step, including interviews; save for later; edit their own situation; save their resume and see its score and tips; turn WhatsApp updates on or off; download their data; message the NGO |
| Employer | `/employer` | Post, edit, copy, close and reopen listings with a last day to apply (the NGO reviews each one first); see applicants the NGO shared by anonymous candidate code; schedule interviews; move them from shortlist to hired; get emails about all of it; message the NGO |

Passwords are hashed with scrypt. Five wrong passwords lock an account for 15 minutes. Sessions end after 12 hours, or 2 hours without use. A new account gets a temporary password that must be changed on first sign-in. Forgotten passwords are reset by an admin. See `IMPLEMENTATION_PLAN.md` sections 9.6 to 9.10 for the full design.

### First run (development)

```bash
make all                                              # build the match files from sample data
make demo-users DEMO_PASSWORD='a long demo password'  # one admin, one officer, 3 students, 1 employer
make demo-outcomes                                    # optional: sample decisions, so a demo can show the learned score
make app                                              # http://localhost:5173
```

With `make app`, demo mode is on: the sign-in page is a drop down of every user and needs no password (`DEMO_LOGIN=1`). The app refuses to start with demo mode and `COOKIE_SECURE=1` together. Without it, the same accounts sign in with the demo password. The demo usernames are `admin`, `officer`, `s001`, `s002`, `s003` and `gopuram`, all with the demo password. `make e2e` (with `E2E_DEMO=1` when the API runs in demo mode, or `E2E_PASSWORD` set to the demo password) signs in as each role in a real browser, checks what each can and cannot reach, walks the whole journey (an employer posts a listing, the NGO admin approves it, a student finds it and shows interest, staff put the student forward, the admin reads the resume beside the listing and shares, the employer schedules an interview and hires, the student is told) and checks a phone-width screen. It leaves test listings and messages behind, so run it on a demo database, not real data.

### Running it for real

1. Copy `.env.example` to `.env`. Set `COOKIE_SECURE=1`, a long random `CANDIDATE_SALT` (for example `openssl rand -hex 32`, and never change it later), `TRUST_PROXY=1`, and `BOOTSTRAP_ADMIN_USERNAME` and `BOOTSTRAP_ADMIN_PASSWORD` for the first admin.
2. `docker compose up -d --build`. Data (database, contacts, match files) lives in the `matcher-data` volume. After the first sign-in, delete the two bootstrap lines from `.env`.
3. Put HTTPS in front. With Caddy, a two-line `Caddyfile` is enough:
   ```
   matcher.your-ngo.org {
       reverse_proxy 127.0.0.1:8000
   }
   ```
4. `make backup` copies the database safely while the app runs. Back up `data/private/contacts.csv` as well. It is the only copy of names and contacts (approved number changes are in the database).
5. Health checks: `/api/health` (the process is up) and `/api/ready` (the database and match files are readable).

Without Docker: `python -m matcher.accounts create-admin --username yourname`, then `uvicorn api.server:app --port 8000` behind HTTPS, after `npm run build` in `web/` (the API then serves the built app).

The web app style follows `handoff_ui.md` (paper and ink, pine sidebar, one green accent, quiet motion).

## Email, WhatsApp, Google and Fireflies (optional)

Each one is set in `.env` (see `.env.example`), and **Settings** in the NGO admin area shows what is live. Until a service is set, the app still works: every email and WhatsApp message is recorded as a dry run under Settings, Sent messages, and interviews get a calendar file by email.

- **Email.** Any SMTP server: set `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` (a Gmail app password works). Put an email on each employer account (Accounts page, or the employer's own Account page). Employers are emailed when a listing is approved or needs a change, when a candidate is shared, and when an interview is set.
- **WhatsApp (Meta Cloud API).** Set `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN` and `WHATSAPP_APP_SECRET`, and point Meta's webhook at `<API address>/api/whatsapp/webhook` (subscribe to `messages`). Messages go only to students who agreed: staff record it on the student's Resume tab, or the student turns it on in their profile. **While testing, use stand-ins (below):** the sample students' numbers are made up but may belong to real people. Employers who write to the number appear under Messages, "WhatsApp from employers", and the first message gets an automatic reply asking for the details a listing needs. An admin makes a listing from it, or links it to one that is already live. When an admin approves or posts a listing, a box (ticked by default) also tells the students it fits best who agreed, up to the best 50.
- **Google Calendar and Meet.** Make a Google Cloud OAuth client (web application) with the Calendar API on, add `<API address>/api/integrations/google/callback` as a redirect address, set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`, then press "Connect a Google account" in Settings. Interviews then get a Meet link and Google sends the invites from that account.
- **Fireflies.ai.** Set `FIREFLIES_API_KEY` and `FIREFLIES_WEBHOOK_SECRET`, and set Fireflies' webhook to `<API address>/api/fireflies/webhook`. When an interview asks for notes, the Fireflies bot is invited and the summary and action points come back to the interview.

### Testing on fake data with real phones and inboxes

Do not type your own number or email into the data. `make all` rewrites the contact list, interview invites drop repeated addresses, and an incoming WhatsApp goes to the first student with that number. Keep the data fake and name stand-ins in `.env`:

```bash
STANDIN_WHATSAPP=*=91FRIENDSNUMBER,admin=91YOURNUMBER
STANDIN_EMAIL=*=friend@gmail.com,admin=you@gmail.com,officer=someone@gmail.com,gopuram=employer@gmail.com
```

- `*` is everyone not named: every student, for WhatsApp. A student ID (`S001`) or a username (`admin`, `officer`, `gopuram`) overrides it for that person.
- Only students get WhatsApp from the app. Staff and employers get email. A phone under a name that is not a student (`admin`, `lead`) plays an employer writing in: its messages become leads, and it can be replied to.
- Just before a message leaves, the address is swapped. Email subjects start with `[TEST for gopuram]`, so one inbox can tell them apart. Settings, Sent messages shows both addresses. Google Calendar guests are swapped too, but Google sends one invite per address.
- Anyone without a stand-in gets a dry run, so no message can reach a made-up number. Consent still applies: a student must have agreed to WhatsApp.
- A reply from a stand-in's phone lands in the chat of the student that phone last got a message about.
- **To go live, delete both lines.** Nothing else changes. If WhatsApp keys are live and the sample students are still loaded, the app will not start until you set stand-ins or load real data.

### Loading real data

Put the NGO's files in `data/raw/students_raw.csv` and `data/raw/opportunities_raw.csv` with the same columns as the sample, then run `make all` (or `docker compose exec app python -m matcher.pipeline`) and restart the app. Once the students file is not the sample (its emails are not all at example.com), the generator leaves `data/raw` alone. To make sample data again, delete the file first.

### Checking every endpoint

`make sweep` calls all the API routes on a running server as the right person, and repeats each call as the wrong people and signed out to check they are refused. Start the API with `DEMO_LOGIN=1`, or pass `PASSWORD='your demo password'`. For a hosted test server, run `python -m eval.sweep --base https://your-server --password '...' --yes-this-is-a-test-server`. It leaves test data behind, and refuses to run if email or WhatsApp is live with no stand-ins. `make test` runs it too, so a new route without a sweep step fails the tests.

### WhatsApp templates

Outside a 24 hour reply window, WhatsApp only delivers templates Meta has approved. Create these four in WhatsApp Manager (language "English", which is code `en`; Meta asks for a sample value for each `{{n}}`), or set your own names with `WHATSAPP_TEMPLATE_*`. Keep the number of `{{n}}` exactly as here: the app sends that many values. Meta does not accept a body that starts or ends with a `{{n}}`, so each one ends with a short sentence.

| Name | Category | Body | Used for |
|---|---|---|---|
| `new_opportunity` | Marketing | A new {{1}} opportunity at {{2}} fits your profile. Apply by {{3}}. See it here: {{4}} Your placement officer can tell you more. | Bulk: a listing to the students it fits best |
| `matches_ready` | Utility | You have {{1}} matches waiting. The best one right now is {{2}}. Open: {{3}} Your placement officer can help you choose. | Bulk: your matches are ready |
| `ngo_update` | Utility | Update from the NGO: {{1}} More here: {{2}} Thank you. | Bulk: an update |
| `interview_scheduled` | Utility | Your interview for {{1}} is on {{2}}. Join here: {{3}} All the best. | Each interview |

## Turn on an LLM (optional)

Copy `.env.example` to `.env`, set `LLM_PROVIDER` to `openai`, `gemini` or `anthropic`, add the key, and run `make all` again. The LLM is used to parse messy skill text and to write one-sentence reasons. Every reason is fact-checked. If a reason fails the check, the template reason is used instead.

## Privacy rules

- Names, phones and emails live only in `data/private/contacts.csv`, plus mobile numbers a student asked to change, which NGO staff must approve before they are used. Those are kept in the `contact_changes` table of `data/app.db`, because the pipeline rewrites `contacts.csv` on every run. Students see only the last four digits of their own number.
- They never go to an LLM, a log, or any file in `data/clean/` or `data/derived/`. They are used only to send a WhatsApp message to a student who agreed, or an interview invite staff chose to send.
- The dashboard hides names unless "Show names" is on.
- Notes that staff type, and every chat message, are redacted for phones, emails and known names before they are saved.
- Employers never see student IDs. They see a short candidate code, and staff can search by that code.
- The audit log records who opened a student, but never names, phone numbers, emails or message text.
- Saved resumes are kept in `data/private/resumes/`. Only NGO staff and the student can open one, every opening is in the audit log, and a resume is never sent to an employer or an LLM. Its score report holds only what was found, never the text.
- The outbox stores student phone numbers and emails masked. Interview invites hide guests from each other.
- Transcripts and pasted meeting notes have names, phones and emails taken out before they are stored.
- The employer area shows students by ID, branch, town, CGPA and skills only.

## Where things are

| File | Written by |
|---|---|
| `data/raw/students_raw.csv`, `data/raw/opportunities_raw.csv` | B1 |
| `data/private/contacts.csv` | B2 |
| `data/private/resumes/<id>.pdf` | B6 (saved resumes) |
| `data/clean/students.json`, `opportunities.json`, `cleaning_report.json` | B2 |
| `data/derived/normalized_skills.json`, `vectors.npz` | B3 |
| `data/derived/pair_scores.csv` | B4 (5,000 rows) |
| `data/derived/top5.json` | B5 |
| `data/app.db` | B6: accounts, decisions, listings, applications, interviews, resumes' scores, consent, the outbox and WhatsApp leads |
| `eval/labels.csv`, `eval/results.md`, `eval/timing.csv` | Eval |

## How labelling works

1. `make eval` writes `eval/labels_template.csv`: 20 students, with our top 5 and the keyword baseline top 5 mixed in random order.
2. `eval/auto_label.py` pre-fills `eval/labels.csv` with a rule (bad if a hard check fails, good if coverage is at least 0.5, else ok) and sets `labeller` to `auto`.
3. A person reviews every row, changes labels where they disagree, and writes their name in `labeller`.

**The headline precision uses only human-reviewed labels.** Rows still marked `auto` are counted and shown separately in `eval/results.md`.

## Issues and blocks

| Issue | Title | Block |
|---|---|---|
| #1 | Data format | B1, B2 |
| #2 | Fake student data | B1 |
| #3 | Fake opportunity data | B1 |
| #4 | Clean and check the data | B2 |
| #5 | Turn messy skill text into clean fields | B2 |
| #6 | Skill list | B3 |
| #7 | Match skill words and make vectors | B3 |
| #8 | Skill score | B4 |
| #9 | Hard filters | B4 |
| #10 | Soft penalties | B4 |
| #11 | Top 5 | B5 |
| #12 | Reasons | B5 |
| #13 | Staff dashboard (React) | B6 |
| #14 | Accept, reject or flag | B6 |
| #15 | Match quality tests | Eval |
| #16 | End to end run and demo | Eval |

See `IMPLEMENTATION_PLAN.md` for the full plan and `DEMO.md` for the demo script.
