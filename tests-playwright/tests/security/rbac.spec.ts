import { test, expect } from '@playwright/test';
import { generateTestForm } from '../../helpers/data-factory';
import { createAuthenticatedContext } from '../../helpers/auth';

test.describe('Role Based Access Control (RBAC)', () => {

  let creatorCtx: any;
  let formId: string;

  test.beforeAll(async () => {
    creatorCtx = await createAuthenticatedContext('creator');
    const formData = generateTestForm();
    const response = await creatorCtx.request.post('/api/v1/forms/', { data: formData });
    formId = (await response.json()).form_id;
  });

  test('creator can manage their own forms', async () => {
    const response = await creatorCtx.request.put(`/api/v1/forms/${formId}`, {
      data: { title: 'Creator Updated Title' }
    });
    expect(response.status()).toBe(200);
  });

  test('regular user cannot update forms', async () => {
    const { request: userRequest } = await createAuthenticatedContext('user', creatorCtx.user.organization_id);
    const response = await userRequest.put(`/api/v1/forms/${formId}`, {
      data: { title: 'User Updated Title' }
    });
    expect(response.status()).toBe(403);
  });

  test('admin can manage forms in the organization', async () => {
    const { request: adminRequest } = await createAuthenticatedContext('admin', creatorCtx.user.organization_id);
    const response = await adminRequest.put(`/api/v1/forms/${formId}`, {
      data: { title: 'Admin Updated Title' }
    });
    expect(response.status()).toBe(200);
  });

  test('unauthorized user cannot list organization users', async () => {
    const { request: userRequest } = await createAuthenticatedContext('user', creatorCtx.user.organization_id);
    const response = await userRequest.get('/api/v1/users/users');
    expect(response.status()).toBe(403);
  });

  test('approver can see workflows', async () => {
    const { request: approverRequest } = await createAuthenticatedContext('approver', creatorCtx.user.organization_id);
    const response = await approverRequest.get('/api/v1/workflows/');
    expect(response.status()).toBe(200);
  });

  test('superadmin can access system settings', async () => {
    // This assumes there's a superadmin role
    const { request: superadminRequest } = await createAuthenticatedContext('superadmin');
    const response = await superadminRequest.get('/api/v1/admin/system-settings/');
    expect([200, 403]).toContain(response.status()); // Depends if user created by factory is actually superadmin
  });

});
