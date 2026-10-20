// Tests for the form tester and the UX evaluator (k0lmena tools).
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');

const K0 = path.resolve(__dirname, '..', '..', 'tools/k0lmena');
const forms = require(path.join(K0, 'tools/forms/forms.js'));
const ux = require(path.join(K0, 'tools/ux/evaluate.js'));

const field = (extra) => ({ n: 1, name: 'x', label: '', label_source: 'label', type: 'text', required: false, required_mark: false,
  maxlength: null, minlength: null, min: null, max: null, step: null, pattern: null, autocomplete: null, placeholder: null, ...extra });

test('forms: the tests depend on the field type', () => {
  const rules = (c) => forms.testsFor(field(c)).map((p) => p.rule);
  assert.deepEqual(rules({ name: 'email', label: 'Email', required: true }).slice(0, 2), ['Required empty', 'Only spaces']);
  assert.ok(rules({ name: 'email', label: 'Email' }).includes('Email without @'));
  assert.ok(rules({ type: 'number', min: 18, max: 99 }).includes('Above the maximum (99)'));
  assert.ok(rules({ name: 'name', label: 'Name' }).includes('Name with accents, ñ and apostrophe'));
  assert.ok(rules({ name: 'tel', label: 'Phone' }).includes('Phone with letters'));
  assert.deepEqual(rules({ type: 'checkbox', required: true }), ['Required not checked']);
  assert.deepEqual(rules({ type: 'select', required: true, options: [{ value: '' }, { value: 'US' }] }), ['Required not selected']);
});

test('forms: findings from the tests and from the field', () => {
  const c = field({ name: 'email', label: 'Email', required: true, tests: [
    { rule: 'Email without @', value: 'ana', expected: 'rejects', result: 'accepts', ok: false },
    { rule: 'Valid email', value: 'ana@test.com', expected: 'accepts', result: 'rejects', ok: false, message: 'Invalid' },
    { rule: 'Required empty', value: '', expected: 'rejects', result: 'rejects', ok: true, source: 'browser', message: 'Please fill out this field.' }] });
  const types = forms.findingsOf({ id: 'F-01' }, c).map((h) => `${h.severity}:${h.type}`);
  assert.ok(types.includes('High:Accepts an invalid value') && types.includes('High:Rejects a valid value'));
  assert.ok(types.includes('Medium:Required') && types.includes('Medium:Field type') && types.includes('Low:Error message'));
});

test("ux: Nielsen's 10 heuristics and the synonym groups", () => {
  assert.equal(Object.keys(ux.HEURISTICS).length, 10);
  assert.ok(ux.SYNONYMS.some((g) => g.includes('sign in') && g.includes('login')));
  assert.throws(() => ux.parseArgs(['--story', 'bad']));
});

test('forms: --submit-empty presses the button of THAT form, not the first one on the page', () => {
  const calls = [];
  const loc = (sel) => ({ locator: (s) => { calls.push(s); return loc(s); }, first: () => ({ sel }) });
  const page = { locator: (s) => { calls.push(s); return loc(s); } };
  forms.submitButton(page, { fields: [{ n: 7 }, { n: 8 }] });
  assert.equal(calls[0], '[data-k0-field="7"]');
  assert.equal(calls[1], 'xpath=ancestor::form[1]');
  assert.ok(calls[2].includes('button[type=submit]') && !calls[2].startsWith('form '));
});
