/* Injects data/catalog.json into course-planner.html (replaces the JSON block).
 * Usage: node embed-data.mjs [--check]
 *   --check  only validate that data/catalog.json parses and report stats
 */
import { readFileSync, writeFileSync } from 'node:fs';

const HTML = new URL('./course-planner.html', import.meta.url);
const JSON_PATH = new URL('./data/catalog.json', import.meta.url);
const checkOnly = process.argv.includes('--check');

let raw;
try { raw = readFileSync(JSON_PATH, 'utf8'); }
catch (e) { console.error('cannot read data/catalog.json:', e.message); process.exit(1); }

let data;
try { data = JSON.parse(raw); }
catch (e) { console.error('data/catalog.json is not valid JSON:', e.message); process.exit(1); }

const courses = data.courses || [];
const terms = (data.meta && data.meta.terms) || [];
const withAttr = courses.filter(c => c.attrSource === 'xlsx').length;
const stats = {
  courses: courses.length,
  colleges: [...new Set(courses.map(c => c.college))].length,
  GE: courses.filter(c => c.isGE).length,
  withAttributes: withAttr,
  withSessions: courses.filter(c => c.terms && Object.values(c.terms).some(t => t.sessions && t.sessions.length)).length,
  sessionsPerTerm: Object.fromEntries(terms.map(t => [t.id, courses.filter(c => c.terms && c.terms[t.id] && c.terms[t.id].sessions.length).length])),
  totalSessions: courses.reduce((n, c) => n + Object.values(c.terms || {}).reduce((m, t) => m + (t.sessions ? t.sessions.length : 0), 0), 0),
  tags: [...new Set(courses.flatMap(c => c.tags || []))].length
};
console.log('catalog stats:', JSON.stringify(stats, null, 1));

if (checkOnly) process.exit(0);

const html = readFileSync(HTML, 'utf8');
const re = /(<script id="course-data" type="application\/json">)([\s\S]*?)(<\/script>)/;
if (!re.test(html)) { console.error('data block not found in course-planner.html'); process.exit(1); }
// keep the file readable: indent the JSON with one space per level
const pretty = JSON.stringify(data, null, 1);
const out = html.replace(re, (_m, a, _b, c) => a + '\n' + pretty + '\n' + c);
writeFileSync(HTML, out);
console.log('embedded into course-planner.html:', (out.length / 1024).toFixed(0) + ' KB');

// verify the result still parses
const verify = out.match(re)[2];
JSON.parse(verify);
console.log('OK: embedded JSON parses');
