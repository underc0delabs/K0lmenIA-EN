// tools/variables.ts
//
// Scenario variables shared between steps (API, database, web).
// E.g.: an API step saves the created id ("I save the response field "id" as "userId"")
// and a database step uses it ("where "id" is "{userId}"").
// They are reset before each scenario.
import { After, Before } from '@cucumber/cucumber';
import { randomUUID } from 'crypto';

export const variables: Record<string, unknown> = {};

// Start and end of each scenario (in the report): the log-analyst cross-references them with the server logs.
let scenarioStart = new Date();
After(function () {
  const end = new Date();
  if (typeof (this as any)?.attach === 'function') {
    return (this as any).attach(`TIME: start=${scenarioStart.toISOString()} end=${end.toISOString()}`, 'text/plain');
  }
});

Before(function ({ pickle }) {
  scenarioStart = new Date();
  for (const k of Object.keys(variables)) delete variables[k];

  // Scenarios that depend on missing information (skill context-research):
  // tags @missing-info and @MI-XX. A visible note is left in the report.
  const tags = (pickle?.tags ?? []).map((t: { name: string }) => t.name.replace(/^@/, ''));
  const ids = tags.filter((t: string) => /^MI-\d+$/i.test(t));
  if (tags.some((t: string) => t.toLowerCase() === 'missing-info') || ids.length) {
    const note = `MISSING INFO (${ids.join(', ') || 'see the context sheet'}): this scenario depends on data `
      + 'that is not defined in the story or its sources. Its result may change once they are resolved. '
      + 'Details in output/context/.';
    if (typeof (this as any)?.attach === 'function') return (this as any).attach(note, 'text/plain');
  }
});

// Unique data so it doesn't clash with a previous run (an email or a name that already exists):
// generated the first time it is used in the scenario and keeps the same value until it ends, so the
// POST and the following GET use the same value. E.g.: "email": "qa+{random}@test.com".
const GENERATED: Record<string, () => string> = {
  uuid: () => randomUUID(),
  random: () => String(Math.floor(100000 + Math.random() * 900000)),
  timestamp: () => String(Date.now()),
  now: () => new Date().toISOString(),
};

/**
 * Replaces {name} with a saved variable, with generated data ({uuid}, {random},
 * {timestamp}, {now}) or, otherwise, with the environment variable. Anything without a value stays as is.
 */
export function interpolate(text: string): string {
  return text.replace(/\{([A-Za-z_][\w.]*)\}/g, (match, name) => {
    if (name in variables) return String(variables[name]);
    if (name in GENERATED) {
      variables[name] = GENERATED[name]();
      return String(variables[name]);
    }
    if (process.env[name] !== undefined) return String(process.env[name]);
    return match;
  });
}
