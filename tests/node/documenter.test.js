// Tests for the project-documenter: functional map (k0lmena tools) and repository connectors.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const ROOT = path.resolve(__dirname, '..', '..');
const map = require(path.join(ROOT, 'tools/k0lmena/tools/functional-map/map.js'));

// Runs a headersHelper with a test .env and without the real environment variables.
function headers(script, env) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'k0-doc-'));
  const file = path.join(dir, '.env');
  fs.writeFileSync(file, Object.entries(env).map(([k, v]) => `${k}=${v}`).join('\n'));
  const clean = Object.fromEntries(Object.entries(process.env).filter(([k]) => !/^(GITHUB|GITLAB)_/.test(k)));
  const r = spawnSync(process.execPath, [path.join(ROOT, 'scripts/mcp', script)], { encoding: 'utf8', env: { ...clean, K0LMENA_ENV_FILE: file } });
  fs.rmSync(dir, { recursive: true, force: true });
  return r;
}

test('functional map: validates the arguments', () => {
  assert.deepEqual(map.parseArgs(['--pages', 'https://a.com/x, https://a.com/y']).pages, ['https://a.com/x', 'https://a.com/y']);
  assert.throws(() => map.parseArgs(['--max-pages', '0']));
  assert.throws(() => map.parseArgs(['--depth', '9']));
  assert.throws(() => map.parseArgs(['--other']));
});

test('functional map: the menus repeated across the site go only once as global navigation', () => {
  const menu = { name: 'Header', items: ['Home', 'Products', 'Contact'] };
  const pages = [
    { menus: [menu, { name: 'Sidebar', items: ['Filters'] }] },
    { menus: [{ ...menu, items: [...menu.items] }] },
    { menus: [{ ...menu, items: [...menu.items] }] },
  ];
  const globals = map.splitGlobalMenus(pages);
  assert.deepEqual(globals, [menu]);
  assert.deepEqual(pages[0].menus, [{ name: 'Sidebar', items: ['Filters'] }]);
  assert.deepEqual(pages[1].menus, []);
});

test('functional map: markdown with a header for the index, forms and constraints', () => {
  const field = { name: 'email', label: 'Email *', type: 'email', required: true, maxlength: 80, minlength: null, min: null, max: null, pattern: null, options: null, placeholder: 'you@mail.com' };
  const md = map.toMarkdown({ url: 'https://a.com/', host: 'a.com', date: '2026-10-14T10:00:00.000Z', max_pages: 30, unvisited: true,
    global_navigation: [{ name: 'Header', items: ['Home', 'Sign up'] }],
    pages: [
      { url: 'https://a.com/signup', path: '/signup', title: 'Sign up', description: '', headings: [{ level: 1, text: 'Create account' }], menus: [], buttons: ['Cancel'],
        messages: ['All fields are required'], tables: [], excerpt: '', forms: [{ name: 'signup', method: 'POST', action: '/api/signup', fields: [field], button: true }] },
      { url: 'https://a.com/down', path: '/down', error: 'net::ERR_TIMED_OUT' },
    ] });
  assert.match(md, /^---\ntitle: Site functional map\ntype: web\nsources: https:\/\/a\.com\/\nupdated: 2026-10-14\n/);
  assert.match(md, /raise --max-pages/);
  assert.match(md, /- \*\*Header\*\*: Home · Sign up/);
  assert.match(md, /### Form: signup \(POST \/api\/signup\)/);
  assert.match(md, /\| email \| Email \* \| email \| Yes \| max\. 80 characters; placeholder "you@mail\.com" \|/);
  assert.match(md, /Could not be opened: net::ERR_TIMED_OUT/);
  assert.doesNotMatch(md, /\n\n\n/);
});

test('functional map: constraints of a field in one line', () => {
  assert.equal(map.constraints({ min: 18, max: 99, pattern: '\\d+', options: [{ value: '', text: 'Choose' }, { value: 'US', text: 'United States' }] }),
    'minimum 18; maximum 99; pattern \\d+; options: Choose, United States');
});

test('github connector: token as Bearer, read-only and toolsets; without a token it stops with a clear message', () => {
  const ok = headers('github-headers.js', { GITHUB_TOKEN: 'ghp_test' });
  assert.equal(ok.status, 0, ok.stderr);
  assert.deepEqual(JSON.parse(ok.stdout), { Authorization: 'Bearer ghp_test', 'X-MCP-Readonly': 'true', 'X-MCP-Toolsets': 'context,repos,issues,pull_requests' });
  const without = headers('github-headers.js', {});
  assert.equal(without.status, 1);
  assert.match(without.stderr, /GITHUB_TOKEN is missing/);
  assert.doesNotMatch(without.stdout + without.stderr, /ghp_/);
  assert.equal(headers('github-headers.js', { GITHUB_TOKEN: 'x', GITHUB_TOOLSETS: 'repos;rm' }).status, 1);
});

test('gitlab connector: without a token it leaves OAuth (toolsets only); with a token it adds the Bearer', () => {
  const oauth = JSON.parse(headers('gitlab-headers.js', {}).stdout);
  assert.deepEqual(oauth, { 'X-Gitlab-Enabled-Mcp-Server-Toolsets': 'meta,core,merge_requests,work_items,repository,wikis' });
  const withToken = JSON.parse(headers('gitlab-headers.js', { GITLAB_TOKEN: 'glpat-test', GITLAB_TOOLSETS: 'repository, merge_requests' }).stdout);
  assert.equal(withToken.Authorization, 'Bearer glpat-test');
  assert.equal(withToken['X-Gitlab-Enabled-Mcp-Server-Toolsets'], 'repository,merge_requests');
});
