import {expect, test} from '@playwright/test';

const api = process.env.E2E_API_URL || 'http://127.0.0.1:8333/api/v1';

test('the farm truck plays once and the mobile dashboard respects reduced motion', async({page, request})=>{
  const session = await request.post(api+'/auth/demo', {data:{}});
  expect(session.ok()).toBeTruthy();
  const {token} = await session.json();
  try {
    await page.addInitScript(value=>localStorage.setItem('agrosphere-token', value), token);
    await page.goto('/en/dashboard');
    await page.getByTestId('farm-route-scene').scrollIntoViewIfNeeded();
    const truck = page.getByTestId('farm-route-truck');
    await expect(truck).toBeVisible();
    await expect(truck).toHaveCSS('animation-iteration-count', '1');
    await expect.poll(()=>truck.evaluate(element=>element.getAnimations().map(animation=>animation.playState))).toEqual(['finished']);
    await expect(page.getByRole('link',{name:'Compare selling prices',exact:true})).toHaveAttribute('href','/en/market');

    await page.emulateMedia({reducedMotion:'reduce'});
    await page.setViewportSize({width:375,height:812});
    await page.goto('/bn/dashboard');
    await expect(truck).toBeVisible();
    await expect(truck).toHaveCSS('animation-name','none');
    const scene = await page.getByTestId('farm-route-scene').boundingBox();
    expect(scene).not.toBeNull();
    expect(scene!.x + scene!.width).toBeLessThanOrEqual(375);
    await expect(page.getByRole('link',{name:'বিক্রির দাম তুলনা করুন',exact:true})).toHaveAttribute('href','/bn/market');
  } finally {
    await request.delete(api+'/me',{headers:{Authorization:'Bearer '+token}});
  }
});
