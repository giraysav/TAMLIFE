// Dedicated ephemeral browser context; no profile/cookie/credential files or screenshots.
import { chromium } from '../../ekran-react/node_modules/@playwright/test/index.mjs'
let input = ''
for await (const chunk of process.stdin) input += chunk
const cfg = JSON.parse(input)
input = ''
const origin = 'https://trafik.superonline.net'
let browser
const timeout = setTimeout(() => { void browser?.close() }, 110000)
const PNG = Buffer.from([137,80,78,71,13,10,26,10])
const MAX = 3145728

async function image(page, href) {
  // Use Chrome networking, including the authenticated session.
  // All browser requests and redirects remain restricted to the configured origins.
  const response = await page.goto(href, {timeout:30000,waitUntil:'load'})
  if (!response || !response.ok() || Number(response.headers()['content-length'] || 0) > MAX)
    throw new Error('graph')
  const data = await response.body()
  if (!data.length || data.length > MAX) throw new Error('image')
  if (data.subarray(0,8).equals(PNG)) return data.toString('base64')
  // Lookouteyes may serve GIF/JPEG: re-encode in the page (no extra package), the server validates PNG again.
  const type = (response.headers()['content-type'] || '').split(';')[0].trim().toLowerCase()
  if (!['image/gif','image/jpeg','image/bmp','image/webp'].includes(type)) throw new Error('image')
  return page.evaluate(async ({b64, type}) => {
    const img = new Image()
    img.src = `data:${type};base64,${b64}`
    await img.decode()
    const canvas = document.createElement('canvas')
    canvas.width = img.naturalWidth
    canvas.height = img.naturalHeight
    canvas.getContext('2d').drawImage(img, 0, 0)
    return canvas.toDataURL('image/png').split(',')[1]
  }, {b64:data.toString('base64'), type})
}
const LOE_ORIGINS = ['http://lookouteyes', 'https://lookouteyes', origin]
const loeOrigin = cfg.loeOrigin || 'http://lookouteyes'
if (!LOE_ORIGINS.includes(loeOrigin)) throw new Error('config')
const hasCacti = cfg.items.some(item => item.tur !== 'loe')
const hasLoe = cfg.items.some(item => item.tur === 'loe')
const allowed = new Set([...(hasCacti ? [origin] : []), ...(hasLoe ? [loeOrigin] : [])])
try {
  browser = await chromium.launch({ channel: 'chrome', headless: true })
  const context = await browser.newContext({ acceptDownloads: false, serviceWorkers: 'block' })
  await context.route('**/*', route => {
    const url = new URL(route.request().url())
    return allowed.has(url.origin) ? route.continue() : route.abort()
  })
  const page = await context.newPage()
  page.setDefaultTimeout(12000)
  page.setDefaultNavigationTimeout(20000)
  if (hasCacti) {
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
  }
  const onLoe = () => {
    const url = new URL(page.url())
    return url.origin === loeOrigin && url.pathname.toLowerCase().startsWith('/lookouteyes/')
  }
  if (hasLoe) {
    // Lookouteyes form: DefaultMetro.aspx -> Pages/Login/Login.aspx?CALLBACK=... (Domain is server-filled).
    // Account of the person requesting the graphs; Graph.ashx returns an empty body without this session.
    await page.goto(new URL('/lookouteyes/DefaultMetro.aspx', loeOrigin).href, {timeout:20000,waitUntil:'domcontentloaded'})
    const loeUser = page.locator('#MainContent_txtUsername:visible')
    if (onLoe() && new URL(page.url()).pathname.toLowerCase().includes('/pages/login/') && await loeUser.count()) {
      await loeUser.fill(cfg.username)
      await page.locator('#MainContent_txtPassword').fill(cfg.password)
      await page.locator('#MainContent_btnLogin').click()
      await page.waitForURL(url => !url.pathname.toLowerCase().includes('/pages/login/'), {timeout:20000})
    }
    if (!onLoe() || new URL(page.url()).pathname.toLowerCase().includes('/pages/login/')) throw new Error('login')
  }
  const images = [], titles = []
  for (const item of cfg.items) {
    if (item.tur === 'loe') {
      // Lookouteyes: Graph.aspx holds one <img id="graph" data-ct/miid/fn/val/s/e>; its zoom (gShow) requests
      // Graph.ashx?<data>&r=<random>. Same request here, with the report month as s/e (Unix seconds).
      const pageUrl = new URL('/lookouteyes/Modules/Graph.aspx', loeOrigin)
      for (const key of ['ct','miid','fn','val']) pageUrl.searchParams.set(key, String(item[key]))
      const response = await page.goto(pageUrl.href, {timeout:20000,waitUntil:'domcontentloaded'})
      if (!response || !response.ok() || !onLoe() || !new URL(page.url()).pathname.toLowerCase().startsWith('/lookouteyes/modules/'))
        throw new Error('page')
      const found = await page.evaluate(() => {
        const graph = document.getElementById('graph')
        const name = [window.ametric_name, window.metric_name].find(v => typeof v === 'string' && v.trim()) || ''
        return graph ? {data:{...graph.dataset}, name} : null
      })
      if (!found || String(found.data.miid) !== String(item.miid)) throw new Error('page')
      const url = new URL('Graph.ashx', pageUrl)
      for (const [key, value] of Object.entries({...found.data, s:cfg.start, e:cfg.end, r:Math.random()}))
        if (/^[a-z0-9]{1,10}$/i.test(key)) url.searchParams.set(key, String(value))
      images.push(await image(page, url.href))
      titles.push(found.name)
      continue
    }
    const url = new URL('graph_image.php', cfg.base)
    for (const [key, value] of Object.entries({
      local_graph_id:item.id, graph_start:cfg.start, graph_end:cfg.end,
      graph_width:1000, graph_height:300, image_format:'png',
    })) url.searchParams.set(key, String(value))
    images.push(await image(page, url.href))
    titles.push('')
  }
  process.stdout.write(JSON.stringify({images, titles}))
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
