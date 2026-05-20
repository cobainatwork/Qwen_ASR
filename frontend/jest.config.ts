import type { Config } from 'jest';
import nextJest from 'next/jest';

const createJestConfig = nextJest({
  dir: './',
});

const config: Config = {
  setupFilesAfterEnv: ['<rootDir>/jest.setup.ts'],
  testEnvironment: 'jsdom',
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/$1',
    '^wavesurfer\\.js$': '<rootDir>/__mocks__/wavesurfer.js.ts',
    '^@wavesurfer/react$': '<rootDir>/__mocks__/@wavesurfer/react.tsx',
  },
  testMatch: ['<rootDir>/tests/**/*.test.{ts,tsx}'],
};

export default createJestConfig(config);
