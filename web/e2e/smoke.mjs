// Browser tests: sign in as each role, check what each can and cannot reach, and walk the whole journey
// (employer posts, the NGO admin approves, student shows interest, staff put them forward, the admin shares after reading
// the resume beside the listing, the employer schedules an interview and hires), then a phone-width check.
// Needs the API and web app running and the demo accounts:  make demo-users DEMO_PASSWORD='...'
// Run:  E2E_DEMO=1 npm run e2e   (API started with DEMO_LOGIN=1)   or   E2E_PASSWORD='...' npm run e2e
import puppeteer from 'puppeteer-core'
import assert from 'node:assert/strict'

const base = process.env.E2E_BASE ?? 'http://localhost:5173'
const PW = process.env.E2E_PASSWORD
const chrome = process.env.CHROME ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
if (!PW && !process.env.E2E_DEMO) { console.error('Set E2E_DEMO=1 or E2E_PASSWORD.'); process.exit(2) }

const browser = await puppeteer.launch({ executablePath: chrome, headless: 'new', args: ['--force-prefers-reduced-motion'], defaultViewport: { width: 1440, height: 900 } })
let failures = 0
let lastStep = ''
const step = (n) => { lastStep = n }
{ const warm = await browser.newPage(); await warm.goto(base + '/login', { waitUntil: 'networkidle0', timeout: 90000 }); await warm.close() }   // the dev server compiles on the first visit
const test = async (name, fn) => {
  const contexts = []
  // every page opened here has its own cookies, like a different person on a different computer
  const open = async (viewport) => { const ctx = await browser.createBrowserContext(); contexts.push(ctx); const p = await ctx.newPage(); p.setDefaultTimeout(15000); p.setDefaultNavigationTimeout(45000); if (viewport) await p.setViewport(viewport); return p }
  try { await fn(open); console.log('ok  ', name) } catch (e) { failures++; console.log('FAIL', name, '-', e.message.split('\n')[0], lastStep ? `(at: ${lastStep})` : '') } finally { for (const c of contexts) await c.close() }
}
const path = (page) => new URL(page.url()).pathname
const until = (page, p) => page.waitForFunction((x) => location.pathname === x, {}, p)
const bodyHas = (page, re) => page.waitForFunction((s) => new RegExp(s, 'i').test(document.body.innerText), {}, re.source)
const goto = (page, p) => page.goto(base + p, { waitUntil: 'networkidle0' })
async function login(page, user, pw = PW) {
  await goto(page, '/login')
  if (await page.$('#demo-user')) {
    await page.waitForFunction((u) => [...document.querySelectorAll('#demo-user option')].some((o) => o.value === u), {}, user)
    await page.select('#demo-user', user)
  } else { await page.type('#username', user); await page.type('#password', pw) }
  await page.click('button[type=submit]')
}
/** Click a button inside the card (article or table row) that contains some text. */
const clickIn = (page, container, button) => page.waitForFunction((c, b) => {
  const box = [...document.querySelectorAll('article, tr, li')].find((e) => e.innerText.includes(c) && [...e.querySelectorAll('button')].some((x) => x.innerText.trim().startsWith(b)))
  const btn = box && [...box.querySelectorAll('button')].find((x) => x.innerText.trim().startsWith(b))
  if (btn) { btn.click(); return true } return false
}, {}, container, button)
/** Click a link inside the table row that contains some text. */
const linkIn = (page, container, link) => page.waitForFunction((c, l) => {
  const row = [...document.querySelectorAll('tr, article, li')].find((e) => e.innerText.includes(c) && [...e.querySelectorAll('a')].some((x) => x.innerText.trim() === l))
  const a = row && [...row.querySelectorAll('a')].find((x) => x.innerText.trim() === l)
  if (a) { a.click(); return true } return false
}, {}, container, link)
const clickText = (page, text) => page.waitForFunction((t) => { const b = [...document.querySelectorAll('button, a')].find((x) => x.innerText.trim() === t); if (b) { b.click(); return true } return false }, {}, text)

