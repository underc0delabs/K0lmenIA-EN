// tools/emails/emails.steps.ts
//
// Email steps for any suite (web and api), against the Mailpit test mailbox (MAILPIT_URL in the .env).
// The app in the test environment has to send its emails over SMTP to Mailpit (see tools/mailpit/README.md).
//
//   Given the test mailbox is empty
//   Then an email arrives at "ana@test.com" with the subject "Confirm your account"
//   Then the email contains "Hi Ana"
//   Then the email does not contain "undefined"
//   Then the email has the attachment "invoice.pdf"
//   When I save the link from the email that contains "/confirm" as "confirmationLink"
//
// "an email arrives" waits up to EMAIL_TIMEOUT_S seconds (30 by default). The saved link is used
// later as {confirmationLink} in other steps (see tools/variables.ts).
import { Given, Then, When } from '@cucumber/cucumber';
import { interpolate, variables } from '../variables';

const base = () => (process.env.MAILPIT_URL || 'http://localhost:8025').replace(/\/+$/, '');

function headers(): Record<string, string> {
  const h: Record<string, string> = { Accept: 'application/json' };
  if (process.env.MAILPIT_USER) {
    h.Authorization = `Basic ${Buffer.from(`${process.env.MAILPIT_USER}:${process.env.MAILPIT_PASSWORD || ''}`).toString('base64')}`;
  }
  return h;
}

async function api(route: string, options: { method?: string; body?: unknown } = {}): Promise<any> {
  const r = await fetch(`${base()}${route}`, {
    method: options.method || 'GET',
    headers: { ...headers(), ...(options.body ? { 'Content-Type': 'application/json' } : {}) },
    body: options.body ? JSON.stringify(options.body) : undefined,
  }).catch((e) => {
    throw new Error(`Could not connect to Mailpit at ${base()} (${e.message}). Is it running? See tools/mailpit/README.md`);
  });
  if (!r.ok) throw new Error(`Mailpit responded ${r.status} on ${route}`);
  const type = r.headers.get('content-type') || '';
  return type.includes('json') ? r.json() : r.text();
}

const text = (m: any) => `${m.Subject || ''}\n${m.Text || ''}\n${String(m.HTML || '').replace(/<[^>]+>/g, ' ')}`.replace(/\s+/g, ' ');

function last(): any {
  const m = variables.__email;
  if (!m) throw new Error('First use "an email arrives at ... with the subject ...": no email has been selected.');
  return m;
}

Given('the test mailbox is empty', async function () {
  await api('/api/v1/messages', { method: 'DELETE', body: {} });
});

Then('an email arrives at {string} with the subject {string}', async function (to: string, subject: string) {
  const target = interpolate(to);
  const topic = interpolate(subject);
  const limit = Date.now() + Number(process.env.EMAIL_TIMEOUT_S || 30) * 1000;
  const query = encodeURIComponent(`to:"${target}" subject:"${topic}"`);
  while (Date.now() < limit) {
    const r = await api(`/api/v1/search?query=${query}&limit=5`);
    const m = (r.messages || [])[0];
    if (m) {
      variables.__email = await api(`/api/v1/message/${m.ID}`);
      if (typeof (this as any)?.attach === 'function') {
        await (this as any).attach(`EMAIL: ${m.Subject}\n- To: ${target}\n- View: ${base()}/view/${m.ID}`, 'text/plain');
      }
      return;
    }
    await new Promise((res) => setTimeout(res, 1500));
  }
  throw new Error(`No email arrived to ${target} with the subject "${topic}" within ${process.env.EMAIL_TIMEOUT_S || 30} s.`);
});

Then('the email contains {string}', function (t: string) {
  const wanted = interpolate(t);
  if (!text(last()).toLowerCase().includes(wanted.toLowerCase())) throw new Error(`The email does not contain "${wanted}".`);
});

Then('the email does not contain {string}', function (t: string) {
  const wanted = interpolate(t);
  if (text(last()).toLowerCase().includes(wanted.toLowerCase())) throw new Error(`The email contains "${wanted}" and should not.`);
});

Then('the email has the attachment {string}', function (name: string) {
  const attachments = (last().Attachments || []).map((a: any) => String(a.FileName || ''));
  if (!attachments.some((a: string) => a.toLowerCase().includes(interpolate(name).toLowerCase()))) {
    throw new Error(`The email does not have the attachment "${name}" (it has: ${attachments.join(', ') || 'none'}).`);
  }
});

When('I save the link from the email that contains {string} as {string}', function (fragment: string, name: string) {
  const m = last();
  const links = [...String(m.HTML || '').matchAll(/href\s*=\s*["']([^"']+)["']/gi)].map((x) => x[1].replace(/&amp;/g, '&'))
    .concat([...String(m.Text || '').matchAll(/https?:\/\/[^\s<>"')]+/g)].map((x) => x[0]));
  const link = links.find((l) => l.includes(interpolate(fragment)));
  if (!link) throw new Error(`The email does not have a link that contains "${fragment}".`);
  variables[name] = link;
});
