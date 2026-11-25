import {expect, test, type Page} from '@playwright/test';

const plot = {id: 'field-one', farm_id: 'farm', name: 'East field', crop: 'rice', stage: 'growing', area_acres: '1', low_lying: false};
const question = 'What should I check today?';
const answer = {
  conversation_id: 'field-chat',
  messages: [
    {id: 'q1', role: 'user', text: question},
    {id: 'a1', role: 'assistant', mode: 'rag', text: 'Check the water level at the field edge.',
      sources: [{label: 'Field observation', detail: 'Farmer-entered record'},
        {label: 'BAMIS field drainage', detail: 'Check low areas for standing water.', url: 'https://www.bamis.gov.bd/bn/bulletin/view/46022/'}],
      actions: [
        {kind: 'note', label: 'Save as a note', target: 'case-note'},
        {kind: 'navigate', label: 'Open AgroDoctor', target: '/agrodoctor'},
        {kind: 'call', label: 'Call an adviser', target: 'tel:16123'},
        {kind: 'handoff', label: 'Prepare a handoff', target: 'I checked the water at the field edge.'},
      ]},
  ],
};

async function openWorkspace(page: Page, locale = 'en', plots = [plot]) {
  await page.addInitScript(() => localStorage.setItem('agrosphere-token', 'ui-fixture'));
  await page.route('**/api/v1/**', route => {
    const path = new URL(route.request().url()).pathname.replace('/api/v1', '');
    if (path.startsWith('/farmer-chat/')) return route.fallback();
    const preferences = {theme: 'light', language: locale, retraining_consent: false, selected_plot_id: plot.id};
    if (path === '/me' && route.request().method() === 'PATCH') return route.fulfill({json: {...preferences, ...route.request().postDataJSON()}});
    const values: Record<string, unknown> = {
      '/me': {id: 'farmer-test', name: 'Nur', role: 'farmer', preferences},
      '/plots': plots, '/farms': [{id: 'farm', name: 'My farm', district: 'Gazipur'}],
      '/doctor/cases': {items: [], total: 0, has_more: false},
      '/doctor/capabilities': {provider: 'groq', crops: []},
      '/doctor/models/current': {available: false, labels: [], limitations: []},
    };
    return route.fulfill({json: values[path] ?? []});
  });
  await page.goto('/' + locale + '/settings');
  await expect(page.getByRole('button', {name: locale === 'en' ? 'Farmer chat' : 'কৃষি সহায়ক', exact: true})).toBeVisible();
}

test('retry keeps the question, sources and explicit actions survive reload, and previous chats can be reopened', async ({page}) => {
  const attempts: string[] = [];
  let notes = 0;
  await page.route('**/farmer-chat/messages', async route => {
    expect(route.request().headers().authorization).toBe('Bearer ui-fixture');
    const body = route.request().postDataJSON();
    expect(body).toMatchObject({locale: 'en', plot_id: plot.id, message: question});
    attempts.push(body.request_id);
    await route.fulfill(attempts.length === 1 ? {status: 503, json: {message: 'temporarily busy'}} : {json: answer});
  });
  await page.route('**/farmer-chat/conversations/field-chat', route => route.fulfill({json: answer}));
  await page.route('**/farmer-chat/conversations?**', route => {
    expect(new URL(route.request().url()).searchParams.get('plot_id')).toBe(plot.id);
    return route.fulfill({json: {items: [{id: 'field-chat', updated_at: '2026-11-18T10:20:00Z'}]}});
  });
  await page.route('**/farmer-chat/conversations/field-chat/notes', async route => {
    notes++;
    expect(route.request().postDataJSON()).toEqual({message_id: 'a1'});
    await route.fulfill({json: {...answer, messages: [answer.messages[0], {...answer.messages[1],
      actions: answer.messages[1].actions!.map(action => ({...action, done: action.kind === 'note'})),
    }]}});
  });
  await openWorkspace(page);
  const launcher = page.getByRole('button', {name: 'Farmer chat', exact: true});
  await launcher.click();
  const chat = page.getByRole('dialog', {name: 'Farmer chat'});
  await expect(chat).toContainText('East field');
  const input = chat.getByRole('textbox', {name: 'Your question'});
  await input.fill(question);
  await input.press('Enter');
  await expect(chat.getByRole('alert')).toBeVisible();
  await expect(input).toHaveValue(question);
  await chat.getByRole('button', {name: 'Retry'}).click();
  await expect(chat).toContainText('Farmer-entered record');
  await expect(chat.getByText('AI reply with sources')).toBeVisible();
  await expect(chat.getByRole('link', {name: 'BAMIS field drainage'})).toHaveAttribute('href', 'https://www.bamis.gov.bd/bn/bulletin/view/46022/');
  expect(attempts[0]).toBeTruthy();
  expect(attempts[0]).toBe(attempts[1]);
  await expect(chat.getByRole('link', {name: 'Open AgroDoctor'})).toHaveAttribute('href', '/en/agrodoctor');
  await expect(chat.getByRole('link', {name: 'Call an adviser'})).toHaveAttribute('href', 'tel:16123');
  await chat.getByText('Prepare a handoff').click();
  await chat.getByRole('textbox', {name: 'Handoff text'}).fill('Edited for my adviser.');
  expect(notes).toBe(0);
  await chat.getByRole('button', {name: 'Save as a note'}).click();
  await expect(chat.getByRole('button', {name: 'Note saved'})).toBeDisabled();
  expect(notes).toBe(1);
  await chat.getByRole('button', {name: 'Close chat'}).press('Escape');
  await expect(launcher).toBeFocused();
  await page.reload();
  await launcher.click();
  await expect(chat).toContainText(answer.messages[1].text);
  await chat.getByRole('button', {name: 'New chat'}).click();
  await expect(chat).not.toContainText(answer.messages[1].text);
  await chat.getByRole('button', {name: 'Previous chats'}).click();
  await chat.getByRole('button', {name: /Conversation 1/}).click();
  await expect(chat).toContainText(answer.messages[1].text);
  await page.evaluate(() => {
    for (const key of Object.keys(localStorage)) if (key.startsWith('agrosphere-farmer-chat:')) localStorage.removeItem(key);
  });
  await page.reload();
  await launcher.click();
  await chat.getByRole('button', {name: 'Previous chats'}).click();
  await chat.getByRole('button', {name: /Conversation 1/}).click();
  await expect(chat).toContainText(answer.messages[1].text);
  await page.reload();
  await launcher.click();
  await expect(chat).toContainText(answer.messages[1].text);
});

