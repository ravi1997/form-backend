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

  test('should list forms', async () => {
    const { request } = await createAuthenticatedContext('creator');
    const formData = generateTestForm();
    
    // Create a form first
    await request.post('/api/v1/forms/', { data: formData });
    
    // List forms
    const response = await request.get('/api/v1/forms/');
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.success).toBe(true);
    expect(body.data.items).toBeInstanceOf(Array);
    expect(body.data.items.length).toBeGreaterThan(0);
  });

  test('should get a specific form', async () => {
    const { request } = await createAuthenticatedContext('creator');
    const formData = generateTestForm();
    
    const createResp = await request.post('/api/v1/forms/', { data: formData });
    const createBody = await createResp.json();
    const formId = createBody.form_id;
    
    const response = await request.get(`/api/v1/forms/${formId}`);
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.success).toBe(true);
    expect(body.data.title).toBe(formData.title);
  });

  test('should update an existing form', async () => {
    const { request } = await createAuthenticatedContext('creator');
    const formData = generateTestForm();
    
    const createResp = await request.post('/api/v1/forms/', { data: formData });
    const formId = (await createResp.json()).form_id;
    
    const response = await request.put(`/api/v1/forms/${formId}`, {
      data: { title: 'Updated Form Title' }
    });
    
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.success).toBe(true);
    
    // Verify update
    const getResp = await request.get(`/api/v1/forms/${formId}`);
    const getBody = await getResp.json();
    expect(getBody.data.title).toBe('Updated Form Title');
  });

  test('unauthorized user cannot create form', async ({ request }) => {
    // request is an unauthenticated context provided by Playwright by default
    const formData = generateTestForm();
    
    const response = await request.post('/api/v1/forms/', {
      data: formData
    });
    
    expect(response.status()).toBe(401);
  });

});
