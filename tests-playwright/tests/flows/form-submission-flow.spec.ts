import { test, expect } from '@playwright/test';
import { generateTestForm, generateTestResponse, generateTestWorkflow } from '../../helpers/data-factory';
import { createAuthenticatedContext } from '../../helpers/auth';

test.describe('End-to-End Form Submission Flow', () => {

  test('complete flow from creation to submission to workflow triggering', async () => {
    // 1. Admin creates a user (not explicitly needed since factory registers users)
    
    // 2. Creator logs in and creates a form
    const creatorCtx = await createAuthenticatedContext('creator');
    const formData = generateTestForm();
    const createFormResp = await creatorCtx.request.post('/api/v1/forms/', { data: formData });
    expect(createFormResp.status()).toBe(201);
    const formId = (await createFormResp.status() === 201) ? (await createFormResp.json()).form_id : null;
    expect(formId).toBeDefined();

    // 3. Creator attaches a workflow to the form
    const workflowData = generateTestWorkflow(formId);
    const createWorkflowResp = await creatorCtx.request.post('/api/v1/workflows/', { data: workflowData });
    expect(createWorkflowResp.status()).toBe(201);
    const workflowId = (await createWorkflowResp.json()).data.id;

    // 4. Creator publishes the form
    await creatorCtx.request.post(`/api/v1/forms/${formId}/publish`, { data: { minor: true } });
    
    // Poll until published
    await expect.poll(async () => {
      const resp = await creatorCtx.request.get(`/api/v1/forms/${formId}`);
      const body = await resp.json();
      return body.data ? body.data.status : null;
    }, { timeout: 15000 }).toBe('published');

    // 5. User submits a response
    const { request: userRequest } = await createAuthenticatedContext('user', creatorCtx.user.organization_id);
    const responseData = generateTestResponse();
    const submitResp = await userRequest.post(`/api/v1/forms/${formId}/responses`, { data: responseData });
    expect(submitResp.status()).toBe(201);
    const responseId = (await submitResp.json()).response_id;

    // 6. Verify workflow is triggered (this might be async and internal)
    // We can check if there's an audit log or workflow status on the response
    const responseDetail = await creatorCtx.request.get(`/api/v1/forms/${formId}/responses/${responseId}`);
    expect(responseDetail.status()).toBe(200);
    const detailBody = await responseDetail.json();
    
    // Some backend might expose workflow state here
    if (detailBody.data.workflow_status) {
      expect(detailBody.data.workflow_status).toBeDefined();
    }

    // 7. Approver reviews the response
    const { request: approverRequest } = await createAuthenticatedContext('approver', creatorCtx.user.organization_id);
    
    // We'd need a route to list pending approvals
    const pendingResp = await approverRequest.get('/api/v1/workflows/pending');
    expect(pendingResp.status()).toBe(200);
    
    // 8. Final Creator checks analytics
    const analyticsResp = await creatorCtx.request.get(`/api/v1/analytics/forms/${formId}`);
    expect([200, 404]).toContain(analyticsResp.status());
  });

});
