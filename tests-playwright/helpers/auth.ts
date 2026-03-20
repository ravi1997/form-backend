import { APIRequestContext, request } from '@playwright/test';
import { generateTestUser } from './data-factory';

export interface AuthContext {
  request: APIRequestContext;
  user: any;
  accessToken: string;
  refreshToken: string;
}

let backendReadyPromise: Promise<void> | null = null;

async function ensureBackendReady(): Promise<void> {
  if (!backendReadyPromise) {
    backendReadyPromise = (async () => {
      const baseURL = process.env.API_BASE_URL || 'http://localhost:8051';

      for (let attempt = 0; attempt < 20; attempt += 1) {
        try {
          const response = await fetch(`${baseURL}/health/`);
          if (response.ok) {
            return;
          }
        } catch (_error) {
          // Backend is still starting up.
        }

        await new Promise((resolve) => setTimeout(resolve, 500));
      }

      throw new Error(`Backend at ${baseURL} did not become healthy in time`);
    })();
  }

  return backendReadyPromise;
}

export async function createAuthenticatedContext(
  role: string = 'user',
  organizationId?: string
): Promise<AuthContext> {
  await ensureBackendReady();
  const userData = generateTestUser(role);
  if (organizationId) {
    userData.organization_id = organizationId;
  }
  const context = await request.newContext({
    baseURL: process.env.API_BASE_URL || 'http://localhost:8051',
    ignoreHTTPSErrors: true,
    extraHTTPHeaders: {
      'X-Organization-ID': userData.organization_id,
    },
  });

  // 1. Register User
  const registerResponse = await context.post('/api/v1/auth/register', {
    data: userData,
  });
  
  if (!registerResponse.ok()) {
    throw new Error(`Failed to register user: ${await registerResponse.text()}`);
  }

  // 2. Login User
  const loginResponse = await context.post('/api/v1/auth/login', {
    data: {
      identifier: userData.email,
      password: userData.password,
    },
  });

  if (!loginResponse.ok()) {
    throw new Error(`Failed to login user: ${await loginResponse.text()}`);
  }

  const loginData = await loginResponse.json();
  const accessToken = loginData.data.access_token;
  const refreshToken = loginData.data.refresh_token;
  const user = loginData.data.user;

  // Create a new context with the Authorization header
  const authContext = await request.newContext({
    baseURL: process.env.API_BASE_URL || 'http://localhost:8051',
    ignoreHTTPSErrors: true,
    extraHTTPHeaders: {
      'Authorization': `Bearer ${accessToken}`,
      'Accept': 'application/json',
      'Content-Type': 'application/json',
    }
  });

  return { request: authContext, user, accessToken, refreshToken };
}
