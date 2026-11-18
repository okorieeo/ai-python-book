// ESLint 9 and 10 read only this "flat" file. Expo ships a ready-made config.
const { defineConfig } = require('eslint/config');
const expoConfig = require('eslint-config-expo/flat');

module.exports = defineConfig([expoConfig, { ignores: ['dist/*', 'node_modules/*', '.expo/*'] }]);
