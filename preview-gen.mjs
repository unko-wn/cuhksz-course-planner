/* Builds preview copies from the embedded catalog for screenshot checks. */
import { readFileSync, writeFileSync } from 'node:fs';
const src = readFileSync(new URL('./course-planner.html', import.meta.url), 'utf8');

const common = `
  var p = window.__planner, D = p.DATA, tid = '2025-26-T1';
  p.state.studentCollege = 'SDS'; p.state.studentYear = 3;
  p.state.acYear = '2025-26'; p.state.term = 'T1';
`;

// 选课页：三层折叠 + 未开课/仅展示标签
const fold = `<script>
(function () {
${common}
  p.state.openGroups.add('MUS');
  p.state.openSubjects.add('MUS|MUS');
  p.state.openSubjects.add('MUS|MED');
  p.render();
})();
<\/script>`;

// 课表页：自动挑 4 门不冲突的课（含一节 21:xx 或周末的课）
const tt = `<script>
(function () {
${common}
  var chosen = [], used = [];
  function clash(a, b) { if (a.day !== b.day) return false;
    var f = a.start <= b.start ? a : b, s = a.start <= b.start ? b : a;
    if (s.start < f.end) return true; return (s.start - f.end) < 40; }
  D.courses.forEach(function (c) {
    if (chosen.length >= 4) return;
    var tv = c.terms && c.terms[tid]; if (!tv) return;
    if (c.collegeRestriction.length && c.collegeRestriction.indexOf('SDS') < 0 && !c.isGE) return;
    if (c.yearMin && 3 < c.yearMin) return; if (c.yearMax && 3 > c.yearMax) return;
    var lec = tv.sessions.filter(function (s) { return s.type === 'lecture' && s.selectable !== false; })[0];
    if (!lec || !lec.slots.length) return;
    var slots = p.api.slotsOf(c, tid, lec.id);
    if (slots.some(function (s) { return used.some(function (u) { return clash(s, u); }); })) return;
    var tut = null;
    if (tv.requireTutorial) {
      var t = tv.sessions.filter(function (s) { return s.type === 'tutorial' && s.selectable !== false; }).filter(function (s) {
        var ts = p.api.slotsOf(c, tid, s.id);
        return !ts.some(function (s2) { return used.concat(slots).some(function (u) { return clash(s2, u); }); });
      })[0];
      if (!t) return; tut = t.id;
    }
    chosen.push([c.code, lec.id, tut]); used = used.concat(slots);
  });
  chosen.forEach(function (r) { p.api.commit(r[0], r[1], r[2]); });
  p.state.tab = 'timetable';
  p.render();
})();
<\/script>`;

writeFileSync(new URL('./_preview-fold.html', import.meta.url), src.replace('</body>', fold + '\n</body>'));
writeFileSync(new URL('./_preview-tt.html', import.meta.url), src.replace('</body>', tt + '\n</body>'));
console.log('previews written');
