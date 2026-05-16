import openapiTS, { astToString } from 'openapi-typescript';
import { writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const BACKEND = process.env.BACKEND_BASE_URL ?? 'http://localhost:8000';
const OUTPUT = resolve(__dirname, '../lib/api/types.ts');

async function main() {
  const ast = await openapiTS(new URL('/openapi.json', BACKEND));
  const content = `// Auto-generated from ${BACKEND}/openapi.json. Do not edit.\n\n${astToString(ast)}`;
  await writeFile(OUTPUT, content, 'utf-8');
  console.log(`Generated ${OUTPUT}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
