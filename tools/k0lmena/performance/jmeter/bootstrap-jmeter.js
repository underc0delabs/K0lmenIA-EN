// bootstrap-jmeter.js — `npm run bootstrap:jmeter`: downloads Apache JMeter into tools/jmeter
// (Windows, Linux and macOS). Verifies Apache's official SHA-512 (pinned for this version)
// before extracting.
// JMeter needs Java 8 or later (the runner looks for it in JAVA_HOME or in the PATH).
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { spawnSync } = require('child_process');

const VERSION = '5.6.3';
const NAME = `apache-jmeter-${VERSION}`;
const ARCHIVE_PATH = `jmeter/binaries/${NAME}.tgz`;
// The CDN has the current version; the historical archive has all of them (and is slower).
const TGZ_MIRRORS = [`https://dlcdn.apache.org/${ARCHIVE_PATH}`, `https://archive.apache.org/dist/${ARCHIVE_PATH}`];
// https://downloads.apache.org/jmeter/binaries/apache-jmeter-5.6.3.tgz.sha512 (update when upgrading)
const SHA512 = '5978a1a35edb5a7d428e270564ff49d2b1b257a65e17a759d259a9283fc17093e522fe46f474a043864aea6910683486340706d745fcdf3db1505fd71e689083';
const DESTINATION = path.resolve(__dirname, '../../tools/jmeter');

async function download(urls) {
  const failures = [];
  for (const url of urls) {
    try {
      console.log(`Downloading ${url} ...`);
      const r = await fetch(url, { signal: AbortSignal.timeout(300000) });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return Buffer.from(await r.arrayBuffer());
    } catch (e) {
      failures.push(`${url}: ${e.cause?.code || e.message}`);
    }
  }
  throw new Error(`could not download:\n  ${failures.join('\n  ')}`);
}

(async () => {
  if (fs.existsSync(path.join(DESTINATION, NAME, 'bin', 'ApacheJMeter.jar'))) {
    console.log(`JMeter ${VERSION} is already in tools/jmeter/${NAME}.`);
    return;
  }
  fs.mkdirSync(DESTINATION, { recursive: true });

  const tgz = await download(TGZ_MIRRORS);
  const actual = crypto.createHash('sha512').update(tgz).digest('hex');
  if (actual !== SHA512) throw new Error('The SHA-512 of the downloaded file does not match the one published by Apache.');

  const file = path.join(DESTINATION, 'jmeter.tgz');
  fs.writeFileSync(file, tgz);
  console.log('Extracting...');
  // Paths relative to cwd: Git Bash's tar does not accept paths with "C:".
  const t = spawnSync('tar', ['-xzf', 'jmeter.tgz'], { cwd: DESTINATION, stdio: 'inherit' });
  fs.rmSync(file, { force: true });
  if (t.status !== 0) throw new Error('Could not extract the file with tar.');

  const java = spawnSync('java', ['-version'], { encoding: 'utf8' });
  console.log(`Done. JMeter in tools/jmeter/${NAME}`);
  if (java.status !== 0) console.log('Note: Java not found in the PATH. JMeter needs Java 8 or later (or define JAVA_HOME).');
})().catch((e) => {
  console.error(`Could not install JMeter: ${e.message}`);

  process.exit(1);
});
