import { test, expect } from '@playwright/test';
import { generateTestForm, generateTestWorkflow } from '../../../helpers/data-factory';
import { createAuthenticatedContext } from '../../../helpers/auth';

test.describe('Workflows API', () => {

  let creatorCtx: any;
  let formId: string;

  test.beforeAll(async () => {
    creatorCtx = await createAuthenticatedContext('creator');
    const formData = generateTestForm();
    const response = await creatorCtx.request.post('/api/v1/forms/', { data: formData });
    formId = (await response.json()).form_id;
  });

  test('should create a new workflow', async () => {
    const workflowData = generateTestWorkflow(formId);
    
    const response = await creatorCtx.request.post('/api/v1/workflows/', {
      data: workflowData
    });
    
    expect(response.status()).toBe(201);
    const body = await response.json();
    expect(body.data.id).toBeDefined();
    return body.data.id;
  });

  test('should list workflows for the organization', async () => {
    // Ensure at least one workflow exists
    await creatorCtx.request.post('/api/v1/workflows/', {
      data: generateTestWorkflow(formId)
    });
    
    const response = await creatorCtx.request.get('/api/v1/workflows/');
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.success).toBe(true);
    expect(body.data.items).toBeInstanceOf(Array);
  });

  test('should fail to create workflow with non-existent trigger form', async () => {
    const workflowData = generateTestWorkflow('65c12345-6789-0abc-def1-234567890abc'); // invalid UUID but valid format
    
    const response = await creatorCtx.request.post('/api/v1/workflows/', {
      data: workflowData
    });
    
    expect([400, 404]).toContain(response.status());
  });

  test('should get a specific workflow by ID', async () => {
    const workflowData = generateTestWorkflow(formId);
    const createResp = await creatorCtx.request.post('/api/v1/workflows/', {
      data: workflowData
    });
    const workflowId = (await createResp.json()).data.id;
    
    const response = await creatorCtx.request.get(`/api/v1/workflows/${workflowId}`);
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.data.name).toBe(workflowData.name);
  });

  test('should update an existing workflow', async () => {
    const workflowData = generateTestWorkflow(formId);
    const createResp = await creatorCtx.request.post('/api/v1/workflows/', {
      data: workflowData
    });
    const workflowId = (await createResp.json()).data.id;
    
    const updateResp = await creatorCtx.request.put(`/api/v1/workflows/${workflowId}`, {
      data: { name: 'Updated Workflow Name' }
    });
    expect(updateResp.status()).toBe(200);
    
    // Verify update
    const getResp = await creatorCtx.request.get(`/api/v1/workflows/${workflowId}`);
    expect((await getResp.json()).data.name).toBe('Updated Workflow Name');
  });

  test('unauthorized user cannot create workflow', async () => {
    const { request: unauthorizedRequest } = await createAuthenticatedContext('user');
    const workflowData = generateTestWorkflow(formId);
    
    const response = await unauthorizedRequest.post('/api/v1/workflows/', {
      data: workflowData
    });
    
    expect([403, 404]).toContain(response.status());
  });

});
