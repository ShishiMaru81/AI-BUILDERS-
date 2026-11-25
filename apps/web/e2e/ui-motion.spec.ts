import {expect, test} from '@playwright/test';

const api = process.env.E2E_API_URL || 'http://127.0.0.1:8333/api/v1';

test('the account headline rises phrase by phrase and stays readable in reduced motion', async({page})=>{
  await page.setViewportSize({width:1280,height:800});
  await page.goto('/en');
  const art=page.locator('.account-farm-art');
  await expect(art).toHaveCSS('animation-name','account-farm-arrive');
  const heading=page.getByRole('heading',{name:'From farm to market'});
  const phrases=heading.locator('.account-headline-line > span');
  await expect(phrases).toHaveText(['From farm', 'to market']);
  await expect(phrases.first()).toHaveCSS('animation-name','account-headline-enter');
  await expect(phrases.last()).toHaveCSS('animation-delay','0.22s');
  await expect.poll(() => phrases.last().evaluate(phrase =>
    phrase.getBoundingClientRect().top - phrase.parentElement!.getBoundingClientRect().top,
  )).toBe(0);
  const asset=await page.request.get('/account-farm-morning.webp');
  expect(asset.ok()).toBeTruthy();
  expect(asset.headers()['content-type']).toContain('image/webp');
  const modes=page.getByRole('group',{name:'Account options'});
  await modes.getByRole('button',{name:'Sign up',exact:true}).click();
  await expect(modes.getByRole('button',{name:'Sign up',exact:true})).toHaveAttribute('aria-pressed','true');
  await expect(page.getByRole('textbox',{name:'Full name'})).toBeVisible();
  await modes.getByRole('button',{name:'Sign in',exact:true}).click();
  await expect(page.getByRole('textbox',{name:'Full name'})).toHaveCount(0);

  await page.setViewportSize({width:375,height:812});
  await page.goto('/bn');
  const bengaliHeading=page.getByRole('heading',{name:'খামার থেকে বাজারে'});
  const bengaliPhrases=bengaliHeading.locator('.account-headline-line > span');
  await expect(bengaliPhrases).toHaveText(['খামার থেকে', 'বাজারে']);
  await expect(bengaliPhrases.last()).toHaveCSS('animation-name','account-headline-enter');
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.goto('/bn');
  await expect(art).toHaveCSS('animation-name','none');
  await expect(bengaliPhrases.first()).toHaveCSS('animation-name','none');
  await expect(bengaliPhrases.last()).toHaveCSS('transform','none');
  const signup=page.getByRole('button',{name:'অ্যাকাউন্ট খুলুন',exact:true});
  await signup.click();
  await expect(page.getByRole('heading',{name:'অ্যাকাউন্ট তৈরি করুন'})).toHaveCSS('animation-name','none');
  await expect(page.getByRole('textbox',{name:'পুরো নাম'})).toBeVisible();
  const dimensions=await page.evaluate(()=>({
    viewport:document.documentElement.clientWidth, content:document.documentElement.scrollWidth,
  }));
  expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport);
});

test('FloodCrop and Farm tools animate loaded content and respect reduced motion', async({page,request})=>{
  const demo=await request.post(api+'/auth/demo',{data:{}});
  expect(demo.ok()).toBeTruthy();
  const {token}=await demo.json();
  try {
    await page.addInitScript(value=>localStorage.setItem('agrosphere-token',value),token);
    await page.goto('/en/floodcrop');
    const total=page.locator('.rain-total');
    await expect(total).toBeVisible();
    await expect(total).toHaveCSS('animation-name','ui-rise');
    await expect(page.locator('.rain-result-chart .recharts-area')).toHaveCSS('animation-name','chart-sweep');
    await page.emulateMedia({reducedMotion:'reduce'});
    await expect(total).toHaveCSS('animation-name','none');
    await expect(page.locator('.rain-result-chart .recharts-area')).toHaveCSS('animation-name','none');
    await page.goto('/en/farm-tools');
    await page.getByRole('link',{name:'Cash ledger',exact:true}).click();
    await expect(page.getByRole('heading',{name:'Plot cash ledger'})).toBeVisible();
    await expect(page.locator('.ui-plot-panel')).toHaveCSS('animation-name','none');
  } finally {
    await request.delete(api+'/me',{headers:{Authorization:'Bearer '+token}});
  }
});
