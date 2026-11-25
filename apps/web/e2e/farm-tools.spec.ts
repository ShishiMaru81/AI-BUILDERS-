import {expect, test, type Page, type APIRequestContext} from '@playwright/test';

const api = process.env.E2E_API_URL || 'http://127.0.0.1:8333/api/v1';

async function demo(page:Page, request:APIRequestContext) {
  const result = await request.post(api + '/auth/demo', {data:{}});
  expect(result.ok()).toBeTruthy();
  const {token} = await result.json();
  await page.addInitScript(value=>localStorage.setItem('agrosphere-token',value),token);
}

test('records farm tasks, cash and storage and reads an encrypted offline copy', async({page,context,request})=>{
  await demo(page,request);
  await page.goto('/en/farm-tools');
  await expect(page.getByRole('heading',{name:'Weekly crop advisory'})).toBeVisible();
  await page.getByLabel('Current crop stage').selectOption('Fruiting');
  await page.getByRole('button',{name:'Update growing details'}).click();
  await expect(page.getByText(/Inspect fruit for splits/)).toBeVisible();
  await page.getByRole('button',{name:'Remind me'}).first().click();
  await expect(page.getByRole('button',{name:'Complete',exact:true})).toBeVisible();

  await page.getByRole('link',{name:'Cash ledger',exact:true}).click();
  await page.getByLabel('Description').fill('Seed cost');
  await page.getByLabel('Amount in BDT').fill('10.25');
  await page.getByRole('button',{name:'Save entry'}).click();
  await expect(page.getByText('Seed cost',{exact:true})).toBeVisible();
  await page.getByLabel('Entry type').selectOption('receipt');
  await page.getByLabel('Description').fill('Cash sale');
  await page.getByLabel('Amount in BDT').fill('30.5');
  await page.getByRole('button',{name:'Save entry'}).click();
  await expect(page.getByText('৳20.25',{exact:true})).toBeVisible();
  await page.getByLabel('Expected sale weight (kg)').fill('2');
  await page.getByRole('button',{name:'Calculate'}).click();
  await expect(page.getByText('৳5.13 per kg')).toBeVisible();

  await page.getByRole('link',{name:'Storage',exact:true}).click();
  await page.getByLabel('Batch name').fill('West field harvest');
  await page.getByLabel('Stored weight (kg)').fill('12.5');
  await page.getByRole('button',{name:'Save batch'}).click();
  await expect(page.getByRole('heading',{name:'West field harvest'})).toBeVisible();
  await page.getByText('Log a storage event',{exact:true}).click();
  await page.getByLabel('Event type').selectOption('loss');
  await page.getByLabel('Observation or reason').fill('Soft produce');
  await page.getByLabel('Weight (kg)',{exact:true}).fill('2.5');
  await page.getByRole('button',{name:'Save event'}).click();
  await expect(page.getByText('10 kg',{exact:true})).toBeVisible();

  await page.getByRole('link',{name:'Community map'}).click();
  await expect(page.getByRole('img',{name:/Bangladesh district map/})).toBeVisible();
  await page.getByRole('combobox',{name:'District',exact:true}).selectOption({label:'Dhaka'});
  await expect(page.getByText(/Below the publication threshold/)).toBeVisible();

  await page.getByRole('link',{name:'Offline notebook',exact:true}).click();
  await page.getByLabel(/New notebook passphrase/).fill('a local notebook passphrase');
  await page.getByRole('button',{name:'Save encrypted copy'}).click();
  await expect(page.getByText(/Offline copy saved/)).toBeVisible();
  const stored = await page.evaluate(()=>localStorage.getItem('agrosphere-encrypted-notebook-v1'));
  expect(stored).toBeTruthy();
  expect(stored).not.toContain('Cash sale');
  await context.setOffline(true);
  await page.getByRole('link',{name:'Open offline notebook'}).click();
  await expect(page.getByRole('heading',{name:'Offline farm notebook'})).toBeVisible();
  await page.getByLabel(/Notebook passphrase/).fill('wrong password');
  await page.getByRole('button',{name:/Unlock/}).click();
  await expect(page.getByText(/Could not unlock/)).toBeVisible();
  await page.getByLabel(/Notebook passphrase/).fill('a local notebook passphrase');
  await page.getByRole('button',{name:/Unlock/}).click();
  await expect(page.getByText(/Cash sale/)).toBeVisible();
  await expect(page.getByText(/West field harvest.*10 kg/)).toBeVisible();
  page.once('dialog',dialog=>void dialog.accept());
  await page.getByRole('button',{name:/Delete offline copy/}).click();
  await expect(page.getByText(/Offline copy deleted/)).toBeVisible();
});

test('Bangla dictation fills an editable draft and does not send it', async({page,request})=>{
  await demo(page,request);
  await page.addInitScript(()=>{
    Object.defineProperty(window,'SpeechRecognition',{configurable:true,value:class {
      lang='';
      onresult?: (event:unknown)=>void;
      onend?: ()=>void;
      start(){
        if(this.lang==='bn-BD')this.onresult?.({results:[[{transcript:'পাতায় দাগ হয়েছে'}]]});
        this.onend?.();
      }
      stop(){this.onend?.();}
      abort(){this.onend?.();}
    }});
  });
  let sends=0;
  page.on('request',req=>{if(req.method()==='POST'&&req.url().includes('/farmer-chat/'))sends++;});
  await page.goto('/bn/farm-tools');
  await page.getByRole('button',{name:'কৃষি সহায়ক',exact:true}).click();
  await page.getByRole('button',{name:'বলে প্রশ্ন করুন'}).click();
  await expect(page.getByRole('textbox',{name:'আপনার প্রশ্ন'})).toHaveValue('পাতায় দাগ হয়েছে');
  await page.getByRole('textbox',{name:'আপনার প্রশ্ন'}).fill('টমেটোর পাতায় দাগ হয়েছে');
  expect(sends).toBe(0);
});