await test('signed-out visitors are sent to the sign-in page', async (open) => {
  const page = await open()
  for (const p of ['/ngo/students', '/student', '/employer', '/ngo/admin/users']) { await goto(page, p); await until(page, '/login') }
})
await test('a wrong password shows one plain message (password mode only)', async (open) => {
  const page = await open(); await goto(page, '/login')
  if (await page.$('#demo-user')) return
  await login(page, 'officer', 'wrong wrong wrong'); await bodyHas(page, /Wrong username or password\./)
})
await test('NGO staff land on the dashboard and cannot open admin pages or other areas', async (open) => {
  const page = await open(); await login(page, 'officer'); await until(page, '/ngo'); await bodyHas(page, /What needs you today/)
  for (const p of ['/ngo/admin/users', '/ngo/admin/audit', '/student', '/employer']) { await goto(page, p); await bodyHas(page, /No access/) }
})
await test('an NGO admin can see accounts and the audit log', async (open) => {
  const page = await open(); await login(page, 'admin'); await until(page, '/ngo')
  await goto(page, '/ngo/admin/users'); await bodyHas(page, /Add an account/)
  await goto(page, '/ngo/admin/audit'); await bodyHas(page, /Audit log/)
})
await test('an unknown address shows a plain not-found page inside each area', async (open) => {
  const page = await open(); await login(page, 'officer'); await until(page, '/ngo')
  await goto(page, '/ngo/nowhere'); await bodyHas(page, /Page not found/)
})
await test('a student lands in /student, is kept out of other areas, and can write to the NGO', async (open) => {
  const page = await open(); await login(page, 's002'); await until(page, '/student'); await bodyHas(page, /matches/)
  await goto(page, '/ngo/students'); await bodyHas(page, /No access/)
  await goto(page, '/student/messages')
  await page.type('#msg', `smoke test ${Date.now()}. Call 9876543210`); await page.keyboard.press('Enter')
  await bodyHas(page, /smoke test \d+\. Call \[phone\]/)
})
await test('an employer sees only their own listings and no student IDs', async (open) => {
  const page = await open(); await login(page, 'gopuram'); await until(page, '/employer'); await bodyHas(page, /My listings/)
  await goto(page, '/employer/J001'); await bodyHas(page, /Not found/)
  await goto(page, '/employer/J028'); await bodyHas(page, /Applicants/)
  await clickText(page, /Best fit/.test('') ? '' : 'Best fit (15)').catch(() => {})
  const text = await page.evaluate(() => document.body.innerText)
  assert.ok(!/\bS\d{3}\b/.test(text), 'a student ID is visible to an employer')
})
await test('sorting a table and the / shortcut work', async (open) => {
  const page = await open(); await login(page, 'officer'); await until(page, '/ngo')
  await goto(page, '/ngo/students'); await bodyHas(page, /Showing 1 to 25 of 100/)
  await page.keyboard.press('/'); assert.equal(await page.evaluate(() => document.activeElement?.id), 'search')
  await page.evaluate(() => [...document.querySelectorAll('th button')].find((b) => b.innerText.trim() === 'CGPA').click())
  await page.waitForSelector('th[aria-sort="ascending"]')
  await page.evaluate(() => document.querySelector('button[aria-label="Next page"]').click()); await bodyHas(page, /Showing 26 to 50 of 100/)
})

await test('the whole journey: employer posts, admin approves, student shows interest, staff put forward, admin shares, employer interviews and hires', async (open) => {
  const title = `Smoke Role ${Date.now()}`
  step('1 employer posts')
  // 1. the employer posts a listing
  const emp = await open(); await login(emp, 'gopuram'); await until(emp, '/employer')
  await goto(emp, '/employer/new'); await emp.waitForSelector('#l-title')
  await emp.type('#l-title', title); await emp.type('#l-skills', 'Python, SQL, Excel')
  await emp.type('#l-pay', '4 LPA'); await clickText(emp, 'Remote')
  await emp.evaluate(() => { const i = document.querySelector('#l-open'); i.focus() }); await emp.keyboard.press('Backspace'); await emp.keyboard.type('1')
  await clickText(emp, 'Submit for review')
  await emp.waitForFunction(() => /^\/employer\/E\d+$/.test(location.pathname)); await bodyHas(emp, /Waiting for the NGO/)
  const oid = path(emp).split('/').pop()
  step('2 NGO admin approves')
  // 2. the NGO admin approves it (staff can read the queue but not approve)
  const ngo = await open(); await login(ngo, 'admin'); await until(ngo, '/ngo')
  await goto(ngo, '/ngo/opportunities?tab=review'); await bodyHas(ngo, new RegExp(title))
  await clickIn(ngo, title, 'Approve'); await bodyHas(ngo, /Approved\. It is live now.*told on WhatsApp/)
  step('3 student browses and shows interest')
  // 3. a student finds it in Browse and shows interest
  const stu = await open(); await login(stu, 's002'); await until(stu, '/student')
  await goto(stu, '/student/browse'); await stu.type('#search', title); await bodyHas(stu, new RegExp(title))
  await clickIn(stu, title, "I'm interested"); await bodyHas(stu, /Sent\. The NGO will look at it next/)
  await goto(stu, '/student/applications'); await bodyHas(stu, new RegExp(title))
  await stu.waitForFunction(() => [...document.querySelectorAll('[aria-current="step"]')].some((li) => /Application/.test(li.textContent ?? '')))   // the lifeline is at Application
  step('4 staff put the student forward')
  // 4. staff put the student forward; they cannot share
  const staff = await open(); await login(staff, 'officer'); await until(staff, '/ngo')
  await goto(staff, '/ngo/applications'); await bodyHas(staff, new RegExp(title))
  assert.ok(!(await staff.evaluate(() => document.body.innerText)).includes('Review and share'), 'staff can share')
  await clickIn(staff, title, 'Put forward'); await staff.waitForSelector('input[placeholder^="Why they fit"]')
  await staff.type('input[placeholder^="Why they fit"]', 'Good Python and SQL.'); await staff.keyboard.press('Enter')
  await bodyHas(staff, /Put forward\. An admin will check and share/)
  step('5 admin reads the resume beside the listing and shares')
  // 5. the admin opens the side-by-side review and shares
  await goto(ngo, '/ngo/applications?tab=approve'); await bodyHas(ngo, new RegExp(title))
  await linkIn(ngo, title, 'Review and share'); await bodyHas(ngo, /check before sharing/)
  await clickText(ngo, 'Share with the employer'); await bodyHas(ngo, /Shared\. The employer was told/)
  step('6 employer schedules an interview and hires')
  // 6. the employer sees an anonymous applicant, schedules an interview and hires them
  await goto(emp, `/employer/${oid}`); await bodyHas(emp, /Applicants \(1\)/)
  const empText = await emp.evaluate(() => document.body.innerText)
  assert.ok(!/\bS002\b/.test(empText) && !/Ravi/.test(empText), 'the employer can see who the student is')
  await clickText(emp, 'Shortlist'); await bodyHas(emp, /Shortlisted/)
  await clickText(emp, 'Schedule interview'); await emp.waitForSelector('input[type=datetime-local]')
  await clickText(emp, 'Schedule and send invites'); await bodyHas(emp, /Note\./)          // no Meet link and no notetaker set up: said plainly
  await clickText(emp, 'OK'); await bodyHas(emp, /Make an offer/)
  await clickText(emp, 'Make an offer'); await bodyHas(emp, /Offered/)
  await clickText(emp, 'Mark as hired')
  await emp.waitForSelector('[role=alertdialog]')
  await emp.evaluate(() => [...document.querySelectorAll('[role=alertdialog] button')].find((b) => b.innerText.trim() === 'Mark as hired').click())   // confirm in the dialog
  await bodyHas(emp, /Filled\./)                                                           // one opening, one hire: the listing closes
  step('7 student sees the result')
  // 7. the student sees the result and a notification
  await goto(stu, '/student/applications'); await bodyHas(stu, /Hired/)                 // the lifeline ends at Hired
  await clickIn(stu, title, 'View'); await bodyHas(stu, /You got the job/)
  await goto(stu, '/student/notifications'); await bodyHas(stu, /Congratulations/)
})

