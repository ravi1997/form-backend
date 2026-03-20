import { test, expect } from '@playwright/test';

test.describe('System Health API', () => {

  test('should return health status', async ({ request }) => {
    await expect
      .poll(async () => {
        try {
          return (await request.get('/health/')).status();
        } catch (_error) {
          return 0;
        }
      }, {
        timeout: 10000,
        intervals: [250, 500, 1000],
      })
      .toBe(200);

    const response = await request.get('/health/');
    const body = await response.json();
    expect(['ok', 'healthy']).toContain(body.status);
    expect(body.dependencies || body.services).toBeDefined();
  });

});
