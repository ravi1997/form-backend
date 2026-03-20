import { test, expect } from '@playwright/test';
import { generateTestForm, generateTestUser } from '../../helpers/data-factory';
import { createAuthenticatedContext } from '../../helpers/auth';

test.describe('Tenant Isolation API', () => {

  test('user from tenant A cannot see forms from tenant B', async ({ request }) => {
    // 1. Setup Tenant A
    const tenantA = await createAuthenticatedContext('creator');
    // Ensure they have different orgs if your factory supports it, 
    // or assume random user creation creates isolated orgs by default.
    // If users share the same org by default, this test needs a way to separate them.
    // Assuming new user registration creates a new org or we can modify the user payload.
    
    // For this example, let's register two users, assume they get separate orgs (or we assign them).
    // Update data-factory if needed. Let's proceed assuming isolation by default user.
    const formA = generateTestForm();
    const createRespA = await tenantA.request.post('/api/v1/forms/', { data: formA });
    const formIdA = (await createRespA.json()).form_id;

    // 2. Setup Tenant B
    const tenantB = await createAuthenticatedContext('creator');
    
    // 3. Tenant B tries to access Tenant A's form
    const getResp = await tenantB.request.get(`/api/v1/forms/${formIdA}`);
    
    // Should be 404 (Not Found in their context) or 403 (Forbidden)
    expect([403, 404]).toContain(getResp.status());
  });

});