await test('an employer who writes on WhatsApp gets an automatic reply, and the admin links it to a live listing', async (open) => {
  const phone = `9190000${String(Date.now()).slice(-5)}`
  const r = await fetch(base + '/api/whatsapp/webhook', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ entry: [{ changes: [{ value: {
    contacts: [{ wa_id: phone, profile: { name: `Smoke Employer ${phone}` } }], messages: [{ from: phone, id: `wamid.smoke.${phone}`, type: 'text', text: { body: 'We are hiring 2 testers in Hyderabad' } }] } }] }] }) })
  if (r.status === 403) return                                  // a signed webhook on a real server: covered by the sweep
  const page = await open(); await login(page, 'admin'); await until(page, '/ngo')
  await goto(page, '/ngo/messages?tab=leads'); await clickText(page, `Smoke Employer ${phone}`).catch(() => {})
  await page.waitForFunction((n) => { const b = [...document.querySelectorAll('button')].find((x) => x.innerText.includes(n)); if (b) { b.click(); return true } return false }, {}, phone)
  await bodyHas(page, /Thank you for writing to the NGO/); await bodyHas(page, /We are hiring 2 testers/)
  await page.waitForFunction(() => document.querySelectorAll('#lead-link option').length > 1)
  const pick = await page.evaluate(() => document.querySelectorAll('#lead-link option')[1].value)
  await page.select('#lead-link', pick); await clickText(page, 'Link it'); await bodyHas(page, /Linked to a listing/)
})
await test('on a phone the menu opens and nothing spills sideways', async (open) => {
  const page = await open({ width: 390, height: 800, isMobile: true, hasTouch: true })
  await login(page, 's001'); await until(page, '/student'); await bodyHas(page, /matches/)
  for (const p of ['/student', '/student/browse', '/student/profile', '/student/applications']) {
    await goto(page, p); await new Promise((r) => setTimeout(r, 400))
    const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
    assert.ok(over <= 1, `${p} is ${over}px wider than the screen`)
  }
  await page.click('button[aria-label="Open the menu"]'); await page.waitForFunction(() => document.querySelector('#sidebar')?.getBoundingClientRect().left >= 0)
  assert.ok(await page.evaluate(() => [...document.querySelectorAll('#sidebar a')].some((a) => a.innerText.includes('Browse'))))
  await page.keyboard.press('Escape'); await page.waitForFunction(() => document.querySelector('#sidebar')?.getBoundingClientRect().right <= 0)
})
await test('signing out ends the session', async (open) => {
  const page = await open(); await login(page, 'officer'); await until(page, '/ngo')
  await page.evaluate(() => [...document.querySelectorAll('button')].find((b) => b.textContent.includes('Sign out')).click())
  await until(page, '/login'); await goto(page, '/ngo/students'); await until(page, '/login')
})
await browser.close()
if (failures) { console.log(`${failures} failed`); process.exit(1) }
console.log('all passed')
