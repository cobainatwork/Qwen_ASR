import { describe, expect, test, afterEach } from '@jest/globals';

describe('lib/config', () => {
  const originalEnv = process.env.NEXT_PUBLIC_DEPLOYMENT_PROFILE;

  afterEach(() => {
    process.env.NEXT_PUBLIC_DEPLOYMENT_PROFILE = originalEnv;
    jest.resetModules();
  });

  test('deploymentProfile defaults to "client" when env var unset', () => {
    delete process.env.NEXT_PUBLIC_DEPLOYMENT_PROFILE;
    const { deploymentProfile } = require('@/lib/config');
    expect(deploymentProfile).toBe('client');
  });

  test('deploymentProfile reflects "vendor" when env var set to vendor', () => {
    process.env.NEXT_PUBLIC_DEPLOYMENT_PROFILE = 'vendor';
    const { deploymentProfile } = require('@/lib/config');
    expect(deploymentProfile).toBe('vendor');
  });

  test('deploymentProfile rejects unknown values back to "client"', () => {
    process.env.NEXT_PUBLIC_DEPLOYMENT_PROFILE = 'something-weird';
    const { deploymentProfile } = require('@/lib/config');
    expect(deploymentProfile).toBe('client');
  });

  test('isVendor is true only when profile === vendor', () => {
    process.env.NEXT_PUBLIC_DEPLOYMENT_PROFILE = 'vendor';
    const { isVendor } = require('@/lib/config');
    expect(isVendor).toBe(true);
  });

  test('isVendor is false when profile === client', () => {
    process.env.NEXT_PUBLIC_DEPLOYMENT_PROFILE = 'client';
    const { isVendor } = require('@/lib/config');
    expect(isVendor).toBe(false);
  });
});
