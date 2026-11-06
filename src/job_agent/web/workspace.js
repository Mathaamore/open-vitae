(() => {
  const el = id => document.getElementById(id);
  let bootstrap, profile = {}, provider = 'chatgpt', step = 0, started = false, readyResolve, connectionTimer, searchBusy = false, chatBusy = false, preparationTimer, draftTimer;
  window.profileDirty = false;
  const gateMessage = (text = '', error = false) => { el('gate-message').textContent = text; el('gate-message').hidden = !text; el('gate-message').classList.toggle('error', error); };
  function providerChoice(value) {
    provider = value;
    document.querySelectorAll('[data-provider]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.provider === provider)));
    const item = bootstrap?.providers?.find(item => item.id === provider);
    el('provider-mode').textContent = item?.mode || 'Compte ChatGPT';
    el('provider-description').textContent = item?.description || 'Connexion dans le navigateur. Les limites de ton forfait s’appliquent.';
    el('provider-key-label').hidden = provider === 'chatgpt'; el('provider-key').value = '';
    el('connect-provider').textContent = provider === 'chatgpt' ? 'Se connecter avec ChatGPT ↗' : 'Connecter ' + (item?.name || provider);
    el('connect-provider').hidden = false; el('connect-provider').disabled = false;
    el('oauth-continue').hidden = true; el('connection-check').hidden = true;
  }
  function showConnection(returnable = false) {
    clearInterval(connectionTimer); el('workspace-root').hidden = true; el('welcome').hidden = false;
    el('connection-step').hidden = false; el('profile-step').hidden = true;
    el('return-workspace').hidden = !returnable; providerChoice(bootstrap?.connection?.provider || 'chatgpt');
    el('connection-title').focus();
  }
  function fillProfile(value) {
    const form = el('profile-form');
    for (const field of form.elements) if (field.name) { if(field.type==='checkbox'){field.checked=value[field.name]===true || value[field.name]==='on';continue;} field.value = Array.isArray(value[field.name]) ? value[field.name].join(', ') : value[field.name] ?? ''; }
    window.profileDirty = false;
  }
  function profileStep(value) {
    step = value;
    document.querySelectorAll('[data-profile-step]').forEach(node => node.hidden = Number(node.dataset.profileStep) !== step);
    el('profile-step-caption').textContent = ['Ton parcours', 'Ta recherche', 'Ce qu’on doit retenir'][step] + ' · ' + (step + 1) + ' sur 3';
    el('profile-title').textContent = ['On part de ton histoire.', 'Où veux-tu aller ?', 'Ce qui te rend utile.'][step];
    el('profile-progress').textContent = (step + 1) + ' / 3';
    el('profile-previous').hidden = step === 0; el('profile-next').hidden = step === 2; el('profile-save').hidden = step !== 2;
    el('profile-save').textContent = bootstrap?.onboarded ? 'Enregistrer mon profil' : 'Créer mon espace →';
    if (!bootstrap?.onboarded && !el('profile-step').hidden) queueDraft();
  }
  function editProfile() {
    if (typeof dirty !== 'undefined' && dirty) { message('Enregistre ou annule les modifications du dossier avant de modifier ton profil.', true); return; }
    el('workspace-root').hidden = true; el('welcome').hidden = false; el('connection-step').hidden = true; el('profile-step').hidden = false;
    el('profile-cancel').hidden = !bootstrap?.onboarded; fillProfile(bootstrap?.onboarded ? profile : bootstrap?.onboarding?.fields || profile); profileStep(bootstrap?.onboarded ? 0 : bootstrap?.onboarding?.step || 0); gateMessage(''); window.scrollTo(0,0);
  }
  function activate() {
    el('provider-key').value = ''; clearInterval(connectionTimer); gateMessage('');
    el('welcome').hidden = true; el('workspace-root').hidden = false;
    if (readyResolve) { const resolve = readyResolve; readyResolve = null; resolve(true); }
    else if (started) start();
  }
  async function checkConnection() {
    try {
      const status = await api('/api/providers');
      if (!status.connected) { gateMessage(status.error || 'Termine la connexion dans le navigateur, puis reviens ici.'); return; }
      clearInterval(connectionTimer); bootstrap = await api('/api/bootstrap'); profile = bootstrap.profile || {};
      if (bootstrap.onboarded) activate(); else editProfile();
    } catch (error) { gateMessage(error.message, true); }
  }
  async function connect() {
    el('connect-provider').disabled = true; gateMessage('Vérification de la connexion…');
    try {
      const result = await api('/api/providers/connect', {method:'POST', body:JSON.stringify({provider, key:el('provider-key').value || undefined})});
      el('provider-key').value = '';
      if (result.url) {
        const url = new URL(result.url);
        if (url.protocol !== 'https:' || !['auth.openai.com','chatgpt.com'].includes(url.hostname)) throw Error('Adresse de connexion inattendue.');
        el('oauth-continue').href = url.href; el('oauth-continue').hidden = false; el('connection-check').hidden = false; el('connect-provider').hidden = true;
        gateMessage('Continue sur OpenAI dans ton navigateur. L’app attend ta connexion.');
        let polls = 0; connectionTimer = setInterval(() => { if (++polls > 90 || el('welcome').hidden) clearInterval(connectionTimer); else checkConnection(); }, 2000);
      } else await checkConnection();
    } catch (error) { gateMessage(error.message, true); }
    finally { el('connect-provider').disabled = false; }
  }
  function queueDraft() {
    if (bootstrap?.onboarded) return;
    clearTimeout(draftTimer);
    draftTimer = setTimeout(async () => {
      const draft = {step, fields:Object.fromEntries(new FormData(el('profile-form')))};
      try { await api('/api/profile/onboarding', {method:'PUT', body:JSON.stringify(draft)}); bootstrap.onboarding=draft; el('draft-status').textContent='Brouillon enregistré sur ce Mac. Tu peux reprendre plus tard.'; }
      catch (error) { el('draft-status').textContent='Brouillon non enregistré : '+error.message; }
    }, 350);
  }
  async function importCV(file = el('cv-upload').files[0]) {
    if (!file) return;
    if (file.size > 8000000) { el('cv-import-status').textContent = 'Le fichier doit faire moins de 8 Mo.'; return; }
    el('cv-import-status').textContent = 'Lecture du CV sur cet ordinateur…'; el('cv-upload').disabled = true;
    try {
      const result = await api('/api/profile/import?name=' + encodeURIComponent(file.name), {method:'POST', headers:{'Content-Type':'application/octet-stream'}, body:await file.arrayBuffer()});
      el('profile-form').elements.namedItem('cv_text').value = result.text; window.profileDirty = true; queueDraft();
      el('cv-import-status').textContent = `${result.characters.toLocaleString('fr')} caractères extraits, sans appel IA. Tu peux relire et corriger le texte.`;
    } catch (error) { el('cv-import-status').textContent = error.message; }
    finally { el('cv-upload').disabled = false; }
  }
  async function saveProfile(event) {
    event.preventDefault(); clearTimeout(draftTimer); const form = el('profile-form'), data = Object.fromEntries(new FormData(form));
    data.roles = data.roles.split(',').map(value => value.trim()).filter(Boolean); data.locations = data.locations.split(',').map(value => value.trim()).filter(Boolean);
    data.strict_constraints = form.elements.namedItem('strict_constraints').checked;
    data.salary_min = data.salary_min ? Number(data.salary_min) : null;
    el('profile-save').disabled = true; gateMessage('Enregistrement du profil…');
    try { profile = await api('/api/profile', {method:'PUT', body:JSON.stringify(data)}); bootstrap.onboarded = true; bootstrap.profile = profile; window.profileDirty = false; activate(); }
    catch (error) { gateMessage(error.message, true); }
    finally { el('profile-save').disabled = false; }
  }
  function go(screen) {
    if (typeof dirty !== 'undefined' && dirty) { message('Enregistre ou annule tes modifications avant de changer de vue.', true); return false; }
    if (current) home();
    ['explore','dashboard','settings-screen','tools-screen'].forEach(id => el(id).hidden = id !== screen);
    el('review').hidden = true;
    document.querySelectorAll('[data-screen]').forEach(button => { if (button.dataset.screen === screen) button.setAttribute('aria-current','page'); else button.removeAttribute('aria-current'); });
    el('screen-title').textContent = {explore:'Recherche',dashboard:'Candidatures','settings-screen':'Connexion et usage','tools-screen':'Utiliser mon IA'}[screen];
    message(''); if(screen==='tools-screen')window.LocalTools?.enter(); if (screen === 'settings-screen') loadSettings(); window.scrollTo(0,0); return true;
  }
  function note(text, role) { const node = document.createElement('div'); node.className = 'chat-message ' + role; const label = document.createElement('span'); label.className='sr-only';label.textContent=role==='user'?'Toi : ':'Assistant : '; const body=document.createElement('p');body.textContent=text;node.append(label,body);el('chat-log').append(node); }
  async function loadChat() {
    const data = await api('/api/chat');el('chat-log').replaceChildren(); data.messages.forEach(item => note(item.text,item.role)); el('chat-empty').hidden = data.messages.length > 0;
    el('chat-log').scrollTop = el('chat-log').scrollHeight;
  }
  async function sendChat(event) {
    event.preventDefault(); if(!bootstrap.connection.connected){window.LocalTools.open('profile_analysis');message('Crée un prompt local pour ton IA, ou connecte un fournisseur depuis Connexion et usage.');return;} const text=el('chat-input').value.trim();if (!text || chatBusy) return;
    chatBusy=true;el('chat-send').disabled=true;el('chat-input').value='';el('chat-empty').hidden=true;note(text,'user');
    const pending=document.createElement('p');pending.className='chat-pending';pending.textContent='Réflexion en cours…';pending.setAttribute('role','status');el('chat-log').append(pending);
    try { const result=await api('/api/chat',{method:'POST',body:JSON.stringify({text})});note(result.text,'assistant');if(result.offers)offers({offers:result.offers});if(result.proposed_preferences)proposePreferences(result.proposed_preferences,result.profile_revision); }
    catch(error){el('chat-input').value=text;message(error.message,true);}
    finally{pending.remove();chatBusy=false;el('chat-send').disabled=false;el('chat-log').scrollTop=el('chat-log').scrollHeight;loadUsage();}
  }
  function proposePreferences(patch, revision) {
    const box=document.createElement('div');box.className='preference-proposal';
    const title=document.createElement('strong');title.textContent='Critères proposés';box.append(title);
    const labels={roles:'Postes',locations:'Lieux',remote:'Organisation',expectations:'Attentes'};
    for(const [key,value] of Object.entries(patch)){const line=document.createElement('p');line.textContent=(labels[key]||key)+' : '+(Array.isArray(value)?value.join(', '):({remote:'Télétravail',hybrid:'Hybride',office:'Sur place',flexible:'Flexible'}[value]||value));box.append(line);}
    const button=document.createElement('button');button.textContent='Appliquer ces critères';box.append(button);
    button.onclick=async()=>{button.disabled=true;try{profile=await api('/api/profile/preferences',{method:'POST',body:JSON.stringify({preferences:patch,revision})});bootstrap.profile=profile;updateProfileDisplay();await loadOffers();button.textContent='Critères enregistrés';}catch(error){message(error.message,true);button.disabled=false;}};
    el('chat-log').append(box);
  }
  function offerMarkup(offer) {
    const location=typeof offer.location==='string'?offer.location:offer.location?.name||'Lieu à confirmer';
    const salary=typeof offer.salary==='string'?offer.salary:offer.salary?.salary_display||'Salaire à confirmer';
    const url=offer.source_url?.startsWith('https://')?offer.source_url:offer.url;
    return `<article class="offer-suggestion"><div class="offer-company"><span>${esc(offer.company)}</span><a href="${esc(offer.url)}" target="_blank" rel="noopener noreferrer" aria-label="Voir l’annonce ${esc(offer.company)}">↗</a></div><h3>${esc(offer.role)}</h3><p class="offer-conditions">${esc(location)}<span aria-hidden="true"> · </span>${esc(salary)}</p>${offer.description?`<p class="offer-excerpt">${esc(offer.description)}</p>`:''}<ul class="match-reasons">${offer.reasons.map(reason=>`<li>${esc(reason)}</li>`).join('')}</ul><details class="offer-checks"><summary>À vérifier avant de postuler</summary><ul>${offer.checks.map(check=>`<li>${esc(check)}</li>`).join('')}</ul></details><div class="offer-choices"><button class="primary" data-interest="accept" data-id="${esc(offer.id)}">Ça m’intéresse <span aria-hidden="true">→</span></button><button class="quiet" data-interest="later" data-id="${esc(offer.id)}">Garder</button><button class="quiet" data-interest="reject" data-id="${esc(offer.id)}">Passer</button><label class="rejection-reason"><span class="sr-only">Motif pour affiner la recherche</span><select data-reason="${esc(offer.id)}" aria-label="Motif du refus pour ${esc(offer.company)}"><option value="">Un motif ?</option><option value="role">Le poste</option><option value="location">Le lieu</option><option value="salary">Le salaire</option><option value="company">L’entreprise</option></select></label></div><p class="offer-source">Source : <a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(offer.source)}</a> · ${offer.published_at?'Publié le '+esc(date(offer.published_at)):'Date de publication inconnue'}</p></article>`;
  }
  function offers(data) {
    const items=data.offers||[];el('recommendation-count').textContent=items.length?String(items.length):'';
    el('recommendations-list').innerHTML=items.length?items.map(offerMarkup).join(''):'<div class="empty-state"><strong>Pas de nouvelle piste dans cette sélection.</strong><p>Tu peux modifier tes critères ou relancer une recherche. Tes dossiers restent dans Candidatures.</p></div>';
    el('recommendation-note').textContent=data.feedback_count?`Le tri tient compte de tes ${data.feedback_count} choix.`:'Accepte une piste pour préparer son dossier.';
  }
  async function loadOffers(){offers(await api('/api/recommendations'));}
  async function search() {
    if(searchBusy || chatBusy)return;searchBusy=true;['first-search','search-offers','refresh-offers'].forEach(id=>el(id).disabled=true);
    el('recommendation-note').textContent='Consultation des sources…';
    el('cancel-search').hidden=false; el('search-progress').hidden=false; el('search-progress').setAttribute('aria-busy','true');
    const poll=setInterval(async()=>{try{const state=await api('/api/discovery/status');if(state.state==='running'){el('search-progress-text').textContent=`${state.source} · ${state.completed} source(s) consultée(s) · ${state.imported} offre(s) collectée(s)`;await loadOffers();}}catch{}},1500);
    try {const result=await api('/api/discovery',{method:'POST',body:JSON.stringify({query:el('chat-input').value.trim()})});offers(result);await refreshJobs();await loadChat();const errors=result.search.errors||[];message(result.search.cancelled?'Recherche arrêtée. Les offres déjà collectées restent disponibles.':errors.length?'Recherche terminée. Certaines sources sont indisponibles ; les pistes conservées restent visibles.':result.search.cached?'Sélection réutilisée : les sources se mettent à jour quotidiennement.':`${result.search.imported} nouvelles offres ajoutées. Le tri n’a utilisé aucun appel IA.`);}
    catch(error){message(error.message,true);el('recommendation-note').textContent='Recherche interrompue. Tu peux réessayer.';}
    finally{clearInterval(poll);el('cancel-search').hidden=true;el('search-progress').hidden=true;el('search-progress').setAttribute('aria-busy','false');searchBusy=false;['first-search','search-offers','refresh-offers'].forEach(id=>el(id).disabled=false);}
  }
  async function interest(button) {
    const identity=button.dataset.id,decision=button.dataset.interest;button.disabled=true;
    const reason=[...document.querySelectorAll('[data-reason]')].find(node=>node.dataset.reason===identity)?.value||'';
    try {await api('/api/jobs/'+encodeURIComponent(identity)+'/interest',{method:'POST',body:JSON.stringify({decision,reason})});await Promise.all([loadOffers(),refreshJobs()]);message(decision==='later'?'Offre conservée dans tes favoris.':decision==='accept'?'Offre retenue. La préparation apparaîtra dans Candidatures.':'Offre écartée. Le motif, si tu en as choisi un, affine la sélection.');if(decision==='reject'){
      const undo=document.createElement('button');undo.textContent='Annuler';undo.className='undo-button';
      undo.onclick=async()=>{undo.disabled=true;try{await api('/api/jobs/'+encodeURIComponent(identity)+'/interest',{method:'POST',body:JSON.stringify({decision:'reset'})});await Promise.all([loadOffers(),refreshJobs()]);message('Choix annulé. Cette offre est à nouveau dans la sélection.');}catch(error){message(error.message,true);}};
      el('message').append(undo);
    }pollPreparations();}
    catch(error){message(error.message,true);button.disabled=false;}
  }
  function pollPreparations(){
    clearInterval(preparationTimer);
    if(!jobs.some(job=>['queued','preparing'].includes(job.preparation?.state)))return;
    preparationTimer=setInterval(async()=>{if(document.hidden)return;try{await refreshJobs();if(!jobs.some(job=>['queued','preparing'].includes(job.preparation?.state))){clearInterval(preparationTimer);await loadUsage();message('La file de préparation est à jour. Les dossiers et éventuels points à compléter sont dans Candidatures.');}}catch(error){clearInterval(preparationTimer);message(error.message,true);}},4000);
  }
  async function loadUsage(){try{const data=await api('/api/usage');el('usage-summary').textContent=`Mode économe · ${data.requests} / ${data.limit} demandes IA aujourd’hui · tri local`;el('daily-limit').value=data.limit;const tokens=data.runs.map(run=>run.usage?.totalTokens ?? run.usage?.totalTokenCount ?? (typeof run.usage?.input_tokens==='number'&&typeof run.usage?.output_tokens==='number'?run.usage.input_tokens+run.usage.output_tokens:null)).filter(value=>typeof value==='number');
      el('usage-detail').textContent=`${data.requests} demandes aujourd’hui. ${tokens.length?tokens.reduce((sum,value)=>sum+value,0).toLocaleString('fr')+' tokens rapportés par le fournisseur.':'Le fournisseur n’a pas rapporté de total de tokens.'} Réinitialisation de la limite à 00:00 UTC.`;}catch(error){message(error.message,true);}}
  async function loadSettings(){
    try{const sources=await api('/api/sources');el('source-boards').value=sources.boards.join('\n');const state=await api('/api/providers');el('connected-provider-name').textContent=state.name||'Ton fournisseur';el('connected-provider-detail').textContent=state.email|| (state.provider==='chatgpt'?'Compte ChatGPT connecté':'Clé conservée dans le trousseau');await loadUsage();}catch(error){message(error.message,true);}
  }
  function updateProfileDisplay(){
    el('profile-name').textContent=profile.name||'Ton profil';el('profile-initial').textContent=(profile.name||'C').slice(0,1).toUpperCase();
    el('provider-indicator').textContent=bootstrap.connection.name||'Mode local · IA facultative';
    el('criteria-summary').textContent=[...(profile.roles||[]),...(profile.locations||[]),{remote:'Télétravail',hybrid:'Hybride',office:'Sur place',flexible:'Organisation flexible'}[profile.remote]].filter(Boolean).join(' · ');
  }
  async function start(){
    started=true;updateProfileDisplay();
    await Promise.all([loadOffers(),loadChat(),loadUsage()]);pollPreparations();go('explore');
  }
  function bind(){
    document.querySelectorAll('[data-provider]').forEach(button=>button.onclick=()=>providerChoice(button.dataset.provider));el('connect-provider').onclick=connect;el('connection-check').onclick=checkConnection;
    el('continue-local').onclick=async()=>{try{await api('/api/providers/local',{method:'POST',body:'{}'});bootstrap=await api('/api/bootstrap');profile=bootstrap.profile||{};if(bootstrap.onboarded)activate();else editProfile();}catch(error){gateMessage(error.message,true);}};
    el('return-workspace').onclick=()=>activate();el('cv-upload').onchange=()=>importCV();
    const drop=document.querySelector('.cv-drop');
    drop.ondragover=event=>{event.preventDefault();drop.classList.add('drag-over');};
    drop.ondragleave=()=>drop.classList.remove('drag-over');
    drop.ondrop=event=>{event.preventDefault();drop.classList.remove('drag-over');if(!el('cv-upload').disabled)importCV(event.dataTransfer.files[0]);};
    el('cancel-search').onclick=async()=>{try{await api('/api/discovery/cancel',{method:'POST',body:'{}'});el('search-progress-text').textContent='Arrêt demandé. La lecture de la source en cours va se terminer…';}catch(error){message(error.message,true);}};
    el('profile-form').oninput=()=>{window.profileDirty=true;queueDraft();};el('profile-form').onsubmit=saveProfile;
    el('profile-next').onclick=()=>{const visible=document.querySelector(`[data-profile-step="${step}"]`);if([...visible.querySelectorAll('input,textarea,select')].every(field=>field.reportValidity()))profileStep(step+1);};
    el('profile-previous').onclick=()=>profileStep(step-1);el('profile-cancel').onclick=()=>{window.profileDirty=false;fillProfile(profile);activate();};
    document.querySelectorAll('[data-screen]').forEach(button=>button.onclick=()=>go(button.dataset.screen));el('profile-open').onclick=editProfile;el('settings-profile').onclick=editProfile;
    el('provider-change').onclick=()=>showConnection(true);el('provider-disconnect').onclick=async()=>{try{await api('/api/providers/disconnect',{method:'POST',body:'{}'});bootstrap.connection={connected:false,name:'Mode local · IA facultative'};updateProfileDisplay();activate();}catch(error){message(error.message,true);}};
    el('save-source-boards').onclick=async()=>{try{const boards=el('source-boards').value.split('\n').map(value=>value.trim()).filter(Boolean);await api('/api/sources',{method:'PUT',body:JSON.stringify({boards})});message('Sources enregistrées. La prochaine recherche les consultera.');}catch(error){message(error.message,true);}};
    el('save-daily-limit').onclick=async()=>{try{await api('/api/usage',{method:'PUT',body:JSON.stringify({limit:Number(el('daily-limit').value)})});await loadUsage();message('Limite quotidienne enregistrée.');}catch(error){message(error.message,true);}};
    el('chat-form').onsubmit=sendChat;['first-search','search-offers','refresh-offers'].forEach(id=>el(id).onclick=search);
    el('recommendations-list').onclick=event=>{const button=event.target.closest('[data-interest]');if(button)interest(button);};
    document.addEventListener('click',event=>{const button=event.target.closest('[data-retry-preparation]');if(button){button.dataset.id=button.dataset.retryPreparation;button.dataset.interest='accept';interest(button);}});
  }
  async function boot(){bind();bootstrap=await api('/api/bootstrap');profile=bootstrap.profile||{};if(bootstrap.onboarded){el('welcome').hidden=true;el('workspace-root').hidden=false;return true;}
    const pending=new Promise(resolve=>readyResolve=resolve);if(bootstrap.connection.connected)editProfile();else{showConnection();if(bootstrap.connection.error)gateMessage(bootstrap.connection.error,true);}return pending;}
  window.WorkspaceUI={boot,start,go,openSettings:()=>go('settings-screen'),showConnection,editProfile};
})();
