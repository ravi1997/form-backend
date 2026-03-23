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
    expect(body.data.username).toBe(user.username);
  });

  test('admin can list users in their organization', async () => {
    const { request, user } = await createAuthenticatedContext('admin');
    
    const response = await request.get('/api/v1/users/users');
    expect(response.status()).toBe(200);
    
    const body = await response.json();
    expect(body.success).toBe(true);
    expect(body.data.items).toBeInstanceOf(Array);
    
    // Check if the current admin is in the list
    const foundUser = body.data.items.find((u: any) => u.email === user.email);
    expect(foundUser).toBeDefined();
  });

  test('regular user cannot list users', async () => {
    const { request } = await createAuthenticatedContext('user');
    
    const response = await request.get('/api/v1/users/users');
    expect(response.status()).toBe(403);
  });

  test('admin can update user roles', async () => {
    const adminCtx = await createAuthenticatedContext('admin');
    const userCtx = await createAuthenticatedContext('user', adminCtx.user.organization_id);
    const userId = userCtx.user.id;
    
    const response = await adminCtx.request.put(`/api/v1/users/users/${userId}/roles`, {
      data: { roles: ['creator', 'user'] }
    });
    
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.success).toBe(true);
    
    // Verify update
    const profileResp = await userCtx.request.get('/api/v1/users/profile');
    const profileBody = await profileResp.json();
    expect(profileBody.data.roles).toContain('creator');
  });

  test('user cannot update their own roles', async () => {
    const { request, user } = await createAuthenticatedContext('user');
    
    const response = await request.put(`/api/v1/users/users/${user.id}/roles`, {
      data: { roles: ['admin'] }
    });
    
    expect(response.status()).toBe(403);
  });

});
