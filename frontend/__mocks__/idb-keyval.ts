// Manual mock: idb-keyval uses IndexedDB which is not available in jsdom test environment.
// Provides an in-memory Map-backed implementation. Tests can reset via __store or __resetMockStore.

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const _self: any = module.exports;

// Initialise the shared store. Tests may replace this reference via `(idb as any).__store = new Map()`.
_self.__store = new Map<IDBValidKey, unknown>();

// Helper so mock functions always read the *current* __store (supports test-side replacement).
function store(): Map<IDBValidKey, unknown> {
  return _self.__store;
}

export const get = jest.fn(async (key: IDBValidKey) => store().get(key) ?? undefined);

export const set = jest.fn(async (key: IDBValidKey, value: unknown) => {
  store().set(key, value);
});

export const del = jest.fn(async (key: IDBValidKey) => {
  store().delete(key);
});

export const clear = jest.fn(async () => {
  store().clear();
});

export const keys = jest.fn(async () => Array.from(store().keys()));

export const values = jest.fn(async () => Array.from(store().values()));

export const entries = jest.fn(async () => Array.from(store().entries()));

export const createStore = jest.fn(() => 'mock-store');

export const __resetMockStore = () => store().clear();
