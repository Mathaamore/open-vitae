(() => {
  const el = id => document.getElementById(id);
  let bootstrap, profile = {}, provider = 'chatgpt', step = 0, started = false, readyResolve, connectionTimer, connectionChecking = false, connectionGeneration = 0, searchBusy = false, chatBusy = false, preparationTimer, draftTimer;
  window.profileDirty = false;
  const gateMessage = (text = '', error = false) => { el('gate-message').textContent = text; el('gate-message').hidden = !text; el('gate-message').classList.toggle('error', error); };
  function providerChoice(value) {
    provider = value;
    document.querySelectorAll('[data-provider]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.provider === provider)));
    const item = bootstrap?.providers?.find(item => item.id === provider);
    el('provider-mode').textContent = item?.mode || t("workspace.chatgpt_account");
    el('provider-description').textContent = item?.description || t("workspace.sign_in_through_your_browser_your_account_s");
    el('provider-key-label').hidden = provider === 'chatgpt'; el('provider-key').value = '';
    clearInterval(connectionTimer); connectionGeneration++;
    el('connection-progress').hidden = true; el('connection-retry').hidden = true; gateMessage('');
    el('connect-provider').textContent = provider === 'chatgpt' ? t('screen.sign_in_with_chatgpt') : t('ux.connect_named', {name:item?.name || provider});
    el('connect-provider').hidden = false; el('connect-provider').disabled = false;
    el('oauth-continue').hidden = true; el('connection-check').hidden = true;
  }
  function closeConnection() {
    clearInterval(connectionTimer); connectionGeneration++;
    el('provider-key').value = '';
    if (el('connection-dialog').open) el('connection-dialog').close();
    el('connection-step').append(el('optional-ai'));
    el('welcome').insertBefore(el('gate-message'), el('connection-step'));
  }
  function showConnection(returnable = false) {
    providerChoice(bootstrap?.connection?.provider || 'chatgpt');
    el('optional-ai').open = returnable;
    if (returnable) {
      el('connection-dialog-body').append(el('optional-ai'), el('gate-message'));
      el('connection-dialog').showModal();
    } else {
      el('workspace-root').hidden = true; el('welcome').hidden = false;
      el('connection-step').hidden = false; el('profile-step').hidden = true;
      el('connection-title').focus();
    }
  }
  function fillProfile(value) {
    const form = el('profile-form');
    for (const field of form.elements) if (field.name) { if(field.type==='checkbox'){field.checked=value[field.name]===true || value[field.name]==='on';continue;} field.value = Array.isArray(value[field.name]) ? value[field.name].join(', ') : value[field.name] ?? ''; }
    el('cv-template-clear').hidden = !value.cv_template;
    el('cv-import-status').textContent = value.cv_template ? t('resume.saved_layout') : t('screen.no_cv_ready_add_a_few_concrete_achievements');
    window.profileDirty = false;
  }
  function profileStep(value) {
    step = value;
    document.querySelectorAll('[data-profile-step]').forEach(node => node.hidden = Number(node.dataset.profileStep) !== step);
    el('profile-step-caption').textContent = [t("workspace.your_experience"), t("workspace.your_next_role"), t("workspace.your_strengths")][step] + ' · ' + (step + 1) + ' of 3';
    el('profile-title').textContent = [t("workspace.start_with_your_experience"), t("workspace.what_are_you_looking_for"), t("workspace.what_do_you_bring_to_the_work")][step];
    el('profile-progress').textContent = (step + 1) + ' / 3';
    el('profile-previous').hidden = step === 0; el('profile-next').hidden = step === 2; el('profile-save').hidden = step !== 2;
    el('profile-save').textContent = bootstrap?.onboarded ? t("workspace.save_profile") : "Create my workspace →";
    if (!bootstrap?.onboarded && !el('profile-step').hidden) queueDraft();
  }
  function editProfile() {
    if (typeof dirty !== 'undefined' && (dirty || trackingDirty)) { message(t("workspace.save_or_discard_your_application_changes_before_editing"), true); return; }
    el('workspace-root').hidden = true; el('welcome').hidden = false; el('connection-step').hidden = true; el('profile-step').hidden = false; el('welcome').scrollTop=0;
    el('profile-cancel').hidden = !bootstrap?.onboarded; fillProfile(bootstrap?.onboarded ? profile : bootstrap?.onboarding?.fields || profile); profileStep(bootstrap?.onboarded ? 0 : bootstrap?.onboarding?.step || 0); gateMessage(''); el('main').scrollTop=0;
  }
  function activate() {
    el('provider-key').value = ''; clearInterval(connectionTimer); gateMessage('');
    el('welcome').hidden = true; el('workspace-root').hidden = false;
    if (readyResolve) { const resolve = readyResolve; readyResolve = null; resolve(true); }
    else if (started) start();
  }
  async function checkConnection(generation = connectionGeneration) {
    if (connectionChecking) return;
    connectionChecking = true;
    try {
      const status = await api('/api/providers');
      if (generation !== connectionGeneration) return;
      if (!status.connected) {
        if (status.error) { clearInterval(connectionTimer); gateMessage(status.error, true); el('connection-retry').hidden = false; }
        return;
      }
      clearInterval(connectionTimer); bootstrap = await api('/api/bootstrap'); profile = bootstrap.profile || {};
      const inWorkspace = el('connection-dialog').open;
      closeConnection(); updateConnection(status);
      if (inWorkspace) { await loadSettings(); message(t('ux.connected', {name:status.name})); }
      else if (bootstrap.onboarded) activate(); else editProfile();
    } catch (error) { if (generation === connectionGeneration) { gateMessage(error.message, true); el('connection-retry').hidden = false; } }
    finally { connectionChecking = false; }
  }
  async function connect() {
    clearInterval(connectionTimer);
    const generation = ++connectionGeneration;
    el('connect-provider').disabled = true; gateMessage('');
    el('connection-progress').hidden = false; el('connection-progress').textContent = t('ux.connecting');
    el('connection-retry').hidden = true; el('oauth-continue').hidden = true;
    try {
      const result = await api('/api/providers/connect', {method:'POST', body:JSON.stringify({provider, key:el('provider-key').value || undefined})});
      el('provider-key').value = '';
      if (generation !== connectionGeneration) return;
      if (result.url) {
        const url = new URL(result.url);
        if (url.protocol !== 'https:' || !['auth.openai.com','chatgpt.com'].includes(url.hostname) || url.username || url.password) throw Error(t('workspace.the_sign_in_link_could_not_be_verified'));
        el('oauth-continue').href = url.href; el('oauth-continue').hidden = false; el('connection-check').hidden = false; el('connect-provider').hidden = true;
        el('connection-progress').textContent = t('ux.browser_ready');
        el('oauth-continue').focus();
        let polls = 0;
        connectionTimer = setInterval(() => {
          if (++polls > 90) {
            clearInterval(connectionTimer); el('connection-progress').textContent = t('ux.expired'); el('connection-retry').hidden = false;
          } else checkConnection(generation);
        }, 2000);
      } else await checkConnection(generation);
    } catch (error) { if (generation === connectionGeneration) { el('connection-progress').hidden = true; gateMessage(error.message, true); el('connection-retry').hidden = false; } }
    finally { if (generation === connectionGeneration) el('connect-provider').disabled = false; }
  }
  function updateConnection(state) {
    bootstrap.connection = state;
    el('chat-send-label').textContent = state.connected ? t('ux.send') : t('ux.connect_ai');
    el('chat-send').setAttribute('aria-label', state.connected ? t('screen.send_message') : t('ux.connect_ai'));
    el('sidebar-ai-status').textContent = state.connected ? t('ux.connected', {name:state.name}) : t('ux.not_connected');
    el('chat-connection-note').textContent = state.connected ? t('ux.chat_connected', {name:state.name}) : t('ux.chat_offline');
    el('provider-disconnect').hidden = !state.connected;
  }
  function queueDraft() {
    if (bootstrap?.onboarded) return;
    clearTimeout(draftTimer);
    draftTimer = setTimeout(async () => {
      const draft = {step, fields:Object.fromEntries(new FormData(el('profile-form')))};
      try { await api('/api/profile/onboarding', {method:'PUT', body:JSON.stringify(draft)}); bootstrap.onboarding=draft; el('draft-status').textContent=t("workspace.progress_saved_you_can_pick_this_up_later"); }
      catch (error) { el('draft-status').textContent=t("workspace.couldn_t_save_your_progress")+error.message; }
    }, 350);
  }
  async function importCV(file = el('cv-upload').files[0]) {
    if (!file) return;
    if (file.size > 8000000) { el('cv-import-status').textContent = t("workspace.choose_a_cv_smaller_than_8_mb"); return; }
    el('cv-import-status').textContent = t("workspace.reading_your_cv"); el('cv-upload').disabled = true;
    try {
      const result = await api('/api/profile/import?name=' + encodeURIComponent(file.name), {method:'POST', headers:{'Content-Type':'application/octet-stream'}, body:await file.arrayBuffer()});
      el('profile-form').elements.namedItem('cv_text').value = result.text; window.profileDirty = true; queueDraft();
      el('profile-form').elements.namedItem('cv_template').value = result.template || ''; el('cv-template-clear').hidden = !result.template; queueDraft();
      el('cv-import-status').textContent = `${result.characters.toLocaleString('en')} characters imported. ${result.template_message} Review the extracted text.`;
    } catch (error) { el('cv-import-status').textContent = error.message; }
    finally { el('cv-upload').disabled = false; }
  }
  async function saveProfile(event) {
    event.preventDefault(); clearTimeout(draftTimer); const form = el('profile-form'), data = Object.fromEntries(new FormData(form));
    data.roles = data.roles.split(',').map(value => value.trim()).filter(Boolean); data.locations = data.locations.split(',').map(value => value.trim()).filter(Boolean);
    data.strict_constraints = form.elements.namedItem('strict_constraints').checked;
    data.salary_min = data.salary_min ? Number(data.salary_min) : null;
    el('profile-save').disabled = true; gateMessage(t("workspace.saving_profile"));
    try { profile = await api('/api/profile', {method:'PUT', body:JSON.stringify(data)}); bootstrap.onboarded = true; bootstrap.profile = profile; window.profileDirty = false; activate(); }
    catch (error) { gateMessage(error.message, true); }
    finally { el('profile-save').disabled = false; }
  }
  function go(screen) {
    if (typeof dirty !== 'undefined' && (dirty || trackingDirty)) { message(t("workspace.save_or_discard_your_changes_before_leaving_this"), true); return false; }
    if (current) home();
    ['explore','dashboard','settings-screen','tools-screen'].forEach(id => el(id).hidden = id !== screen);
    el('review').hidden = true;
    document.querySelectorAll('[data-screen]').forEach(button => { if (button.dataset.screen === screen) button.setAttribute('aria-current','page'); else button.removeAttribute('aria-current'); });
    el('screen-title').textContent = {explore:t("workspace.discover"),dashboard:t("app.applications"),'settings-screen':t("workspace.ai_and_usage"),'tools-screen':t('ux.ai_imports')}[screen];
    message(''); if(screen==='tools-screen')window.LocalTools?.enter(); if (screen === 'settings-screen') {settingsTab('account');loadSettings();} el('main').scrollTop=0; return true;
  }
  function note(text, role) { const node = document.createElement('div'); node.className = 'chat-message ' + role; const label = document.createElement('span'); label.className='sr-only';label.textContent=role==='user'?"You: ":"Assistant: "; const body=document.createElement('p');body.textContent=text;node.append(label,body);el('chat-log').append(node); }
  async function loadChat() {
    const data = await api('/api/chat');el('chat-log').replaceChildren(); data.messages.forEach(item => note(item.text,item.role)); el('chat-empty').hidden = data.messages.length > 0;
    el('chat-log').scrollTop = el('chat-log').scrollHeight;
  }
  async function sendChat(event) {
    event.preventDefault(); if(!bootstrap.connection.connected){showConnection(true);return;} const text=el('chat-input').value.trim();if (!text || chatBusy) return;
    chatBusy=true;el('chat-send').disabled=true;el('chat-input').value='';el('chat-empty').hidden=true;note(text,'user');
    const pending=document.createElement('p');pending.className='chat-pending';pending.textContent=t("workspace.working_on_your_request");pending.setAttribute('role','status');el('chat-log').append(pending);
    try { const result=await api('/api/chat',{method:'POST',body:JSON.stringify({text})});note(result.text,'assistant');if(result.offers)offers({offers:result.offers});if(result.proposed_preferences)proposePreferences(result.proposed_preferences,result.profile_revision); }
    catch(error){el('chat-input').value=text;message(error.message,true);}
    finally{pending.remove();chatBusy=false;el('chat-send').disabled=false;el('chat-log').scrollTop=el('chat-log').scrollHeight;loadUsage();}
  }
  function proposePreferences(patch, revision) {
    const box=document.createElement('div');box.className='preference-proposal';
    const title=document.createElement('strong');title.textContent=t("workspace.suggested_preferences");box.append(title);
    const labels={roles:'Roles',locations:'Locations',remote:t("app.work_arrangement"),expectations:'Preferences'};
    for(const [key,value] of Object.entries(patch)){const line=document.createElement('p');line.textContent=(labels[key]||key)+' : '+(Array.isArray(value)?value.join(', '):({remote:t("workspace.remote"),hybrid:t("workspace.hybrid"),office:t("workspace.on_site"),flexible:t("workspace.flexible")}[value]||value));box.append(line);}
    const button=document.createElement('button');button.textContent=t("workspace.apply_preferences");box.append(button);
    button.onclick=async()=>{button.disabled=true;try{profile=await api('/api/profile/preferences',{method:'POST',body:JSON.stringify({preferences:patch,revision})});bootstrap.profile=profile;updateProfileDisplay();await loadOffers();button.textContent=t("workspace.preferences_updated");}catch(error){message(error.message,true);button.disabled=false;}};
    el('chat-log').append(box);
  }
  function offerMarkup(offer) {
    const location=typeof offer.location==='string'?offer.location:offer.location?.name||t("app.location_not_provided");
    const salary=typeof offer.salary==='string'?offer.salary:offer.salary?.salary_display||t("app.salary_not_provided");
    const url=offer.source_url?.startsWith('https://')?offer.source_url:offer.url;
    return `<article class="offer-suggestion"><div class="offer-company"><span>${esc(offer.company)}</span><a href="${esc(offer.url)}" target="_blank" rel="noopener noreferrer" aria-label="View listing ${esc(offer.company)}">↗</a></div><h3>${esc(offer.role)}</h3><p class="offer-conditions">${esc(location)}<span aria-hidden="true"> · </span>${esc(salary)}</p>${offer.description?`<p class="offer-excerpt">${esc(offer.description)}</p>`:''}<ul class="match-reasons">${offer.reasons.map(reason=>`<li>${esc(reason)}</li>`).join('')}</ul><details class="offer-checks"><summary>${esc(t("app.before_you_apply"))}</summary><ul>${offer.checks.map(check=>`<li>${esc(check)}</li>`).join('')}</ul></details><div class="offer-choices"><button class="primary" data-interest="accept" data-id="${esc(offer.id)}">${esc(t("app.prepare_application"))} <span aria-hidden="true">→</span></button><button class="quiet" data-interest="later" data-id="${esc(offer.id)}">${esc(t("workspace.save"))}</button><button class="quiet" data-interest="reject" data-id="${esc(offer.id)}">${esc(t("app.dismiss"))}</button><label class="rejection-reason"><span class="sr-only">${esc(t("workspace.reason_for_dismissing"))}</span><select data-reason="${esc(offer.id)}" aria-label="Dismissal reason for ${esc(offer.company)}"><option value="">${esc(t("workspace.reason_optional"))}</option><option value="role">${esc(t("workspace.role"))}</option><option value="location">${esc(t("app.location"))}</option><option value="salary">${esc(t("app.salary"))}</option><option value="company">${esc(t("app.company"))}</option></select></label></div><p class="offer-source">${esc(t("workspace.source"))} <a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(offer.source)}</a> · ${offer.published_at?"Published "+esc(date(offer.published_at)):t("workspace.publication_date_not_provided")}</p></article>`;
  }
  function offers(data) {
    const items=data.offers||[];el('recommendation-count').textContent=items.length?String(items.length):'';
    el('recommendations-list').innerHTML=items.length?items.map(offerMarkup).join(''):`<div class="empty-state"><strong>${esc(t("workspace.no_new_matches_yet"))}</strong><p>${esc(t("workspace.try_different_preferences_or_check_again_later_your"))}</p></div>`;
    el('recommendation-note').textContent=data.feedback_count?`Based on ${data.feedback_count} choices you’ve made.`:t("workspace.choose_a_job_to_prepare_an_application");
  }
  async function loadOffers(){offers(await api('/api/recommendations'));}
  async function search() {
    if(searchBusy || chatBusy)return;discoveryPane('jobs');searchBusy=true;['first-search','search-offers','refresh-offers'].forEach(id=>el(id).disabled=true);
    el('recommendation-note').textContent=t("workspace.checking_job_sources");
    el('cancel-search').hidden=false; el('search-progress').hidden=false; el('search-progress').setAttribute('aria-busy','true');
    const poll=setInterval(async()=>{try{const state=await api('/api/discovery/status');if(state.state==='running'){el('search-progress-text').textContent=`${state.source} · ${state.completed} sources checked · ${state.imported} jobs found`;await loadOffers();}}catch{}},1500);
    try {const result=await api('/api/discovery',{method:'POST',body:JSON.stringify({query:el('chat-input').value.trim()})});offers(result);await refreshJobs();await loadChat();const errors=result.search.errors||[];message(result.search.cancelled?t("workspace.search_stopped_jobs_already_found_are_still_available"):errors.length?t("workspace.search_finished_some_sources_couldn_t_be_reached"):result.search.cached?t("workspace.showing_your_recent_results_sources_refresh_daily"):`${result.search.imported} new jobs added.`);}
    catch(error){message(error.message,true);el('recommendation-note').textContent=t("workspace.search_interrupted_try_again_when_you_re_ready");}
    finally{clearInterval(poll);el('cancel-search').hidden=true;el('search-progress').hidden=true;el('search-progress').setAttribute('aria-busy','false');searchBusy=false;['first-search','search-offers','refresh-offers'].forEach(id=>el(id).disabled=false);}
  }
  async function interest(button) {
    const identity=button.dataset.id,decision=button.dataset.interest;
    if(decision==='accept'){button.dataset.prepareJob=identity;await prepareApplication(button);return;}
    button.disabled=true;
    const reason=[...document.querySelectorAll('[data-reason]')].find(node=>node.dataset.reason===identity)?.value||'';
    try {await api('/api/jobs/'+encodeURIComponent(identity)+'/interest',{method:'POST',body:JSON.stringify({decision,reason})});await Promise.all([loadOffers(),refreshJobs()]);message(decision==='later'?t("workspace.job_saved"):decision==='accept'?t("workspace.application_started_find_your_draft_in_applications"):t("workspace.job_dismissed_your_feedback_helps_refine_future_suggestions"));if(decision==='reject'){
      const undo=document.createElement('button');undo.textContent=t("workspace.undo");undo.className='undo-button';
      undo.onclick=async()=>{undo.disabled=true;try{await api('/api/jobs/'+encodeURIComponent(identity)+'/interest',{method:'POST',body:JSON.stringify({decision:'reset'})});await Promise.all([loadOffers(),refreshJobs()]);message(t("workspace.job_restored_to_your_suggestions"));}catch(error){message(error.message,true);}};
      el('message').append(undo);
    }pollPreparations();}
    catch(error){message(error.message,true);button.disabled=false;}
  }
  async function prepareApplication(button) {
    if (dirty || trackingDirty) { message(t('workspace.save_or_discard_your_changes_before_leaving_this'), true); return; }
    button.disabled = true;
    try {
      const state = await api('/api/providers'); updateConnection(state);
      if (!state.connected) { showConnection(true); gateMessage(t('prepare.connect_help')); return; }
      const job = await api('/api/jobs/'+encodeURIComponent(button.dataset.prepareJob));
      await api('/api/jobs/'+encodeURIComponent(job.id)+'/prepare', {method:'POST',body:JSON.stringify({revision:job.revision,updated_at:job.updated_at})});
      await refreshJobs();
      if (current?.id !== job.id) { go('dashboard');await window.open(job.id); }
      current=await api('/api/jobs/'+encodeURIComponent(job.id));currentTab='dossier';render();
      pollPreparations();
    } catch(error) { message(error.message,true); }
    finally { button.disabled=false; }
  }
  function pollPreparations(){
    clearInterval(preparationTimer);
    if(!jobs.some(job=>['queued','preparing'].includes(job.preparation?.state)))return;
    preparationTimer=setInterval(async()=>{
      if(document.hidden)return;
      try {
        await refreshJobs();
        if(current && !dirty && !trackingDirty) {
          const updated=jobs.find(job=>job.id===current.id);
          if(updated && (updated.preparation?.updated_at!==current.preparation?.updated_at || updated.revision!==current.revision)) {
            const wasPreparing=['queued','preparing'].includes(current.preparation?.state);
            current=await api('/api/jobs/'+encodeURIComponent(current.id));
            if(wasPreparing && current.preparation?.state==='ready')currentTab='dossier';
            render();
          }
        }
        if(!jobs.some(job=>['queued','preparing'].includes(job.preparation?.state))){clearInterval(preparationTimer);await loadUsage();}
      } catch(error){clearInterval(preparationTimer);message(error.message,true);}
    },1500);
  }
  async function loadUsage(){try{const data=await api('/api/usage');el('daily-limit').value=data.limit;const tokens=data.runs.map(run=>run.usage?.totalTokens ?? run.usage?.totalTokenCount ?? (typeof run.usage?.input_tokens==='number'&&typeof run.usage?.output_tokens==='number'?run.usage.input_tokens+run.usage.output_tokens:null)).filter(value=>typeof value==='number');
      el('usage-detail').textContent=`${data.requests} requests today. ${tokens.length?tokens.reduce((sum,value)=>sum+value,0).toLocaleString('en')+t("workspace.tokens_reported_by_your_ai_service"):t("workspace.your_ai_service_hasn_t_reported_token_usage")} The daily limit resets at 00:00 UTC.`;}catch(error){message(error.message,true);}}
  async function loadSettings(){
    try{const sources=await api('/api/sources');el('source-boards').value=sources.boards.join('\n');const state=await api('/api/providers');el('connected-provider-name').textContent=state.name||t("workspace.your_ai_service");el('connected-provider-detail').textContent=state.connected ? (state.email || (state.provider==='chatgpt'?t("workspace.chatgpt_connected"):t("workspace.api_key_stored_in_your_system_keychain"))) : t('ux.disconnected_detail'); updateConnection(state);await loadUsage();}catch(error){message(error.message,true);}
  }
  function updateProfileDisplay(){
    el('profile-name').textContent=profile.name||t("workspace.your_profile");el('profile-initial').textContent=(profile.name||'C').slice(0,1).toUpperCase();
    el('criteria-summary').textContent=[...(profile.roles||[]),...(profile.locations||[]),{remote:t("workspace.remote"),hybrid:t("workspace.hybrid"),office:t("workspace.on_site"),flexible:t("workspace.flexible_work_arrangement")}[profile.remote]].filter(Boolean).join(' · ');
    el('criteria-summary').title=el('criteria-summary').textContent;
  }
  async function start(){
    started=true;updateProfileDisplay();updateConnection(bootstrap.connection);
    await Promise.all([loadOffers(),loadChat(),loadUsage()]);pollPreparations();go('explore');
    if (!bootstrap.local_mode) { try { updateConnection(await api('/api/providers')); } catch { updateConnection({connected:false}); } }
  }
  function discoveryPane(value) {
    el('explore').dataset.pane = value;
    document.querySelectorAll('[data-discovery-pane]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.discoveryPane === value)));
  }
  function settingsTab(value) {
    document.querySelectorAll('[data-settings-tab]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.settingsTab === value)));
    document.querySelectorAll('[data-settings-panel]').forEach(panel => panel.hidden = panel.dataset.settingsPanel !== value);
  }
  function bind(){
    document.querySelectorAll('[data-discovery-pane]').forEach(button => button.onclick = () => discoveryPane(button.dataset.discoveryPane));
    document.querySelectorAll('[data-settings-tab]').forEach(button => button.onclick = () => settingsTab(button.dataset.settingsTab));
    document.querySelectorAll('[data-provider]').forEach(button=>button.onclick=()=>providerChoice(button.dataset.provider));el('connect-provider').onclick=connect;el('connection-check').onclick=()=>checkConnection();
    el('connection-retry').onclick=connect; el('connection-close').onclick=closeConnection;
    el('connection-dialog').addEventListener('cancel', event=>{event.preventDefault();closeConnection();});
    el('oauth-continue').onclick=()=>{el('connection-progress').textContent=t('ux.waiting');};
    el('continue-local').onclick=async()=>{try{await api('/api/providers/local',{method:'POST',body:'{}'});bootstrap=await api('/api/bootstrap');profile=bootstrap.profile||{};if(bootstrap.onboarded)activate();else editProfile();}catch(error){gateMessage(error.message,true);}};
    el('cv-template-clear').onclick=()=>{el('profile-form').elements.namedItem('cv_template').value='';el('cv-template-clear').hidden=true;window.profileDirty=true;queueDraft();el('cv-import-status').textContent=t('resume.removed_layout');};
    el('cv-upload').onchange=()=>importCV();
    const drop=document.querySelector('.cv-drop');
    drop.ondragover=event=>{event.preventDefault();drop.classList.add('drag-over');};
    drop.ondragleave=()=>drop.classList.remove('drag-over');
    drop.ondrop=event=>{event.preventDefault();drop.classList.remove('drag-over');if(!el('cv-upload').disabled)importCV(event.dataTransfer.files[0]);};
    el('cancel-search').onclick=async()=>{try{await api('/api/discovery/cancel',{method:'POST',body:'{}'});el('search-progress-text').textContent=t("workspace.stopping_after_the_current_source_finishes");}catch(error){message(error.message,true);}};
    el('profile-form').oninput=()=>{window.profileDirty=true;queueDraft();};el('profile-form').onsubmit=saveProfile;
    el('profile-next').onclick=()=>{const visible=document.querySelector(`[data-profile-step="${step}"]`);if([...visible.querySelectorAll('input,textarea,select')].every(field=>field.reportValidity()))profileStep(step+1);};
    el('profile-previous').onclick=()=>profileStep(step-1);el('profile-cancel').onclick=()=>{window.profileDirty=false;fillProfile(profile);activate();};
    document.querySelectorAll('[data-screen]').forEach(button=>button.onclick=()=>go(button.dataset.screen));el('profile-open').onclick=editProfile;el('settings-profile').onclick=editProfile;
    el('provider-change').onclick=()=>showConnection(true);el('provider-disconnect').onclick=async()=>{try{await api('/api/providers/disconnect',{method:'POST',body:'{}'});bootstrap.connection={connected:false,name:t("workspace.ai_not_connected")};updateProfileDisplay();updateConnection(bootstrap.connection);await loadSettings();}catch(error){message(error.message,true);}};
    el('save-source-boards').onclick=async()=>{try{const boards=el('source-boards').value.split('\n').map(value=>value.trim()).filter(Boolean);await api('/api/sources',{method:'PUT',body:JSON.stringify({boards})});message(t("workspace.sources_saved_they_ll_be_included_in_your"));}catch(error){message(error.message,true);}};
    el('save-daily-limit').onclick=async()=>{try{await api('/api/usage',{method:'PUT',body:JSON.stringify({limit:Number(el('daily-limit').value)})});await loadUsage();message(t("workspace.daily_limit_saved"));}catch(error){message(error.message,true);}};
    el('chat-form').onsubmit=sendChat;['first-search','search-offers','refresh-offers'].forEach(id=>el(id).onclick=search);
    el('recommendations-list').onclick=event=>{const button=event.target.closest('[data-interest]');if(button)interest(button);};
    document.addEventListener('click',event=>{const prepare=event.target.closest('[data-prepare-job]');if(prepare){prepareApplication(prepare);return;}const button=event.target.closest('[data-retry-preparation]');if(button){button.dataset.prepareJob=button.dataset.retryPreparation;prepareApplication(button);}});
  }
  async function boot(){bind();bootstrap=await api('/api/bootstrap');profile=bootstrap.profile||{};if(bootstrap.onboarded){el('welcome').hidden=true;el('workspace-root').hidden=false;return true;}
    const pending=new Promise(resolve=>readyResolve=resolve);if(bootstrap.connection.connected)editProfile();else{showConnection();if(bootstrap.connection.error)gateMessage(bootstrap.connection.error,true);}return pending;}
  window.WorkspaceUI={get connection(){return bootstrap?.connection;},boot,start,go,openSettings:()=>go('settings-screen'),showConnection,editProfile};
})();
