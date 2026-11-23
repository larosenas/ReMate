import js from '@eslint/js'
import jsxA11y from 'eslint-plugin-jsx-a11y-x'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import globals from 'globals'

export default [
  { ignores: ['dist'] },
  js.configs.recommended,
  reactHooks.configs.flat.recommended,
  reactRefresh.configs.vite,
  // Accesibilidad en el JSX. Es la versión mantenida de eslint-plugin-jsx-a11y, que no
  // admite ESLint 10; lo que se pinta de verdad se comprueba además con axe-core en las pruebas.
  jsxA11y.configs.strict,
  {
    rules: {
      // El foco va a propósito al primer campo de un formulario que el usuario acaba de abrir (y
      // vuelve al botón al cerrarlo); nunca al cargar la página.
      'jsx-a11y-x/no-autofocus': 'off',
    },
  },
  {
    files: ['**/*.{js,jsx}'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: { ...globals.browser, ...globals.node },
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
  },
]
