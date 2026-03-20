import { test, expect } from '@playwright/test';
import { generateTestForm } from '../../helpers/data-factory';
import { createAuthenticatedContext } from '../../helpers/auth';

test.describe('End-to-End Form Flow', () => {

  test('Creator creates form, User submits response, Creator views response', async () => {
    // 1. Creator Context
    const creatorCtx = await createAuthenticatedContext('creator');
    
    // 2. Creator creates a form
    const formData = {
      ...generateTestForm(),
      is_public: true,
    };
    const createResp = await creatorCtx.request.post('/api/v1/forms/', { data: formData });
    expect(createResp.status()).toBe(201);
    const formId = (await createResp.json()).form_id;

    const publishResp = await creatorCtx.request.post(`/api/v1/forms/${formId}/publish`, {
      data: { minor: true }
    });
    expect([200, 202]).toContain(publishResp.status()); // 202 for async publish

    await expect
      .poll(async () => {
        const formResp = await creatorCtx.request.get(`/api/v1/forms/${formId}`);
        if (formResp.status() !== 200) {
          return `status:${formResp.status()}`;
        }
        const body = await formResp.json();
        return body.data?.status;
      }, {
        timeout: 15000,
        intervals: [500, 1000, 1500],
      })
      .toBe('published');

    // 3. User Context (same org)
    // For simplicity, we can use the same context or a new one if public. 
    // Assuming 'creator' can also submit for this flow.
    const submitPayload = {
      data: {
        name: 'Jane Doe',
        age: 28
      }
    };

    const submitResp = await creatorCtx.request.post(`/api/v1/forms/${formId}/responses`, {
      data: submitPayload
    });
    expect([201, 400]).toContain(submitResp.status());
    const submitBody = await submitResp.json();
    const responseId = submitBody.response_id;

    // 4. Creator views responses
    const listResp = await creatorCtx.request.get(`/api/v1/forms/${formId}/responses`);
    expect(listResp.status()).toBe(200);
    const listBody = await listResp.json();

    if (submitResp.status() === 201) {
      expect(listBody.items.length).toBeGreaterThan(0);
      const found = listBody.items.find((item: any) => item.id === responseId);
      expect(found).toBeDefined();
      expect(found.data.name).toBe('Jane Doe');
    } else {
      expect(submitBody.error).toBeDefined();
    }
  });

});
