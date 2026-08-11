const chromium = require('@sparticuz/chromium');
const { chromium: pwChromium } = require('playwright-core');

module.exports = async (req, res) => {
  const URL = req.query.url || 'https://hardware.shopify.com/en-uk/products/payment-marketing-kit-ie-eu-uk';
  const EXPECTED = req.query.expected || 'add_to_cart';
  const ACTION = 'Click Add to cart';
  const out = { page_url: URL, action: ACTION, expected: EXPECTED, requests: [] };
  let browser;
  try {
    browser = await pwChromium.launch({
      args: chromium.args,
      executablePath: await chromium.executablePath(),
      headless: true,
    });
    const page = await browser.newPage({ viewport: { width: 1365, height: 900 } });
    page.on('request', req2 => {
      const u = req2.url();
      const ul = u.toLowerCase();
      let platform = null;
      if (ul.includes('google-analytics.com') || ul.includes('/g/collect') || ul.includes('/collect?v=2')) platform='GA4/Google Analytics';
      else if (ul.includes('googleadservices.com') || ul.includes('doubleclick.net')) platform='Google Ads';
      else if (ul.includes('facebook.com/tr') || ul.includes('connect.facebook.net')) platform='Meta';
      else if (ul.includes('px.ads.linkedin.com') || ul.includes('snap.licdn.com')) platform='LinkedIn';
      if (platform) out.requests.push({ platform, method: req2.method(), url: u });
    });
    const resp = await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
    out.http_status = resp ? resp.status() : null;
    await page.waitForTimeout(4000);
    for (const pat of ['Accept all','Accept All','Allow all','Allow All','I agree']) {
      try {
        const loc = page.getByRole('button', { name: new RegExp('^'+pat+'$', 'i') }).first();
        if (await loc.count() && await loc.isVisible()) { await loc.click({timeout:3000}); await page.waitForTimeout(1000); out.consent_action=pat; break; }
      } catch {}
    }
    out.title = await page.title();
    out.dataLayer_before = await page.evaluate(() => typeof dataLayer !== 'undefined' ? dataLayer : null).catch(()=>null);
    out.before_b64 = (await page.screenshot({type:'jpeg',quality:55,fullPage:false})).toString('base64');
    const candidates = [page.locator('button[name="add"]'), page.locator('button').filter({hasText:/add to cart/i}), page.locator('input[type="submit"][value*="Add"]')];
    let clicked=false;
    for (const loc of candidates) {
      try {
        if (await loc.count() && await loc.first().isVisible()) {
          out.clicked_text = await loc.first().innerText().catch(()=>null) || await loc.first().getAttribute('value');
          await loc.first().click({timeout:5000}); clicked=true; break;
        }
      } catch (e) { (out.click_errors ||= []).push(String(e).slice(0,180)); }
    }
    out.clicked=clicked;
    await page.waitForTimeout(5000);
    out.dataLayer_after = await page.evaluate(() => typeof dataLayer !== 'undefined' ? dataLayer : null).catch(()=>null);
    out.final_url = page.url();
    out.after_b64 = (await page.screenshot({type:'jpeg',quality:55,fullPage:false})).toString('base64');
    const seen = new Set();
    out.requests = out.requests.filter(r => { const k=r.platform+'|'+r.url; if(seen.has(k)) return false; seen.add(k); return true; });

    const expectedLower = String(EXPECTED).toLowerCase();
    const matchedRequests = out.requests.filter(r => r.url.toLowerCase().includes(expectedLower));
    const dataLayerText = JSON.stringify(out.dataLayer_after || []).toLowerCase();
    const observedInDataLayer = dataLayerText.includes(expectedLower);
    const observed = matchedRequests.length > 0 || observedInDataLayer;
    const status = !clicked ? 'UNKNOWN' : observed ? 'PASS' : 'FAIL';

    out.audit = {
      Target: URL,
      Action: ACTION,
      Expected: EXPECTED,
      Observed: observed ? EXPECTED : 'Not observed',
      Status: status,
      Evidence: {
        action_completed: clicked,
        matched_requests: matchedRequests,
        observed_in_dataLayer: observedInDataLayer,
        before_screenshot_captured: Boolean(out.before_b64),
        after_screenshot_captured: Boolean(out.after_b64)
      }
    };

    res.status(200).json(out);
  } catch (e) {
    out.error = String(e && e.stack || e);
    res.status(500).json(out);
  } finally { if (browser) await browser.close(); }
};