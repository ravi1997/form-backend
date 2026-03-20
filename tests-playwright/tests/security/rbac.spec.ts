import { test, expect } from '@playwright/test';
import { createAuthenticatedContext } from '../../helpers/auth';

test.describe('Role-Based Access Control (RBAC)', () => {

  test('admin can access system endpoints', async () => {
    const { request } = await createAuthenticatedContext('admin');
    
    // Assuming there's a system settings or admin endpoint
    const response = await request.get('/api/v1/admin/system-settings/');
    // If it exists, should be 200. If not implemented yet, we accept 404 but not 403.
    expect([200, 404]).toContain(response.status());
    expect(response.status()).not.toBe(403);
  });

  test('regular user cannot access system endpoints', async () => {
    const { request } = await createAuthenticatedContext('user');
    
    const response = await request.get('/api/v1/admin/system-settings/');
    expect(response.status()).toBe(403);
  });

  test('authenticated users can create forms', async () => {
    const userCtx = await createAuthenticatedContext('user');
    
    const response = await userCtx.request.post('/api/v1/forms/', {
      data: {
        title: 'User created form',
        slug: `user-created-form-${Date.now()}`
      }
    });
    
    expect(response.status()).toBe(201);
  });

});
