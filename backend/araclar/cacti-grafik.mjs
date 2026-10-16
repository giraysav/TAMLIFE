// Dedicated ephemeral browser context; no profile/cookie/credential files or screenshots.
import { chromium } from '../../ekran-react/node_modules/@playwright/test/index.mjs'
let input = ''
for await (const chunk of process.stdin) input += chunk
const cfg = JSON.parse(input)
input = ''
const origin = 'https://trafik.superonline.net'
let browser
const timeout = setTimeout(() => { void browser?.close() }, 65000)
try {
  browser = await chromium.launch({ channel: 'chrome', headless: true })
  const context = await browser.newContext({ acceptDownloads: false, serviceWorkers: 'block' })
  await context.route('**/*', route => {
    const url = new URL(route.request().url())
    return url.origin === origin ? route.continue() : route.abort()
  })
  const page = await context.newPage()
  page.setDefaultTimeout(12000)
  page.setDefaultNavigationTimeout(20000)
  await page.goto(cfg.base)
  const gatewayUser = page.locator('input[name="username"]:visible').first()
  const cactiUser = page.locator('input[name="login_username"]:visible').first()
  // The gateway initializes via JavaScript after the first response.
  await Promise.race([
    gatewayUser.waitFor({state:'visible', timeout:10000}),
    cactiUser.waitFor({state:'visible', timeout:10000}),
  ]).catch(() => {})
  if (await gatewayUser.isVisible()) {
    const form = gatewayUser.locator('xpath=ancestor::form')
    await gatewayUser.fill(cfg.username)
    await form.locator('input[name="password"]').fill(cfg.password)
    await form.locator('button[type="submit"],input[type="submit"],button:not([type])').first().click()
    await page.waitForURL(url => !url.pathname.includes('/webr/auth/'), {timeout:15000})
    await page.goto(cfg.base)
  }
  if (await cactiUser.isVisible()) {
    const form = cactiUser.locator('xpath=ancestor::form')
    await cactiUser.fill(cfg.username)
    await form.locator('input[name="login_password"]').fill(cfg.password)
    const realm = form.locator('select[name="realm"]')
    if (await realm.count()) await realm.selectOption(cfg.realm)
    await form.locator('button[type="submit"],input[type="submit"],input[type="image"]').first().click()
    await cactiUser.waitFor({state:'hidden',timeout:12000})
  }
  const images = []
  for (const id of cfg.ids) {
    const url = new URL('graph_image.php', cfg.base)
    for (const [key, value] of Object.entries({
      local_graph_id:id, graph_start:cfg.start, graph_end:cfg.end,
      graph_width:1000, graph_height:300, image_format:'png',
    })) url.searchParams.set(key, String(value))
    // Use Chrome networking, including the authenticated gateway session.
    // All browser requests and redirects remain restricted to the configured origin.
    const response = await page.goto(url.href, {timeout:10000,waitUntil:'load'})
    if (!response || !response.ok() || Number(response.headers()['content-length'] || 0) > 3145728)
      throw new Error('graph')
    const data = await response.body()
    if (data.length > 3145728 || !data.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10])))
      throw new Error('image')
    images.push(data.toString('base64'))
  }
  process.stdout.write(JSON.stringify({images}))
} catch {
  // Never emit browser exceptions, URLs with queries, page bodies, user or password.
  process.stdout.write(JSON.stringify({error:'Cacti kurumsal oturumu veya grafik alımı başarısız. LDAP hesabı, erişim izni, MFA ve grafik ID bilgilerini kontrol edin.'}))
  process.exitCode = 1
} finally {
  cfg.password = ''
  cfg.username = ''
  clearTimeout(timeout)
  await browser?.close()
}
