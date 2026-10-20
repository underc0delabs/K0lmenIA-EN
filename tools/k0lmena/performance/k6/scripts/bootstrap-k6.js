// bootstrap-k6.js — `npm run bootstrap:k6`: downloads k6 into tools/k6 (Windows, Linux and macOS).
// Verifies the release's official SHA-256 (pinned for this version) before extracting.
// To upgrade: change VERSION and the hashes, which come from
// https://github.com/grafana/k6/releases/download/<version>/k6-<version>-checksums.txt
const fs = require('fs');
const os = require('os');
const path = require('path');
const crypto = require('crypto');
const { spawnSync } = require('child_process');

const VERSION = 'v2.3.0';
const SHA256 = {
  'linux-amd64.tar.gz': '39c3117b6af817592dcd0ce4242105c0a7af10948c2a425306f0be8f7a8a8ab1',
  'linux-arm64.tar.gz': '5ca3433e8201da72a284aaa241a1bb5fb47f4abb4e384d39410ddd8062f49b90',
  'macos-amd64.zip': 'c83bb16f54f0676afa4ea235fd757f3892d307dbd1bd201450de83af31986654',
  'macos-arm64.zip': 'b2417a3038edc5fe81dc178a889237724b595c5c9cfed875822008e46e862c7d',
  'windows-amd64.zip': '112276d495e5741c968e2bc09ea6196099c1275bd6db9ee0875d173c7148ce43',
};
const DESTINATION = path.resolve(__dirname, '../../../tools/k6');

function platform() {
  const arch = { x64: 'amd64', arm64: 'arm64' }[process.arch];
  if (process.platform === 'win32') return 'windows-amd64.zip'; // k6 publishes Windows only for amd64
  if (!arch) throw new Error(`unsupported architecture: ${process.arch}`);
  return process.platform === 'darwin' ? `macos-${arch}.zip` : `linux-${arch}.tar.gz`;
}

function extract(file, folder) {
  // Paths relative to cwd: Git Bash's tar does not accept paths with "C:".
  const r = file.endsWith('.zip') && process.platform === 'win32'
    ? spawnSync('powershell', ['-NoProfile', '-Command', `Expand-Archive -Force -Path '${path.basename(file)}' -DestinationPath .`], { cwd: folder, stdio: 'inherit' })
    : file.endsWith('.zip')
      ? spawnSync('unzip', ['-o', path.basename(file)], { cwd: folder, stdio: 'inherit' })
      : spawnSync('tar', ['-xzf', path.basename(file)], { cwd: folder, stdio: 'inherit' });
  if (r.status !== 0) throw new Error('could not extract the downloaded file');
}

(async () => {
  const binary = path.join(DESTINATION, process.platform === 'win32' ? 'k6.exe' : 'k6');
  if (fs.existsSync(binary)) {
    console.log(`k6 is already in ${path.relative(process.cwd(), binary)}.`);
    return;
  }
  const suffix = platform();
  const name = `k6-${VERSION}-${suffix}`;
  const url = `https://github.com/grafana/k6/releases/download/${VERSION}/${name}`;
  console.log(`Downloading ${url} ...`);
  const r = await fetch(url, { signal: AbortSignal.timeout(300000) });
  if (!r.ok) throw new Error(`HTTP ${r.status} while downloading k6`);
  const data = Buffer.from(await r.arrayBuffer());
  if (crypto.createHash('sha256').update(data).digest('hex') !== SHA256[suffix]) {
    throw new Error('the SHA-256 of the downloaded file does not match the one published by Grafana');
  }
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'k6-'));
  const file = path.join(temp, name);
  fs.writeFileSync(file, data);
  console.log('Extracting...');
  extract(file, temp);
  const folder = path.join(temp, name.replace(/\.(zip|tar\.gz)$/, ''));
  fs.mkdirSync(DESTINATION, { recursive: true });
  fs.copyFileSync(path.join(folder, path.basename(binary)), binary);
  if (process.platform !== 'win32') fs.chmodSync(binary, 0o755);
  fs.rmSync(temp, { recursive: true, force: true });
  console.log(`Done. Binary in tools/k6/${path.basename(binary)}`);
})().catch((e) => {
  console.error(`Could not install k6: ${e.message}`);

  process.exit(1);
});
