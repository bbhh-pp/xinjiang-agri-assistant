// Browser interaction smoke test. All external requests are mocked.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
(async () => {
  const browser = await chromium.launch({headless:true, executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
  const page = await browser.newPage({viewport:{width:1440,height:960}});
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => {
    window.testSpoken = [];
    window.testCancelled = 0;
    window.SpeechSynthesisUtterance = function(text){this.text=text;};
    Object.defineProperty(window,'speechSynthesis',{value:{getVoices:()=>[],cancel:()=>window.testCancelled++,speak:u=>window.testSpoken.push(u.text)}});
  });
  const serveMock = async route => {
    const url = new URL(route.request().url());
    if (url.pathname.startsWith('/api/')) {
      const request = route.request();
      if (request.method()==='POST' && url.pathname==='/api/ask-stream') {
        const submitted=request.postDataJSON();
        if (submitted.question === '中断测试') {
          await new Promise(resolve=>setTimeout(resolve,1500));
          try { return await route.fulfill({contentType:'text/event-stream',body:'event: done\ndata: {}\n\n'}); }
          catch (_) { return; }
        }
      }
      const events = [
        ['question',{question_zh:'羊不吃草怎么办？'}],
        ['answer_zh_token',{content:'先观察反刍、饮水和精神状态。\n1. 检查草料与饮水。\n2. 严重腹胀时及时联系兽医。'}],
        ['answer_zh_done',{answer_zh:'先观察反刍、饮水和精神状态。\n1. 检查草料与饮水。\n2. 严重腹胀时及时联系兽医。'}],
        ['done',{answer_zh:'先观察反刍、饮水和精神状态。\n1. 检查草料与饮水。\n2. 严重腹胀时及时联系兽医。',answer_ug:'قوينىڭ ھالىتىنى كۆزىتىڭ. تازا سۇ بېرىڭ.'}],
      ];
      return route.fulfill({contentType:'text/event-stream',body:events.map(([name,data])=>`event: ${name}\ndata: ${JSON.stringify(data)}\n\n`).join('')});
    }
    const name = url.pathname === '/' ? 'index.html' : url.pathname.replace('/static/','');
    const file = path.join(root,'web',name);
    const types={'.html':'text/html','.css':'text/css','.js':'text/javascript','.jpg':'image/jpeg'};
    if (!fs.existsSync(file)) return route.fulfill({status:404,body:'Not found'});
    return route.fulfill({contentType:types[path.extname(file)]||'application/octet-stream',body:fs.readFileSync(file)});
  };
  await page.route('http://home.test/**', serveMock);
  await page.goto('http://home.test/');
  await page.locator('.page-shell').waitFor({state:'visible'});
  await page.waitForTimeout(900);
  await page.screenshot({path:path.join(root,'design-previews/home-desktop.png')});
  await page.locator('[data-language="ug"]').click();
  assert.equal(await page.locator('#uyghur-text-panel').isVisible(),true);
  assert.equal(await page.locator('[data-language="ug"]').textContent(),'ئۇيغۇر تىلى');
  assert.equal(await page.locator('#page-title').textContent(),'دېھقانچىلىق ۋە چارۋىچىلىق سوئاللىرىڭىزغا جاۋاب بار');
  assert.equal(await page.locator('[data-input="text"]').textContent(),'يېزىق');
  assert.equal(await page.locator('[data-input="voice"]').textContent(),'ئاۋاز');
  assert.equal(await page.locator('[data-input="image"]').textContent(),'رەسىم');
  await page.locator('[data-input="voice"]').click();
  assert.equal(await page.locator('#audio-panel').isVisible(),true);
  assert.equal(await page.locator('#record-button').textContent(),'بېسىپ تۇرۇپ سۆزلەڭ');
  await page.locator('[data-language="zh"]').click();
  assert.equal(await page.locator('#chinese-audio-panel').isVisible(),true);
  assert.equal(await page.locator('#page-title').textContent(),'农牧问题，有答案');
  await page.locator('[data-language="ug"]').click();
  await page.reload();
  assert.equal(await page.locator('[data-language="ug"]').getAttribute('aria-pressed'),'true');
  assert.equal(await page.locator('#page-title').textContent(),'دېھقانچىلىق ۋە چارۋىچىلىق سوئاللىرىڭىزغا جاۋاب بار');
  await page.locator('[data-language="zh"]').click();
  await page.locator('[data-input="image"]').click();
  await page.locator('#image-file').setInputFiles(path.join(root,'web/grassland-home.jpg'));
  assert.equal(await page.locator('#image-preview').isVisible(),true);
  await page.locator('[data-input="text"]').click();
  await page.locator('#question').fill('羊不吃草怎么办？');
  await page.locator('#composer-send').click();
  await page.waitForFunction(()=>!document.getElementById('submit-button').disabled);
  assert.match(await page.locator('#uyghur-answer-zh').textContent(),/检查草料/);
  assert.match(await page.locator('#uyghur-answer-ug').textContent(),/قوينىڭ/);
  await page.locator('[data-language="ug"]').click();
  assert.match(await page.locator('#uyghur-answer-zh').textContent(),/检查草料/);
  assert.match(await page.locator('#uyghur-answer-ug').textContent(),/قوينىڭ/);
  await page.waitForTimeout(100);
  const secondContext = await browser.newContext({viewport:{width:390,height:844}});
  const secondPage = await secondContext.newPage();
  secondPage.on('pageerror', error => errors.push(error.message));
  await secondPage.route('http://home.test/**', serveMock);
  await secondPage.goto('http://home.test/');
  await secondPage.locator('.page-shell').waitFor({state:'visible'});
  assert.equal(await secondPage.locator('[data-language="zh"]').getAttribute('aria-pressed'),'true');
  await secondContext.close();
  await page.locator('[data-language="zh"]').click();
  await page.locator('#speak-chinese').click();
  assert.equal(await page.locator('#speak-chinese').getAttribute('aria-pressed'),'true');
  await page.locator('#speak-chinese').click();
  assert.equal(await page.locator('#speak-chinese').getAttribute('aria-pressed'),'false');
  await page.reload();
  assert.equal(await page.locator('#uyghur-answer-card').isVisible(),false);
  await page.evaluate(()=>window.scrollTo(0,0));
  await page.waitForTimeout(500);
  await page.screenshot({path:path.join(root,'design-previews/home-answer-desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await page.waitForTimeout(300);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:path.join(root,'design-previews/home-answer-mobile.png'),fullPage:true});
  await page.locator('[data-input="text"]').click();
  await page.evaluate(()=>window.scrollTo(0,0));
  await page.screenshot({path:path.join(root,'design-previews/home-mobile.png'),fullPage:true});
  await page.locator('#question').fill('中断测试');
  await page.locator('#composer-send').click();
  await page.locator('#stop-answer').waitFor({state:'visible'});
  await page.locator('#stop-answer').click();
  await page.waitForFunction(()=>document.getElementById('stop-answer').hidden);
  assert.equal(await page.locator('#uyghur-answer-card').isVisible(),false);
  assert.deepEqual(errors,[]);
  console.log('PASS: local no-login page, desktop/mobile, language switches, voice modes, image preview, mocked bilingual stream, stop, speaker toggle, no history persistence, no overflow or JS errors.');
  await browser.close();
})().catch(error=>{console.error(error);process.exit(1)});
