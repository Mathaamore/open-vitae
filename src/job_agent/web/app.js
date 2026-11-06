let token, jobs = [], current, dirty = false, trackingDirty = false, busy = false, selectedView = 'all', currentTab = 'dossier', layout = 'list';
const $ = selector => document.querySelector(selector);
const labels = {DISCOVERED:t("app.saved"), VERIFIED:t("app.details_checked"), CV_READY:t("app.cv_ready"), APPLICATION_READY:t("app.ready_to_review"), REVIEWED:t("app.ready_to_apply"), APPROVED:t("app.ready_to_apply"), SUBMITTING:t("app.submission_in_progress"), SUBMITTED:t("app.applied"), SUBMISSION_UNCERTAIN:t("app.check_submission"), NEEDS_INPUT:t("app.needs_your_input"), MANUAL_ACTION_REQUIRED:t("app.needs_your_input"), FAILED:t("app.needs_attention"), SKIPPED:t("app.dismissed"), CLOSED:t("app.closed"), PRIORITY:t("app.strong_match"), STRETCH:t("app.stretch_role"), NEEDS_VERIFICATION:t("app.needs_verification"), INELIGIBLE:t("app.not_eligible")};
const recruitmentStages=['APPLIED','IN_REVIEW','INTERVIEW','OFFER','REJECTED','WITHDRAWN'];
for(const value of recruitmentStages)labels[value]=t('tracking.'+value);
const lockedStatuses = ['SUBMITTING', 'SUBMITTED', 'SUBMISSION_UNCERTAIN'];
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
const date = value => value ? new Date(value).toLocaleString('en-GB', {dateStyle:'short', timeStyle:'short'}) : t("app.not_provided");
const salary = job => typeof job.audit.salary === 'string' ? job.audit.salary : job.audit.salary_display || t("app.salary_not_provided");
const locationText = job => typeof job.audit.location === 'string' ? job.audit.location : job.audit.location?.name || t("app.location_not_provided");
const mark = company => `<span class="company-mark" data-company="${esc(company)}" aria-hidden="true">${esc(company.replace(/[^\p{L}\p{N}]/gu, '').slice(0, company.includes(' ') ? 2 : 1))}</span>`;
function status(value) {
  const tone = ['NEEDS_INPUT','NEEDS_VERIFICATION','STRETCH','APPROVED','SUBMISSION_UNCERTAIN'].includes(value) ? 'warn' : ['SUBMITTED','REVIEWED','APPLICATION_READY','PRIORITY','INTERVIEW','OFFER'].includes(value) ? 'good' : ['CLOSED','INELIGIBLE','FAILED','REJECTED'].includes(value) ? 'bad' : '';
  return `<span class="status ${tone}">${esc(labels[value] || value)}</span>`;
}
function displayStatus(job) {
  if(['SUBMITTING','SUBMISSION_UNCERTAIN'].includes(job.status))return job.status;
  if(job.tracking?.stage)return job.tracking.stage;
  return job.status === 'SUBMITTED' ? 'SUBMITTED' : ['CLOSED','INELIGIBLE'].includes(job.category) ? job.category : job.status;
}
function matchesFilter(job, filter) {
  if (filter === 'all') return true;
  if (filter === 'tracked') return Boolean(job.tracking) || job.revision > 0 || ['accept','later'].includes(job.interest) || job.status === 'SUBMITTED';
  if (filter === 'saved') return job.interest === 'later';
  if (filter === 'dossiers') return job.interest === 'accept' && !job.revision || job.revision > 0 && job.status === 'NEEDS_INPUT';
  if (filter === 'ready') return job.status === 'APPLICATION_READY';
  if (filter === 'closed') return ['REJECTED','WITHDRAWN'].includes(job.tracking?.stage);
  if (filter === 'sent') return !matchesFilter(job,'closed') && (job.status === 'SUBMITTED' || ['APPLIED','IN_REVIEW','INTERVIEW','OFFER'].includes(job.tracking?.stage));
  if (recruitmentStages.includes(filter))return job.tracking?.stage===filter || filter==='APPLIED' && job.status==='SUBMITTED' && !job.tracking?.stage;
  return job.status === filter || job.category === filter;
}
function stageFor(job) {
  if (job.status === 'SUBMITTED' || job.tracking?.stage) return 3;
  if (['REVIEWED','APPROVED','MANUAL_ACTION_REQUIRED','SUBMITTING','SUBMISSION_UNCERTAIN'].includes(job.status)) return 2;
  return 1;
}
function formatAnswer(field, value) {
  return (Array.isArray(value) ? value : [value]).filter(v => v !== undefined && v !== null && v !== '').map(v => field.options?.find(o => o.value === v)?.label || (v === true ? t("app.yes") : v === false ? t("app.no") : String(v))).join(', ');
}
function eventDetails(event) { try { return JSON.parse(event.details); } catch { return {}; } }
async function api(path, options = {}) {
  const response = await fetch(path, {...options, headers:{'Content-Type':'application/json', 'X-Local-Token':token, ...options.headers}});
  const result = await response.json();
  if (!response.ok) { throw Error(result.error || t("app.something_went_wrong_reload_the_page_and_try")); }
  return result;
}
function message(text, error = false) {
  const node = $('#message'); node.replaceChildren(); node.hidden = !text;
  node.className = 'message' + (error ? ' error' : ''); node.setAttribute('role', error ? 'alert' : 'status');
  if (!text) return;
  const copy = document.createElement('span'); copy.textContent = text;
  const close = document.createElement('button'); close.className = 'quiet dismiss-message'; close.setAttribute('aria-label', t('screen.close'));
  close.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"/></svg>';
  close.onclick = () => {node.hidden = true;};
  node.append(copy, close);
}
function syncUrl() {
  const params = new URLSearchParams();
  if (current) { params.set('job', current.id); params.set('tab', currentTab); }
  if (selectedView !== 'all') params.set('view', selectedView);
  if (layout !== 'list') params.set('layout', layout);
  if ($('#search').value) params.set('q', $('#search').value);
  if ($('#filter').value !== 'all') params.set('filter', $('#filter').value);
  if ($('#sort').value !== 'score') params.set('sort', $('#sort').value);
  history.replaceState(null, '', location.pathname + (params.size ? '?' + params : ''));
}
function table() {
  const query = $('#search').value.trim().toLocaleLowerCase('en'), filter = $('#filter').value;
  const filtered = jobs.filter(job => matchesFilter(job, 'tracked') && matchesFilter(job, selectedView) && matchesFilter(job, filter) && (job.company + ' ' + job.role + ' ' + (job.audit.title || '')).toLocaleLowerCase('en').includes(query));
  const sort = $('#sort').value;
  filtered.sort((a, b) => sort === 'company' ? a.company.localeCompare(b.company, 'en') : sort === 'updated' ? (b.updated_at || '').localeCompare(a.updated_at || '') : Number(['CLOSED','INELIGIBLE'].includes(a.category)) - Number(['CLOSED','INELIGIBLE'].includes(b.category)) || b.score - a.score);
  $('#count').textContent = `${filtered.length} ${filtered.length === 1 ? 'job' : 'jobs'}`;
  $('#rows').innerHTML = filtered.length ? filtered.map(job => `<tr class="opportunity" data-company="${esc(job.company)}" data-inactive="${['CLOSED','INELIGIBLE'].includes(displayStatus(job))}">
    <td><span class="dossier-reference">${job.revision > 0 ? 'DOSSIER' : t("app.job")} <span> / ${esc(job.id)}</span></span><div class="employer">${mark(job.company)}<div><strong>${esc(job.company)}</strong><span class="role-name">${esc(job.audit.title || job.role)}</span></div></div></td>
    <td class="condition"><strong>${esc(salary(job))}</strong><small>${esc(locationText(job))}</small></td>
    <td class="assessment">${job.coverage ? `<div class="score"><span class="number">${esc(job.score)}</span><small>/ 100</small></div><span class="coverage">${esc(job.coverage)} ${esc(t("app.documented"))}</span>` : `<span class="coverage">${esc(t("app.not_assessed"))}</span>`}</td>
    <td class="progress-cell">${job.preparation && ['queued','preparing','failed'].includes(job.preparation.state) ? `<span class="status ${job.preparation.state === 'failed' ? 'warn' : ''}">${esc(job.preparation.state === 'failed' ? t("app.needs_attention") : job.preparation.state === 'queued' ? t("app.queued") : t("app.preparing"))}</span><small class="preparation-note">${esc(job.preparation.message)}</small>${job.preparation.state === 'failed' ? `<button class="text-button" data-retry-preparation="${esc(job.id)}">${esc(t("app.try_again"))}</button>` : ''}` : status(displayStatus(job))}${job.tracking ? `<small class="tracking-updated">${esc(date(job.tracking.updated_at))}</small>` : ''}<span class="category-label">${esc(displayStatus(job) === job.category ? t("app.not_shortlisted") : labels[job.category] || job.category)}</span></td>
    <td class="action-cell"><a class="button-link open-row" href="?job=${encodeURIComponent(job.id)}" data-open="${esc(job.id)}" aria-label="View job ${esc(job.company)}">${job.revision > 0 ? t("app.open_application") : t("app.view_job")} <span class="open-arrow" aria-hidden="true">↗</span></a></td>
  </tr>`).join('') : `<tr><td colspan="5"><div class="empty-state"><strong>${esc(t("app.no_jobs_in_this_view"))}</strong><p>${esc(t("app.try_a_different_search_or_clear_your_filters"))}</p><button id="reset-filters">${esc(t("app.clear_filters"))}</button></div></td></tr>`;
  document.querySelectorAll('[data-open]').forEach(link => link.onclick = event => { if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return; event.preventDefault(); open(link.dataset.open); });
  syncUrl();
  if ($('#reset-filters')) $('#reset-filters').onclick = () => { selectedView = 'all'; $('#filter').value = 'all'; $('#search').value = ''; updateViews(); table(); };
}
function updateViews() {
  const headings = {all:[t("app.applications"),t("app.saved_jobs_and_applications_in_progress")],dossiers:[t("app.drafting"),t("app.applications_you_re_working_on")],ready:[t("app.ready_to_review"),t("app.check_your_cv_and_answers_before_marking_the")],sent:[t('tracking.in_progress'),t('tracking.in_progress_detail')],closed:[t('tracking.closed'),t('tracking.closed_detail')]};
  const [title, description] = headings[selectedView] || [t("app.saved"), t("app.jobs_you_want_to_come_back_to")];
  $('#dashboard-title').innerHTML = title;
  $('#view-description').textContent = description;
  document.querySelectorAll('[data-view]').forEach(button => {
    const active = button.dataset.view === selectedView;
    if (active) button.setAttribute('aria-current','page'); else button.removeAttribute('aria-current');
  });
  document.querySelectorAll('[data-count]').forEach(node => node.textContent = jobs.filter(job => matchesFilter(job, 'tracked') && matchesFilter(job, node.dataset.count)).length);
}
async function refreshJobs() {
  jobs = await api('/api/jobs');
  const prepared = jobs.filter(job => job.revision > 0).length, sent = jobs.filter(job => job.status === 'SUBMITTED').length;
  $('#summary').textContent = `${prepared} with materials · ${sent} applied`;
  if ($('#tracked-count')) $('#tracked-count').textContent = jobs.filter(job => matchesFilter(job, 'tracked')).length;
  updateViews(); table();
}
function setLayout(value) {
  layout = value;
  $('.table-wrap').dataset.layout = layout;
  document.querySelectorAll('button[data-layout]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.layout === layout)));
  syncUrl();
}
function home() {
  if (dirty || trackingDirty) { message(t("app.save_or_discard_your_changes_before_leaving_this"), true); return; }
  if ($('#explore')) $('#explore').hidden = true; if ($('#settings-screen')) $('#settings-screen').hidden = true; if ($('#tools-screen')) $('#tools-screen').hidden = true;
  document.querySelectorAll('[data-screen]').forEach(button=>button.toggleAttribute('aria-current',false));
  document.querySelector('[data-screen=dashboard]').setAttribute('aria-current','page'); $('#screen-title').textContent=t('app.applications');
  $('#review').hidden = true; $('#dashboard').hidden = false; current = undefined; message(''); document.title = t("app.open_vit_applications");
  syncUrl(); $('#main').scrollTop=0; $('#dashboard-title').focus();
}
async function open(id) {
  if (dirty || trackingDirty) { message(t("app.save_or_discard_your_changes_before_opening_another"), true); return; }
  try {
    message(''); current = await api('/api/jobs/' + encodeURIComponent(id)); dirty = false;
    currentTab = current.dossier ? 'dossier' : 'offre';
    if ($('#explore')) $('#explore').hidden = true; if ($('#settings-screen')) $('#settings-screen').hidden = true; if ($('#tools-screen')) $('#tools-screen').hidden = true;
    document.querySelectorAll('[data-screen]').forEach(button=>button.removeAttribute('aria-current'));
    document.querySelector('[data-screen=dashboard]').setAttribute('aria-current','page'); $('#screen-title').textContent=t('app.applications');
    $('#dashboard').hidden = true; $('#review').hidden = false; render(); $('#main').scrollTop=0;
    document.title = `${current.company} — Open Vitæ`; $('#job-title').focus();
  } catch (error) { message(error.message, true); }
}
function companyContext(job) {
  const company = job.context?.company, role = job.context?.role;
  if (!company) return `<section aria-label="${esc(t("app.company_context"))}"><h2>${esc(t("app.understand_the_role"))}</h2><p class="footnote">${esc(t("app.no_company_brief_yet_check_the_employer_s"))}</p></section>`;
  const sources = [...new Set([...(company.sources || []), ...(role?.sources || [])])].filter(url => url.startsWith('https://'));
  return `<section aria-label="${esc(t("app.company_context"))}"><div class="panel-intro"><h2>${esc(t("app.understand_the_role"))}</h2><p>${company.basis === 'job_feed' ? t("app.based_on_the_job_source_check_the_employer") : t("app.what_the_company_does_and_where_this_role")}</p></div><div class="company-context">
    <div><h3>${esc(t("app.company"))}</h3><div class="context-copy"><p>${esc(company.summary)}</p></div></div>
    <div><h3>${esc(t("app.product"))}</h3><div class="context-copy"><p>${esc(company.product)}</p></div></div>
    <div><h3>${esc(t("app.team_and_role"))}</h3><div class="context-copy"><strong>${esc(role?.team || "Team not confirmed")}</strong><p>${esc(role?.scope || 'Check the team and responsibilities on the employer’s listing.')}</p></div></div>
    </div><p class="source-links">${esc(t("app.sources_checked"))} ${esc(company.checked_on.split('-').reverse().join('/'))} · ${sources.map((url, index) => `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${index === 0 ? 'Company source' : 'Job source'} ↗</a>`).join(' ')}</p></section>`;
}
function verification(job) {
  if (!job.dossier || lockedStatuses.includes(job.status) || !job.problems.includes(t("app.check_that_the_role_is_open_and_that")) && !job.problems.some(text => text.startsWith('Check the exact questions'))) return '';
  return `<div class="verification-box"><h3>${esc(t("app.before_you_apply"))}</h3><p>${esc(t("app.confirm_these_details_on_the_employer_s_page"))}</p><label class="option"><input id="eligibility-checked" type="checkbox">${esc(t("app.i_checked_that_the_role_is_open_and"))}</label><label class="option"><input id="form-checked" type="checkbox">${esc(t("app.i_checked_the_questions_against_the_employer_s"))}</label><button id="confirm-checks">${esc(t("app.confirm_checks"))}</button></div>`;
}
function offer(job) {
  const audit = job.audit, criteria = {technical:t("app.skills_and_experience"), ownership:t("app.ownership_and_product"), growth:t("app.growth"), remote:t("app.work_arrangement"), compensation:t("app.salary"), culture:t("app.working_environment")};
  return `${companyContext(job)}${verification(job)}<div class="context"><div><small>${esc(t("app.listed_salary"))}</small><strong>${esc(salary(job))}</strong></div><div><small>${esc(t("app.location"))}</small><strong>${esc(locationText(job))}</strong></div><div><small>${esc(t("app.location_eligibility"))}</small><strong>${(audit.location_allowed ?? audit.france_allowed) === true ? t("app.confirmed") : (audit.location_allowed ?? audit.france_allowed) === false ? t("app.not_eligible") : t("app.not_confirmed")}</strong></div><div><small>${esc(t("app.last_collected_or_updated"))}</small><strong>${date(audit.checked_at)}</strong></div></div>
    <div class="offer-details">${audit.description?`<section><h3>${esc(t("app.job_description"))}</h3><p class="job-description">${esc(audit.description)}</p></section>`:''}${audit.source?`<p class="footnote">${esc(t("app.origine"))} ${esc(audit.source)}${audit.source_url?.startsWith('https://')?` · <a href="${esc(audit.source_url)}" target="_blank" rel="noopener noreferrer">${esc(t("app.source_originale"))}</a>`:''}</p>`:''}${audit.blockers?.length ? `<div class="notice"><strong>${esc(t("app.known_eligibility_concerns"))}</strong><ul>${audit.blockers.map(text => `<li>${esc(text)}</li>`).join('')}</ul></div>` : ''}
    ${audit.requirements?.length ? `<h3>${esc(t("app.role_requirements"))}</h3><ul>${audit.requirements.map(text => `<li>${esc(text)}</li>`).join('')}</ul>` : ''}
    ${audit.warnings?.length ? `<details><summary>${esc(t("app.things_to_check"))}${audit.warnings.length})</summary><ul>${audit.warnings.map(text => `<li>${esc(text)}</li>`).join('')}</ul></details>` : ''}
    <details><summary>${esc(t("app.about_this_match"))} ${job.coverage ? job.score + '/100' : t("app.not_assessed_2")}</summary><p class="footnote">${job.coverage} ${esc(t("app.of_criteria_have_supporting_information_missing_details_do"))}</p>${Object.entries(audit.scores || {}).map(([key, value]) => `<div class="score-row"><strong>${esc(criteria[key] || key)}</strong><span>${value.value ?? '—'}/100</span><span>${esc(value.reason)}</span></div>`).join('') || `<p class="footnote">${esc(t("app.there_isn_t_enough_information_to_assess_this"))}</p>`}</details>
    <p class="footnote">${esc(t("app.first_published"))} ${esc(audit.published_at || t("app.not_confirmed_2"))}${esc(t("app.a_company_brief_does_not_confirm_that_the"))}</p></div>`;
}
function field(field, answers, index, readonly) {
  const value = answers[field.key], key = esc(field.key), id = 'answer-' + index;
  const title = field.key === 'body' ? t("app.your_message") : field.label || t("app.check_this_question_with_the_employer");
  const heading = `<span>${esc(title)}${field.required ? ` <span class="required-mark" aria-label="${esc(t("app.obligatoire"))}">*</span>` : ''}</span>`;
  if (field.type === 'file') return `<div class="attachment-field"><div><strong>${esc(title)}</strong><small>${value ? t("app.document_ready_to_upload_on_the_employer_s") : t("app.no_additional_document_prepared")}</small></div>${value && String(value).endsWith('/resume.pdf') ? `<a class="button-link" href="/api/jobs/${encodeURIComponent(current.id)}/artifact/resume.pdf" target="_blank">${esc(t("app.pdf"))}</a>` : ''}<input type="hidden" data-answer="${key}" value="${esc(value || '')}"></div>`;
  if (['radio','checkbox'].includes(field.type) && field.options?.length) return `<fieldset ${readonly ? 'disabled' : ''}><legend>${heading}</legend>${field.options.map(option => `<label class="option"><input type="${field.type}" name="${id}" data-choice="${key}" value="${esc(option.value)}" ${field.type === 'radio' ? value === option.value ? 'checked' : '' : Array.isArray(value) && value.includes(option.value) ? 'checked' : ''}>${esc(option.label)}</label>`).join('')}</fieldset>`;
  if (field.type === 'select') return `<label class="field"><span class="field-heading">${heading}</span><select name="${key}" aria-required="${Boolean(field.required)}" data-answer="${key}" ${readonly ? 'disabled' : ''}><option value="">${esc(t("app.choose_an_option"))}${field.required ? '' : ' (facultatif)'}</option>${field.options.map(option => `<option value="${esc(option.value)}" ${value === option.value ? 'selected' : ''}>${esc(option.label)}</option>`).join('')}</select></label>`;
  if (field.type === 'checkbox') return `<label class="option field"><input type="checkbox" data-bool="${key}" ${value === true ? 'checked' : ''} ${readonly ? 'disabled' : ''}>${heading}</label>`;
  const text = String(value ?? ''), rows = Math.min(18, Math.max(field.type === 'textarea' ? 4 : 2, Math.ceil(text.length / 70)));
  const maxWords = /(?:in |than )?(\d+) words/i.exec(field.label || '')?.[1];
  const maxLength = Number.isInteger(field.max_length) && field.max_length > 0 ? field.max_length : null;
  const attributes = `id="${id}" name="${key}" autocomplete="off" aria-required="${Boolean(field.required)}" data-answer="${key}" ${maxLength ? `maxlength="${maxLength}"` : ''} ${maxWords ? `data-word-limit="${maxWords}"` : ''} ${readonly ? 'readonly' : ''}`;
  const multiline = field.type === 'textarea' || field.key === 'body' || text.length > 160 || maxWords;
  const inputType = ['text','email','url','tel','number'].includes(field.type) ? field.type : 'text';
  const control = multiline ? `<textarea ${attributes} rows="${rows}">${esc(text)}</textarea>` : `<input ${attributes} type="${inputType}" ${['email','url'].includes(inputType) ? 'spellcheck="false"' : ''} value="${esc(text)}">`;
  return `<div class="field"><div class="field-heading"><label for="${id}">${heading}</label><span class="field-tools">${multiline && !readonly ? `<button class="text-button assist-field" data-assist="${key}" aria-label="Revise answer: ${esc(title)}">${esc(t("app.reformuler"))} <span aria-hidden="true">↗</span></button>` : ''}<button class="text-button" data-copy="${key}" aria-label="Copy answer: ${esc(title)}">${esc(t("app.copier"))}</button></span></div>${control}${maxLength || maxWords ? `<small class="field-counter" data-counter="${id}"></small>` : ''}${field.key === 'body' ? `<small>${esc(t("app.use_this_text_where_the_employer_asks_for"))}</small>` : ''}</div>`;
}
function dossier(job, data) {
  const form = data.form || {fields:[]}, readonly = lockedStatuses.includes(job.status), base = '/api/jobs/' + encodeURIComponent(job.id);
  return `${job.problems.length && !readonly ? `<div class="notice"><strong>${esc(t("app.encore"))} ${job.problems.length} ${esc(t("app.item"))}${job.problems.length > 1 ? 's' : ''} ${esc(t("app.to_complete"))}</strong><ul>${job.problems.map(text => `<li>${esc(text)}</li>`).join('')}</ul></div>` : ''}
    ${readonly ? `<p class="footnote">${esc(t("app.recorded_application_you_can_still_read_and_copy"))}</p>` : ''}
    <div class="split"><div class="document-column"><div class="section-bar"><h2>${esc(t("app.your_cv_draft"))}</h2><a class="button-link" href="${base}/artifact/resume.pdf" target="_blank">${esc(t("app.open_pdf"))}</a></div><details class="document-preview"><summary>${esc(t("clean.preview_pdf"))}</summary><iframe loading="lazy" class="pdf" title="CV draft for ${esc(job.company)}" src="${base}/artifact/resume.pdf"></iframe></details><div class="file-links"><a href="${base}/artifact/resume.json" target="_blank">${esc(t("app.draft_source"))}</a><a href="${base}/artifact/tailoring.json" target="_blank">${esc(t("app.preparation_details"))}</a></div><p class="document-note">${esc(t("app.download_the_pdf_to_attach_to_your_application"))}</p></div>
    <div class="answer-form"><div class="section-bar"><h2>${esc(t("app.your_answers"))} <small>· ${form.fields.length}</small></h2><button id="copy-answers">${esc(t("app.copy_all_answers"))}</button></div><p class="form-intro">${readonly ? t("app.saved_version") : 'Version ' + job.revision + ""}${esc(t("app.required_fields_are_marked_with"))}</p>
    ${form.fields.map((item, index) => field(item, data.answers, index, readonly)).join('')}
    <details class="additional-motivation"><summary>${esc(t("app.additional_notes"))}</summary><label class="field"><span class="field-heading">${esc(t("app.a_short_introduction_you_can_reuse"))}</span><textarea id="motivation" rows="6" ${readonly ? 'readonly' : ''}>${esc(data.motivation)}</textarea><small>${data.submission.mode === 'email' ? t("app.the_email_draft_uses_your_main_message_above") : t("app.use_this_if_the_employer_asks_for_a")}</small></label></details>
    ${!readonly ? `<div class="review-footer"><button class="primary" id="save" disabled>${esc(t("app.save_changes"))}</button><button class="quiet" id="discard" hidden>${esc(t("app.discard_changes"))}</button><p id="save-state">${esc(t("app.all_changes_saved"))}</p></div>` : ''}
    <div class="delivery-card"><h3>${esc(t("app.when_you_re_ready_to_apply"))}</h3>${data.submission.mode === 'email' ? `<p>${esc(t("app.open_the_draft_in_your_email_app_check"))}</p><p class="recipient">${esc(data.submission.recipient || '')}</p><a class="button-link" href="${base}/email">${esc(t("app.download_email_draft"))}</a>` : `<p>${esc(t("app.copy_your_answers_download_your_cv_and_complete"))}</p>${job.url?`<a class="button-link" href="${esc(job.url)}" target="_blank" rel="noopener noreferrer">${esc(t("app.open_employer_application"))}</a>`:`<p>${esc(t("app.add_the_employer_s_link_to_open_the"))}</p>`}`}<p class="footnote">${esc(t("app.once_you_ve_sent_it_choose_mark_as"))}</p></div></div></div>`;
}
function tracking(job) {
  const sent = job.status === 'SUBMITTED', preparing = ['queued','preparing'].includes(job.preparation?.state), canRecord = !preparing && ['REVIEWED','APPROVED','MANUAL_ACTION_REQUIRED','SUBMISSION_UNCERTAIN'].includes(job.status);
  const events = job.history.events, receipts = events.filter(event => ['MANUAL_CONFIRMATION','SUBMITTED'].includes(event.action));
  const names = {DOSSIER_SAVED:t("app.materials_saved"), REVIEW:t("app.marked_ready_to_apply"), MANUAL_CONFIRMATION:t("app.marked_as_applied"), SUBMITTED:t("app.application_recorded"), AUDIT:t("app.details_checked"), SKIP:t("app.application_dismissed"), LATER:t("app.application_set_aside"), GO:t("app.review_recorded"), SUBMITTING:t("app.submission_attempt_recorded"), SUBMISSION_UNCERTAIN:t("app.submission_needs_checking")};
  const recruitment=job.tracking?.stage || (sent?'APPLIED':'');
  const today=new Date(Date.now()-new Date().getTimezoneOffset()*60000).toISOString().slice(0,10);
  const form=`<form id="tracking-form" class="tracking-form"><h3>${esc(t('tracking.update'))}</h3><p>${esc(t('tracking.help'))}</p><label class="stacked-label">${esc(t('tracking.stage'))}<select id="tracking-stage"><option value="">${esc(t('tracking.keep'))}</option>${recruitmentStages.map(value=>`<option value="${value}" ${value===recruitment?'selected':''}>${esc(labels[value])}</option>`).join('')}</select></label><label class="stacked-label">${esc(t('tracking.date'))}<input id="tracking-date" type="date" value="${today}" required></label><label class="stacked-label">${esc(t('tracking.note'))}<textarea id="tracking-note" rows="4" maxlength="2000" placeholder="${esc(t('tracking.placeholder'))}"></textarea></label><div class="tracking-form-actions"><button class="primary" id="save-tracking" disabled>${esc(t('tracking.save'))}</button><button id="discard-tracking" type="button" class="quiet" hidden>${esc(t('tracking.cancel'))}</button></div></form>`;
  return `<div class="tracking-layout"><section><h2>${esc(t("app.application_progress"))}</h2><div class="tracking-note"><div class="notice ${sent ? 'good' : ''}"><strong>${esc(recruitment ? labels[recruitment] : canRecord ? t("app.ready_to_apply") : t("app.drafting"))}</strong><p>${recruitment ? t('tracking.recorded_by_you') : canRecord ? t("app.after_sending_the_application_yourself_choose_mark_as") : t("app.review_your_materials_and_complete_any_missing_answers")}</p></div>
    ${sent && receipts.length ? (() => { const event = receipts[0], receipt = eventDetails(event); return `<p><strong>${date(event.created_at)}</strong> · ${receipt.verified_by === 'user' ? t("app.recorded_by_you") : t("app.confirmation_recorded")}</p><p class="footnote">${esc(receipt.confirmation || '')}</p>`; })() : ''}
    ${canRecord ? `<label class="field"><span class="field-heading">${esc(t("app.note_or_receipt_optional"))}</span><textarea id="receipt" rows="3" placeholder="${esc(t("app.for_example_submitted_on_the_company_website_confirmation"))}"></textarea><small>${esc(t("app.you_can_leave_this_blank"))}</small></label>` : ''}
    ${form}</div></section>
    <section><h2>${esc(t("app.activity"))}</h2><ol class="timeline">${events.map(event => { const details = eventDetails(event); return `<li><span class="timeline-dot" aria-hidden="true"></span><div><strong>${esc(event.action==='TRACKING_UPDATED' ? labels[details.stage] || t('tracking.note_added') : names[event.action] || t("app.application_updated"))}</strong><time datetime="${esc(details.occurred_on || event.created_at)}">${details.occurred_on ? esc(details.occurred_on) : date(event.created_at)}</time>${details.revision ? `<p>${esc(t("app.version"))} ${esc(details.revision)}</p>` : ''}${details.confirmation ? `<p>${esc(details.confirmation)}</p>` : ''}${details.note ? `<p>${esc(details.note)}</p>` : ''}</div></li>`; }).join('') || `<li>${esc(t("app.no_activity_yet"))}</li>`}</ol>
    <details class="history-versions"><summary>${esc(t("app.saved_versions"))}${job.history.versions.length})</summary><ul>${job.history.versions.map(version => `<li>${esc(t("app.version"))} ${esc(version.revision)} · ${date(version.created_at)}</li>`).join('')}</ul></details><details><summary>${esc(t("app.activity_details"))}</summary><pre>${esc(JSON.stringify(job.history, null, 2))}</pre></details></section></div>`;
}
function preparationActions(job, preparing) {
  const locked = lockedStatuses.includes(job.status), hasAI = Boolean(job.dossier && job.audit.company_context);
  const name = window.WorkspaceUI?.connection?.connected ? window.WorkspaceUI.connection.name : 'AI';
  const prepare = `<button data-prepare-job="${esc(job.id)}" ${preparing?'disabled':''}>${esc(t(job.dossier?'prepare.new_version':'prepare.with_provider',{name}))}</button>`;
  const main = locked ? '' : preparing ? `<button class="primary" disabled>${esc(t('app.preparing'))}</button>` : hasAI && job.preparation?.state!=='failed' ? `<button data-review-materials>${esc(t('prepare.review'))}</button>` : prepare.replace('<button ', '<button class="primary" ');
  return `${main}<details class="preparation-alternatives"><summary>${esc(t('prepare.other_ways'))}</summary>${hasAI && !locked ? prepare : ''}<button data-local-tools="${esc(job.id)}" ${preparing?'disabled':''}>${esc(t('prepare.manual'))}</button></details>`;
}
function preparationPanel(job) {
  const preparation = job.preparation;
  if (!preparation || !['queued','preparing','failed'].includes(preparation.state)) return '';
  const failed = preparation.state === 'failed';
  return `<section class="notice ${failed ? 'preparation-error' : 'preparation-progress'}" role="${failed ? 'alert' : 'status'}"><strong>${esc(t(failed ? 'prepare.failed' : 'prepare.progress'))}</strong><p>${esc(preparation.message)}</p><p>${esc(t(failed ? 'prepare.failure_help' : 'prepare.progress_help'))}</p></section>`;
}
function render() {
  const job = current, data = job.dossier, stage = stageFor(job), preparing = ['queued','preparing'].includes(job.preparation?.state), canReview = !preparing && data && !job.problems.length && ['APPLICATION_READY','NEEDS_INPUT','SKIPPED','VERIFIED'].includes(job.status), canRecord = !preparing && ['REVIEWED','APPROVED','MANUAL_ACTION_REQUIRED','SUBMISSION_UNCERTAIN'].includes(job.status);
  $('#review').innerHTML = `<a class="back" href="/" id="back">${esc(t("app.all_jobs"))}</a><div class="review-top"><div class="company-heading">${mark(job.company)}<div><h1 id="job-title" tabindex="-1">${esc(job.company)}</h1><p class="review-role">${esc(job.audit.title || job.role)}</p>${status(displayStatus(job))}</div></div><div class="review-actions"><button id="tracking-open">${esc(t("tracking.update"))}</button><button data-edit-opportunity="${esc(job.id)}" ${lockedStatuses.includes(job.status)?'disabled':''}>${esc(t("app.edit_job"))}</button>${preparationActions(job,preparing)}${job.url?`<a class="button-link" href="${esc(job.url)}" target="_blank" rel="noopener noreferrer">${esc(t("app.view_listing"))}</a>`:''}${canReview ? `<button class="primary" id="review-dossier">${esc(t("app.mark_ready_to_apply"))}</button>` : ''}${canRecord ? `<button class="primary" id="record-receipt">${esc(t("app.mark_as_applied"))}</button>` : ''}<span class="action-hint">${job.status === 'SUBMITTED' ? t("app.recorded_as_applied") : canRecord ? t("app.use_this_after_sending_the_application_yourself") : canReview ? t("app.this_records_your_review_you_still_send_the") : t("app.check_the_materials_for_missing_details")}</span></div></div>
    <div class="review-secondary"><div class="review-stage" aria-label="Step ${stage} of 3">${[t("app.draft"),t("app.apply"),t("app.track")].map((text, index) => `<span class="${stage === index + 1 ? 'current-step' : ''}"><span class="step-index" aria-hidden="true">${index + 1}</span>${text}</span>`).join('')}</div><div class="secondary-actions"><button class="text-button" id="later" ${lockedStatuses.includes(job.status) ? 'disabled' : ''}>${esc(t("app.set_aside"))}</button><button class="text-button" id="skip" ${lockedStatuses.includes(job.status) ? 'disabled' : ''}>${esc(t("app.dismiss"))}</button></div></div>
    <div class="review-tabs" role="tablist" aria-label="${esc(t("app.application_sections"))}"><button role="tab" id="tab-offre" aria-controls="panel-offre" data-tab="offre">${esc(t("app.job_2"))}</button><button role="tab" id="tab-dossier" aria-controls="panel-dossier" data-tab="dossier">${esc(t("app.materials"))}${data ? '' : ` <small>${esc(t("app.draft_2"))}</small>`}</button><button role="tab" id="tab-suivi" aria-controls="panel-suivi" data-tab="suivi">${esc(t('tracking.progress'))}</button></div>
    ${preparationPanel(job)}<section id="panel-offre" role="tabpanel" aria-labelledby="tab-offre">${job.audit.pending_retrieval?`<p class="notice">${esc(t("app.link_saved_choose_edit_job_to_get_its"))}</p>`:''}${job.audit.origin==='portable_ai'?`<p class="notice">${esc(t("app.imported_from_an_external_ai_confirm_that_the"))}</p>`:''}${offer(job)}${job.audit.external_analysis?`<section class="notice"><h2>${esc(t("app.imported_analysis_not_verified"))}</h2><pre class="portable-result">${esc(JSON.stringify(job.audit.external_analysis,null,2))}</pre></section>`:''}</section><section id="panel-dossier" role="tabpanel" aria-labelledby="tab-dossier">${data ? dossier(job, data) : preparing ? `<p class="footnote">${esc(t("prepare.waiting"))}</p>` : `<div class="empty-state"><strong>${esc(t("app.start_your_application_materials"))}</strong><p>${esc(t("app.prepare_a_draft_from_your_profile_then_check"))}</p><button id="see-offer">${esc(t("app.review_job_details"))}</button></div>`}</section><section id="panel-suivi" role="tabpanel" aria-labelledby="tab-suivi">${tracking(job)}</section>`;
  $('#back').onclick = event => { if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return; event.preventDefault(); home(); };
  $('#tracking-open').onclick=()=>{selectTab('suivi');if(!dirty && !trackingDirty){$('#tracking-form').scrollIntoView({block:'start'});$('#tracking-stage').focus();}};
  $('#tracking-form').oninput=()=>{trackingDirty=true;$('#save-tracking').disabled=false;$('#discard-tracking').hidden=false;updateEditingState();};
  $('#tracking-form').onsubmit=saveTracking;
  $('#discard-tracking').onclick=()=>{trackingDirty=false;render();};
  $('#later').onclick = () => decide('LATER'); $('#skip').onclick = () => decide('SKIP');
  if ($('#review-dossier')) $('#review-dossier').onclick = () => decide('REVIEW');
  if ($('#record-receipt')) $('#record-receipt').onclick = recordSent;
  if ($('#see-offer')) $('#see-offer').onclick = () => selectTab('offre');
  if ($('[data-review-materials]')) $('[data-review-materials]').onclick=()=>{selectTab('dossier');$('#panel-dossier').scrollIntoView({block:'start'});};
  document.querySelectorAll('[data-tab]').forEach(button => {
    button.onclick = () => selectTab(button.dataset.tab);
    button.onkeydown = event => { const tabs = ['offre','dossier','suivi'], index = tabs.indexOf(button.dataset.tab); let next;
      if (event.key === 'ArrowRight') next = tabs[(index + 1) % tabs.length];
      if (event.key === 'ArrowLeft') next = tabs[(index + 2) % tabs.length];
      if (event.key === 'Home') next = tabs[0]; if (event.key === 'End') next = tabs[2];
      if (next) { event.preventDefault(); selectTab(next); $('#tab-' + next).focus(); }
    };
  });
  if (data) {
    if ($('#save')) $('#save').onclick = save;
    if ($('#discard')) $('#discard').onclick = async () => { try { current = await api('/api/jobs/' + encodeURIComponent(current.id)); dirty = false; render(); message(t("app.changes_discarded")); } catch (error) { message(error.message, true); } };
    $('#copy-answers').onclick = async () => { const answers = readAnswers(); await copyText((data.form?.fields || []).filter(field => field.type !== 'file').map(field => field.label + '\n' + (formatAnswer(field, answers[field.key]) || (field.required ? t("app.needs_your_input") : t("app.not_provided")))).join('\n\n'), t("app.answers_copied")); };
    document.querySelectorAll('[data-copy]').forEach(button => button.onclick = async () => { const field = data.form.fields.find(field => field.key === button.dataset.copy); await copyText(formatAnswer(field, readAnswers()[field.key]), t("app.answer_copied")); });
    $('#review').querySelectorAll('[data-answer],[data-choice],[data-bool],#motivation').forEach(element => element.addEventListener('input', () => { dirty = true; updateEditingState(); updateCounter(element); }));
    $('#review').querySelectorAll('[data-word-limit],[maxlength]').forEach(updateCounter);
  }
  if ($('#confirm-checks')) $('#confirm-checks').onclick = async () => {
    if (dirty) { message(t("app.save_your_answers_before_confirming_these_checks"), true); return; }
    if (!$('#eligibility-checked').checked || !$('#form-checked').checked) { message(t("app.confirm_both_checks_before_continuing"), true); return; }
    await updateJob('/checks', {revision:current.revision, eligibility_checked:true, form_checked:true}, t("app.checks_saved"));
  };
  selectTab(currentTab); updateEditingState();
  if (preparing) $('#review').querySelectorAll('input,textarea,select,[data-assist],#save,[data-edit-opportunity]').forEach(node=>node.disabled=true);
}
function selectTab(tab) {
  if(tab!==currentTab && (dirty || trackingDirty)){message(t('tracking.unsaved'),true);return;}
  currentTab = tab;
  document.querySelectorAll('[data-tab]').forEach(button => { const active = button.dataset.tab === tab; button.setAttribute('aria-selected', String(active)); button.tabIndex = active ? 0 : -1; });
  ['offre','dossier','suivi'].forEach(name => $('#panel-' + name).hidden = name !== tab);
  syncUrl();
}
async function saveTracking(event) {
  event.preventDefault();
  const button=$('#save-tracking');button.disabled=true;
  try {
    current=await api('/api/jobs/'+encodeURIComponent(current.id)+'/tracking',{method:'POST',body:JSON.stringify({stage:$('#tracking-stage').value || null,note:$('#tracking-note').value,occurred_on:$('#tracking-date').value,expected_updated_at:current.tracking?.updated_at || null})});
    trackingDirty=false;currentTab='suivi';render();await refreshJobs();message(t('tracking.saved'));
  } catch(error){message(error.message,true);button.disabled=false;}
}
function updateEditingState() {
  if ($('#save')) { $('#save').disabled = !dirty || busy; $('#save').textContent = busy ? t("app.saving") : t("app.save_changes"); }
  if ($('#discard')) $('#discard').hidden = !dirty;
  if ($('.review-footer')) $('.review-footer').classList.toggle('is-dirty', dirty);
  if ($('#save-state')) $('#save-state').textContent = dirty ? t("app.unsaved_changes") : t("app.all_changes_saved");
  ['review-dossier','record-receipt','later','skip'].forEach(id => { const button = $('#' + id); if (button) button.disabled = busy || dirty || trackingDirty || (['later','skip'].includes(id) && lockedStatuses.includes(current.status)); });
}
function updateCounter(element) {
  const counter = document.querySelector(`[data-counter="${element.id}"]`); if (!counter) return;
  const words = element.value.trim() ? element.value.trim().split(/\s+/).length : 0, limit = Number(element.dataset.wordLimit);
  counter.textContent = limit ? `${words} / ${limit} words` : `${element.value.length} / ${element.maxLength} characters`;
  counter.classList.toggle('limit-error', limit ? words > limit : element.value.length > element.maxLength);
}
function readAnswers() {
  const answers = {...current.dossier.answers};
  document.querySelectorAll('[data-answer]').forEach(element => answers[element.dataset.answer] = element.value);
  const keys = new Set([...document.querySelectorAll('[data-choice]')].map(element => element.dataset.choice));
  keys.forEach(key => { const elements = [...document.querySelectorAll('[data-choice]')].filter(element => element.dataset.choice === key); answers[key] = elements[0].type === 'radio' ? elements.find(element => element.checked)?.value || '' : elements.filter(element => element.checked).map(element => element.value); });
  document.querySelectorAll('[data-bool]').forEach(element => answers[element.dataset.bool] = element.checked);
  return answers;
}
async function copyText(text, success) { try { await navigator.clipboard.writeText(text); message(success); } catch { message(t("app.couldn_t_copy_automatically_select_the_text_and"), true); } }
async function updateJob(path, body, success) {
  if (busy) return; busy = true; updateEditingState();
  try { current = await api('/api/jobs/' + encodeURIComponent(current.id) + path, {method:path ? 'POST' : 'PUT', body:JSON.stringify(body)}); dirty = false; render(); await refreshJobs(); message(success); }
  catch (error) { message(error.message, true); }
  finally { busy = false; updateEditingState(); }
}
async function save() {
  const exceeded = [...document.querySelectorAll('[data-word-limit]')].find(element => element.value.trim().split(/\s+/).filter(Boolean).length > Number(element.dataset.wordLimit));
  if (exceeded) { message(`This answer exceeds the ${exceeded.dataset.wordLimit} word limit. Shorten it before saving.`, true); selectTab('dossier'); exceeded.focus(); return; }
  await updateJob('', {revision:current.revision, answers:readAnswers(), motivation:$('#motivation').value}, t("app.changes_saved"));
}
async function decide(choice) {
  if (dirty || trackingDirty) { message(t("app.save_your_changes_before_marking_this_application_ready"), true); return; }
  await updateJob('/decision', {choice, fingerprint:current.fingerprint}, choice === 'REVIEW' ? t("app.application_ready_send_it_through_the_employer_s") : choice === 'LATER' ? t("app.application_set_aside_2") : t("app.application_dismissed_2"));
}
async function recordSent() {
  if (dirty || trackingDirty) { message(t("app.save_your_changes_before_updating_the_tracker"), true); return; }
  await updateJob('/confirmation', {confirmation:$('#receipt')?.value || '', fingerprint:current.fingerprint, declared_sent:true}, t("app.application_marked_as_applied"));
  if (current.status === 'SUBMITTED') selectTab('suivi');
}
async function init() {
  const route = new URLSearchParams(location.search);
  if (['all','saved','dossiers','ready','sent','closed'].includes(route.get('view'))) selectedView = route.get('view');
  if (route.get('layout') === 'grid') layout = 'grid';
  $('#search').value = route.get('q') || '';
  if ([...$('#filter').options].some(option => option.value === route.get('filter'))) $('#filter').value = route.get('filter');
  if (['score','company','updated'].includes(route.get('sort'))) $('#sort').value = route.get('sort');
  try {
    token = (await api('/api/session')).token; if (window.WorkspaceUI) await window.WorkspaceUI.boot(); await refreshJobs(); setLayout(layout);
    document.querySelectorAll('button[data-layout]').forEach(button => button.onclick = () => setLayout(button.dataset.layout));
    $('#search').oninput = table; $('#filter').onchange = table; $('#sort').onchange = table;
    document.querySelectorAll('[data-view]').forEach(button => button.onclick = () => { if (dirty || trackingDirty) { home(); return; } if (current) home(); selectedView = button.dataset.view; $('#filter').value = 'all'; updateViews(); table(); });
    $('#home-link').onclick = event => { if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return; event.preventDefault(); home(); };
    window.addEventListener('beforeunload', event => { if (dirty || trackingDirty || window.profileDirty) { event.preventDefault(); event.returnValue = ''; } });
    if (window.WorkspaceUI) await window.WorkspaceUI.start();
    if (route.get('job')) { await open(route.get('job')); if (current && ['offre','dossier','suivi'].includes(route.get('tab'))) selectTab(route.get('tab')); }
  } catch (error) { message(t("app.couldn_t_load_your_workspace") + error.message, true); }
}
init();
