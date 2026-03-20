import { test, expect, request as playwrightRequest } from '@playwright/test';
import { generateTestUser } from '../../../helpers/data-factory';
import { createAuthenticatedContext } from '../../../helpers/auth';

test.describe('Authentication API', () => {
  
  test('should register a new user successfully', async ({ request }) => {
    const userData = generateTestUser();
    
    const response = await request.post('/api/v1/auth/register', {
      data: userData,
      headers: {
        'X-Organization-ID': userData.organization_id,
      },
    });
    
    expect(response.status()).toBe(201);
    const body = await response.json();
    expect(body.success).toBe(true);
    expect(body.data.user).toBeDefined();
    expect(body.data.user.email).toBe(userData.email);
  });

  test('should fail to register with invalid email', async ({ request }) => {
    const userData = generateTestUser();
    userData.email = "invalid-email";
    
    const response = await request.post('/api/v1/auth/register', {
      data: userData,
      headers: {
        'X-Organization-ID': userData.organization_id,
      },
    });
    
    expect(response.status()).toBe(400);
    const body = await response.json();
    expect(body.success).toBe(false);
  });

  test('should login successfully with valid credentials', async ({ request }) => {
    const userData = generateTestUser();
    await request.post('/api/v1/auth/register', {
      data: userData,
      headers: {
        'X-Organization-ID': userData.organization_id,
      },
    });
    
    const response = await request.post('/api/v1/auth/login', {
      data: {
        identifier: userData.email,
        password: userData.password
      },
      headers: {
        'X-Organization-ID': userData.organization_id,
      },
    });
    
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.success).toBe(true);
    expect(body.data.access_token).toBeDefined();
    expect(body.data.refresh_token).toBeDefined();
    
    // Verify cookies are set
    const cookies = response.headers()['set-cookie'];
    expect(cookies).toBeDefined();
    expect(cookies).toContain('access_token_cookie');
  });

  test('should fail to login with invalid credentials', async ({ request }) => {
    const response = await request.post('/api/v1/auth/login', {
      data: {
        identifier: 'nonexistent@example.com',
        password: 'wrongpassword'
      },
      headers: {
        'X-Organization-ID': `playwright-org-invalid-${Date.now()}`,
      },
    });
    
    expect(response.status()).toBe(401);
    const body = await response.json();
    expect(body.success).toBe(false);
  });

  test('should refresh token successfully', async () => {
    const { refreshToken } = await createAuthenticatedContext();
    const refreshRequest = await playwrightRequest.newContext({
      baseURL: process.env.API_BASE_URL || 'http://localhost:8051',
      ignoreHTTPSErrors: true,
      extraHTTPHeaders: {
        'Authorization': `Bearer ${refreshToken}`,
        'Accept': 'application/json',
        'Content-Type': 'application/json',
      },
    });
    
    const response = await refreshRequest.post('/api/v1/auth/refresh');
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.success).toBe(true);
    expect(body.access_token).toBeDefined();

    await refreshRequest.dispose();
  });

  test('should logout successfully', async () => {
    const { request: authRequest } = await createAuthenticatedContext();
    
    const response = await authRequest.post('/api/v1/auth/logout');
    expect(response.status()).toBe(200);
    
    const cookies = response.headers()['set-cookie'];
    expect(cookies).toContain('access_token_cookie=;');
  });

});
