/* Catalog validator for course-planner.html (schema v2, real data).
 * Usage: node validate-catalog.mjs
 * Structural rules are errors; scheduling oddities in real source data are warnings.
 */
import { readFileSync } from 'node:fs';

const html = readFileSync(new URL('./course-planner.html', import.meta.url), 'utf8');
const m = html.match(/<script id="course-data"[^>]*>([\s\S]*?)<\/script>/);
if (!m) { console.error('FAIL: course-data block not found'); process.exit(1); }
let DATA;
try { DATA = JSON.parse(m[1]); } catch (e) { console.error('FAIL: data block is not valid JSON:', e.message); process.exit(1); }

const R = DATA.meta.rules;
const COLLEGES = DATA.meta.colleges || {};
const TERMS = DATA.meta.terms || [];
const COURSES = DATA.courses || [];
const TAGGROUPS = DATA.meta.tagGroups || {};

const toMin = s => { const [h, mi] = String(s).split(':').map(Number); return h * 60 + mi; };
const fmt = x => String(Math.floor(x / 60)).padStart(2, '0') + ':' + String(x % 60).padStart(2, '0');
const DAY_START = toMin(R.dayStart), DAY_END = toMin(R.dayEnd);
const CLOSED = R.closedWindow.map(toMin), MIN_GAP = R.minGapMinutes;
const DURS = new Set(R.allowedDurations);
const DAYNAME = ['', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri'];
const CODE_RE = /^[A-Z]{2,4} \d{4}[A-Z]?$/;

const errors = [], warns = [], notes = [];
const fail = s => errors.push(s);
const warn = s => warns.push(s);
const note = s => notes.push(s);

/* ---------------------------------------------------------------- 1. shape */
if (!TERMS.length) fail('meta.terms is empty');
const TERM_IDS = new Set(TERMS.map(t => t.id));
for (const t of TERMS) {
  if (!t.id || !t.year || !t.term) fail(`term entry incomplete: ${JSON.stringify(t)}`);
  if (typeof t.selectable !== 'boolean') warn(`term ${t.id}: selectable flag missing`);
}
const seen = new Set();
for (const c of COURSES) {
  const tag = c.code || '(no code)';
  if (seen.has(c.code)) fail(`duplicate course code: ${c.code}`);
  seen.add(c.code);
  if (!CODE_RE.test(tag)) fail(`${tag}: code does not match "ABC 1234"`);
  if (!c.name) fail(`${tag}: missing name`);
  if (!COLLEGES[c.college]) fail(`${tag}: unknown college "${c.college}"`);
  if (!Array.isArray(c.tags)) fail(`${tag}: tags must be an array`);
  if (c.attrSource === 'xlsx') {
    if (typeof c.units !== 'number' && c.units !== null) fail(`${tag}: units must be a number or null`);
    if (c.language !== null && typeof c.language !== 'string') fail(`${tag}: language must be a string or null`);
    if (c.units === null) warn(`${tag}: attrSource=xlsx but units is null`);
    if (!c.language) warn(`${tag}: attrSource=xlsx but language is empty`);
  } else if (c.attrSource !== 'none') {
    warn(`${tag}: unexpected attrSource "${c.attrSource}"`);
  }
  if (c.yearMin !== null && c.yearMin !== undefined && !(c.yearMin >= 1 && c.yearMin <= 6)) fail(`${tag}: bad yearMin ${c.yearMin}`);
  if (c.yearMax !== null && c.yearMax !== undefined && !(c.yearMax >= 1 && c.yearMax <= 6)) fail(`${tag}: bad yearMax ${c.yearMax}`);
  if (c.yearMin && c.yearMax && c.yearMin > c.yearMax) fail(`${tag}: yearMin > yearMax`);
  for (const g of c.prereqGroups || []) if (!Array.isArray(g) || !g.length) fail(`${tag}: empty prereq group`);
  for (const code of c.exclusionCodes || []) if (!CODE_RE.test(code) && !/^[A-Z]{2,4}\d{4}[A-Z]?$/.test(code)) warn(`${tag}: odd exclusion code "${code}"`);
  for (const k of Object.keys(c.terms || {})) if (!TERM_IDS.has(k)) fail(`${tag}: sessions under unknown term "${k}"`);
}

/* --------------------------------------------- 2. sessions & time geometry */
let nSessions = 0, nSlots = 0, tbaSessions = 0, multiRoom = 0, multiSlot = 0, weekendSlots = 0, displayOnly = 0;
const timeDurations = new Map();
const placements = [];      // for teacher/venue clash checks
for (const c of COURSES) {
  for (const [tid, tv] of Object.entries(c.terms || {})) {
    const tag = `${c.code}@${tid}`;
    if (!tv || !Array.isArray(tv.sessions)) { fail(`${tag}: term entry has no sessions array`); continue; }
    const ids = new Set();
    const tuts = tv.sessions.filter(s => s.type === 'tutorial');
    const lects = tv.sessions.filter(s => s.type === 'lecture');
    for (const s of tv.sessions) {
      nSessions++;
      if (ids.has(s.id)) fail(`${tag}: duplicate session id ${s.id}`);
      ids.add(s.id);
      if (!['lecture', 'tutorial'].includes(s.type)) fail(`${tag}/${s.id}: bad type ${s.type}`);
      if (!Array.isArray(s.rooms)) fail(`${tag}/${s.id}: rooms must be an array`);
      if (s.rooms && s.rooms.length > 1) { multiRoom++; }
      if (!Array.isArray(s.slots)) { fail(`${tag}/${s.id}: slots must be an array`); continue; }
      if (s.slots.length > 1) multiSlot++;
      if (!s.slots.length) { if (!s.timeTBA) warn(`${tag}/${s.id}: no slots and timeTBA is not true`); else tbaSessions++; }
      const own = [];
      for (const sl of s.slots) {
        nSlots++;
        const st = toMin(sl.start), en = toMin(sl.end), dur = en - st;
        const w = `${tag}/${s.id} ${DAYNAME[sl.day] || '?'} ${sl.start}-${sl.end}`;
        if (!(sl.day >= 1 && sl.day <= 7)) fail(`${w}: day outside Mon-Sun`);
        if (st % 30 !== 0) fail(`${w}: start not on :00/:30`);
        if (!DURS.has(dur)) fail(`${w}: duration ${dur} not in allowed set [${R.allowedDurations}]`);
        if (st < DAY_START) fail(`${w}: starts before ${R.dayStart}`);
        if (en > DAY_END) fail(`${w}: ends after ${R.dayEnd}`);
        if (st < CLOSED[1] && en > CLOSED[0]) warn(`${w}: overlaps the closed 12:30-13:30 window [source data]`);
        if (sl.day >= 6) weekendSlots++;
        if (s.selectable === false) displayOnly++;
        for (const o of own) if (o.day === sl.day && st < o.end && o.start < en) fail(`${w}: overlaps another slot of the same session`);
        own.push({ day: sl.day, start: st, end: en });
        timeDurations.set(dur, (timeDurations.get(dur) || 0) + 1);
        placements.push({ code: c.code, sid: s.id, teacher: s.teacher || '', rooms: s.rooms || [], day: sl.day, start: st, end: en });
      }
    }
    if (tv.requireTutorial) {
      if (!tuts.filter(t => t.selectable !== false).length) fail(`${tag}: requireTutorial but no selectable tutorial session`);
    } else if (tuts.length) {
      warn(`${tag}: has tutorial sessions but requireTutorial is false`);
    }
    if (!lects.length && !tuts.length) fail(`${tag}: no sessions at all`);
  }
}

/* ------------------------------------------------- 3. teacher / venue clash */
const overlap = (a, b) => a.day === b.day && a.start < b.end && b.start < a.end;
const byKey = (arr, k) => arr.reduce((mp, x) => ((mp[k(x)] = mp[k(x)] || []).push(x), mp), {});
for (const [teacher, list] of Object.entries(byKey(placements.filter(p => p.teacher && !/^(staff|tba|to be announced)$/i.test(p.teacher)), p => p.teacher))) {
  for (let i = 0; i < list.length; i++) for (let j = i + 1; j < list.length; j++) {
    if (list[i].code === list[j].code && list[i].sid === list[j].sid) continue;   // same session
    if (!overlap(list[i], list[j])) continue;
    const msg = `${teacher} double-booked: ${list[i].code}/${list[i].sid} vs ${list[j].code}/${list[j].sid} (${DAYNAME[list[i].day]} ${fmt(list[i].start)}-${fmt(list[i].end)})`;
    if (list[i].code === list[j].code) warn(msg + ' [same course, parallel sections share a teacher: source data]');
    else warn(msg + ' [cross-course]');
  }
}
const venueMap = {};
for (const p of placements) for (const room of p.rooms) {
  if (!room || room === 'TBA') continue;
  (venueMap[room] = venueMap[room] || []).push(p);
}
for (const [room, list] of Object.entries(venueMap)) {
  for (let i = 0; i < list.length; i++) for (let j = i + 1; j < list.length; j++) {
    if (list[i].code === list[j].code && list[i].sid === list[j].sid) continue;   // same session, two rooms = intentional
    if (overlap(list[i], list[j]))
      warn(`${room} double-booked: ${list[i].code}/${list[i].sid} vs ${list[j].code}/${list[j].sid} (${DAYNAME[list[i].day]} ${fmt(list[i].start)}-${fmt(list[i].end)})`);
  }
}

/* --------------------------------------------------------- 4. tag vocabulary */
const tagCount = {};
for (const c of COURSES) for (const t of c.tags || []) tagCount[t] = (tagCount[t] || 0) + 1;
const declared = new Set([...(TAGGROUPS.specialStudentTypes || []), ...(TAGGROUPS.specialMajors || [])]);
const undeclared = Object.keys(tagCount).filter(t => !declared.has(t) && !COLLEGES[t] && t !== 'GE');
if (undeclared.length) note(`${undeclared.length} tag(s) outside the declared groups (college/GE tags excluded): ${undeclared.slice(0, 12).join(', ')}`);

/* --------------------------------------------------- 5. feasibility sampling */
function clash(a, b) {
  if (a.day !== b.day) return false;
  let f = a, s = b; if (b.start < a.start) { f = b; s = a; }
  if (s.start < f.end) return true;
  const gap = s.start - f.end;
  if (gap >= MIN_GAP) return false;
  if (f.end <= CLOSED[0] && s.start >= CLOSED[1]) return false;
  return true;
}
function planFor(college, year, tid) {
  const pool = COURSES.filter(c => {
    const tv = c.terms && c.terms[tid];
    if (!tv || !tv.sessions.length) return false;
    if (!c.isGE && (c.collegeRestriction || []).length && !c.collegeRestriction.includes(college)) return false;
    if (c.yearMin && year < c.yearMin) return false;
    if (c.yearMax && year > c.yearMax) return false;
    return true;
  });
  const chosen = [];
  const used = () => chosen.flatMap(x => x.slots);
  const free = slots => !used().some(u => slots.some(s => clash(u, s)));
  for (const c of pool) {
    if ((c.exclusionCodes || []).some(x => chosen.some(y => y.code === x))) continue;
    const tv = c.terms[tid];
    const lects = tv.sessions.filter(s => s.type === 'lecture' && s.selectable !== false);
    const tuts = tv.sessions.filter(s => s.type === 'tutorial' && s.selectable !== false);
    for (const lec of lects) {
      const ls = lec.slots.map(x => ({ day: x.day, start: toMin(x.start), end: toMin(x.end) }));
      if (!free(ls)) continue;
      if (tv.requireTutorial) {
        const ok = tuts.find(t => {
          const ts = t.slots.map(x => ({ day: x.day, start: toMin(x.start), end: toMin(x.end) }));
          return free(ls.concat(ts));
        });
        if (!ok) continue;
        chosen.push({ code: c.code, slots: ls.concat(ok.slots.map(x => ({ day: x.day, start: toMin(x.start), end: toMin(x.end) }))) });
      } else {
        chosen.push({ code: c.code, slots: ls });
      }
      break;
    }
  }
  return chosen.length;
}
const termPlans = {};
for (const t of TERMS.filter(x => x.selectable)) {
  let best = 0, worst = Infinity, empty = 0;
  for (const col of Object.keys(COLLEGES)) {
    for (const y of [1, 2, 3, 4]) {
      const n = planFor(col, y, t.id);
      best = Math.max(best, n); worst = Math.min(worst, n);
      if (n === 0) empty++;
    }
  }
  termPlans[t.id] = { best, worst, emptyProfiles: empty };
}
const totalWithSessions = {};
for (const t of TERMS) totalWithSessions[t.id] = COURSES.filter(c => c.terms && c.terms[t.id] && c.terms[t.id].sessions.length).length;

/* ------------------------------------------------------------------ report */
console.log('=== catalog ===');
console.log(`  courses: ${COURSES.length} | colleges: ${Object.keys(COLLEGES).length} | GE: ${COURSES.filter(c => c.isGE).length} | tagged: ${COURSES.filter(c => (c.tags || []).length).length}`);
console.log(`  attributes from xlsx: ${COURSES.filter(c => c.attrSource === 'xlsx').length} | units known: ${COURSES.filter(c => typeof c.units === 'number').length}`);
console.log(`  sessions: ${nSessions} | weekly slots: ${nSlots} | multi-slot: ${multiSlot} | multi-room: ${multiRoom} | time-TBA: ${tbaSessions}`);
console.log(`  weekend (Sat/Sun) slots: ${weekendSlots} | display-only sessions: ${displayOnly} | day range: ${R.dayStart}-${R.dayEnd} | durations: ${R.allowedDurations.join('/')}`);
console.log('  durations in use: ' + [...timeDurations.entries()].sort((a, b) => a[0] - b[0]).map(([d, n]) => `${d}min x${n}`).join(', '));
console.log('=== terms ===');
for (const t of TERMS) {
  const p = termPlans[t.id];
  console.log(`  ${t.id}${t.selectable ? '' : ' [locked]'}: courses with sessions=${totalWithSessions[t.id]} | tutorial-required=${COURSES.filter(c => c.terms && c.terms[t.id] && c.terms[t.id].requireTutorial).length}` +
    (p ? ` | sample plan size: ${p.worst}..${p.best} (empty profiles: ${p.emptyProfiles}/28)` : ''));
}
if (notes.length) { console.log('=== notes ==='); notes.forEach(n => console.log('  - ' + n)); }
if (warns.length) { console.log(`=== warnings (${warns.length}) ===`); warns.slice(0, 25).forEach(w => console.log('  ! ' + w)); if (warns.length > 25) console.log(`  ... and ${warns.length - 25} more`); }
if (errors.length) { console.log(`=== ERRORS (${errors.length}) ===`); errors.slice(0, 40).forEach(e => console.log('  x ' + e)); process.exit(1); }
console.log('\nOK: catalog structure valid.');
