// Shared launcher for MCP servers over stdio (used by the scripts in scripts/mcp/).
//
// - Pinned versions for each package (no @latest: a server receives tokens through the environment and
//   a new, unreviewed version shouldn't receive them without someone deciding so). To bump a
//   version, change it here (or, to try one out, with the <PACKAGE>_MCP_VERSION variable).
// - On Windows npx is a .cmd and needs a shell: the command line is built by hand from arguments that
//   were already validated (no spaces or characters that cmd interprets).
// - When Claude Code closes, the whole process tree is terminated (on Windows, with taskkill /T),
//   so no orphan servers are left behind.
const { spawn, spawnSync } = require('child_process');
const path = require('path');

const VERSIONS = {
  '@playwright/mcp': '0.0.83',
  '@smartbear/mcp': '0.42.0',
  'appium-mcp': '1.97.1',
  '@azure-devops/mcp': '2.10.0',
  'mcp-remote': '0.15.1',
  '@salesforce/mcp': '0.30.15',
};

const ROOT = path.resolve(__dirname, '..', '..');
const SAFE = /^[\w@./:=${}-]+$/; // what can go unquoted on the cmd command line

function exitWithError(connector, message) {
  console.error(`${connector}: ${message} (see .env.example and CONNECTORS.md).`);
  process.exit(1);
}

/** "package@version" with the pinned version (or the one from <PACKAGE>_MCP_VERSION, if defined). */
function pinnedPackage(pkg) {
  const key = `${pkg.replace(/^@/, '').replace(/[^\w]+/g, '_').toUpperCase()}_MCP_VERSION`;
  const version = process.env[key] || VERSIONS[pkg];
  if (!version || !/^[\w.-]+$/.test(version)) throw new Error(`invalid version for ${pkg}`);
  return `${pkg}@${version}`;
}

/** Runs `npx -y <pinned package> ...args` inheriting stdio (the MCP protocol goes over stdout). */
function launchNpx(connector, pkg, args, env = process.env) {
  let all;
  try {
    all = ['-y', pinnedPackage(pkg), ...args];
  } catch (e) {
    exitWithError(connector, e.message);
  }
  const invalid = all.find((a) => !SAFE.test(a));
  if (invalid) exitWithError(connector, `argument not allowed: "${invalid}"`);
  const options = { stdio: 'inherit', env, cwd: ROOT };
  const child = process.platform === 'win32'
    ? spawn(['npx', ...all].join(' '), { ...options, shell: true })
    : spawn('npx', all, options);
  child.on('error', (e) => exitWithError(connector, `could not start the server (${e.message})`));
  child.on('exit', (code) => process.exit(code ?? 1));
  const close = () => {
    if (process.platform === 'win32' && child.pid) {
      spawnSync('taskkill', ['/PID', String(child.pid), '/T', '/F'], { stdio: 'ignore' });
    } else {
      child.kill('SIGTERM');
    }
  };
  for (const signal of ['SIGINT', 'SIGTERM', 'SIGHUP']) process.on(signal, () => { close(); process.exit(0); });
  return child;
}

module.exports = { launchNpx, exitWithError, pinnedPackage, VERSIONS, ROOT };
