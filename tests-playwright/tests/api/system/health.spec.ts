import { test, expect } from '@playwright/test';

test.describe('System Health API', () => {

  test('should return health status with services information', async ({ request }) => {
    // Wait for backend to be ready
    await expect.poll(async () => {
      try {
        return (await request.get('/health/')).status();
      } catch {
        return 0;
      }
    }, { timeout: 15000 }).toBe(200);

    const response = await request.get('/health/');
    const body = await response.json();
    
    expect(body.status).toBeDefined();
    expect(['ok', 'healthy', 'degraded']).toContain(body.status);
    
    // Check for dependencies info if available
    if (body.dependencies) {
      expect(body.dependencies.mongodb).toBeDefined();
      expect(body.dependencies.redis).toBeDefined();
    }
  });

  test('should have a working ping endpoint if available', async ({ request }) => {
    const response = await request.get('/health/ping');
    // If ping exists, expect 200. If not, expect 404 but don't fail test if it's optional.
    expect([200, 404]).toContain(response.status());
    if (response.status() === 200) {
      const body = await response.json();
      expect(body.message).toBe('pong');
    }
  });

});
