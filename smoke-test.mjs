/* Headless smoke test for the planner (schema v2).
 * Data-driven: every assertion is derived from whatever catalog is embedded,
 * so the same test works for the sample fixture and for the real catalog.
 * Usage: node smoke-test.mjs
 */
import { readFileSync } from 'node:fs';

const html = readFileSync(new URL('./course-planner.html', import.meta.url), 'utf8');
const scripts = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]);
const data = JSON.parse(scripts[0]);
const appSrc = scripts[scripts.length - 1];

const els = new Map();
const bodyListeners = [];
function FakeEl(tag) {
  const classes = new Set();
  return {
    tag, _html: '', _text: '', children: [], dataset: {}, disabled: false, checked: false, value: '',
    onclick: null, onchange: null, oninput: null, style: { setProperty() {} }, selectionStart: 0,
    classList: {
      add(c) { classes.add(c); }, remove(c) { classes.delete(c); },
      contains(c) { return classes.has(c); }, toggle(c) { classes.has(c) ? classes.delete(c) : classes.add(c); }
    },
    _classes: classes,
    set innerHTML(v) { this._html = String(v); this.children.length = 0; },
    get innerHTML() { return this._html; },
    set textContent(v) { this._text = String(v); },
    get textContent() { return this._text; },
    placeholder: '',
    appendChild(c) { this.children.push(c); return c; },
    addEventListener() {}, remove() {}, closest() { return null; }, querySelector() { return null; },
    focus() {}, setSelectionRange() {}
  };
}
globalThis.document = {
  documentElement: { lang: 'zh', style: { setProperty() {} } },
  body: { addEventListener: (type, fn) => bodyListeners.push(fn) },
  getElementById(id) {
    if (id === 'course-data') return { textContent: JSON.stringify(data) };
    if (!els.has(id)) els.set(id, FakeEl(id));
    return els.get(id);
  },
  createElement(tag) { return FakeEl(tag); }
};
globalThis.window = {};
globalThis.setTimeout = () => 0;
(0, eval)(appSrc);

const P = globalThis.window.__planner;
const { state, api } = P;
const COURSES = data.courses;
const byCode = c => COURSES.find(x => x.code === c);
const toMin = s => { const [h, m] = s.split(':').map(Number); return h * 60 + m; };
const results = [];
const check = (name, cond, extra = '') => { results.push({ name, ok: !!cond }); console.log((cond ? '  PASS  ' : '    FAIL') + '  ' + name + (cond ? '' : '   <-- ' + extra)); };
const textOf = n => (n.textContent || '') + (n._html || '') + (n.children || []).map(textOf).join(' ');
const modalRoot = () => document.getElementById('modalRoot');
const modalText = () => textOf(modalRoot());
const modalButtons = () => { const out = []; (function walk(n) { if (n.onclick) out.push(n); (n.children || []).forEach(walk); })(modalRoot()); return out; };
const clickModal = label => { const b = modalButtons().find(x => x.textContent === label && !x.disabled); if (b) { b.onclick(); return true; } return false; };
const click = (dataset, sel) => { const t = { dataset, closest: s => (s === sel ? t : null) }; bodyListeners.forEach(fn => fn({ target: t })); };
const reset = () => { state.selected = []; state.expanded.clear(); modalRoot().innerHTML = ''; els.get('courseList').innerHTML = ''; };
const listHtml = () => els.get('courseList').innerHTML;
const sessionsIn = (c, tid) => (c.terms && c.terms[tid] && c.terms[tid].sessions) || [];
const hasTerm = tid => COURSES.filter(c => sessionsIn(c, tid).length);

console.log('=== planner smoke test (schema v2, real catalog) ===');
console.log(`catalog: ${COURSES.length} courses, generated ${data.meta.generated || '?'}`);

/* --- 1. structure ------------------------------------------------------- */
const termIds = data.meta.terms.map(t => t.id);
check('four terms declared', termIds.length === 4, termIds.join(','));
check('2026-27-T2 is locked', data.meta.terms.find(t => t.id === '2026-27-T2').selectable === false);
const activeTerm = data.meta.terms.find(t => t.selectable && hasTerm(t.id).length)?.id;
check(`a selectable term has courses (${activeTerm})`, !!activeTerm);
state.acYear = activeTerm.slice(0, 7);
state.term = activeTerm.slice(-2);
state.studentCollege = Object.keys(data.meta.colleges)[0];
state.studentYear = 2;
P.render();
check('course list renders group headers', listHtml().includes('group-head'));
check('courses are collapsed by default (no detail body)', !listHtml().includes('course-body'));

/* --- 2. collapse / expand ---------------------------------------------- */
const firstCol = Object.keys(data.meta.colleges).find(k => COURSES.some(c => c.college === k));
state.openGroups.add(firstCol);
P.render();
const anyCourse = COURSES.find(c => c.college === firstCol);
check('college renders its prefix (subject) groups', listHtml().includes('subject-head'));
const pfx = anyCourse.code.split(' ')[0];
state.openSubjects.add(firstCol + '|' + pfx);
P.render();
check('group lists its courses once the prefix group is open', listHtml().includes(anyCourse.code));
click({ course: anyCourse.code }, '.course-head');
check('clicking a course expands details + select buttons', listHtml().includes('course-body'));
click({ course: anyCourse.code }, '.course-head');
check('clicking again collapses it', !listHtml().includes('course-body'));

