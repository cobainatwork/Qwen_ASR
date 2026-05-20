import '@testing-library/jest-dom';

// jsdom older versions lack crypto.randomUUID; provide stub so tests can exercise
// components that call crypto.randomUUID() for Idempotency-Key generation.
if (!('randomUUID' in globalThis.crypto)) {
  // Cast to any to satisfy the `${string}-...-${string}` branded template literal
  // required by the Crypto interface while still providing a functional stub.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (globalThis.crypto as any).randomUUID = (): ReturnType<Crypto['randomUUID']> =>
    (`test-uuid-${Math.random().toString(36).slice(2)}` as ReturnType<Crypto['randomUUID']>);
}
