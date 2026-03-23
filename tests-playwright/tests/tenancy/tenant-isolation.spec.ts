import { test, expect } from '@playwright/test';
import { generateTestForm, generateTestResponse } from '../../helpers/data-factory';
import { createAuthenticatedContext } from '../../helpers/auth';

test.describe('Tenant Isolation API', () => {

  test('user from tenant A cannot see forms from tenant B', async () => {
    // 1. Setup Tenant A
    const tenantA = await createAuthenticatedContext('creator');
    const formA = generateTestForm();
    const createRespA = await tenantA.request.post('/api/v1/forms/', { data: formA });
    const formIdA = (await createRespA.json()).form_id;

    // 2. Setup Tenant B
    const tenantB = await createAuthenticatedContext('creator');
    
    // 3. Tenant B tries to access Tenant A's form
    const getResp = await tenantB.request.get(`/api/v1/forms/${formIdA}`);
    expect([403, 404]).toContain(getResp.status());
  });

  test('user from tenant A cannot see responses from tenant B', async () => {
    // 1. Setup Tenant A
    const tenantA = await createAuthenticatedContext('creator');
    const formA = generateTestForm();
    const createRespA = await tenantA.request.post('/api/v1/forms/', { data: formA });
    const formIdA = (await createRespA.json()).form_id;
    
    // Publish and submit a response in Tenant A
    await tenantA.request.post(`/api/v1/forms/${formIdA}/publish`, { data: { minor: true } });
    const responseA = generateTestResponse();
    const submitRespA = await tenantA.request.post(`/api/v1/forms/${formIdA}/responses`, { data: responseA });
    const responseIdA = (await submitRespA.json()).response_id;

    // 2. Setup Tenant B
    const tenantB = await createAuthenticatedContext('admin');
    
    // 3. Tenant B tries to access Tenant A's response
    const getResp = await tenantB.request.get(`/api/v1/forms/${formIdA}/responses/${responseIdA}`);
    expect([403, 404]).toContain(getResp.status());
    
    const listResp = await tenantB.request.get(`/api/v1/forms/${formIdA}/responses`);
    expect([403, 404]).toContain(listResp.status());
  });

  test('analytics results should be tenant-scoped', async () => {
    const tenantA = await createAuthenticatedContext('admin');
    const tenantB = await createAuthenticatedContext('admin');

    // Create forms in each tenant
    await tenantA.request.post('/api/v1/forms/', { data: generateTestForm() });
    await tenantB.request.post('/api/v1/forms/', { data: generateTestForm() });
    await tenantB.request.post('/api/v1/forms/', { data: generateTestForm() });

    const statsA = await tenantA.request.get('/api/v1/analytics/dashboard');
    const bodyA = await statsA.json();
    
    const statsB = await tenantB.request.get('/api/v1/analytics/dashboard');
    const bodyB = await statsB.json();

    expect(bodyA.data.total_forms).not.toBe(bodyB.data.total_forms);
  });

  test('search results should be tenant-scoped', async () => {
    const tenantA = await createAuthenticatedContext('creator');
    const tenantB = await createAuthenticatedContext('creator');
    
    const uniqueTitle = `Unique-${Date.now()}`;
    await tenantA.request.post('/api/v1/forms/', { data: { ...generateTestForm(), title: uniqueTitle } });

    // Search in Tenant B should NOT find the form from Tenant A
    const searchResp = await tenantB.request.get('/api/v1/forms/', { params: { search: uniqueTitle } });
    const body = await searchResp.json();
    
    const found = body.data.items.some((f: any) => f.title === uniqueTitle);
    expect(found).toBe(false);
  });

});
