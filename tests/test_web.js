const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../src/job_agent/web/app.js'), 'utf8').replace(/\ninit\(\);\s*$/, '');
const context = vm.createContext({});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/job_agent/web/copy.en.js'),'utf8'),context);
vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/job_agent/web/i18n.js'),'utf8'),context);
vm.runInContext(source, context);
const evaluate = code => vm.runInContext(code, context);

test('views separate a prepared draft from a recorded send', () => {
  assert.equal(evaluate("matchesFilter({revision:2,status:'APPLICATION_READY',category:'PRIORITY'},'ready')"), true);
  assert.equal(evaluate("matchesFilter({revision:2,status:'APPLICATION_READY',category:'PRIORITY'},'sent')"), false);
  assert.equal(evaluate("matchesFilter({revision:2,status:'SUBMITTED',category:'PRIORITY'},'sent')"), true);
  assert.equal(evaluate("matchesFilter({revision:0,status:'NEEDS_INPUT',category:'NEEDS_VERIFICATION'},'dossiers')"), false);
  assert.equal(evaluate("stageFor({status:'APPLICATION_READY'})"), 1);
  assert.equal(evaluate("stageFor({status:'REVIEWED'})"), 2);
  assert.equal(evaluate("stageFor({status:'SUBMITTED'})"), 3);
});
test('copy uses option labels and preserves a negative answer', () => {
  assert.equal(evaluate("formatAnswer({options:[{value:'false',label:'No'}]},'false')"), 'No');
  assert.equal(evaluate("formatAnswer({},false)"), 'No');
  assert.equal(evaluate("formatAnswer({},0)"), '0');
  assert.equal(evaluate("formatAnswer({},['Python','React'])"), 'Python, React');
});
test('source links reject executable URLs and text remains escaped', () => {
  const html = evaluate("companyContext({context:{company:{summary:'<script>bad</script>',product:'APIs',checked_on:'2026-11-05',sources:['javascript:alert(1)','https://example.com']},role:{team:null,scope:'Unknown'}}})");
  assert.ok(html.includes('&lt;script&gt;'));
  assert.ok(!html.includes('href="javascript:'));
  assert.ok(html.includes('Team not confirmed'));
});
test('receipt details tolerate a malformed historical event', () => {
  assert.equal(JSON.stringify(evaluate("eventDetails({details:'broken'})")), '{}');
});
test('inactive offers stay distinct from drafts and sent applications', () => {
  assert.equal(evaluate("displayStatus({status:'NEEDS_INPUT',category:'INELIGIBLE'})"), 'INELIGIBLE');
  assert.equal(evaluate("displayStatus({status:'NEEDS_INPUT',category:'CLOSED'})"), 'CLOSED');
  assert.equal(evaluate("displayStatus({status:'SUBMITTED',category:'CLOSED'})"), 'SUBMITTED');
});
test('short answers use native inputs and long answers remain editable textareas', () => {
  evaluate("current={id:'39'}");
  const email = evaluate("field({key:'email',label:'Email',type:'email',required:true},{email:'a@example.com'},0,false)");
  assert.ok(email.includes('type="email"'));
  assert.ok(email.includes('spellcheck="false"'));
  assert.ok(email.includes('name="email"'));
  const narrative = evaluate("field({key:'why',label:'In 200 words or less',type:'textarea'},{why:'A concrete experience'},1,true)");
  assert.ok(narrative.includes('<textarea'));
  assert.ok(narrative.includes('data-word-limit="200"'));
  assert.ok(narrative.includes('readonly'));
});
test('English fallback and interpolation preserve source text', () => {
  const key = evaluate('Object.keys(OV_COPY)[0]');
  const original = evaluate(`t(${JSON.stringify(key)})`);
  evaluate("I18n.register('test', {sample:'Review {source}'})");
  evaluate("I18n.setLocale('test')");
  assert.equal(evaluate(`t(${JSON.stringify(key)})`), original);
  assert.equal(evaluate("t('sample',{source:'Mon CV $& <br>'})"), 'Review Mon CV $& <br>');
  evaluate("I18n.setLocale('unknown')");
  assert.equal(evaluate('I18n.locale'), 'en');
});
test('saved jobs prepare through connected AI and manual tools are a separate choice', () => {
  evaluate("globalThis.window={WorkspaceUI:{connection:{connected:true,name:'ChatGPT'}}}");
  const html=evaluate("preparationActions({id:'saved',status:'NEEDS_INPUT',audit:{},dossier:null},false)");
  assert.match(html, /class="primary" data-prepare-job="saved"/);
  assert.match(html, /Prepare with ChatGPT/);
  assert.match(html, /<details class="preparation-alternatives">/);
  const ready=evaluate("preparationActions({id:'saved',status:'NEEDS_INPUT',audit:{company_context:{}},dossier:{}},false)");
  assert.match(ready, /data-review-materials/);
  const failed=evaluate("preparationPanel({preparation:{state:'failed',message:'<unsafe> provider failure'}})");
  assert.match(failed,/role="alert"/);
  assert.match(failed,/&lt;unsafe&gt;/);
});
test('recruitment outcomes appear in the right views without hiding uncertain submissions', () => {
  const interviewing={status:'SUBMITTED',revision:1,tracking:{stage:'INTERVIEW'}};
  const rejected={...interviewing,tracking:{stage:'REJECTED'}};
  context.interviewing=interviewing;context.rejected=rejected;
  assert.equal(evaluate('displayStatus(interviewing)'), 'INTERVIEW');
  assert.equal(evaluate("matchesFilter(interviewing,'sent')"), true);
  assert.equal(evaluate("matchesFilter(interviewing,'INTERVIEW')"), true);
  assert.equal(evaluate("matchesFilter(rejected,'closed')"), true);
  assert.equal(evaluate("matchesFilter(rejected,'sent')"), false);
  assert.equal(evaluate("displayStatus({...rejected,status:'SUBMISSION_UNCERTAIN'})"), 'SUBMISSION_UNCERTAIN');
});
