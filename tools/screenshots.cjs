// Render README screenshots from the exported map with the three.js viewer.
// usage: node tools/screenshots.cjs [preset ...]
// env:   PLAYWRIGHT=<path to playwright-core>  CHROME=<chrome executable>  PORT=8765  OUT=screenshots
// Serve the repository root first:  python3 -m http.server 8765
const path = require('path');
const { chromium } = require(process.env.PLAYWRIGHT || 'playwright-core');
const presets = require(path.join(__dirname, '..', 'viewer', 'presets.json'));
const port = process.env.PORT || 8765, out = process.env.OUT || path.join(__dirname, '..', 'screenshots');
const names = process.argv.slice(2).length ? process.argv.slice(2) : Object.keys(presets);
(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: true, args: ['--use-angle=metal', '--enable-unsafe-swiftshader']
  });
  for (const name of names) {
    const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
    const logs = []; page.on('console', m => logs.push(m.text())); page.on('pageerror', e => logs.push(String(e)));
    try {
      await page.goto(`http://127.0.0.1:${port}/viewer/?data=../dist&clean#${name}`);
      await page.waitForFunction(() => window.__viewerReady, null, { timeout: 600000 });
      await page.waitForTimeout(Number(process.env.WAIT || 4000));
      const file = path.join(out, `${name}.jpg`);
      await page.screenshot({ path: file, type: 'jpeg', quality: 85 });
      console.log('ok', name);
    } catch (e) { console.log('FAIL', name, e.message, logs.slice(-6).join(' | ')); }
    await page.close();
  }
  await browser.close();
})();
