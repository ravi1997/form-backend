import { test, expect } from '@playwright/test';
import { createAuthenticatedContext } from '../../helpers/auth';

test.describe('Error Handling and Negative Tests', () => {

  test('should handle invalid JSON gracefully', async ({ request }) => {
    const response = await request.post('/api/v1/auth/login', {
      headers: {
        'Content-Type': 'application/json'
      },
      data: '{"broken_json":'
    });
    
    // Express/Flask generally returns 400 for bad JSON
    expect(response.status()).toBe(400);
  });

  test('should return 404 for unknown routes', async ({ request }) => {
    const response = await request.get('/api/v1/this-route-does-not-exist');
    expect(response.status()).toBe(404);
  });

  test('should return 401 for protected routes without token', async ({ request }) => {
    const response = await request.get('/api/v1/users/profile');
    expect(response.status()).toBe(401);
  });

  test('should reject invalid auth tokens', async ({ request }) => {
    const response = await request.get('/api/v1/users/profile', {
      headers: {
        'Authorization': 'Bearer invalid.token.here'
      }
    });
    expect([401, 422]).toContain(response.status());
  });

  test('should handle missing required fields in payload', async () => {
    const { request } = await createAuthenticatedContext('creator');
    
    // Creating a form without required title
    const response = await request.post('/api/v1/forms/', {
      data: { description: 'Missing title' }
    });
    
    expect(response.status()).toBe(400);
  });

});
