import { test, expect } from '@playwright/test';
import { createAuthenticatedContext } from '../../../helpers/auth';

test.describe('Workflows API', () => {

  test('should fail to get non-existent workflow', async () => {
    const { request } = await createAuthenticatedContext('creator');
    
    const response = await request.get('/api/v1/workflows/invalid-id');
    expect(response.status()).toBe(404);
  });

  test('should require authentication to create workflow', async ({ request }) => {
    const response = await request.post('/api/v1/workflows/', {
      data: {
        name: 'Test Workflow',
        steps: []
      }
    });
    
    expect(response.status()).toBe(401);
  });

});
