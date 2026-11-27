import {expect, test} from '@playwright/test';

const overview = {
  generated_at: '2026-11-27T04:00:00Z',
  accounts: {total: 3, active: 3, demo: 1, farmer: 1, customer: 1, admin: 1, other: 0},
  records: {farm: 2, plot: 4, case: 5, farmer_chat: 7},
  marketplace: {listings: 3, orders: 2, auctions: 1, open_reports: 1, enabled: true},
};

test('sign-up links to a separate admin sign-in and a farmer session stays outside the panel', async ({page}) => {
  const protectedRequests: string[] = [];
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/v1/auth/admin/login') return route.fulfill({status:401, json:{message:'Invalid administrator email or password'}});
    if (path === '/api/v1/me') return route.fulfill({json:{id:'farmer', name:'Demo farmer', role:'farmer', preferences:{theme:'light'}}});
    if (path === '/api/v1/auth/options') return route.fulfill({json:{signup:true,demo:true}});
    if (path.startsWith('/api/v1/admin/')) protectedRequests.push(path);
    return route.fulfill({json:[]});
  });
  await page.goto('/en');
  await page.getByRole('button', {name:'Sign up', exact:true}).click();
  await expect(page.getByLabel('Account type').locator('option')).toHaveCount(2);
  await page.getByRole('link', {name:'Admin sign in'}).click();
  await expect(page).toHaveURL(/\/en\/admin$/);
  await expect(page.getByRole('heading', {name:'Admin sign in'})).toBeVisible();
  await page.getByLabel('Admin email').fill('farmer@example.test');
  await page.getByLabel('Password', {exact:true}).fill('test-farmer-password');
  await page.getByRole('button', {name:'Sign in as admin'}).click();
  await expect(page.getByRole('main').getByRole('alert')).toContainText('administrator email and password');
  await page.evaluate(() => localStorage.setItem('agrosphere-token', 'farmer-test'));
  await page.goto('/en/marketplace/admin');
  await expect(page).toHaveURL(/\/en\/admin$/);
  await expect(page.getByText(/current account has regular access/)).toBeVisible();
  expect(protectedRequests).toEqual([]);
});

test('admin sees the dashboard, searches users, reviews an open report and signs out on mobile', async ({page}) => {
  await page.setViewportSize({width:390, height:820});
  await page.addInitScript(() => {
    if (!sessionStorage.getItem('initial-admin-session')) {
      localStorage.setItem('agrosphere-token', 'admin-test');
      sessionStorage.setItem('initial-admin-session', '1');
    }
  });
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url());
    if (url.pathname.startsWith('/api/v1/admin/')) {
      expect(route.request().headers().authorization).toBe('Bearer admin-test');
    }
    if (url.pathname === '/api/v1/me') return route.fulfill({json:{id:'operator',name:'Test Operator',role:'admin',preferences:{theme:'light'}}});
    if (url.pathname === '/api/v1/admin/overview') return route.fulfill({json:overview});
    if (url.pathname === '/api/v1/admin/market/users') {
      const search = url.searchParams.get('search');
      return route.fulfill({json:{
        items:[{id:'seller', role:'customer', name: search === 'Nur' ? 'Nur Seller' : 'First Seller',
          email:'seller@example.test', is_active:true, verification_status:'pending'}], total:1, has_more:false,
      }});
    }
    if (url.pathname === '/api/v1/admin/market/reports') return route.fulfill({json:{
      items:[{id:'report', status:'open', reason:'Incorrect listing', created_at:'2026-11-27'}],
      total:1, has_more:false,
    }});
    return route.fulfill({json:{}});
  });
  await page.goto('/en/admin');
  await expect(page.getByRole('heading', {name:'Overview'})).toBeVisible();
  const nav = page.getByRole('navigation', {name:'Admin sections'});
  await expect(nav.getByRole('link', {name:'Overview'})).toHaveAttribute('aria-current','page');
  await nav.getByRole('link', {name:'Users'}).click();
  await page.getByRole('searchbox', {name:'Search records'}).fill('Nur');
  await page.getByRole('button', {name:'Search', exact:true}).click();
  await page.locator('summary').getByText('Nur Seller', {exact:true}).click();
  await expect(page.getByLabel('Seller verification')).toHaveValue('pending');
  await nav.getByRole('link', {name:'Reports'}).click();
  await page.locator('summary').getByText('Incorrect listing', {exact:true}).click();
  await expect(page.getByLabel('Report status')).toHaveValue('');
  await expect(page.getByText('Open · Select a decision')).toBeAttached();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(391);
  await page.getByRole('button', {name:'Sign out'}).click();
  await expect(page.getByRole('heading', {name:'Admin sign in'})).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem('agrosphere-token'))).toBeNull();
});
