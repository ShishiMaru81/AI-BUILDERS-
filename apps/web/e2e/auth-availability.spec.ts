import {test, expect} from '@playwright/test';

test('customer signs up and returns with an email and password', async ({page}) => {
  const email = `customer-${crypto.randomUUID()}@example.test`;
  const password = 'Test-customer-9842';
  const otpRequests: string[] = [];
  page.on('request', req => { if (req.url().includes('/auth/otp/')) otpRequests.push(req.url()); });
  await page.goto('/en/marketplace/auth');
  await page.getByRole('button', {name: 'Sign up', exact: true}).click();
  await page.getByLabel('Full name').fill('Test Customer');
  await page.getByLabel('Age in years').fill('29');
  await page.getByLabel('Account type').selectOption('customer');
  await page.getByLabel('Bangladesh national ID number').fill('0123456789012');
  await page.getByLabel('Gender').selectOption('female');
  await page.getByLabel('Permanent address').fill('Sample permanent address');
  await page.getByLabel('Present address').fill('Sample present address');
  await page.getByLabel('Ward number').fill('5');
  await page.getByLabel('Passport-size photo').setInputFiles('public/crops/tomato.jpg');
  await page.getByLabel('Set password').fill(password);
  await page.getByLabel('Confirm password').fill(password);
  await page.getByLabel('Account contact').selectOption('email');
  await page.getByLabel('Email address').fill(email);
  await page.getByRole('button', {name: 'Create account'}).click();
  await expect(page.getByRole('link', {name: 'Buy produce', exact: true})).toBeVisible();
  await page.evaluate(() => localStorage.removeItem('agrosphere-token'));
  await page.goto('/en');
  await page.getByLabel('Account contact').selectOption('email');
  await page.getByLabel('Email address').fill(email);
  await page.getByLabel('Password', {exact: true}).fill(password);
  await page.locator('form').getByRole('button', {name: 'Sign in', exact: true}).click();
  await expect(page.getByRole('link', {name: 'Buy produce', exact: true})).toBeVisible();
  await expect(page.getByRole('link', {name: 'Sell produce', exact: true})).toHaveCount(0);
  expect(otpRequests).toEqual([]);
});

for (const {locale, viewport, demo, signOut, signUp} of [
  {locale:'en', viewport:{width:1440,height:768}, demo:'Explore a demo farm', signOut:'Sign out', signUp:'Sign up'},
  {locale:'bn', viewport:{width:360,height:780}, demo:'ডেমো খামার দেখুন', signOut:'বের হন', signUp:'অ্যাকাউন্ট খুলুন'},
]) {
  test(`dashboard sign-out is visible and returns to account access (${locale})`, async ({page}) => {
    await page.setViewportSize(viewport);
    await page.goto(`/${locale}`);
    await page.getByRole('button', {name:demo, exact:true}).click();
    await expect(page).toHaveURL(new RegExp(`/${locale}/dashboard$`));
    const button = page.locator('.topbar').getByRole('button', {name:signOut, exact:true});
    await expect(button).toBeInViewport({ratio:1, timeout:8000});
    const [logout] = await Promise.all([
      page.waitForResponse(response => response.url().endsWith('/auth/logout') && response.request().method() === 'POST'),
      button.click(),
    ]);
    expect(logout.ok()).toBe(true);
    await expect(page).toHaveURL(new RegExp(`/${locale}$`));
    await expect(page.getByRole('button', {name:signUp, exact:true})).toBeVisible();
    expect(await page.evaluate(() => localStorage.getItem('agrosphere-token'))).toBeNull();
  });
}
