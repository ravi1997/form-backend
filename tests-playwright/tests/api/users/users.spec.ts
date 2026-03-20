import { test, expect } from '@playwright/test';
import { createAuthenticatedContext } from '../../../helpers/auth';

test.describe('Users API', () => {

  test('should get current user profile', async () => {
    const { request, user } = await createAuthenticatedContext('user');
    
    const response = await request.get('/api/v1/users/profile');
    expect(response.status()).toBe(200);
    
    const body = await response.json();
    expect(body.success).toBe(true);
    expect(body.data.email).toBe(user.email);
  });

  test('admin can list users', async () => {
    const { request } = await createAuthenticatedContext('admin');
    
    const response = await request.get('/api/v1/users/users');
    expect(response.status()).toBe(200);
    
    const body = await response.json();
    expect(body.success).toBe(true);
    expect(body.data.items).toBeInstanceOf(Array);
  });

  test('regular user cannot list users', async () => {
    const { request } = await createAuthenticatedContext('user');
    
    const response = await request.get('/api/v1/users/users');
    expect(response.status()).toBe(403);
  });

});
