import { test, expect } from '@playwright/test';
import { generateTestForm, generateTestResponse } from '../../../helpers/data-factory';
import { createAuthenticatedContext } from '../../../helpers/auth';

test.describe('Responses API', () => {

  let formId: string;
  let creatorCtx: any;

  test.beforeAll(async () => {
    creatorCtx = await createAuthenticatedContext('creator');
    const formData = generateTestForm();
    const createResp = await creatorCtx.request.post('/api/v1/forms/', { data: formData });
    formId = (await createResp.json()).form_id;

    // Publish the form
    await creatorCtx.request.post(`/api/v1/forms/${formId}/publish`, { data: { minor: true } });
    
    // Poll until published
    await expect.poll(async () => {
      const resp = await creatorCtx.request.get(`/api/v1/forms/${formId}`);
      const body = await resp.json();
      return body.data ? body.data.status : null;
    }, { timeout: 15000 }).toBe('published');
  });

  test('should submit a valid response', async () => {
    const { request } = await createAuthenticatedContext('user', creatorCtx.user.organization_id);
    const responseData = generateTestResponse();
    
    const response = await request.post(`/api/v1/forms/${formId}/responses`, {
      data: responseData
    });
    
    expect(response.status()).toBe(201);
    const body = await response.json();
    expect(body.response_id).toBeDefined();
  });

  test('should fail to submit response with missing required fields', async () => {
    const { request } = await createAuthenticatedContext('user', creatorCtx.user.organization_id);
    
    const response = await request.post(`/api/v1/forms/${formId}/responses`, {
      data: { data: { age: 25 } } // missing full_name and email which are required in schema
    });
    
    expect(response.status()).toBe(400);
  });

  test('should fail to submit response with invalid data types', async () => {
    const { request } = await createAuthenticatedContext('user', creatorCtx.user.organization_id);
    
    const response = await request.post(`/api/v1/forms/${formId}/responses`, {
      data: { data: { full_name: 123, email: "not-an-email", age: "twenty" } }
    });
    
    expect(response.status()).toBe(400);
  });

  test('should list responses for the form creator', async () => {
    // Submit a few responses first
    for (let i = 0; i < 2; i++) {
      const { request: submitterReq } = await createAuthenticatedContext('user', creatorCtx.user.organization_id);
      await submitterReq.post(`/api/v1/forms/${formId}/responses`, { data: generateTestResponse() });
    }

    const response = await creatorCtx.request.get(`/api/v1/forms/${formId}/responses`);
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.success).toBe(true);
    expect(body.data.items).toBeInstanceOf(Array);
    expect(body.data.items.length).toBeGreaterThanOrEqual(2);
  });

  test('should get a specific response by ID', async () => {
    const { request: submitterReq } = await createAuthenticatedContext('user', creatorCtx.user.organization_id);
    const responseData = generateTestResponse();
    const submitResp = await submitterReq.post(`/api/v1/forms/${formId}/responses`, { data: responseData });
    const responseId = (await submitResp.json()).response_id;

    const response = await creatorCtx.request.get(`/api/v1/forms/${formId}/responses/${responseId}`);
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.data.data.full_name).toBe(responseData.data.full_name);
  });

  test('non-admin/non-creator cannot list responses', async () => {
    const { request: unauthorizedRequest } = await createAuthenticatedContext('user');
    const response = await unauthorizedRequest.get(`/api/v1/forms/${formId}/responses`);
    
    // Isolation or RBAC should prevent this
    expect([403, 404]).toContain(response.status());
  });

});
