import js from '@eslint/js';
import { defineConfig, globalIgnores } from 'eslint/config';
import reactHooks from 'eslint-plugin-react-hooks';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export default defineConfig([
  // The earlier OmaGenomi views are kept verbatim behind VITE_ENABLE_LEGACY_APP and are outside the lint scope.
  globalIgnores(['dist', 'node_modules', 'src/App.tsx', 'src/loop/**', 'src/support/**', 'src/wellbeing/**']),
  {
    files: ['src/**/*.{ts,tsx}', 'vite.config.ts'],
    extends: [js.configs.recommended, tseslint.configs.recommended, reactHooks.configs.flat.recommended],
    languageOptions: {
      ecmaVersion: 2022,
      globals: { ...globals.browser, ...globals.node },
    },
  },
]);