test('Bengali mobile chat scopes a saved case and leaves preview drafts editable', async ({page}) => {
  await page.setViewportSize({width: 360, height: 640});
  const sent: Record<string, unknown>[] = [];
  await page.route('**/farmer-chat/messages', async route => {
    const body = route.request().postDataJSON();
    sent.push(body);
    await route.fulfill({json: {conversation_id: 'case-chat', messages: [
      {id: 'q', role: 'user', text: body.message}, {id: 'a', role: 'assistant', mode: 'limited', text: 'পাতার দুই পাশ দেখুন।'},
    ]}});
  });
  await openWorkspace(page, 'bn');
  const open = (detail: {draft?: string; caseId?: string; plotId?: string}) =>
    page.evaluate(value => window.dispatchEvent(new CustomEvent('agrosphere:open-farmer-chat', {detail: value})), detail);
  await open({draft: 'আমার ছবিতে পাতার দাগ দেখা যাচ্ছে।'});
  const chat = page.getByRole('dialog', {name: 'কৃষি সহায়ক'});
  const input = chat.getByRole('textbox', {name: 'আপনার প্রশ্ন'});
  await expect(input).toHaveValue('আমার ছবিতে পাতার দাগ দেখা যাচ্ছে।');
  expect(sent).toHaveLength(0);
  await expect(async () => {
    const bounds = await chat.boundingBox();
    expect(bounds).not.toBeNull();
    expect(bounds!.x).toBeGreaterThanOrEqual(0);
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(360);
    expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(640);
  }).toPass({timeout:5000});
  await open({caseId: 'saved-screening'});
  await expect(input).toHaveValue('');
  await chat.getByRole('button', {name: 'এই ফলাফলের মানে কী?'}).click();
  await expect(chat).toContainText('পাতার দুই পাশ দেখুন।');
  expect(sent[0]).toMatchObject({locale: 'bn', case_id: 'saved-screening', message: 'এই ফলাফলের মানে কী?'});
  expect(sent[0]).not.toHaveProperty('plot_id');
});

test('switching plots clears the previous case and ignores its late reply', async ({page}) => {
  const second = {...plot, id: 'field-two', name: 'West field'};
  let release: () => void = () => {};
  const delayed = new Promise<void>(resolve => {release = resolve;});
  await page.route('**/farmer-chat/messages', async route => {
    const body = route.request().postDataJSON();
    if (body.case_id) {
      await delayed;
      return route.fulfill({json: answer});
    }
    expect(body).toMatchObject({plot_id: second.id});
    await route.fulfill({json: {conversation_id: 'west-chat', messages: [{id: 'west', role: 'assistant', text: 'West field has a separate record.'}]}});
  });
  await openWorkspace(page, 'en', [plot, second]);
  await expect(page.getByLabel('Select plot')).toHaveValue(plot.id);
  await page.evaluate(() => window.dispatchEvent(new CustomEvent('agrosphere:open-farmer-chat', {detail: {caseId: 'east-case', plotId: 'field-one'}})));
  const chat = page.getByRole('dialog', {name: 'Farmer chat'});
  await chat.getByRole('button', {name: 'What does this result mean?'}).click();
  await expect(chat.getByRole('status')).toHaveText('Preparing a reply…');
  await page.getByLabel('Select plot').selectOption(second.id);
  await expect(chat).toContainText('West field');
  release();
  await chat.getByRole('textbox', {name: 'Your question'}).fill('What is on this plot?');
  await chat.getByRole('button', {name: 'Send message'}).click();
  await expect(chat).toContainText('West field has a separate record.');
  await expect(chat).not.toContainText(answer.messages[1].text);
});
