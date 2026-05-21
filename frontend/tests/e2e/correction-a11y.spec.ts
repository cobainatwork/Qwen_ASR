/**
 * E2E: correction-a11y — axe-core accessibility audit
 *
 * Scenario:
 *   1. Seed a session and navigate to /correction/:id
 *   2. Run AxeBuilder.analyze() on the fully-rendered page
 *   3. Assert zero "critical" impact violations
 *
 * axe-core impact levels: critical > serious > moderate > minor
 * Threshold: critical = 0 (no blocker accessibility issues).
 * Serious/moderate/minor violations are reported but do not fail the test
 * in this baseline scan — address them incrementally.
 *
 * Preconditions (manual verification needed — see CLAUDE.md #24):
 *   - Backend running with DEPLOYMENT_PROFILE=vendor, ENV=development
 *   - Frontend dev server running
 *   - E2E_API_TOKEN set to a valid asr:write key
 */

import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { injectToken, seedCorrectionSession, gotoSession, TOKEN } from './correction-fixtures';

test.describe('Accessibility audit', () => {
  test.beforeEach(async ({ context }) => {
    await context.addInitScript((token: string) => {
      localStorage.setItem('qwen-asr-token', token);
    }, TOKEN);
  });

  test('correction workbench has zero critical axe violations', async ({ page }) => {
    await injectToken(page);
    const sessionId = await seedCorrectionSession(page, 3);
    await gotoSession(page, sessionId);

    // Wait for the editor panel to be fully rendered before scanning
    await page.getByLabel('文字編輯區').waitFor({ state: 'visible', timeout: 15_000 });
    // Also wait for at least one textarea to appear (segments loaded)
    await page.getByRole('textbox').first().waitFor({ state: 'visible', timeout: 10_000 });

    const results = await new AxeBuilder({ page })
      // Disable color-contrast rule: font colours are design choices, not blockers
      .disableRules(['color-contrast'])
      .analyze();

    const criticalViolations = results.violations.filter(
      (v) => v.impact === 'critical',
    );

    // Report all violations for diagnostics even when test passes
    if (results.violations.length > 0) {
      console.log(
        'axe violations (non-critical allowed):',
        results.violations.map((v) => `[${v.impact}] ${v.id}: ${v.description}`),
      );
    }

    expect(
      criticalViolations,
      `Critical axe violations found:\n${criticalViolations
        .map((v) => `  [${v.id}] ${v.description}\n    ${v.nodes.map((n) => n.html).join('\n    ')}`)
        .join('\n')}`,
    ).toHaveLength(0);
  });
});
