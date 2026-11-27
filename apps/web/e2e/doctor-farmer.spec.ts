import {test, expect} from '@playwright/test';
import type {Page} from '@playwright/test';

const api = process.env.E2E_API_URL || 'http://127.0.0.1:8300/api/v1';
const image = {name:'crop.png', mimeType:'image/png', buffer:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=', 'base64')};
const first = {
  crop:'potato', screening_locale:'en', photo_count:1, model:{version:'test-vision', model_id:'groq-vision'},
  classification:{abstained:false, top_label:'Possible internal decay'},
  assessment:{subject:'Potato tuber', part:'produce', crop_match:'unknown',
    outcome:'possible_condition', condition:'Possible internal decay', produce_finding:'internal_breakdown',
    signs:['Dark patches below the skin.'], explanation:'Discoloration extends beneath the skin.',
    uncertainty:'The precise cause remains unclear.'},
  advice:['Check other tubers in the batch.'],
  farmer_context:{kind:'produce',location:'storage',extent:'many',onset:'unknown'},
};
const second = {...first, photo_count:2, initial_assessment:first.assessment,
  assessment:{...first.assessment, explanation:'Both views show damage extending into the flesh.'}};

async function stubVision(page: Page) {
  await page.route('**/doctor/capabilities', async route => {
    const data = await (await route.fetch()).json();
    await route.fulfill({json:{...data, provider:'groq'}});
  });
}

test('reported answers, Bangla referral and follow-up survive an unsuccessful preview retry', async ({page,request}) => {
  const session = await (await request.post(api+'/auth/demo',{data:{}})).json();
  await page.addInitScript(token=>localStorage.setItem('agrosphere-token',token),session.token);
  await stubVision(page);
  let pairs=0;
  await page.route('**/doctor/cases', async route => {
    if(route.request().method()!=='POST') return route.continue();
    const body=route.request().postDataBuffer()!.toString('latin1');
    expect(body).toContain('name="farmer_context"');
    expect(body).toContain('"extent":"many"');
    expect(body).toContain('"location":"storage"');
    expect(body).not.toContain('name="plot_id"');
    if(body.includes('name="follow_up_image"')) {
      expect(body).toContain('name="image"');
      pairs++;
      if(pairs===1) return route.fulfill({status:503,json:{message:'Try again shortly.'}});
      return route.fulfill({json:second});
    }
    return route.fulfill({json:first});
  });
  await page.goto('/en/agrodoctor');
  await expect(page.getByLabel('Screening plot',{exact:true})).toHaveValue(session.plot_id);
  await page.getByLabel('Screening crop',{exact:true}).selectOption('potato');
  await page.getByRole('radio',{name:'Fruit, vegetable or tuber'}).check();
  await page.getByRole('radio',{name:'In storage'}).check();
  await page.getByRole('radio',{name:'Many items'}).check();
  await page.getByLabel('Upload crop photo',{exact:true}).setInputFiles(image);
  await page.getByRole('button',{name:'Screen photo',exact:true}).click();
  const result=page.getByRole('region',{name:'Screening result'});
  await expect(result.getByRole('heading').first()).toContainText('Possible internal decay');
  await expect(result.getByRole('heading',{name:'What should I do today?'})).toBeVisible();
  const referral = result.getByRole('link',{name:'Call the Agriculture Call Centre · 16123',exact:true});
  await expect(referral).toBeVisible();
  await expect(referral).toHaveAttribute('href','tel:16123');
  await expect(result.locator('p[lang=bn]')).toContainText('অনেক');
  await expect(result.locator('p[lang=bn]')).toContainText('আলু');
  await result.getByLabel('Second crop photo',{exact:true}).setInputFiles(image);
  await result.getByRole('button',{name:'Review both photos'}).click();
  await expect(result.getByRole('alert')).toHaveText('Try again shortly.');
  await expect(result).toContainText(first.assessment.explanation);
  await result.getByRole('button',{name:'Review both photos'}).click();
  await expect(result).toContainText(second.assessment.explanation);
  await result.getByText('See the second photo and the first assessment').click();
  await expect(result.getByAltText('Original crop photo')).toBeVisible();
  await expect(result.getByAltText('Second crop photo')).toBeVisible();
  await expect(result).toContainText(first.assessment.explanation);
  expect(pairs).toBe(2);
});

test('a second photo updates a reopened saved case at its original URL', async ({page,request}) => {
  const session=await (await request.post(api+'/auth/demo',{data:{}})).json();
  await page.addInitScript(token=>localStorage.setItem('agrosphere-token',token),session.token);
  await stubVision(page);
  const id='saved-photo-case';
  const base={id,crop:'potato',plot_id:session.plot_id,image_available:true,plot_name:'Potato plot',feedback:[]};
  let revised=false;
  await page.route('**/doctor/cases/'+id,route => route.fulfill({json:{
    ...(revised?second:first),...base,second_photo_available:revised,
  }}));
  await page.route('**/doctor/cases/'+id+'/image*',route=>route.fulfill({contentType:'image/png',body:image.buffer}));
  await page.route('**/doctor/cases/'+id+'/follow-up', route=>{
    expect(route.request().method()).toBe('POST'); revised=true;
    return route.fulfill({json:{...second,...base,second_photo_available:true}});
  });
  await page.goto('/en/agrodoctor/'+id);
  await page.getByLabel('Second crop photo',{exact:true}).setInputFiles(image);
  await page.getByRole('button',{name:'Review both photos'}).click();
  await expect(page.getByText(second.assessment.explanation)).toBeVisible();
  await page.reload();
  await expect(page.getByText('Both photos reviewed together')).toBeVisible();
  await page.getByText('See the second photo and the first assessment').click();
  await expect(page.getByAltText('Original crop photo')).toBeVisible();
  await expect(page.getByAltText('Second crop photo')).toBeVisible();
  await expect(page.getByText(first.assessment.explanation)).toBeVisible();
  expect(new URL(page.url()).pathname).toBe('/en/agrodoctor/'+id);
});

