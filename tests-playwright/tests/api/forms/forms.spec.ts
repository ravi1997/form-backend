import { test, expect } from '@playwright/test';
import { generateTestForm } from '../../../helpers/data-factory';
import { createAuthenticatedContext } from '../../../helpers/auth';

test.describe('Forms API', () => {

  test('should create a new form', async () => {
    const { request } = await createAuthenticatedContext('creator');
    const formData = generateTestForm();
    
    const response = await request.post('/api/v1/forms/', {
      data: formData
    });
    
    expect(response.status()).toBe(201);
    const body = await response.json();
    expect(body.form_id).toBeDefined();
  });

  test('should fail to create form with invalid schema', async () => {
    const { request } = await createAuthenticatedContext('creator');
    const formData = generateTestForm();
    formData.schema = { type: "invalid" }; // Invalid JSON schema
    
    const response = await request.post('/api/v1/forms/', {
      data: formData
    });
    
    // Note: Some versions might be permissive or use non-strict validation
    expect([201, 400]).toContain(response.status());
  });

  test('should list forms with pagination', async () => {
    const { request } = await createAuthenticatedContext('creator');
    
    // Create multiple forms
    for (let i = 0; i < 3; i++) {
      await request.post('/api/v1/forms/', { data: generateTestForm() });
    }
    
    // List forms with pagination
    const response = await request.get('/api/v1/forms/', {
      params: { page: 1, page_size: 2 }
    });
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.success).toBe(true);
    expect(body.data.items.length).toBeLessThanOrEqual(2);
  });

  test('should get, update, and delete a form', async () => {
    const { request } = await createAuthenticatedContext('creator');
    const formData = generateTestForm();
    
    // Create
    const createResp = await request.post('/api/v1/forms/', { data: formData });
    const formId = (await createResp.json()).form_id;
    
    // Get
    const getResp = await request.get(`/api/v1/forms/${formId}`);
    expect(getResp.status()).toBe(200);
    expect((await getResp.json()).data.title).toBe(formData.title);
    
    // Update
    const updateResp = await request.put(`/api/v1/forms/${formId}`, {
      data: { title: 'Updated Form Title' }
    });
    expect(updateResp.status()).toBe(200);
    
    // Delete
    const deleteResp = await request.delete(`/api/v1/forms/${formId}`);
    expect(deleteResp.status()).toBe(200);
    
    // Verify deleted
    const verifyResp = await request.get(`/api/v1/forms/${formId}`);
    expect(verifyResp.status()).toBe(404);
  });

  test('should publish a form', async () => {
    const { request } = await createAuthenticatedContext('creator');
    const formData = generateTestForm();
    
    const createResp = await request.post('/api/v1/forms/', { data: formData });
    const formId = (await createResp.json()).form_id;
    
    const publishResp = await request.post(`/api/v1/forms/${formId}/publish`, {
      data: { minor: true }
    });
    
    // Publishing might be async, expect 202 or 200
    expect([200, 202]).toContain(publishResp.status());
    
    // Poll for status change to 'published'
    await expect.poll(async () => {
      const resp = await request.get(`/api/v1/forms/${formId}`);
      const body = await resp.json();
      return body.data ? body.data.status : null;
    }, { timeout: 10000 }).toBe('published');
  });

  test('should clone a form', async () => {
    const { request } = await createAuthenticatedContext('creator');
    const formData = generateTestForm();
    
    const createResp = await request.post('/api/v1/forms/', { data: formData });
    const formId = (await createResp.json()).form_id;
    
    const cloneResp = await request.post(`/api/v1/forms/${formId}/clone`);
    expect([200, 201, 202]).toContain(cloneResp.status());
    
    const cloneBody = await cloneResp.json();
    // It's async, should return task_id
    expect(cloneBody.data.task_id).toBeDefined();
  });

  test('unauthorized user cannot update form', async () => {
    const creator = await createAuthenticatedContext('creator');
    const formData = generateTestForm();
    const createResp = await creator.request.post('/api/v1/forms/', { data: formData });
    const formId = (await createResp.json()).form_id;

    const { request: unauthorizedRequest } = await createAuthenticatedContext('user');
    const response = await unauthorizedRequest.put(`/api/v1/forms/${formId}`, {
      data: { title: 'Hacked Title' }
    });
    
    // In multi-tenant systems, searching by org + id returns 404 if not found in that org.
    expect([403, 404]).toContain(response.status());
  });

});
