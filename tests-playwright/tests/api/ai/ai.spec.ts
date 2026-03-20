import { test, expect } from '@playwright/test';
import { createAuthenticatedContext } from '../../../helpers/auth';

test.describe('AI Endpoints API', () => {

  test('should check AI health', async () => {
    // Health check might be public or require auth. Assuming public or low privilege.
    const { request } = await createAuthenticatedContext('user');
    
    const response = await request.get('/api/v1/ai/health');
    
    // Might be 200 (healthy) or 503 (unavailable) depending on setup
    expect([200, 503]).toContain(response.status());
    const body = await response.json();
    expect(body.status).toBeDefined();
  });

  test('should fail to summarize without required form_id', async () => {
    const { request } = await createAuthenticatedContext('creator');
    
    const response = await request.post('/api/v1/ai/invalid-form-id/summarize', {
      data: { max_bullet_points: 3 }
    });
    
    // Should be 404 since form doesn't exist
    expect(response.status()).toBe(404);
  });

});
