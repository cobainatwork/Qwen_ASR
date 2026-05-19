const RAW_PROFILE = (process.env.NEXT_PUBLIC_DEPLOYMENT_PROFILE ?? 'client').toLowerCase();

export type DeploymentProfile = 'client' | 'vendor';

export const deploymentProfile: DeploymentProfile =
  RAW_PROFILE === 'vendor' ? 'vendor' : 'client';

export const isVendor: boolean = deploymentProfile === 'vendor';
