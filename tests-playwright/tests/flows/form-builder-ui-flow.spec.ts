import { test, expect } from '@playwright/test';

test.describe('Form Builder UI Flow', () => {

  test('login, select project, create form, and go to builder', async ({ page }) => {
    // 1. Navigate to the frontend app
    const appUrl = process.env.APP_URL || 'http://localhost:38233';
    await page.goto(appUrl);

    // 2. Wait for page load and click accessibility placeholder to enable semantics
    const accessibilityPlaceholder = page.locator('flt-semantics-placeholder');
    if (await accessibilityPlaceholder.isVisible()) {
      await accessibilityPlaceholder.click();
    }

    // 3. Fill in the login form using direct CSS selectors
    await page.locator('input[aria-label="name@company.com"]').fill('alice@hospital.org');
    await page.locator('input[aria-label="Enter your password"]').fill('SecureP@ss2026');

    // 4. Click Sign in button (custom flt-semantics button)
    await page.locator('flt-semantics[role="button"]:has-text("Sign in"), flt-semantics:has-text("Sign in")').first().click();

    // 5. Verify navigation to the projects dashboard
    await expect(page.locator('flt-semantics:has-text("Projects dashboard")').first()).toBeVisible({ timeout: 15000 });

    // 6. Click on the Hospital OPD project card
    await page.locator('flt-semantics:has-text("Hospital OPD")').first().click();

    // 7. Verify navigation to project details and click "New form"
    await expect(page.locator('flt-semantics:has-text("Hospital OPD")').first()).toBeVisible({ timeout: 10000 });
    await page.locator('flt-semantics[role="button"]:has-text("New form"), flt-semantics:has-text("New form")').first().click();

    // 8. Fill in form creation fields in modal
    await page.locator('input[aria-label="Title"]').fill('Patient Registration');
    await page.locator('input[aria-label="Slug"]').fill('patient-registration');
    await page.locator('textarea[aria-label="Description"]').fill('Form to register new patient information.');

    // 9. Click Create button to submit
    await page.locator('flt-semantics[role="button"]:has-text("Create"), flt-semantics:has-text("Create")').first().click();

    // 10. Verify form created and navigated to form dashboard
    await expect(page.locator('flt-semantics:has-text("Form dashboard")').first()).toBeVisible({ timeout: 15000 });

    // 11. Click on the Builder tab to edit (using the specific tab role or text matching)
    await page.locator('flt-semantics[role="tab"]:has-text("Builder"), flt-semantics:has-text("Builder")').first().click();

    // 12. Verify the Builder canvas loaded
    await expect(page.locator('flt-semantics:has-text("Jump into the builder")').first()).toBeVisible({ timeout: 10000 });
  });

});
