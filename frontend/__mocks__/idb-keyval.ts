// Manual mock: idb-keyval uses IndexedDB which is not available in jsdom test environment
// This provides a simple in-memory implementation for testing

const store: Record<string, unknown> = {};

export const get = jest.fn(async (key: string) => {
  return store[key];
});

export const set = jest.fn(async (key: string, value: unknown) => {
  store[key] = value;
  return undefined;
});

export const del = jest.fn(async (key: string) => {
  delete store[key];
  return undefined;
});

export const clear = jest.fn(async () => {
  Object.keys(store).forEach(key => delete store[key]);
  return undefined;
});

export const keys = jest.fn(async () => {
  return Object.keys(store);
});

export const values = jest.fn(async () => {
  return Object.values(store);
});

export const entries = jest.fn(async () => {
  return Object.entries(store);
});
