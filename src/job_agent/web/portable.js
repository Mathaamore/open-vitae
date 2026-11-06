(() => {
  const el=id=>document.getElementById(id);
  let editing=null, expectedUpdate=null, reviewed=null, generated=null;
  const status=(text,error=false)=>{el('portable-status').textContent=text;el('portable-status').classList.toggle('error',error);};
  function download(name,content,type='application/json') {
    const url=URL.createObjectURL(new Blob([content],{type}));
    const link=document.createElement('a');link.href=url;link.download=name;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function refresh() {
    const selected=el('portable-job').value;
    el('portable-job').replaceChildren();
    for(const job of jobs){const option=document.createElement('option');option.value=job.id;option.textContent=job.company+' · '+job.role;el('portable-job').append(option);}
    if(jobs.some(job=>job.id===selected))el('portable-job').value=selected;
    const kind=el('portable-kind').value;
    el('local-draft-details').hidden=kind!=='application_draft';
    el('portable-job-label').hidden=!['job_analysis','application_draft'].includes(kind);
    el('local-draft').disabled=!el('portable-job').value;
  }
  async function enter() {
    refresh();
    try{const state=await api('/api/bootstrap');if(!el('local-summary').value)el('local-summary').value=state.profile?.bio||'';el('portable-notes').textContent=state.profile_analysis?JSON.stringify(state.profile_analysis,null,2):'Aucune analyse importée. Ton profil reste utilisable sans IA.';}catch(error){status(error.message,true);}
  }
  function openTools(kind='profile_analysis',jobId=null) {
    if(!window.WorkspaceUI.go('tools-screen'))return;
    el('portable-kind').value=kind;refresh();if(jobId)el('portable-job').value=jobId;
  }
  async function manual(identity=null) {
    if(dirty){message('Enregistre ou annule le dossier avant de modifier cette offre.',true);return;}
    const form=el('manual-job-form');form.reset();editing=identity;expectedUpdate=null;
    el('manual-title').textContent=identity?'Modifier cette offre':'Ajouter une offre';el('manual-status').textContent='';
    if(identity){const job=await api('/api/jobs/'+encodeURIComponent(identity));expectedUpdate=job.updated_at;for(const field of form.elements)if(field.name)field.value=job[field.name]??job.audit[field.name]??'';}
    el('manual-job-dialog').showModal();
  }
  async function loadFile(file) {
    if(!file)return;
    reviewed=null;el('portable-apply').disabled=true;
    if(file.size>1000000){status('Le fichier JSON doit faire au maximum 1 Mo.',true);return;}
    el('portable-input').value=await file.text();status('Fichier chargé. Vérifie et prévisualise son contenu avant de confirmer.');
  }
  el('add-job').onclick=()=>manual().catch(error=>message(error.message,true));
  el('manual-close').onclick=()=>el('manual-job-dialog').close();
  el('manual-job-form').onsubmit=async event=>{
    event.preventDefault();el('manual-save').disabled=true;
    const value=Object.fromEntries(new FormData(el('manual-job-form')));if(editing)value.updated_at=expectedUpdate;
    try{const result=await api(editing?'/api/opportunities/'+encodeURIComponent(editing):'/api/opportunities',{method:editing?'PUT':'POST',body:JSON.stringify(value)});el('manual-job-dialog').close();await refreshJobs();window.WorkspaceUI.go('dashboard');await window.open(result.id);message(result.duplicate?'Cette offre existe déjà. Sa fiche a été conservée.':'Offre enregistrée localement. Aucun appel IA ni envoi.');}
    catch(error){el('manual-status').textContent=error.message;}
    finally{el('manual-save').disabled=false;}
  };
  el('manual-retrieve').onclick=async()=>{
    el('manual-retrieve').disabled=true;el('manual-status').textContent='Lecture de la fiche publique…';
    try{const form=el('manual-job-form');const result=await api('/api/opportunities/retrieve',{method:'POST',body:JSON.stringify({url:form.elements.namedItem('url').value})});for(const [key,value] of Object.entries(result))if(value&&form.elements.namedItem(key))form.elements.namedItem(key).value=value;el('manual-status').textContent='Métadonnées lues, à vérifier. Confirme leur enregistrement après relecture.';}
    catch(error){el('manual-status').textContent=error.message+' Tu peux conserver l’URL ou coller le texte.';}
    finally{el('manual-retrieve').disabled=false;}
  };
  el('portable-connect').onclick=()=>window.WorkspaceUI.showConnection(true);
  el('assistant-portable').onclick=()=>{el('assistant-dialog').close();openTools('application_draft',current?.id);};
  el('portable-kind').onchange=()=>{generated=null;el('portable-prompt').value='';refresh();};
  el('portable-job').onchange=()=>{generated=null;};
  el('portable-generate').onclick=async()=>{try{generated=await api('/api/portable/prompt',{method:'POST',body:JSON.stringify({type:el('portable-kind').value,job_id:el('portable-job').value||undefined})});el('portable-prompt').value=generated.prompt;status('Prompt créé sur ce Mac. Relis les données personnelles avant de le partager.');}catch(error){status(error.message,true);}};
  el('portable-copy').onclick=async()=>{if(!el('portable-prompt').value){status('Crée d’abord un prompt.',true);return;}try{await copyText(el('portable-prompt').value,'Prompt copié. Son partage vers un service externe reste ton choix.');}catch(error){status(error.message,true);}};
  el('portable-example').onclick=()=>{if(!generated){status('Crée d’abord le prompt pour inclure le contexte actuel.',true);return;}download('open-vitae-example.json',JSON.stringify(generated.example,null,2));};
  el('portable-schema').onclick=async()=>{try{download('open-vitae-schema-v1.json',JSON.stringify(await api('/api/portable/schema'),null,2));}catch(error){status(error.message,true);}};
  el('portable-file').onchange=()=>loadFile(el('portable-file').files[0]).catch(error=>status(error.message,true));
  el('portable-drop').ondragover=event=>{event.preventDefault();el('portable-drop').classList.add('drag-over');};
  el('portable-drop').ondragleave=()=>el('portable-drop').classList.remove('drag-over');
  el('portable-drop').ondrop=event=>{event.preventDefault();el('portable-drop').classList.remove('drag-over');loadFile(event.dataTransfer.files[0]).catch(error=>status(error.message,true));};
  el('portable-input').oninput=()=>{reviewed=null;el('portable-apply').disabled=true;};
  el('portable-preview').onclick=async()=>{
    reviewed=null;el('portable-apply').disabled=true;
    try{const result=await api('/api/portable/preview',{method:'POST',body:el('portable-input').value});reviewed=result.artifact;el('portable-result').textContent=JSON.stringify(reviewed,null,2);el('portable-apply').disabled=false;status(result.warning+(result.duplicates.length?' '+result.duplicates.length+' doublon(s) seront conservés sans remplacement.':''));}
    catch(error){el('portable-result').textContent='';status(error.message,true);}
  };
  el('portable-apply').onclick=async()=>{
    if(!reviewed)return;el('portable-apply').disabled=true;
    try{const result=await api('/api/portable/import',{method:'POST',body:JSON.stringify(reviewed)});reviewed=null;await refreshJobs();status('Import confirmé. Le contenu reste à relire ; aucun fait du profil ni envoi n’a été validé automatiquement.');if(result.imported==='profile_analysis')el('portable-notes').textContent=JSON.stringify(result.data,null,2);if(result.jobs)refresh();}
    catch(error){reviewed=null;status(error.message,true);}
  };
  el('local-draft').onclick=async()=>{
    el('local-draft').disabled=true;
    try{const identity=el('portable-job').value;const job=await api('/api/jobs/'+encodeURIComponent(identity));await api('/api/opportunities/'+encodeURIComponent(identity)+'/draft',{method:'POST',body:JSON.stringify({revision:job.revision,updated_at:job.updated_at,summary:el('local-summary').value,motivation:el('local-motivation').value})});await refreshJobs();window.WorkspaceUI.go('dashboard');await window.open(identity);message('Nouvelle version locale créée. Relis les faits et complète les questions employeur.');}
    catch(error){status(error.message,true);}finally{el('local-draft').disabled=false;}
  };
  el('export-data').onclick=async()=>{try{download('open-vitae-export.json',JSON.stringify(await api('/api/export'),null,2));}catch(error){status(error.message,true);}};
  el('backup-data').onclick=async()=>{
    el('backup-data').disabled=true;
    try{const response=await fetch('/api/backup',{method:'POST',headers:{'X-Local-Token':token}});if(!response.ok)throw Error((await response.json()).error||'Sauvegarde impossible.');download('open-vitae-backup.zip',await response.blob(),'application/zip');status('Sauvegarde privée créée. Elle contient tes données personnelles, sans identifiants IA.');}
    catch(error){status(error.message,true);}finally{el('backup-data').disabled=false;}
  };
  document.addEventListener('click',event=>{const edit=event.target.closest('[data-edit-opportunity]');const tools=event.target.closest('[data-local-tools]');if(edit)manual(edit.dataset.editOpportunity).catch(error=>message(error.message,true));if(tools)openTools('application_draft',tools.dataset.localTools);});
  window.LocalTools={open:openTools,refresh,enter};
})();
