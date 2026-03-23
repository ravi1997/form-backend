import { test, expect } from '@playwright/test';
import { createAuthenticatedContext } from '../../helpers/auth';

test.describe('Negative and Error Handling Tests', () => {

  test('should return 404 for non-existent resource', async () => {
    const { request } = await createAuthenticatedContext('user');
    const response = await request.get('/api/v1/forms/65c1234567890abcdef12345');
    expect(response.status()).toBe(404);
  });

  test('should return 401 for requests without token', async ({ request }) => {
    const response = await request.get('/api/v1/forms/');
    expect(response.status()).toBe(401);
  });

  test('should return 400 for malformed JSON payload', async () => {
    const { request } = await createAuthenticatedContext('creator');
    
    // Playwright `post` with `data` might handle JSON serialization, 
    // so we can use a raw body to test malformed JSON
    const response = await request.post('/api/v1/forms/', {
      headers: { 'Content-Type': 'application/json' },
      body: '{ "title": "Malformed", }' // trailing comma in JSON
    });
    
    expect(response.status()).toBe(400);
  });

  test('should return 415 for unsupported media type', async () => {
    const { request } = await createAuthenticatedContext('creator');
    
    const response = await request.post('/api/v1/forms/', {
      headers: { 'Content-Type': 'text/plain' },
      data: 'Some text'
    });
    
    expect([415, 400]).toContain(response.status());
  });

  test('should return 405 for unsupported method on a route', async () => {
    const { request } = await createAuthenticatedContext('user');
    
    // Assuming /api/v1/auth/login doesn't support GET
    const response = await request.get('/api/v1/auth/login');
    expect(response.status()).toBe(405);
  });

  test('should return 403 for cross-tenant resource access', async () => {
    const tenantA = await createAuthenticatedContext('creator');
    const createResp = await tenantA.request.post('/api/v1/forms/', { data: { title: 'Secret Form' } });
    const formId = (await createResp.json()).form_id;

    const tenantB = await createAuthenticatedContext('user');
    const response = await tenantB.request.get(`/api/v1/forms/${formId}`);
    
    // In many multi-tenant systems, it returns 404 to avoid leaking existence, 
    // but 403 is also possible if the ID is known.
    expect([403, 404]).toContain(response.status());
  });

});