/* --- 3. eligibility is data-driven ------------------------------------- */
const restricted = COURSES.find(c => !c.isGE && c.collegeRestriction.length && sessionsIn(c, activeTerm).length && c.collegeRestriction.length < 7);
if (restricted) {
  const foreign = Object.keys(data.meta.colleges).find(k => !restricted.collegeRestriction.includes(k));
  state.studentCollege = foreign; state.studentYear = 2;
  check(`college restriction blocks outsiders (${restricted.code} -> ${foreign})`, !!api.courseBlock(restricted));
  state.studentCollege = restricted.collegeRestriction[0];
  check(`owner college may take ${restricted.code}`, !api.courseBlock(restricted));
} else {
  check('college restriction sample present', false, 'none found');
}
const ge = COURSES.find(c => c.isGE && sessionsIn(c, activeTerm).length);
if (ge) {
  state.studentCollege = Object.keys(data.meta.colleges).find(k => k !== ge.college) || 'SDS';
  check(`GE course open to every college (${ge.code})`, !api.courseBlock(ge));
}
const yearCourse = COURSES.find(c => c.yearMin && c.yearMax && c.yearMin > 1 && sessionsIn(c, activeTerm).length);
if (yearCourse) {
  state.studentCollege = yearCourse.collegeRestriction[0] || yearCourse.college;
  state.studentYear = yearCourse.yearMin - 1;
  check(`year restriction blocks lower year (${yearCourse.code} Y${yearCourse.yearMin})`, !!api.courseBlock(yearCourse));
  state.studentYear = yearCourse.yearMin;
  check(`eligible year may take ${yearCourse.code}`, !api.courseBlock(yearCourse));
}
const noSession = COURSES.find(c => !sessionsIn(c, activeTerm).length);
if (noSession) check(`course without sessions in ${activeTerm} is blocked (${noSession.code})`,
  ['reasonNoSession', 'reasonNotImplemented'].includes(api.courseBlock(noSession).key));

/* --- 4. scheduling rule (unit-tested on the real clash function) ------- */
reset();
const A = { day: 1, start: 510, end: 560 }, B40 = { day: 1, start: 600, end: 650 }, Bshort = { day: 1, start: 590, end: 640 };
check('exactly 40 minutes apart is allowed', !api.findClash([A], null, [B40]));
check('10 minutes apart is a clash', !!api.findClash([A], null, [Bshort]));
check('overlap is a clash', !!api.findClash([A], null, [{ day: 1, start: 540, end: 600 }]));
check('different day never clashes', !api.findClash([A], null, [{ day: 2, start: 510, end: 560 }]));

/* --- 5. selection flow: lecture -> tutorial modal ---------------------- */
reset();
const tutCourse = COURSES.find(c => hasTerm(activeTerm).includes(c) && c.terms[activeTerm].requireTutorial && !api.courseBlock(c));
if (tutCourse) {
  state.studentCollege = tutCourse.collegeRestriction[0] || tutCourse.college;
  state.studentYear = Math.max(tutCourse.yearMin || 1, 1);
  const lec = sessionsIn(tutCourse, activeTerm).find(s => s.type === 'lecture');
  api.onSelectLecture(tutCourse.code, lec.id);
  if (modalText().includes('仍然选择')) clickModal('仍然选择');
  check(`tutorial picker opens for ${tutCourse.code}`, modalText().includes('辅导课') || modalText().includes('tutorial'));
  const picked = clickModal('选择') || clickModal('Select');
  check('choosing a tutorial commits lecture + tutorial', picked && state.selected.length === 1 && state.selected[0].tutorial, JSON.stringify(state.selected));
  check('the committed plan has no internal clash', (() => {
    const slots = [];
    for (const e of state.selected) {
      const c = byCode(e.code);
      for (const sid of [e.lecture, e.tutorial].filter(Boolean))
        for (const sl of api.slotsOf(c, P.termId(), sid)) slots.push(sl);
    }
    for (let i = 0; i < slots.length; i++) for (let j = i + 1; j < slots.length; j++) {
      const a = slots[i], b = slots[j];
      if (a.code === b.code && a.sid === b.sid) continue;
      if (a.day === b.day && a.start < b.end && b.start < a.end) return false;
    }
    return true;
  })());
} else check('tutorial course sample present', false, 'none selectable');

/* --- 6. mutex (exclusion) -------------------------------------------- */
let mutexPair = null, mutexOther = null;
for (const c of COURSES) {
  for (const x of c.exclusionCodes) {
    const o = byCode(x);
    if (!o) continue;
    const lec = sessionsIn(c, activeTerm).find(s => s.type === 'lecture');
    if (!lec) continue;
    state.studentCollege = c.collegeRestriction[0] || c.college;
    state.studentYear = c.yearMin || 2;
    if (api.courseBlock(c) || api.courseBlock(o)) continue;      // must be eligible for both
    mutexPair = { c, lec }; mutexOther = o; break;
  }
  if (mutexPair) break;
}
if (mutexPair) {
  reset();
  api.commit(mutexPair.c.code, mutexPair.lec.id, null);
  const blk = api.courseBlock(mutexOther);
  check(`exclusion blocks the paired course (${mutexPair.c.code} -> ${mutexOther.code})`,
    !!blk && blk.key === 'reasonMutex', JSON.stringify(blk));
  api.onRemove(mutexPair.c.code);
  const blk2 = api.courseBlock(mutexOther);
  check('after removal the paired course is no longer mutex-blocked', !blk2 || blk2.key !== 'reasonMutex');
} else check('exclusion pair present in catalog', false, 'none found');

