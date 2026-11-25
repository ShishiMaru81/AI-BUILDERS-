import {expect, test} from '@playwright/test';

const api=process.env.E2E_API_URL||'http://127.0.0.1:8333/api/v1';

test('new account can reach the farm and plot setup without an invalid weather request', async({page,request})=>{
  const account=await request.post(api+'/auth/register',{data:{
    name:'Flood grower',email:`flood-${crypto.randomUUID()}@example.test`,password:'Example password 275!',role:'farmer',
  }});
  expect(account.ok()).toBeTruthy();
  const {token}=await account.json();
  await page.addInitScript(t=>localStorage.setItem('agrosphere-token',t),token);
  const urls:string[]=[];
  page.on('request',r=>{if(r.url().includes('/flood/plots/'))urls.push(r.url())});
  await page.goto('/en/floodcrop');
  const setup=page.getByRole('link',{name:'Set up a farm and plot',exact:true});
  await expect(setup).toHaveAttribute('href','/en/farms');
  await expect(page.getByRole('checkbox',{name:/low-lying/})).toHaveCount(0);
  await setup.click();
  await expect(page.getByRole('heading',{name:'Create a farm',exact:true})).toBeVisible();
  expect(urls).toEqual([]);
});

test('live outages have retry; switching to an unlocated plot resets the source',async({page,request})=>{
  const session=await (await request.post(api+'/auth/demo',{data:{}})).json();
  const headers={Authorization:'Bearer '+session.token};
  const [farm]=await (await request.get(api+'/farms',{headers})).json();
  const location=await request.patch(api+'/farms/'+farm.id+'/location',{headers,data:{
    latitude:24.8,longitude:91.8,location_name:'Sylhet location',district:'Sylhet',country:'Bangladesh',location_consent:true,
  }});
  expect(location.ok()).toBeTruthy();
  const other=await (await request.post(api+'/farms',{headers,data:{name:'District only farm',district:'Dhaka'}})).json();
  const plot=await (await request.post(api+'/plots',{headers,data:{farm_id:other.id,name:'District only plot',crop:'tomato',area_acres:1,stage:'Vegetative'}})).json();
  await page.addInitScript(t=>localStorage.setItem('agrosphere-token',t),session.token);
  let fail=true;
  const invalid:string[]=[];
  await page.route('**/flood/plots/*/outlook?*',async route=>{
    const url=new URL(route.request().url());
    if(url.searchParams.get('mode')==='LIVE'){
      if(url.pathname.includes(plot.id))invalid.push(url.href);
      if(fail)return route.fulfill({status:503,json:{message:'Weather unavailable'}});
      return route.fulfill({json:{
        hourly:[{time:'2026-11-20T00:00:00Z',rain_mm:12}],total_mm:12,horizon_hours:48,
        threshold_mm:75,level:'monitor',reasons:[],disclaimer:'fixture',
        meta:{mode:'LIVE',source_name:'Test forecast',is_simulated:false},
      }});
    }
    return route.continue();
  });
  await page.goto('/en/floodcrop');
  await page.getByLabel('Select plot',{exact:true}).selectOption(session.plot_id);
  await page.getByLabel('Weather data mode').selectOption('DEMO');
  await page.getByLabel('Weather data mode').selectOption('LIVE');
  await expect(page.getByRole('alert').filter({hasText:'Weather unavailable'})).toBeVisible();
  await expect(page.getByText('Monitor conditions',{exact:true})).toHaveCount(0);
  await expect(page.getByTestId('rain-outlook-scene')).toHaveCount(0);
  fail=false;
  await page.getByRole('button',{name:'Retry forecast'}).click();
  await expect(page.getByText('Test forecast',{exact:true})).toBeVisible();
  await page.getByLabel('Select plot',{exact:true}).selectOption(plot.id);
  await expect(page.getByLabel('Weather data mode')).toHaveValue('DEMO');
  await expect(page.locator('option[value="LIVE"]')).toBeDisabled();
  await expect(page.getByText('Test forecast',{exact:true})).toHaveCount(0);
  expect(invalid).toEqual([]);
});

test('the forecast scene follows the selected window and reduced-motion preference', async({page,request})=>{
  const demo=await request.post(api+'/auth/demo',{data:{}});
  expect(demo.ok()).toBeTruthy();
  const {token}=await demo.json();
  try {
    await page.setViewportSize({width:390,height:840});
    await page.addInitScript(value=>localStorage.setItem('agrosphere-token',value),token);
    await page.route('**/flood/plots/*/outlook?*', route=>{
      const horizon=Number(new URL(route.request().url()).searchParams.get('horizon_hours'));
      const expired=horizon===72;
      const total=horizon===24?0:12;
      return route.fulfill({json:{
        hourly:[{time:'2026-11-25T00:00:00Z',rain_mm:total}],
        total_mm:total,horizon_hours:horizon,threshold_mm:75,level:'monitor',
        reasons:[],disclaimer:'Simulated QA fixture',is_expired:expired,
        meta:{mode:'DEMO',source_name:'QA simulation',is_simulated:true,freshness:expired?'expired':'fresh'},
      }});
    });
    await page.goto('/en/floodcrop');
    const scene=page.getByTestId('rain-outlook-scene');
    const rain=page.getByTestId('rain-outlook-streaks');
    await expect(scene).toBeVisible();
    await expect(page.getByText('Simulated scenario',{exact:true})).toBeVisible();
    await expect(rain).toBeVisible();
    expect(await rain.evaluate(el=>getComputedStyle(el,'::before').animationName)).not.toBe('none');
    await page.emulateMedia({reducedMotion:'reduce'});
    expect(await rain.evaluate(el=>getComputedStyle(el,'::before').animationName)).toBe('none');
    const window=page.getByRole('group',{name:'Forecast window'});
    const dry=window.getByRole('button',{name:'24 hours',exact:true});
    await dry.click();
    await expect(dry).toHaveAttribute('aria-pressed','true');
    await expect(page.locator('.rain-total')).toHaveText('0mm');
    await expect(scene).toBeVisible();
    await expect(rain).toHaveCount(0);
    await window.getByRole('button',{name:'72 hours',exact:true}).click();
    await expect(page.getByText('Forecast expired',{exact:true})).toBeVisible();
    await expect(scene).toHaveCount(0);
    const viewport=await page.evaluate(()=>({width:document.documentElement.clientWidth,content:document.documentElement.scrollWidth}));
    expect(viewport.content).toBeLessThanOrEqual(viewport.width);
  } finally {
    await request.delete(api+'/me',{headers:{Authorization:'Bearer '+token}});
  }
});
