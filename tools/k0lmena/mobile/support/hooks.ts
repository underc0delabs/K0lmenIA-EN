// mobile/support/hooks.ts
//
// Evidence per scenario (as in web):
//  - Passes -> final screenshot of the screen (and GIF of the walkthrough with EVIDENCE=both).
//  - Fails  -> screenshot, full video of the run, page source and device logs.
// VIDEO=on-failure (default) | on | off   ·   EVIDENCE=screenshot (default) | both | off

import { Before, After, AfterStep } from '@wdio/cucumber-framework';
import { writeFileSync, mkdirSync } from 'fs';
import { resolve } from 'path';
import { createGif, htmlGif, evidenceMode } from '../../tools/evidence/gif';

const reportDir = resolve(__dirname, '../../reports/mobile');
const videoMode = (process.env.VIDEO ?? 'on-failure').trim().toLowerCase();
const evidence = evidenceMode();
const evidenceOn = evidence !== 'off';
let frames: Buffer[] = [];

const dir = (name: string) => {
  const d = resolve(reportDir, name);
  mkdirSync(d, { recursive: true });
  return d;
};
const safe = (s: string) => s.replace(/[<>:"/\\|?*\x00-\x1F]/g, '_').replace(/\s+/g, ' ').trim().slice(0, 100);

let recording = false;

Before(async function () {
  await browser.reloadSession();
  recording = false;
  frames = [];
  if (videoMode === 'off') return;
  // UiAutomator2 and XCUITest record the screen; if the target does not support it, it continues without video.
  try {
    await browser.startRecordingScreen();
    recording = true;
  } catch (err) {
    console.log('>> Could not start the screen recording:', String(err));
  }
});

// One screenshot per step for the walkthrough GIF (only with EVIDENCE=both).
AfterStep(async function () {
  if (evidence !== 'both') return;
  const shot = await browser.takeScreenshot().catch(() => '');
  if (shot) frames.push(Buffer.from(shot, 'base64'));
});

After(async function (scenario) {
  const failed = scenario.result?.status !== 'PASSED';
  const name = safe(scenario.pickle?.name ?? 'scenario');
  const ts = Date.now();

  try {
    if (failed || evidenceOn) {
      const shot = await browser.takeScreenshot();
      if (shot) {
        const folder = failed ? 'screenshots' : 'evidence';
        writeFileSync(resolve(dir(folder), `${failed ? 'error' : 'ok'}-${name}-${ts}.png`), shot, 'base64');
        if (typeof this.attach === 'function') await this.attach(shot, 'image/png');
      }
    }

    if (!failed && evidence === 'both' && typeof this.attach === 'function') {
      const gif = createGif(frames, { width: 400 }); // phone screens: narrow
      if (gif) {
        // Inside html/ so the report (html/features/*.html) finds it in ../evidence/.
        const file = `gif-${name}-${ts}.gif`;
        writeFileSync(resolve(dir('html/evidence'), file), gif);
        await this.attach(htmlGif(`../evidence/${file}`, 'Scenario walkthrough'), 'text/html');
      }
    }

    if (recording) {
      const video = await browser.stopRecordingScreen();
      if (video && (videoMode === 'on' || failed)) {
        const file = `video-${name}-${ts}.mp4`;
        // It goes inside html/ so the report (html/features/*.html) finds it in ../videos/.
        writeFileSync(resolve(dir('html/videos'), file), video, 'base64');
        if (typeof this.attach === 'function') {
          await this.attach(
            `<p><strong>Run video:</strong></p>` +
              `<video controls preload="metadata" style="max-width:100%" src="../videos/${file}"></video>` +
              `<p><a href="../videos/${file}" download>${file}</a></p>`,
            'text/html'
          );
        }
      }
    }

    if (failed && typeof this.attach === 'function') {
      const source = await browser.getPageSource().catch(() => '');
      if (source) await this.attach(`PAGE SOURCE ON FAILURE\n${source}`, 'text/plain');

      const logType = (await browser.getLogTypes().catch(() => [] as string[])).find((t) => t === 'logcat' || t === 'syslog');
      if (logType) {
        const logs = await browser.getLogs(logType).catch(() => [] as any[]);
        const tail = logs.slice(-300).map((l: any) => `${l.timestamp ?? ''} ${l.level ?? ''} ${l.message ?? ''}`);
        if (tail.length) await this.attach(`DEVICE LOGS (${logType}, last ${tail.length} lines)\n${tail.join('\n')}`, 'text/plain');
      }
    }
  } catch (err) {
    console.error('>> Error saving evidence:', err);

  }
});
