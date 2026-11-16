import puppeteer from 'puppeteer-core'
// Accessibility audit (WCAG 2.1 A and AA) of the main screens of every role, with axe-core.
// Needs the API in demo mode and the web app running:  npm run a11y
import fs from 'node:fs'
const axeSrc = fs.readFileSync(new URL('../node_modules/axe-core/axe.min.js', import.meta.url), 'utf8')
const base = process.env.E2E_BASE ?? 'http://localhost:5173'
const chrome = process.env.CHROME ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const b = await puppeteer.launch({ executablePath: chrome, headless: 'new', args: ['--force-prefers-reduced-motion'], defaultViewport: { width: 1280, height: 900 } })
const plan = {
  officer: ['/ngo', '/ngo/students', '/ngo/students/S001', '/ngo/students/S001?tab=resume', '/ngo/students/S001?tab=plan', '/ngo/students/S001?tab=notes',
            '/ngo/students/resumes', '/ngo/opportunities', '/ngo/opportunities?tab=review', '/ngo/applications', '/ngo/applications?tab=interviews',
            '/ngo/messages', '/ngo/help', '/ngo/notifications'],
  admin: ['/ngo', '/ngo/opportunities/new', '/ngo/applications?tab=approve', '/ngo/messages?tab=leads', '/ngo/messages?tab=bulk',
          '/ngo/settings', '/ngo/settings?tab=scoring', '/ngo/settings?tab=sent', '/ngo/admin/users', '/ngo/admin/audit'],
  s001: ['/student', '/student/browse', '/student/applications', '/student/profile', '/student/messages', '/student/help'],
  gopuram: ['/employer', '/employer/new', '/employer/J028', '/employer/messages'],
}
const seen = new Map()
for (const [user, paths] of Object.entries(plan)) {
  const ctx = await b.createBrowserContext(); const p = await ctx.newPage(); p.setDefaultNavigationTimeout(45000)
  await p.goto(base + '/login', { waitUntil: 'networkidle0' })
  await p.waitForSelector('#demo-user'); await p.select('#demo-user', user); await p.click('button[type=submit]')
  await p.waitForFunction(() => location.pathname !== '/login')
  for (const path of paths) {
    await p.goto(base + path, { waitUntil: 'networkidle0' }); await new Promise((r) => setTimeout(r, 500))
    await p.evaluate(axeSrc)
    const res = await p.evaluate(() => axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] } }))
    for (const v of res.violations) {
      const key = v.id
      const nodes = v.nodes.slice(0, 2).map((n) => n.target.join(' ') + ' :: ' + (n.failureSummary || '').split('\n')[1]?.trim())
      if (!seen.has(key)) seen.set(key, { impact: v.impact, help: v.help, pages: new Set(), nodes })
      seen.get(key).pages.add(path)
    }
  }
  await ctx.close()
}
for (const [id, v] of seen) console.log(`${v.impact.toUpperCase()} ${id}: ${v.help}\n   pages: ${[...v.pages].join(', ')}\n   e.g. ${v.nodes.join('\n        ')}`)
await b.close()
if (seen.size === 0) console.log('No accessibility violations found.')
else process.exit(1)
