import {readFile} from 'node:fs/promises';
import {expect, test} from '@playwright/test';

const api = process.env.E2E_API_URL || 'http://127.0.0.1:8000/api/v1';

test('the copilot keeps a check-in and a plot reminder across reloads on mobile', async ({page, request}) => {
  await page.setViewportSize({width: 390, height: 820});
  await page.emulateMedia({reducedMotion: 'reduce'});
  const login = await request.post(api + '/auth/demo', {data: {}});
  expect(login.ok()).toBeTruthy();
  const session = await login.json();
  const screened = await request.post(api + '/doctor/cases', {
    headers: {Authorization: 'Bearer ' + session.token},
    multipart: {
      plot_id: session.plot_id,
      plant_part: 'leaf',
      screening_mode: 'local_leaf',
      image: {name:'sample-crop.jpg', mimeType:'image/jpeg', buffer:await readFile('public/crops/tomato.jpg')},
    },
  });
  expect(screened.ok()).toBeTruthy();
  const {id} = await screened.json();
  const route = '/en/agrodoctor/' + id;
  await page.addInitScript(token => localStorage.setItem('agrosphere-token', token), session.token);
  await page.goto(route);
  const copilot = page.getByRole('region', {name:'AgroDoctor Follow-up Copilot'});
  await expect(copilot).toBeVisible();
  await copilot.getByRole('button', {name:'Check-in', exact:true}).click();
  await copilot.getByRole('radio', {name:'Getting worse'}).check();
  await copilot.getByLabel('What did you notice? (optional)', {exact:true}).fill('Three additional plants have spots.');
  await copilot.getByRole('button', {name:'Save check-in'}).click();
  await expect(copilot.getByText('Check-in saved.', {exact:true})).toBeVisible();
  await expect(copilot.getByRole('link', {name:/Call an adviser/})).toHaveAttribute('href','tel:16123');
  const panel = copilot.getByRole('heading', {name:'How does it look today?'}).locator('..');
  expect(await panel.evaluate(element => getComputedStyle(element).animationName)).toBe('none');

  await copilot.getByRole('button', {name:'Reminder', exact:true}).click();
  const due = new Intl.DateTimeFormat('en-CA', {
    timeZone:'Asia/Dhaka', year:'numeric', month:'2-digit', day:'2-digit',
  }).format(Date.now() + 7 * 24 * 60 * 60 * 1000);
  await copilot.getByLabel('Recheck date').fill(due);
  await copilot.getByRole('button', {name:'Save reminder'}).click();
  await expect(copilot.getByText('Recheck reminder saved.', {exact:true})).toBeVisible();
  await page.reload();
  await copilot.getByRole('button', {name:'Check-in', exact:true}).click();
  await expect(copilot.getByText('Three additional plants have spots.', {exact:true})).toBeVisible();
  await copilot.getByRole('button', {name:'Reminder', exact:true}).click();
  await expect(copilot.getByLabel('Recheck date')).toHaveValue(due);

  await copilot.getByRole('button', {name:'Ask about this screening'}).click();
  const chat = page.getByRole('dialog', {name:'Farmer chat'});
  await expect(chat.getByRole('textbox', {name:'Your question'})).toHaveValue(/saved crop screening/);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(391);
  await page.goto('/en/farm-tools');
  await expect(page.getByRole('link',{name:'Open screening',exact:true})).toHaveAttribute('href',route);
  const removed = await request.delete(api + '/doctor/cases/' + id, {
    headers: {Authorization: 'Bearer ' + session.token},
  });
  expect(removed.ok()).toBeTruthy();
});

test('a supported screening shows the referenced fungicide and opens case-scoped treatment chat', async ({page, request}) => {
  const session = await (await request.post(api + '/auth/demo', {data: {}})).json();
  await page.addInitScript(token => localStorage.setItem('agrosphere-token', token), session.token);
  const id = 'saved-treatment-screening';
  const treatment = {
    status: 'registry_reference',
    summary: 'The photo suggests late blight. Ask a local agricultural extension officer to confirm it before choosing a treatment.',
    steps: ['Verify the current Bangladesh label for the crop and disease.'],
    products: [{name:'Revus 250 SC', ingredient:'Mandipropamid', registration:'AP-2534'}],
    sources: [{label:'DAE pesticide directory', url:'https://prism.dae.gov.bd/pesticide-list'}],
  };
  await page.route('**/doctor/cases/' + id, route => route.fulfill({json: {
    id, plot_id:session.plot_id, crop:'potato', status:'completed', quality_flags:[], advice:[],
    model:{model_id:'groq-vision',version:'test-vision'},
    classification:{abstained:false,top_label:'Late blight'},
    assessment:{part:'leaf',outcome:'possible_condition',subject:'Potato leaf',condition:'Late blight',
      signs:['Pale growth along lesion edges.'],explanation:'Compare with the existing field signs.',
      uncertainty:'This is a photo-based screening.'},
    treatment_guidance:{en:treatment,bn:treatment},
  }}));
  await page.route('**/doctor/cases/' + id + '/image', route => route.fulfill({status:410, json:{message:'Photo unavailable'}}));
  await page.goto('/en/agrodoctor/' + id);
  const copilot = page.getByRole('region', {name:'AgroDoctor Follow-up Copilot'});
  await expect(copilot.getByRole('heading', {name:'Treatment guidance'})).toBeVisible();
  await expect(copilot.getByText('Revus 250 SC', {exact:false})).toBeVisible();
  await expect(copilot.getByText('AP-2534', {exact:true})).toBeVisible();
  await expect(copilot.getByRole('link', {name:'DAE pesticide directory'})).toHaveAttribute('href', 'https://prism.dae.gov.bd/pesticide-list');
  await copilot.getByRole('button', {name:'Ask about treatment'}).click();
  await expect(page.getByRole('dialog', {name:'Farmer chat'}).getByRole('textbox', {name:'Your question'}))
    .toHaveValue(/treatment options.*saved crop screening/);
});
