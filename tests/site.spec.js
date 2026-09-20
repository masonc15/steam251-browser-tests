import { test, expect } from '@playwright/test';

for (const path of ['/', '/7day', '/30day', '/tag/5613']) {
  test(`cold load and stable text: ${path}`, async ({ page }, testInfo) => {
    const externalFonts = [], appErrors = [], failedAssets = [];
    page.on('pageerror', error => appErrors.push(error.message));
    page.on('response', response => {
      if (response.url().startsWith('https://steam251.com/') && response.status() >= 400)
        failedAssets.push({ url: response.url(), status: response.status() });
    });
    await page.route('**/*', async route => {
      const r = route.request();
      if (r.resourceType() === 'font') { externalFonts.push(r.url()); await route.abort(); }
      else await route.continue();
    });
    await page.addInitScript(() => {
      window.fontFrames = [];
      function sample() {
        const nodes = [...document.querySelectorAll('#header h1, #header .slogan')];
        if (nodes.length && getComputedStyle(nodes[0]).fontFamily.toLowerCase().includes('lobster')) {
          window.fontFrames.push(nodes.map(el => {
            const s = getComputedStyle(el), r = document.createRange(); r.selectNodeContents(el);
            const rect = r.getBoundingClientRect();
            return { text: el.textContent, font: s.fontFamily, width: rect.width, height: rect.height,
              loaded: document.fonts.check(`${s.fontStyle} ${s.fontWeight} ${s.fontSize} ${s.fontFamily}`, el.textContent) };
          }));
        }
        if (window.fontFrames.length < 90) requestAnimationFrame(sample);
      }
      requestAnimationFrame(sample);
    });
    const response = await page.goto(path, { waitUntil: 'domcontentloaded' });
    expect(response.status()).toBe(200);
    await expect(page.locator('h1').first()).toBeVisible();
    await expect(page).toHaveTitle(/Steam|Detective|Club/i);
    await expect(page.locator('body')).not.toBeEmpty();
    await page.evaluate(() => document.fonts.ready);
    if (path !== '/tag/5613') await page.waitForFunction(() => window.fontFrames.length >= 30);
    else await page.waitForTimeout(1800);
    const measurement = await page.evaluate(() => ({
      overflow: document.documentElement.scrollWidth - innerWidth,
      frames: window.fontFrames,
      fonts: [...document.fonts].map(f => ({ family: f.family, status: f.status })),
      visibleFontFailures: [...document.querySelectorAll('body *')].filter(el => {
        if (!el.getClientRects().length || ![...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) return false;
        const s = getComputedStyle(el);
        return !document.fonts.check(`${s.fontStyle} ${s.fontWeight} ${s.fontSize} ${s.fontFamily}`, el.textContent);
      }).map(el => el.tagName),
    }));
    await testInfo.attach('font-observations', { body: JSON.stringify(measurement, null, 2), contentType: 'application/json' });
    expect(measurement.overflow).toBeLessThanOrEqual(1);
    expect(measurement.visibleFontFailures).toEqual([]);
    expect(externalFonts).toEqual([]);
    expect(appErrors).toEqual([]);
    expect(failedAssets).toEqual([]);
    if (path !== '/tag/5613') {
      expect(measurement.frames.length).toBeGreaterThan(2);
      // Ignore the first callback: layout can trigger initial inline-font decoding.
      // Record it in the evidence rather than treating rAF as proof of a paint.
      for (const frame of measurement.frames.slice(1)) {
        expect(frame.every(item => item.loaded)).toBe(true);
        expect(frame.map(({ width, height }) => ({ width, height })))
          .toEqual(measurement.frames.at(-1).map(({ width, height }) => ({ width, height })));
      }
    }
    await page.screenshot({ path: testInfo.outputPath('loaded.png'), fullPage: false });
  });
}

test('ranking links and early-access filter persist', async ({ page }) => {
  await page.goto('/7day');
  await expect(page.locator('.ranking-row')).toHaveCount(50);
  const filter = page.getByLabel('Hide Early Access games');
  await filter.check();
  await expect(page.locator('body')).toHaveClass(/hide-ea/);
  await expect(page.locator('.ranking-row.is-ea:visible')).toHaveCount(0);
  await page.reload();
  await expect(filter).toBeChecked();
  await filter.uncheck();
  await expect(page.locator('body')).not.toHaveClass(/hide-ea/);
  await page.locator('#footer').getByRole('link', { name: 'Month Top 100', exact: true }).click();
  await expect(page).toHaveURL('https://steam251.com/30day');
  await expect(page.locator('.ranking-row')).toHaveCount(100);
  await page.locator('#footer').getByRole('link', { name: 'Home', exact: true }).click();
  await expect(page).toHaveURL('https://steam251.com/');
});

test('comparison loads our ranking frame', async ({ page }) => {
  await page.goto('/compare?path=%2F7day');
  await expect(page.frameLocator('#ours-frame').locator('.ranking-row')).toHaveCount(50);
  await expect(page.locator('#steam250-frame')).toBeVisible();
  // External Steam250 content is outside this site's font guarantees.
});
