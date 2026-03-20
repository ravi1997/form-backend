import { test, expect } from '@playwright/test';
import { createAuthenticatedContext } from '../../../helpers/auth';

test.describe('Analytics API', () => {

  test('admin should get dashboard stats', async () => {
    const { request } = await createAuthenticatedContext('admin');
    
    const response = await request.get('/api/v1/analytics/dashboard');
    expect(response.status()).toBe(200);
    
    const body = await response.json();
    expect(body.success).toBe(true);
    expect(body.data.total_forms).toBeDefined();
  });

  test('regular user should not access analytics dashboard', async () => {
    const { request } = await createAuthenticatedContext('user');
    
    const response = await request.get('/api/v1/analytics/dashboard');
    expect(response.status()).toBe(403);
  });

});
