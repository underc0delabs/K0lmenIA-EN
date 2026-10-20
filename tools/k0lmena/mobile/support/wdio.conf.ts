// mobile/support/wdio.conf.ts
//
// Where the mobile suite runs is chosen from the .env, without touching this file:
//   MOBILE_TARGET=device       -> physical device over USB with local Appium (default)
//   MOBILE_TARGET=emulator     -> Android emulator / iOS simulator with local Appium
//   MOBILE_TARGET=browserstack -> real device on BrowserStack
//
// Common variables:   MOBILE_PLATFORM (Android | iOS), MOBILE_DEVICE_NAME,
//                     MOBILE_PLATFORM_VERSION, MOBILE_APP (path to the .apk/.ipa, relative to mobile/apps/)
// Device only:        MOBILE_UDID
// BrowserStack only:  BROWSERSTACK_USER, BROWSERSTACK_KEY, BROWSERSTACK_APP (bs://...)

import type { Options } from '@wdio/types';
import { resolve, isAbsolute } from 'path';
// single .env at the k0lmenIA root
require('../../env');

const env = (name: string, fallback = '') => (process.env[name] ?? fallback).trim();

const target = env('MOBILE_TARGET', 'device').toLowerCase();
const platform = env('MOBILE_PLATFORM', 'Android');
const isIOS = platform.toLowerCase() === 'ios';
const automationName = isIOS ? 'XCUITest' : 'UiAutomator2';
const appFile = env('MOBILE_APP', 'app.apk');
const appPath = isAbsolute(appFile) ? appFile : resolve(__dirname, '../apps', appFile);
// Scenarios tagged @blocked (steps that could not be mapped) never run.
const rawTags = env('TAGS');
const tags = rawTags ? `(${rawTags}) and not @blocked` : 'not @blocked';

const localCapabilities = {
  platformName: platform,
  'appium:automationName': automationName,
  'appium:deviceName': env('MOBILE_DEVICE_NAME', target === 'emulator' ? 'emulator-5554' : '') || undefined,
  'appium:platformVersion': env('MOBILE_PLATFORM_VERSION') || undefined,
  'appium:app': appPath,
  // Physical device only: the udid comes from `adb devices`.

  ...(target === 'device' && env('MOBILE_UDID') ? { 'appium:udid': env('MOBILE_UDID') } : {}),
};

const browserstackCapabilities = {
  platformName: platform,
  'appium:automationName': automationName,
  'appium:app': env('BROWSERSTACK_APP'),
  'bstack:options': {
    deviceName: env('MOBILE_DEVICE_NAME', 'Samsung Galaxy S22'),
    osVersion: env('MOBILE_PLATFORM_VERSION', '12.0'),
    projectName: 'k0lmena Mobile',
    buildName: env('BROWSERSTACK_BUILD', 'k0lmenIA'),
    sessionName: 'Mobile Test on BrowserStack',
  },
};

const connection =
  target === 'browserstack'
    ? {
        user: env('BROWSERSTACK_USER'),
        key: env('BROWSERSTACK_KEY'),
        hostname: 'hub.browserstack.com',
        port: 443,
        protocol: 'https' as const,
        services: [['browserstack', {}]] as Options.Testrunner['services'],
      }
    : {
        port: 4723,
        services: ['appium'] as Options.Testrunner['services'],
      };

export const config: Options.Testrunner = {
  runner: 'local',
  ...connection,

  specs: [resolve(__dirname, '../features/**/*.feature')],
  maxInstances: 1,
  logLevel: 'info',
  bail: 0,
  baseUrl: '',
  waitforTimeout: 10000,
  framework: 'cucumber',
  reporters: ['spec'],
  cucumberOpts: {
    require: [
      resolve(__dirname, '../steps/**/*.ts'),
      resolve(__dirname, './hooks.ts'),
      resolve(__dirname, '../../tools/variables.ts'),
      resolve(__dirname, '../../tools/db/db.steps.ts'),
    ],
    timeout: 60000,
    failFast: false,
    tags,
    format: [
      'pretty',
      `json:${resolve(__dirname, '../../reports/mobile/cucumber-report.json')}`,
    ],
  },
  autoCompileOpts: {
    tsNodeOpts: {
      transpileOnly: true,
      project: resolve(__dirname, '../../tsconfig.json'),
    },
  },
  capabilities: [target === 'browserstack' ? browserstackCapabilities : localCapabilities],
} as unknown as Options.Testrunner;
