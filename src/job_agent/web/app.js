let token, jobs = [], current, dirty = false, busy = false, selectedView = 'all', currentTab = 'dossier', layout = 'list';
const $ = selector => document.querySelector(selector);
const labels = {DISCOVERED:'À découvrir', VERIFIED:'Annonce vérifiée', CV_READY:'CV prêt', APPLICATION_READY:'Prête à relire', REVIEWED:'Validée, à envoyer', APPROVED:'Approuvée', SUBMITTING:'Envoi en cours', SUBMITTED:'Envoyée', SUBMISSION_UNCERTAIN:'Envoi à vérifier', NEEDS_INPUT:'À compléter', MANUAL_ACTION_REQUIRED:'Action nécessaire', FAILED:'À reprendre', SKIPPED:'Ignorée', CLOSED:'Fermée', PRIORITY:'Prioritaire', STRETCH:'Ambitieuse', NEEDS_VERIFICATION:'À vérifier', INELIGIBLE:'Inéligible'};
const lockedStatuses = ['SUBMITTING', 'SUBMITTED', 'SUBMISSION_UNCERTAIN'];
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
const date = value => value ? new Date(value).toLocaleString('fr-FR', {dateStyle:'short', timeStyle:'short'}) : 'Non précisée';
const salary = job => typeof job.audit.salary === 'string' ? job.audit.salary : job.audit.salary_display || 'Salaire non publié';
const locationText = job => typeof job.audit.location === 'string' ? job.audit.location : job.audit.location?.name || 'Localisation à préciser';
const mark = company => `<span class="company-mark" data-company="${esc(company)}" aria-hidden="true">${esc(company.replace(/[^\p{L}\p{N}]/gu, '').slice(0, company.includes(' ') ? 2 : 1))}</span>`;
function status(value) {
  const tone = ['NEEDS_INPUT','NEEDS_VERIFICATION','STRETCH','APPROVED','SUBMISSION_UNCERTAIN'].includes(value) ? 'warn' : ['SUBMITTED','REVIEWED','APPLICATION_READY','PRIORITY'].includes(value) ? 'good' : ['CLOSED','INELIGIBLE','FAILED'].includes(value) ? 'bad' : '';
  return `<span class="status ${tone}">${esc(labels[value] || value)}</span>`;
}
function displayStatus(job) {
  return job.status === 'SUBMITTED' ? 'SUBMITTED' : ['CLOSED','INELIGIBLE'].includes(job.category) ? job.category : job.status;
}
function matchesFilter(job, filter) {
  if (filter === 'all') return true;
  if (filter === 'tracked') return job.revision > 0 || ['accept','later'].includes(job.interest) || job.status === 'SUBMITTED';
  if (filter === 'saved') return job.interest === 'later';
  if (filter === 'dossiers') return job.interest === 'accept' && !job.revision || job.revision > 0 && job.status === 'NEEDS_INPUT';
  if (filter === 'ready') return job.status === 'APPLICATION_READY';
  if (filter === 'sent') return job.status === 'SUBMITTED';
  return job.status === filter || job.category === filter;
}
function stageFor(job) {
  if (job.status === 'SUBMITTED') return 3;
  if (['REVIEWED','APPROVED','MANUAL_ACTION_REQUIRED','SUBMITTING','SUBMISSION_UNCERTAIN'].includes(job.status)) return 2;
  return 1;
}
function formatAnswer(field, value) {
  return (Array.isArray(value) ? value : [value]).filter(v => v !== undefined && v !== null && v !== '').map(v => field.options?.find(o => o.value === v)?.label || (v === true ? 'Oui' : v === false ? 'Non' : String(v))).join(', ');
}
function eventDetails(event) { try { return JSON.parse(event.details); } catch { return {}; } }
async function api(path, options = {}) {
  const response = await fetch(path, {...options, headers:{'Content-Type':'application/json', 'X-Local-Token':token, ...options.headers}});
  const result = await response.json();
  if (!response.ok) { throw Error(result.error || 'Opération impossible. Recharge la page et réessaie.'); }
  return result;
}
function message(text, error = false) {
  const node = $('#message'); node.textContent = text; node.hidden = !text;
  node.className = 'message' + (error ? ' error' : ''); node.setAttribute('role', error ? 'alert' : 'status');
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
  const query = $('#search').value.trim().toLocaleLowerCase('fr'), filter = $('#filter').value;
  const filtered = jobs.filter(job => matchesFilter(job, 'tracked') && matchesFilter(job, selectedView) && matchesFilter(job, filter) && (job.company + ' ' + job.role + ' ' + (job.audit.title || '')).toLocaleLowerCase('fr').includes(query));
  const sort = $('#sort').value;
  filtered.sort((a, b) => sort === 'company' ? a.company.localeCompare(b.company, 'fr') : sort === 'updated' ? (b.updated_at || '').localeCompare(a.updated_at || '') : Number(['CLOSED','INELIGIBLE'].includes(a.category)) - Number(['CLOSED','INELIGIBLE'].includes(b.category)) || b.score - a.score);
  $('#count').textContent = `${filtered.length} offre${filtered.length > 1 ? 's' : ''}`;
  $('#rows').innerHTML = filtered.length ? filtered.map(job => `<tr class="opportunity" data-company="${esc(job.company)}" data-inactive="${['CLOSED','INELIGIBLE'].includes(displayStatus(job))}">
    <td><span class="dossier-reference">${job.revision > 0 ? 'DOSSIER' : 'OPPORTUNITÉ'} <span> / ${esc(job.id)}</span></span><div class="employer">${mark(job.company)}<div><strong>${esc(job.company)}</strong><span class="role-name">${esc(job.audit.title || job.role)}</span></div></div></td>
    <td class="condition"><strong>${esc(salary(job))}</strong><small>${esc(locationText(job))}</small></td>
    <td class="assessment">${job.coverage ? `<div class="score"><span class="number">${esc(job.score)}</span><small>/ 100</small></div><span class="coverage">${esc(job.coverage)} % documenté</span>` : '<span class="coverage">À évaluer</span>'}</td>
    <td class="progress-cell">${job.preparation && ['queued','preparing','failed'].includes(job.preparation.state) ? `<span class="status ${job.preparation.state === 'failed' ? 'warn' : ''}">${esc(job.preparation.state === 'failed' ? 'À reprendre' : job.preparation.state === 'queued' ? 'En attente' : 'En préparation')}</span><small class="preparation-note">${esc(job.preparation.message)}</small>${job.preparation.state === 'failed' ? `<button class="text-button" data-retry-preparation="${esc(job.id)}">Relancer</button>` : ''}` : status(displayStatus(job))}<span class="category-label">${esc(displayStatus(job) === job.category ? 'Hors sélection' : labels[job.category] || job.category)}</span></td>
    <td class="action-cell"><a class="button-link open-row" href="?job=${encodeURIComponent(job.id)}" data-open="${esc(job.id)}" aria-label="Ouvrir la fiche ${esc(job.company)}">${job.revision > 0 ? 'Ouvrir le dossier' : 'Explorer l’offre'} <span class="open-arrow" aria-hidden="true">↗</span></a></td>
  </tr>`).join('') : '<tr><td colspan="5"><div class="empty-state"><strong>Aucune offre dans cette vue.</strong><p>Essaie un autre mot ou retrouve toutes les opportunités.</p><button id="reset-filters">Réinitialiser les filtres</button></div></td></tr>';
  document.querySelectorAll('[data-open]').forEach(link => link.onclick = event => { if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return; event.preventDefault(); open(link.dataset.open); });
  syncUrl();
  if ($('#reset-filters')) $('#reset-filters').onclick = () => { selectedView = 'all'; $('#filter').value = 'all'; $('#search').value = ''; updateViews(); table(); };
}
function updateViews() {
  const headings = {all:['Candidatures','Les offres que tu as retenues et tes dossiers en préparation.'],dossiers:['À préparer','Les dossiers qui demandent encore ton attention.'],ready:['À relire','CV et réponses préparés. Relis les faits avant de postuler.'],sent:['Envoyées','Les candidatures dont tu as enregistré l’envoi.']};
  const [title, description] = headings[selectedView] || ['Favoris', 'Les offres conservées pour plus tard.'];
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
  $('#summary').textContent = `${prepared} dossiers · ${sent} candidature${sent > 1 ? 's' : ''} envoyée${sent > 1 ? 's' : ''}`;
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
  if (dirty) { message('Tes modifications ne sont pas enregistrées. Enregistre-les ou annule-les avant de quitter la fiche.', true); return; }
  if ($('#explore')) $('#explore').hidden = true; if ($('#settings-screen')) $('#settings-screen').hidden = true;
  $('#review').hidden = true; $('#dashboard').hidden = false; current = undefined; message(''); document.title = 'Open Vitæ — Ton espace de travail';
  syncUrl(); window.scrollTo(0,0); $('#dashboard-title').focus();
}
async function open(id) {
  if (dirty) { message('Enregistre ou annule tes modifications avant de changer de fiche.', true); return; }
  try {
    message(''); current = await api('/api/jobs/' + encodeURIComponent(id)); dirty = false;
    currentTab = current.dossier ? 'dossier' : 'offre';
    if ($('#explore')) $('#explore').hidden = true; if ($('#settings-screen')) $('#settings-screen').hidden = true;
    $('#dashboard').hidden = true; $('#review').hidden = false; render(); window.scrollTo(0,0);
    document.title = `${current.company} — Open Vitæ`; $('#job-title').focus();
  } catch (error) { message(error.message, true); }
}
function companyContext(job) {
  const company = job.context?.company, role = job.context?.role;
  if (!company) return '<section aria-label="Contexte de l’entreprise"><h2>Comprendre l’opportunité</h2><p class="footnote">Le résumé de cette entreprise reste à préparer. L’équipe n’est pas confirmée.</p></section>';
  const sources = [...new Set([...(company.sources || []), ...(role?.sources || [])])].filter(url => url.startsWith('https://'));
  return `<section aria-label="Contexte de l’entreprise"><div class="panel-intro"><h2>Comprendre l’opportunité</h2><p>${company.basis === 'job_feed' ? 'Résumé établi à partir de la source d’offres ; la page employeur reste à vérifier.' : 'Ce qu’ils construisent, pour qui, et la place du poste dans l’équipe.'}</p></div><div class="company-context">
    <div><h3>L’entreprise</h3><div class="context-copy"><p>${esc(company.summary)}</p></div></div>
    <div><h3>Le produit</h3><div class="context-copy"><p>${esc(company.product)}</p></div></div>
    <div><h3>L’équipe et le rôle</h3><div class="context-copy"><strong>${esc(role?.team || 'Équipe non confirmée')}</strong><p>${esc(role?.scope || 'Le périmètre précis n’est pas confirmé par une annonce officielle accessible.')}</p></div></div>
    </div><p class="source-links">Vérifié le ${esc(company.checked_on.split('-').reverse().join('/'))} · ${sources.map((url, index) => `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${index === 0 ? 'Source entreprise' : 'Source du poste'} ↗</a>`).join(' ')}</p></section>`;
}
function verification(job) {
  if (!job.dossier || lockedStatuses.includes(job.status) || !job.problems.includes('Éligibilité et annonce à vérifier') && !job.problems.some(text => text.startsWith('Questions exactes du formulaire'))) return '';
  return `<div class="verification-box"><h3>À vérifier sur l’annonce</h3><p>La lecture d’une page ne suffit pas à confirmer l’éligibilité. Ces choix sont tes vérifications, pas une validation indépendante de l’app.</p><label class="option"><input id="eligibility-checked" type="checkbox">J’ai vérifié que le poste est ouvert et compatible avec ma situation.</label><label class="option"><input id="form-checked" type="checkbox">J’ai comparé les questions avec le formulaire de l’entreprise.</label><button id="confirm-checks">Enregistrer mes vérifications</button></div>`;
}
function offer(job) {
  const audit = job.audit, criteria = {technical:'Technique et expérience', ownership:'Autonomie et produit', growth:'Progression technique', remote:'Organisation du travail', compensation:'Rémunération', culture:'Culture engineering'};
  return `${companyContext(job)}${verification(job)}<div class="context"><div><small>Rémunération publiée</small><strong>${esc(salary(job))}</strong></div><div><small>Lieu de travail</small><strong>${esc(locationText(job))}</strong></div><div><small>Compatibilité géographique</small><strong>${(audit.location_allowed ?? audit.france_allowed) === true ? 'Confirmée' : (audit.location_allowed ?? audit.france_allowed) === false ? 'Incompatible' : 'À confirmer'}</strong></div><div><small>Collecte ou modification</small><strong>${date(audit.checked_at)}</strong></div></div>
    <div class="offer-details">${audit.description?`<section><h3>Description fournie · à vérifier</h3><p class="job-description">${esc(audit.description)}</p></section>`:''}${audit.source?`<p class="footnote">Origine : ${esc(audit.source)}${audit.source_url?.startsWith('https://')?` · <a href="${esc(audit.source_url)}" target="_blank" rel="noopener noreferrer">Source originale ↗</a>`:''}</p>`:''}${audit.blockers?.length ? `<div class="notice"><strong>Points bloquants identifiés</strong><ul>${audit.blockers.map(text => `<li>${esc(text)}</li>`).join('')}</ul></div>` : ''}
    ${audit.requirements?.length ? `<h3>Ce qu’ils recherchent</h3><ul>${audit.requirements.map(text => `<li>${esc(text)}</li>`).join('')}</ul>` : ''}
    ${audit.warnings?.length ? `<details><summary>Points à vérifier (${audit.warnings.length})</summary><ul>${audit.warnings.map(text => `<li>${esc(text)}</li>`).join('')}</ul></details>` : ''}
    <details><summary>Comprendre le score · ${job.coverage ? job.score + '/100' : 'à évaluer'}</summary><p class="footnote">${job.coverage} % des critères sont documentés. Les critères inconnus n’ajoutent aucun point.</p>${Object.entries(audit.scores || {}).map(([key, value]) => `<div class="score-row"><strong>${esc(criteria[key] || key)}</strong><span>${value.value ?? '—'}/100</span><span>${esc(value.reason)}</span></div>`).join('') || '<p class="footnote">Évaluation en attente de sources.</p>'}</details>
    <p class="footnote">Publication initiale : ${esc(audit.published_at || 'non confirmée')}. Le résumé de l’entreprise ne confirme pas à lui seul que le poste est encore ouvert.</p></div>`;
}
function field(field, answers, index, readonly) {
  const value = answers[field.key], key = esc(field.key), id = 'answer-' + index;
  const title = field.key === 'body' ? 'Ton message' : field.label || 'Question à vérifier sur le site';
  const heading = `<span>${esc(title)}${field.required ? ' <span class="required-mark" aria-label="obligatoire">*</span>' : ''}</span>`;
  if (field.type === 'file') return `<div class="attachment-field"><div><strong>${esc(title)}</strong><small>${value ? 'Document préparé · à joindre sur le site officiel' : 'Facultatif · aucun document complémentaire préparé'}</small></div>${value && String(value).endsWith('/resume.pdf') ? `<a class="button-link" href="/api/jobs/${encodeURIComponent(current.id)}/artifact/resume.pdf" target="_blank">PDF ↗</a>` : ''}<input type="hidden" data-answer="${key}" value="${esc(value || '')}"></div>`;
  if (['radio','checkbox'].includes(field.type) && field.options?.length) return `<fieldset ${readonly ? 'disabled' : ''}><legend>${heading}</legend>${field.options.map(option => `<label class="option"><input type="${field.type}" name="${id}" data-choice="${key}" value="${esc(option.value)}" ${field.type === 'radio' ? value === option.value ? 'checked' : '' : Array.isArray(value) && value.includes(option.value) ? 'checked' : ''}>${esc(option.label)}</label>`).join('')}</fieldset>`;
  if (field.type === 'select') return `<label class="field"><span class="field-heading">${heading}</span><select name="${key}" aria-required="${Boolean(field.required)}" data-answer="${key}" ${readonly ? 'disabled' : ''}><option value="">À choisir${field.required ? '' : ' (facultatif)'}</option>${field.options.map(option => `<option value="${esc(option.value)}" ${value === option.value ? 'selected' : ''}>${esc(option.label)}</option>`).join('')}</select></label>`;
  if (field.type === 'checkbox') return `<label class="option field"><input type="checkbox" data-bool="${key}" ${value === true ? 'checked' : ''} ${readonly ? 'disabled' : ''}>${heading}</label>`;
  const text = String(value ?? ''), rows = Math.min(18, Math.max(field.type === 'textarea' ? 4 : 2, Math.ceil(text.length / 70)));
  const maxWords = /(?:in |than )?(\d+) words/i.exec(field.label || '')?.[1];
  const maxLength = Number.isInteger(field.max_length) && field.max_length > 0 ? field.max_length : null;
  const attributes = `id="${id}" name="${key}" autocomplete="off" aria-required="${Boolean(field.required)}" data-answer="${key}" ${maxLength ? `maxlength="${maxLength}"` : ''} ${maxWords ? `data-word-limit="${maxWords}"` : ''} ${readonly ? 'readonly' : ''}`;
  const multiline = field.type === 'textarea' || field.key === 'body' || text.length > 160 || maxWords;
  const inputType = ['text','email','url','tel','number'].includes(field.type) ? field.type : 'text';
  const control = multiline ? `<textarea ${attributes} rows="${rows}">${esc(text)}</textarea>` : `<input ${attributes} type="${inputType}" ${['email','url'].includes(inputType) ? 'spellcheck="false"' : ''} value="${esc(text)}">`;
  return `<div class="field"><div class="field-heading"><label for="${id}">${heading}</label><span class="field-tools">${multiline && !readonly ? `<button class="text-button assist-field" data-assist="${key}" aria-label="Reformuler la réponse : ${esc(title)}">Reformuler <span aria-hidden="true">↗</span></button>` : ''}<button class="text-button" data-copy="${key}" aria-label="Copier la réponse : ${esc(title)}">Copier</button></span></div>${control}${maxLength || maxWords ? `<small class="field-counter" data-counter="${id}"></small>` : ''}${field.key === 'body' ? '<small>Ce texte est le corps du brouillon d’e-mail.</small>' : ''}</div>`;
}
function dossier(job, data) {
  const form = data.form || {fields:[]}, readonly = lockedStatuses.includes(job.status), base = '/api/jobs/' + encodeURIComponent(job.id);
  return `${job.problems.length && !readonly ? `<div class="notice"><strong>Encore ${job.problems.length} point${job.problems.length > 1 ? 's' : ''} à compléter</strong><ul>${job.problems.map(text => `<li>${esc(text)}</li>`).join('')}</ul></div>` : ''}
    ${readonly ? '<p class="footnote">Dossier conservé dans le suivi. Les réponses restent consultables et copiables.</p>' : ''}
    <div class="split"><div class="document-column"><div class="section-bar"><h2>Ton CV adapté</h2><a class="button-link" href="${base}/artifact/resume.pdf" target="_blank">Ouvrir le PDF ↗</a></div><iframe class="pdf" title="CV adapté pour ${esc(job.company)}" src="${base}/artifact/resume.pdf"></iframe><div class="file-links"><a href="${base}/artifact/resume.json" target="_blank">Source éditable</a><a href="${base}/artifact/tailoring.json" target="_blank">Choix de personnalisation</a></div><p class="document-note">Télécharge ce PDF pour le joindre à ta candidature.</p></div>
    <div class="answer-form"><div class="section-bar"><h2>Tes réponses <small>· ${form.fields.length}</small></h2><button id="copy-answers">Tout copier</button></div><p class="form-intro">${readonly ? 'Version conservée' : 'Version ' + job.revision + ' · tes modifications sont enregistrées localement'}. Les champs marqués d’un * sont obligatoires.</p>
    ${form.fields.map((item, index) => field(item, data.answers, index, readonly)).join('')}
    <details class="additional-motivation"><summary>Motivation complémentaire</summary><label class="field"><span class="field-heading">Un texte de motivation réutilisable</span><textarea id="motivation" rows="6" ${readonly ? 'readonly' : ''}>${esc(data.motivation)}</textarea><small>${data.submission.mode === 'email' ? 'Le brouillon utilise ton message ci-dessus, pas ce texte complémentaire.' : 'À utiliser si une courte motivation est demandée sur le site.'}</small></label></details>
    ${!readonly ? '<div class="review-footer"><button class="primary" id="save" disabled>Enregistrer les réponses</button><button class="quiet" id="discard" hidden>Annuler les modifications</button><p id="save-state">Tes réponses sont enregistrées. Aucun envoi automatique.</p></div>' : ''}
    <div class="delivery-card"><h3>Pour postuler</h3>${data.submission.mode === 'email' ? `<p>Ouvre le brouillon dans ta messagerie, vérifie le destinataire et le CV joint, puis envoie-le toi-même.</p><p class="recipient">${esc(data.submission.recipient || '')}</p><a class="button-link" href="${base}/email">Télécharger le brouillon .eml ↓</a>` : `<p>Copie les réponses, télécharge ton CV et termine sur le site de l’entreprise.</p>${job.url?`<a class="button-link" href="${esc(job.url)}" target="_blank" rel="noopener noreferrer">Ouvrir le formulaire officiel ↗</a>`:'<p>Ajoute une URL employeur si tu souhaites ouvrir le formulaire depuis cette fiche.</p>'}`}<p class="footnote">Après l’envoi, utilise « J’ai postulé » pour mettre ton suivi à jour.</p></div></div></div>`;
}
function tracking(job) {
  const sent = job.status === 'SUBMITTED', canRecord = ['REVIEWED','APPROVED','MANUAL_ACTION_REQUIRED','SUBMISSION_UNCERTAIN'].includes(job.status);
  const events = job.history.events, receipts = events.filter(event => ['MANUAL_CONFIRMATION','SUBMITTED'].includes(event.action));
  const names = {DOSSIER_SAVED:'Dossier enregistré', REVIEW:'Dossier validé pour un envoi manuel', MANUAL_CONFIRMATION:'Candidature déclarée envoyée', SUBMITTED:'Envoi enregistré', AUDIT:'Annonce vérifiée', SKIP:'Candidature ignorée', LATER:'Candidature reportée', GO:'Validation enregistrée', SUBMITTING:'Tentative d’envoi enregistrée', SUBMISSION_UNCERTAIN:'Résultat d’envoi à vérifier'};
  return `<div class="tracking-layout"><section><h2>Où tu en es</h2><div class="tracking-note"><div class="notice ${sent ? 'good' : ''}"><strong>${esc(sent ? 'Candidature envoyée' : canRecord ? 'Prête pour ton envoi manuel' : 'Dossier en préparation')}</strong><p>${sent ? 'L’envoi est enregistré dans ton suivi.' : canRecord ? 'Après l’envoi réel, clique sur « J’ai postulé ». Aucun justificatif n’est obligatoire.' : 'Relis le dossier et complète les réponses avant de le valider. La validation ne déclenche aucun envoi.'}</p></div>
    ${sent && receipts.length ? (() => { const event = receipts[0], receipt = eventDetails(event); return `<p><strong>${date(event.created_at)}</strong> · ${receipt.verified_by === 'user' ? 'Déclaré par toi' : 'Confirmation enregistrée'}</p><p class="footnote">${esc(receipt.confirmation || '')}</p>`; })() : ''}
    ${canRecord ? '<label class="field"><span class="field-heading">Note ou reçu (facultatif)</span><textarea id="receipt" rows="3" placeholder="Par exemple : formulaire envoyé ce matin, confirmation reçue par e-mail…"></textarea><small>Tu peux laisser ce champ vide.</small></label>' : ''}
    <p class="footnote">Le suivi est conservé sur cet ordinateur. Les réponses des recruteurs et les entretiens ne sont pas synchronisés.</p></div></section>
    <section><h2>Le fil de ta candidature</h2><ol class="timeline">${events.map(event => { const details = eventDetails(event); return `<li><span class="timeline-dot" aria-hidden="true"></span><div><strong>${esc(names[event.action] || 'Mise à jour du suivi')}</strong><time datetime="${esc(event.created_at)}">${date(event.created_at)}</time>${details.revision ? `<p>Version ${esc(details.revision)}</p>` : ''}${details.confirmation ? `<p>${esc(details.confirmation)}</p>` : ''}</div></li>`; }).join('') || '<li>Aucune action enregistrée.</li>'}</ol>
    <details class="history-versions"><summary>Versions conservées (${job.history.versions.length})</summary><ul>${job.history.versions.map(version => `<li>Version ${esc(version.revision)} · ${date(version.created_at)}</li>`).join('')}</ul></details><details><summary>Données du journal</summary><pre>${esc(JSON.stringify(job.history, null, 2))}</pre></details></section></div>`;
}
function render() {
  const job = current, data = job.dossier, stage = stageFor(job), canReview = data && !job.problems.length && ['APPLICATION_READY','NEEDS_INPUT','SKIPPED','VERIFIED'].includes(job.status), canRecord = ['REVIEWED','APPROVED','MANUAL_ACTION_REQUIRED','SUBMISSION_UNCERTAIN'].includes(job.status);
  $('#review').innerHTML = `<a class="back" href="/" id="back">← Toutes les opportunités</a><div class="review-top"><div class="company-heading">${mark(job.company)}<div><h1 id="job-title" tabindex="-1">${esc(job.company)}</h1><p class="review-role">${esc(job.audit.title || job.role)}</p>${status(displayStatus(job))}</div></div><div class="review-actions"><button data-edit-opportunity="${esc(job.id)}" ${lockedStatuses.includes(job.status)?'disabled':''}>Modifier l’offre</button><button data-local-tools="${esc(job.id)}">Préparer sans connexion IA</button>${job.url?`<a class="button-link" href="${esc(job.url)}" target="_blank" rel="noopener noreferrer">Voir l’annonce ↗</a>`:''}${canReview ? '<button class="primary" id="review-dossier">Valider le dossier</button>' : ''}${canRecord ? '<button class="primary" id="record-receipt">J’ai postulé</button>' : ''}<span class="action-hint">${job.status === 'SUBMITTED' ? 'Envoi enregistré dans ton suivi.' : canRecord ? 'À utiliser après ton envoi. Note facultative dans le suivi.' : canReview ? 'Validation locale. Aucun envoi automatique.' : 'Les informations manquantes sont indiquées dans le dossier.'}</span></div></div>
    <div class="review-secondary"><div class="review-stage" aria-label="Étape ${stage} sur 3">${['Préparer','Envoyer','Suivre'].map((text, index) => `<span class="${stage === index + 1 ? 'current-step' : ''}"><span class="step-index" aria-hidden="true">${index + 1}</span>${text}</span>`).join('')}</div><div class="secondary-actions"><button class="text-button" id="later" ${lockedStatuses.includes(job.status) ? 'disabled' : ''}>Reporter</button><button class="text-button" id="skip" ${lockedStatuses.includes(job.status) ? 'disabled' : ''}>Ignorer</button></div></div>
    <div class="review-tabs" role="tablist" aria-label="Contenu de la candidature"><button role="tab" id="tab-offre" aria-controls="panel-offre" data-tab="offre">L’offre</button><button role="tab" id="tab-dossier" aria-controls="panel-dossier" data-tab="dossier">Le dossier${data ? '' : ' <small>à préparer</small>'}</button><button role="tab" id="tab-suivi" aria-controls="panel-suivi" data-tab="suivi">Le suivi</button></div>
    <section id="panel-offre" role="tabpanel" aria-labelledby="tab-offre">${job.audit.pending_retrieval?'<p class="notice">URL conservée pour plus tard. Utilise « Modifier l’offre » pour récupérer la fiche en ligne ou coller sa description.</p>':''}${job.audit.source==='Import IA · non vérifié'?'<p class="notice">Offre proposée par une IA externe. Son existence, sa fraîcheur et ses conditions ne sont pas vérifiées.</p>':''}${offer(job)}${job.audit.external_analysis?`<section class="notice"><h2>Analyse IA importée · non vérifiée</h2><pre class="portable-result">${esc(JSON.stringify(job.audit.external_analysis,null,2))}</pre></section>`:''}</section><section id="panel-dossier" role="tabpanel" aria-labelledby="tab-dossier">${data ? dossier(job, data) : '<div class="empty-state"><strong>Le dossier reste à préparer.</strong><p>Les informations de l’offre et l’éligibilité doivent être vérifiées avant de générer un CV et des réponses.</p><button id="see-offer">Comprendre cette offre</button></div>'}</section><section id="panel-suivi" role="tabpanel" aria-labelledby="tab-suivi">${tracking(job)}</section>`;
  $('#back').onclick = event => { if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return; event.preventDefault(); home(); };
  $('#later').onclick = () => decide('LATER'); $('#skip').onclick = () => decide('SKIP');
  if ($('#review-dossier')) $('#review-dossier').onclick = () => decide('REVIEW');
  if ($('#record-receipt')) $('#record-receipt').onclick = recordSent;
  if ($('#see-offer')) $('#see-offer').onclick = () => selectTab('offre');
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
    if ($('#discard')) $('#discard').onclick = async () => { try { current = await api('/api/jobs/' + encodeURIComponent(current.id)); dirty = false; render(); message('Modifications annulées.'); } catch (error) { message(error.message, true); } };
    $('#copy-answers').onclick = async () => { const answers = readAnswers(); await copyText((data.form?.fields || []).filter(field => field.type !== 'file').map(field => field.label + '\n' + (formatAnswer(field, answers[field.key]) || (field.required ? 'À compléter' : 'Non renseigné'))).join('\n\n'), 'Réponses copiées.'); };
    document.querySelectorAll('[data-copy]').forEach(button => button.onclick = async () => { const field = data.form.fields.find(field => field.key === button.dataset.copy); await copyText(formatAnswer(field, readAnswers()[field.key]), 'Réponse copiée.'); });
    $('#review').querySelectorAll('[data-answer],[data-choice],[data-bool],#motivation').forEach(element => element.addEventListener('input', () => { dirty = true; updateEditingState(); updateCounter(element); }));
    $('#review').querySelectorAll('[data-word-limit],[maxlength]').forEach(updateCounter);
  }
  if ($('#confirm-checks')) $('#confirm-checks').onclick = async () => {
    if (dirty) { message('Enregistre les réponses avant de confirmer tes vérifications.', true); return; }
    if (!$('#eligibility-checked').checked || !$('#form-checked').checked) { message('Vérifie les deux points avant de confirmer.', true); return; }
    await updateJob('/checks', {revision:current.revision, eligibility_checked:true, form_checked:true}, 'Tes vérifications sont enregistrées dans le dossier.');
  };
  selectTab(currentTab); updateEditingState();
}
function selectTab(tab) {
  currentTab = tab;
  document.querySelectorAll('[data-tab]').forEach(button => { const active = button.dataset.tab === tab; button.setAttribute('aria-selected', String(active)); button.tabIndex = active ? 0 : -1; });
  ['offre','dossier','suivi'].forEach(name => $('#panel-' + name).hidden = name !== tab);
  syncUrl();
}
function updateEditingState() {
  if ($('#save')) { $('#save').disabled = !dirty || busy; $('#save').textContent = busy ? 'Enregistrement…' : 'Enregistrer les réponses'; }
  if ($('#discard')) $('#discard').hidden = !dirty;
  if ($('.review-footer')) $('.review-footer').classList.toggle('is-dirty', dirty);
  if ($('#save-state')) $('#save-state').textContent = dirty ? 'Modifications non enregistrées.' : 'Tes réponses sont enregistrées. Aucun envoi automatique.';
  ['review-dossier','record-receipt','later','skip'].forEach(id => { const button = $('#' + id); if (button) button.disabled = busy || dirty || (['later','skip'].includes(id) && lockedStatuses.includes(current.status)); });
}
function updateCounter(element) {
  const counter = document.querySelector(`[data-counter="${element.id}"]`); if (!counter) return;
  const words = element.value.trim() ? element.value.trim().split(/\s+/).length : 0, limit = Number(element.dataset.wordLimit);
  counter.textContent = limit ? `${words} / ${limit} mots` : `${element.value.length} / ${element.maxLength} caractères`;
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
async function copyText(text, success) { try { await navigator.clipboard.writeText(text); message(success); } catch { message('Copie indisponible. Tu peux sélectionner le texte et le copier.', true); } }
async function updateJob(path, body, success) {
  if (busy) return; busy = true; updateEditingState();
  try { current = await api('/api/jobs/' + encodeURIComponent(current.id) + path, {method:path ? 'POST' : 'PUT', body:JSON.stringify(body)}); dirty = false; render(); await refreshJobs(); message(success); }
  catch (error) { message(error.message, true); }
  finally { busy = false; updateEditingState(); }
}
async function save() {
  const exceeded = [...document.querySelectorAll('[data-word-limit]')].find(element => element.value.trim().split(/\s+/).filter(Boolean).length > Number(element.dataset.wordLimit));
  if (exceeded) { message(`Cette réponse dépasse la limite de ${exceeded.dataset.wordLimit} mots. Raccourcis-la avant d’enregistrer.`, true); selectTab('dossier'); exceeded.focus(); return; }
  await updateJob('', {revision:current.revision, answers:readAnswers(), motivation:$('#motivation').value}, 'Réponses enregistrées. Ton dossier est à jour.');
}
async function decide(choice) {
  if (dirty) { message('Enregistre tes modifications avant de valider le dossier.', true); return; }
  await updateJob('/decision', {choice, fingerprint:current.fingerprint}, choice === 'REVIEW' ? 'Dossier validé. Tu peux maintenant effectuer ton envoi.' : choice === 'LATER' ? 'Candidature reportée.' : 'Candidature ignorée.');
}
async function recordSent() {
  if (dirty) { message('Enregistre tes modifications avant de mettre le suivi à jour.', true); return; }
  await updateJob('/confirmation', {confirmation:$('#receipt')?.value || '', fingerprint:current.fingerprint, declared_sent:true}, 'Candidature enregistrée comme envoyée.');
  if (current.status === 'SUBMITTED') selectTab('suivi');
}
async function init() {
  const route = new URLSearchParams(location.search);
  if (['all','saved','dossiers','ready','sent'].includes(route.get('view'))) selectedView = route.get('view');
  if (route.get('layout') === 'grid') layout = 'grid';
  $('#search').value = route.get('q') || '';
  if ([...$('#filter').options].some(option => option.value === route.get('filter'))) $('#filter').value = route.get('filter');
  if (['score','company','updated'].includes(route.get('sort'))) $('#sort').value = route.get('sort');
  try {
    token = (await api('/api/session')).token; if (window.WorkspaceUI) await window.WorkspaceUI.boot(); await refreshJobs(); setLayout(layout);
    document.querySelectorAll('button[data-layout]').forEach(button => button.onclick = () => setLayout(button.dataset.layout));
    $('#search').oninput = table; $('#filter').onchange = table; $('#sort').onchange = table;
    document.querySelectorAll('[data-view]').forEach(button => button.onclick = () => { if (dirty) { home(); return; } if (current) home(); selectedView = button.dataset.view; $('#filter').value = 'all'; updateViews(); table(); });
    $('#home-link').onclick = event => { if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return; event.preventDefault(); home(); };
    window.addEventListener('beforeunload', event => { if (dirty || window.profileDirty) { event.preventDefault(); event.returnValue = ''; } });
    if (window.WorkspaceUI) await window.WorkspaceUI.start();
    if (route.get('job')) { await open(route.get('job')); if (current && ['offre','dossier','suivi'].includes(route.get('tab'))) selectTab(route.get('tab')); }
  } catch (error) { message('Chargement impossible : ' + error.message, true); }
}
init();