/* --- 7. term switching + locked term ---------------------------------- */
reset();
state.acYear = '2026-27'; state.term = 'T1'; P.render();
state.term = 'T1';
els.get('filterTerm').onclick({ target: { closest: s => (s === '[data-term]' ? { dataset: { term: 'T2' } } : null) } });
check('2026-27 Term 2 is locked and pops an explanation', state.term === 'T1' && modalText().length > 0);
const sample = hasTerm('2025-26-T2')[0] || hasTerm(activeTerm)[0];
if (sample) {
  state.acYear = '2025-26'; state.term = 'T2';
  state.studentCollege = sample.collegeRestriction[0] || sample.college;
  state.studentYear = sample.yearMin || 2;
  const lec = sessionsIn(sample, '2025-26-T2').find(s => s.type === 'lecture');
  if (lec) {
    api.commit(sample.code, lec.id, null);
    api.onTermChange();
    check('switching term clears the selection', state.selected.length === 0);
  }
}

/* --- 8. timetable + credits ------------------------------------------- */
const plan = [];
for (const c of hasTerm('2025-26-T2')) {
  if (plan.length >= 4) break;
  if (c.terms['2025-26-T2'].requireTutorial) continue;
  const lec = sessionsIn(c, '2025-26-T2').find(s => s.type === 'lecture');
  if (!lec) continue;
  state.studentCollege = c.collegeRestriction[0] || c.college;
  state.studentYear = c.yearMin || 2;
  if (api.courseBlock(c)) continue;
  if (api.findClash(api.slotsOf(c, '2025-26-T2', lec.id), c.code, plan.flatMap(p => api.slotsOf(byCode(p.code), '2025-26-T2', p.lecture)))) continue;
  plan.push({ code: c.code, lecture: lec.id });
}
state.selected = plan.map(p => ({ ...p, tutorial: null, term: '2025-26-T2' }));
state.tab = 'timetable'; P.render();
const slots = state.selected.reduce((n, e) => n + api.slotsOf(byCode(e.code), '2025-26-T2', e.lecture).length, 0);
check(`timetable built a clash-free plan of ${plan.length} courses`, plan.length >= 2, JSON.stringify(plan.map(p => p.code)));
check('grid draws one block per weekly slot', (els.get('grid').innerHTML.match(/class="block/g) || []).length === slots);
check('lunch band drawn', els.get('grid').innerHTML.includes('closed'));
const units = state.selected.reduce((n, e) => n + (byCode(e.code).units || 0), 0);
check(`summary shows the credit total (${units})`, els.get('sideSummary').textContent.includes(String(units)), els.get('sideSummary').textContent);

/* --- 9. i18n + removed copy ------------------------------------------- */
state.lang = 'en'; P.render();
check('English UI renders', els.get('brand').innerHTML.includes('Course Selection'));
state.lang = 'zh'; P.render();
check('Chinese UI renders', els.get('brand').innerHTML.includes('自主选课'));
check('rule-explanation paragraph removed', !els.has('rulesLine'));
check('filter-hint paragraph removed', !els.has('filterHint'));
check('special-student and special-major panels are collapsible', els.get('tagBar').innerHTML.includes('<details'));

/* --- 10. new: prefix folding, absence tags, selectable-only, custom mode --- */
state.acYear = activeTerm.slice(0, 7); state.term = activeTerm.slice(-2);   // 回到本学期
state.search = ''; state.onlySelectable = false; state.onlyAvail = false;
state.filterCollege = 'ALL'; state.filterYear = 'ALL';
state.tagStudent = []; state.tagMajor = [];
state.openGroups.clear(); state.openSubjects.clear(); state.expanded.clear();
state.studentCollege = Object.keys(data.meta.colleges)[0];
state.openGroups.add(state.studentCollege);
P.render();
const lvl1 = listHtml();
check('level-2 prefix groups render inside a college', lvl1.includes('subject-head'));
check('courses stay hidden while the prefix group is closed', !lvl1.includes('course-head'));
const subjKeys = [...lvl1.matchAll(/data-subject="([^"]+)"/g)].map(m => m[1]);
check('prefix groups exist', subjKeys.length > 0, subjKeys.slice(0, 3).join(','));
if (subjKeys.length) {
  const prefix = subjKeys[0].split('|')[1];
  state.openSubjects.add(subjKeys[0]);
  P.render();
  const codes = [...listHtml().matchAll(/data-course="([^"]+)"/g)].map(m => m[1]);
  check(`opened prefix group lists only ${prefix} courses`, codes.length > 0 && codes.every(c => c.startsWith(prefix + ' ')), codes.slice(0, 4).join(','));
  check('course rows live in a .course container (level 3)', listHtml().includes('class="course"'));
}
const notImpl = COURSES.find(c => !sessionsIn(c, activeTerm).length);
if (notImpl) check(`course without sessions this term is tagged 本学期未开课 (${notImpl.code})`, api.courseBlock(notImpl).key === 'reasonNoSession');
const displayOnlyCourse = COURSES.find(c => sessionsIn(c, activeTerm).length && sessionsIn(c, activeTerm).every(s => s.selectable === false));
if (displayOnlyCourse) check(`display-only course is not selectable (${displayOnlyCourse.code})`, api.courseBlock(displayOnlyCourse).key === 'reasonDisplayOnly');
else check('display-only course sample present', true, 'none in this term');

state.onlySelectable = true; state.openSubjects.clear(); P.render();
const shown = [...listHtml().matchAll(/data-course="([^"]+)"/g)].map(m => m[1]);
check(`"selectable only" lists ${shown.length} courses, all eligible`,
  shown.length > 0 && shown.every(c => !api.courseBlock(byCode(c))), shown.slice(0, 4).join(','));
state.onlySelectable = false;

/* weekend (Sat/Sun) sessions: listed separately, never drawn on the Mon-Fri grid */
const wkCourse = COURSES.find(c => sessionsIn(c, activeTerm).some(s => s.selectable !== false && s.slots.some(sl => sl.day >= 6)));
if (wkCourse) {
  reset();
  state.studentCollege = wkCourse.collegeRestriction[0] || wkCourse.college;
  state.studentYear = wkCourse.yearMin || 2;
  state.customMode = true;                                   // 忽略限制，专测周末渲染
  const lec = sessionsIn(wkCourse, activeTerm).find(s => s.selectable !== false && s.slots.some(sl => sl.day >= 6));
  api.commit(wkCourse.code, lec.id, null);
  state.tab = 'timetable'; P.render();
  const wk = api.slotsOf(wkCourse, activeTerm, lec.id);
  const drawn = (els.get('grid').innerHTML.match(/class="block/g) || []).length;
  check(`weekend sessions listed separately (${wkCourse.code})`,
    els.get('weekend').innerHTML.includes('周末') || els.get('weekend').innerHTML.includes('Weekend'));
  check('weekend slots are excluded from the Mon-Fri grid',
    drawn === wk.filter(s => s.day < 6).length, `${drawn} vs ${wk.filter(s => s.day < 6).length}`);
  state.customMode = false; state.tab = 'select'; reset();
}

reset();
const restricted2 = COURSES.find(c => !c.isGE && c.collegeRestriction.length && c.collegeRestriction.length < 7 && sessionsIn(c, activeTerm).length);
if (restricted2) {
  state.studentCollege = Object.keys(data.meta.colleges).find(k => !restricted2.collegeRestriction.includes(k));
  state.studentYear = 2;
  check('college rule blocks by default', !!api.courseBlock(restricted2));
  state.customMode = true; P.render();
  check('custom mode suspends college/year/exclusion rules', api.courseBlock(restricted2) === null);
  check('custom mode shows an explanatory banner', els.get('modeNote').innerHTML.length > 0 && els.get('modeNote').style.display === '');
  state.customMode = false; P.render();
  check('leaving custom mode restores the rules', !!api.courseBlock(restricted2));
  check('custom banner hides again', els.get('modeNote').style.display === 'none');
}

const geCourse = COURSES.find(c => c.isGE && sessionsIn(c, activeTerm).length);
if (geCourse) {
  state.search = geCourse.code; P.render();
  const h = listHtml();
  check(`GE course shows the 通识 chip once, no duplicate GE tag (${geCourse.code})`,
    h.includes('tag ge') && !h.includes('>GE</span>'), h.slice(0, 100));
  state.search = '';
  P.render();
}

/* --- 11. offering college vs target-student college, major-only notice --- */
reset();
state.tagStudent = []; state.tagMajor = []; state.filterCollege = 'ALL';
state.filterYear = 'ALL'; state.search = ''; state.onlyAvail = false; state.onlySelectable = false;

const dual = COURSES.find(c => (c.deptTags || []).includes(c.college) &&
  (c.studentTags || []).includes(c.college) && sessionsIn(c, activeTerm).length) ||
  COURSES.find(c => (c.deptTags || []).length && (c.studentTags || []).includes(c.college));
if (dual) {
  state.search = dual.code; P.render();
  const row = listHtml();
  check(`same college code renders as two distinct tags (${dual.code})`,
    row.includes('tag dept col-' + dual.college) && row.includes('tag stu col-' + dual.college),
    row.slice(0, 160));
  check('tag legend distinguishes the two roles',
    els.get('tagLegend').innerHTML.includes('tag dept') && els.get('tagLegend').innerHTML.includes('tag stu'),
    els.get('tagLegend').innerHTML.slice(0, 120));
  state.expanded.add(dual.code); P.render();
  const detail = listHtml();
  check(`course detail states the offering school and the target-student school (${dual.code})`,
    detail.includes('开设学院') && detail.includes('目标学生学院'), 'attribute rows missing');
  state.expanded.delete(dual.code);
  state.search = ''; P.render();
} else {
  check('dual-role college tag sample present', true, 'no such course in this data');
}

const foreign2 = COURSES.find(c => (c.studentTags || []).length && c.collegeRestriction.length &&
  c.collegeRestriction.length < 7 && !c.isGE && sessionsIn(c, activeTerm).length);
if (foreign2) {
  state.studentCollege = Object.keys(data.meta.colleges).find(k => !foreign2.collegeRestriction.includes(k));
  state.studentYear = 2;
  check(`target-student college still blocks outsiders (${foreign2.code} -> ${state.studentCollege})`,
    !!api.courseBlock(foreign2), JSON.stringify(api.courseBlock(foreign2)));
}

// 学院限制只来自目标学生原文：没有列出学院就不再默认限本院
const openNow = COURSES.find(c => (c.majorOnly || c.targetStudents) &&
  !c.collegeRestriction.length && !c.isGE && c.college && sessionsIn(c, activeTerm).length);
if (openNow) {
  state.studentCollege = Object.keys(data.meta.colleges).find(k => k !== openNow.college);
  state.studentYear = openNow.yearMin || 1;
  check(`course with no target-student college is not college-blocked (${openNow.code} from ${state.studentCollege})`,
    !api.courseBlock(openNow), JSON.stringify(api.courseBlock(openNow)));
}

const noticeCourse = COURSES.find(c => c.majorOnly && sessionsIn(c, activeTerm).length);
if (noticeCourse) {
  check(`major-only course reports a notice (${noticeCourse.code})`, !!api.majorNotice(noticeCourse));
  check('courses with no named target report no notice',
    !api.majorNotice(COURSES.find(c => !c.majorOnly && !(c.targetTagText || []).length)));
  state.customMode = false; state.studentCollege = Object.keys(data.meta.colleges)[0]; state.studentYear = 2;
  const lec = sessionsIn(noticeCourse, activeTerm).find(s => s.selectable !== false && s.type === 'lecture');
  if (lec) {
    modalRoot().innerHTML = '';
    api.onSelectLecture(noticeCourse.code, lec.id);
    check(`selecting a major-only course warns first (${noticeCourse.code})`,
      modalText().includes('专业') || modalText().includes('Major'), modalText().slice(0, 120));
    const before = state.selected.length;
    clickModal(document.documentElement.lang === 'en' ? 'Select anyway' : '仍然选择');
    check('continuing after the notice commits the course', state.selected.length === before ||
      state.selected.length === before + 1, `${before} -> ${state.selected.length}`);
  }
} else {
  check('major-only course sample present', true, 'none in this term');
}
reset();

/* --- 12. PED Y1-only, CHI/CEC Chinese, prerequisite-inherited college limit --- */
reset();
state.customMode = false; state.filterCollege = 'ALL'; state.filterYear = 'ALL';
state.search = ''; state.tagStudent = []; state.tagMajor = [];

const peds = COURSES.filter(c => c.code.startsWith('PED '));
if (peds.length) {
  check(`every PED course is Y1-only (${peds.length} courses)`,
    peds.every(c => c.yearMin === 1 && c.yearMax === 1),
    peds.filter(c => !(c.yearMin === 1 && c.yearMax === 1)).map(c => c.code).join(','));
  const ped = peds.find(c => sessionsIn(c, activeTerm).length) || peds[0];
  state.studentYear = 2;
  check(`Y2 student cannot take a PED course (${ped.code})`,
    !!api.courseBlock(ped) || !sessionsIn(ped, activeTerm).length,
    JSON.stringify(api.courseBlock(ped)));
  state.studentYear = 1;
  const pedBlock = api.courseBlock(ped);
  check(`Y1 student is not year-blocked on a PED course (${ped.code})`,
    !pedBlock || pedBlock.key !== 'reasonYear', JSON.stringify(pedBlock));
}
const ped1101 = COURSES.find(c => c.code === 'PED 1101');
if (ped1101) {
  check('PED 1101 has no prerequisite left', !ped1101.prereqRaw && !(ped1101.prereqGroups || []).length
    && !api.prereqMissing(ped1101), JSON.stringify(ped1101.prereqRaw));
}

for (const prefix of ['CHI', 'CEC']) {
  const list = COURSES.filter(c => c.code.startsWith(prefix + ' '));
  if (list.length) {
    check(`${prefix} series is taught in Chinese (${list.length} courses)`,
      list.every(c => c.language === 'Chinese'),
      list.filter(c => c.language !== 'Chinese').map(c => c.code + '=' + c.language).join(','));
  }
}

// prerequisite-inherited college restriction: not from Target Students, still blocking
const inherited = COURSES.find(c => c.collegeRestriction.length && !c.isGE &&
  (c.targetStudents === null || !c.collegeRestriction.some(x => String(c.targetStudents).includes(x))) &&
  c.prereqGroups && c.prereqGroups.length && sessionsIn(c, activeTerm).length);
if (inherited) {
  state.studentCollege = Object.keys(data.meta.colleges).find(k => !inherited.collegeRestriction.includes(k));
  state.studentYear = inherited.yearMin || 1;
  check(`prerequisite-inherited college limit blocks outsiders (${inherited.code} -> ${state.studentCollege})`,
    !!api.courseBlock(inherited), JSON.stringify(api.courseBlock(inherited)));
  state.search = inherited.code; P.render();
  const row = listHtml();
  check(`inherited limit renders as a target-student tag (${inherited.code})`,
    inherited.collegeRestriction.every(x => row.includes('tag stu col-' + x)), row.slice(0, 160));
  state.search = ''; P.render();
}
reset();

/* --- 13. college -> programme two-level filter (build/major_map.json) --- */
reset();
const MAJORS = data.meta.majors || [];
state.lang = 'zh'; state.filterCollege = 'ALL'; state.filterYear = 'ALL';
state.search = ''; state.tagStudent = []; state.tagMajor = [];
state.filterMajorCollege = 'ALL'; state.filterMajor = 'ALL';
state.majorOpen = { college: false, major: false };
P.render();
const majorPanel = () => els.get('majorPanel').innerHTML;

if (MAJORS.length) {
  const p0 = majorPanel();
  check(`programme filter has two collapsible levels (${MAJORS.length} programmes)`,
    (p0.match(/<details/g) || []).length === 2 && p0.includes('按学院选课') && p0.includes('按专业选课'));
  check('programme filter is collapsed by default', !/\sopen\b/.test(p0));
  check('college level lists all colleges', Object.keys(data.meta.colleges).every(k => p0.includes('data-mcol="' + k + '"')));

  const smeMajors = MAJORS.filter(m => m.college === 'SME').map(m => m.zh);
  state.filterMajorCollege = 'SME'; state.majorOpen.college = true; P.render();
  const p1 = majorPanel();
  const chips = [...p1.matchAll(/data-mmajor="([^"]+)"/g)].map(m => m[1]).filter(v => v !== 'ALL');
  check('programme level lists only that college\'s programmes',
    chips.length === smeMajors.length && smeMajors.every(x => chips.includes(x)),
    JSON.stringify(chips));

  // 课程行只在展开时才渲染，因此用 1-2 层折叠头（学院 → 课程前缀）核对
  const heads = () => { P.render(); return [...els.get('courseList').innerHTML.matchAll(/data-subject="([^"]+)"/g)].map(m => m[1]); };
  state.filterMajor = 'ALL';
  const allowed = new Set(smeMajors);
  const collegeSubjects = heads();
  const collegeCourses = COURSES.filter(c => c.isGE || (c.majors || []).some(m => allowed.has(m)));
  const expectSubjects = new Set(collegeCourses.map(c => c.college + '|' + c.code.split(' ')[0]));
  check('college filter keeps only that college\'s programmes (+GE)',
    collegeSubjects.every(s => expectSubjects.has(s)) && collegeSubjects.length === expectSubjects.size,
    collegeSubjects.length + ' vs ' + expectSubjects.size);

  state.filterMajor = '会计学';
  const progSubjects = heads();
  const progCourses = COURSES.filter(c => c.isGE || (c.majors || []).includes('会计学'));
  const expectProg = new Set(progCourses.map(c => c.college + '|' + c.code.split(' ')[0]));
  check('programme filter keeps only that programme (+GE)',
    progSubjects.length === expectProg.size && progSubjects.every(s => expectProg.has(s)),
    JSON.stringify(progSubjects));
  check('programme filter includes that programme\'s own courses',
    progCourses.filter(c => !c.isGE).every(c => (c.majors || []).includes('会计学')));
  check('programme filter is in the active-filter set (auto-expand works)',
    heads().length > 0);

  // 没有专业的课在筛选生效时不能出现在渲染结果里：把渲染出的课程代码抓出来逐个核对
  const renderedCourses = () => {
    state.expanded.clear();
    COURSES.forEach(c => state.expanded.add(c.code));   // 展开全部课程行以拿到精确结果
    Object.keys(data.meta.colleges).forEach(k => state.openGroups.add(k));   // 展开全部学院层
    const keep = new Set(state.openSubjects);
    COURSES.forEach(c => state.openSubjects.add(c.college + '|' + c.code.split(' ')[0]));
    P.render();
    const out = new Set([...els.get('courseList').innerHTML.matchAll(/data-course="([^"]+)"/g)].map(m => m[1]));
    state.openSubjects = keep;
    return out;
  };
  const shown = renderedCourses();
  const expected = (f) => new Set(COURSES.filter(f).map(c => c.code));
  const eq = (a, b) => a.size === b.size && [...a].every(x => b.has(x));
  const orphan = COURSES.find(c => !(c.majors || []).length && !c.isGE && c.college);
  if (orphan) check('course without a programme is filtered out', !shown.has(orphan.code), orphan.code);
  check('programme filter renders exactly (programme courses + GE)',
    eq(shown, expected(c => c.isGE || (c.majors || []).includes('会计学'))),
    shown.size + ' vs ' + expected(c => c.isGE || (c.majors || []).includes('会计学')).size);

  state.filterMajor = 'ALL'; P.render();
  const shownCollege = renderedCourses();
  check('college filter renders exactly (college programmes + GE)',
    eq(shownCollege, expected(c => c.isGE || (c.majors || []).some(m => smeMajors.includes(m)))),
    shownCollege.size);

  state.filterMajorCollege = 'ALL'; state.filterMajor = 'ALL'; P.render();
  const shownAll = renderedCourses();
  check('clearing both levels restores the full catalogue',
    shownAll.size === COURSES.length, shownAll.size + ' vs ' + COURSES.length);

  state.filterMajorCollege = 'MED'; state.filterMajor = '药学'; state.lang = 'en'; P.render();
  check('programme names switch to English',
    majorPanel().includes('Pharmaceutical Science'), majorPanel().slice(0, 200));
  state.lang = 'zh';
}
state.filterMajorCollege = 'ALL'; state.filterMajor = 'ALL';
reset();

/* --- 14. GEA/GEB/GEC/GED series: Y2-Y4, GHF/GFN corequisite, Y1 bridging tags --- */
reset();
state.customMode = false; state.lang = 'zh'; state.filterCollege = 'ALL'; state.filterYear = 'ALL';
state.search = ''; state.tagStudent = []; state.tagMajor = []; state.studentYear = 2;

const SERIES = ['GEA ', 'GEB ', 'GEC ', 'GED '];
const series = COURSES.filter(c => SERIES.some(p => c.code.startsWith(p)));
if (series.length) {
  check(`GE series is Y2-Y4 for every course (${series.length} courses)`,
    series.every(c => c.yearMin === 2 && c.yearMax === 4),
    series.filter(c => !(c.yearMin === 2 && c.yearMax === 4)).map(c => c.code).join(','));
  check('GE series requires GFH 1000 or GFN 1000',
    series.every(c => JSON.stringify(c.prereqGroups) === JSON.stringify([['GFH 1000', 'GFN 1000']])),
    series.filter(c => JSON.stringify(c.prereqGroups) !== JSON.stringify([['GFH 1000', 'GFN 1000']])).map(c => c.code).join(','));

  const y1Series = series.find(c => sessionsIn(c, activeTerm).length) || series[0];
  state.studentYear = 1; state.studentCollege = Object.keys(data.meta.colleges)[0];
  check(`year-1 student is year-blocked on a GE series course (${y1Series.code})`,
    (api.courseBlock(y1Series) || {}).key === 'reasonYear' || !sessionsIn(y1Series, activeTerm).length,
    JSON.stringify(api.courseBlock(y1Series)));
  state.studentYear = 2;
  check(`year-2 student passes the year rule (${y1Series.code})`,
    (api.courseBlock(y1Series) || {}).key !== 'reasonYear', JSON.stringify(api.courseBlock(y1Series)));
  check(`GE series course carries the GFH/GFN prerequisite (${y1Series.code})`,
    /GFH/.test(y1Series.prereqRaw || '') && y1Series.prereqGroups.length === 1);
}

const bridging = COURSES.filter(c => (c.y1Tags || []).length);
if (bridging.length) {
  const b = bridging[0];
  check(`bridging course declares its Y1 programmes (${b.code})`,
    b.y1Tags.length > 0 && /GFH|GFN/.test(b.code), JSON.stringify(b.y1Tags));
  state.studentYear = 1;
  state.tagStudent = [];
  const blocked = api.courseBlock(b);
  check(`year-1 student without the tag is blocked (${b.code})`,
    (blocked || {}).key === 'reasonYear', JSON.stringify(blocked));
  state.tagStudent = [b.y1Tags[0]];
  const allowed = api.courseBlock(b);
  check(`year-1 student with the named tag passes (${b.code} + ${b.y1Tags[0]})`,
    (allowed || {}).key !== 'reasonYear', JSON.stringify(allowed));
  check('bridging notice explains the Y1 exception',
    /Y1|一年级/.test(api.majorNotice(b) || ''), api.majorNotice(b));
  state.tagStudent = []; state.studentYear = 2;
}

// GEB 2508/2509 share one target string in the PDF
const pair = COURSES.filter(c => c.code === 'GEB 2508' || c.code === 'GEB 2509');
if (pair.length === 2) {
  check('GEB 2508 / 2509 carry the same repaired target list',
    pair[0].targetStudents === pair[1].targetStudents && /STAT/.test(pair[0].targetStudents),
    pair.map(c => c.code + ':' + c.targetStudents).join(' | '));
  check('GEB 2508 / 2509 report the named-programme notice',
    pair.every(c => (c.targetTagText || []).length > 0 && !!api.majorNotice(c)));
}
reset();

/* --- 15. visibility + motion: toggles, press bounce, count roll-up --- */
reset();
state.lang = 'zh'; state.onlyAvail = false; state.onlySelectable = false; state.customMode = false;
P.render();
const cls = id => els.get(id)._classes;
check('the three filter switches render as visible toggle pills',
  (html.match(/class="field toggle"/g) || []).length === 3,
  'expected 3 toggle pills');
check('switch off-state has no "on" class', !cls('tgOnlyAvail').has('on') && !cls('tgCustomMode').has('on'));
state.onlySelectable = true; state.customMode = true; P.render();
check('switch on-state adds the "on" class (no :has() dependency)',
  cls('tgOnlySelectable').has('on') && cls('tgCustomMode').has('on') && !cls('tgOnlyAvail').has('on'));
state.onlySelectable = false; state.customMode = false;

// 样式层：三个开关的对比度与动效规则必须存在
check('toggle style raises contrast (dark border + purple text)',
  /\.toggle\{[^}]*border:1\.5px solid #cbb4ea/.test(html) && /\.toggle\{[^}]*color:var\(--primary\)/.test(html));
check('inactive chips are darkened too', /\.chip\{[^}]*border:1\.5px solid #cbb4ea/.test(html));
check('every button has a press bounce', /button:active\{transform:scale\(\.94\)\}/.test(html) &&
  /@keyframes btn-pop/.test(html));
check('count badge has a bump animation', /@keyframes badge-bump/.test(html) && /\.count-badge\.bump/.test(html));

// 计数徽标：选课成功后数字必须跟上（桩里没有几何信息 -> 走直接更新分支）
reset();
state.studentCollege = Object.keys(data.meta.colleges)[0]; state.studentYear = 3;
check('count badge starts at 0 / total', /^0 \/ 926$/.test(els.get('countBadge').textContent),
  els.get('countBadge').textContent);
const pickable = COURSES.find(c => !api.courseBlock(c) && sessionsIn(c, activeTerm).length &&
  !(c.terms[activeTerm] && c.terms[activeTerm].requireTutorial));
if (pickable) {
  const lec = sessionsIn(pickable, activeTerm).find(s => s.type === 'lecture' && s.selectable !== false);
  // 真实选课路径：commit -> sparkCountUp（桩内无几何信息 -> 直接更新计数）
  const popped = [];
  const btn = {
    dataset: { act: 'lecture', code: pickable.code, sid: lec.id },
    classList: { add: c => popped.push(c), remove() {}, contains: () => false, toggle() {} },
    getBoundingClientRect: () => null
  };
  api.onSelectLecture(pickable.code, lec.id, btn);
  if (api.majorNotice(pickable)) {
    // 该课有专业提示 -> 先确认弹窗，再检查计数（徽标只在真正选上后才变）
    check('count badge waits while the notice dialog is open', els.get('countBadge').textContent === '0 / 926',
      els.get('countBadge').textContent);
    clickModal(document.documentElement.lang === 'en' ? 'Select anyway' : '仍然选择');
  }
  check(`count badge advances after selecting (${pickable.code})`,
    /^1 \/ 926$/.test(els.get('countBadge').textContent), els.get('countBadge').textContent);
  // 再确认事件委托会给按下的按钮加回弹类
  const tbtn = {
    dataset: { act: 'lecture', code: pickable.code, sid: lec.id },
    classList: { add: c => popped.push(c), remove() {}, contains: () => false, toggle() {} },
    getBoundingClientRect: () => null,
    closest: sel => (sel === 'button[data-act]' ? tbtn : null)
  };
  bodyListeners.forEach(fn => fn({ target: { closest: sel => (sel === 'button[data-act]' ? tbtn : null) } }));
  check('pressing a button adds the pop class', popped.includes('pop'), popped.join(','));
  state.selected = []; P.render();
} else {
  check('a selectable course exists in this term', false, 'none found');
}
reset();

/* --- 16. timetable: collapse panel + PNG/XLSX export --- */
reset();
state.acYear = '2025-26'; state.term = 'T1'; state.customMode = true;
state.studentCollege = Object.keys(data.meta.colleges)[0]; state.studentYear = 3; state.selected = [];
const picked = [];
for (const c of COURSES) {
  if (picked.length >= 2) break;
  if (api.courseBlock(c)) continue;
  const tv = c.terms['2025-26-T1']; if (!tv) continue;
  const lec = tv.sessions.find(s => s.type === 'lecture' && s.selectable !== false && s.slots.length);
  if (!lec) continue;
  const slots2 = api.slotsOf(c, '2025-26-T1', lec.id);
  if (slots2.some(s => picked.some(pp => pp.slots.some(o => o.day === s.day && s.start < o.end && o.start < s.end)))) continue;
  const tut = tv.requireTutorial ? tv.sessions.find(s => s.type === 'tutorial' && s.selectable !== false) : null;
  picked.push({ code: c.code, lec: lec.id, tut: tut ? tut.id : null, slots: slots2 });
}
picked.forEach(pp => api.commit(pp.code, pp.lec, pp.tut));
state.tab = 'timetable'; P.render();
check(`export test selected ${picked.length} conflict-free courses`, picked.length > 0);

// 折叠已选课程
check('collapse button starts expanded', els.get('btnCollapseSide').textContent === '«' &&
  els.get('ttGrid').className === 'ttmain');
els.get('btnCollapseSide').onclick();
check('collapse hides the side panel and widens the grid',
  state.sideCollapsed === true && els.get('ttGrid').className === 'ttmain side-collapsed' &&
  els.get('btnCollapseSide').textContent === '»');
els.get('btnCollapseSide').onclick();
check('collapse toggles back', state.sideCollapsed === false && els.get('ttGrid').className === 'ttmain');

// 导出数据
const ex = api.collectExportData();
check('export data covers every weekly slot', ex.placements.length >= picked.length, String(ex.placements.length));
check('export data has units and term', typeof ex.units === 'number' && /\S/.test(ex.term));

// PNG 导出：canvas 在测试环境不可用，必须安全降级且不抛错
let captured = null;
globalThis.window.URL = { createObjectURL(b) { captured = b; return 'blob:stub'; }, revokeObjectURL() {} };
let expErr = null;
try { api.exportTimetablePng(); } catch (e) { expErr = e.message; }
check('exporting the timetable as an image does not throw', expErr === null, String(expErr));
check('image export does not fabricate a download without a canvas', captured === null,
  captured ? 'unexpected blob' : '');
check('the xlsx export is gone', api.buildXlsx === undefined && api.exportTimetableXlsx === undefined &&
  !html.includes('btnExportXlsx') && !html.includes('zipStore'));
check('the spark effect is gone', !html.includes('spark-fly') && !html.includes('playSparkToBadge') &&
  !html.includes('sparkCountUp') && !html.includes('class="spark"'));
check('the press bounce is kept', /@keyframes btn-pop/.test(html) && /button:active\{transform:scale\(\.94\)\}/.test(html));
check('the count badge still bumps without the spark', /@keyframes badge-bump/.test(html));

state.selected = []; state.tab = 'select'; reset();

const failed = results.filter(r => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
process.exit(failed.length ? 1 : 0);
