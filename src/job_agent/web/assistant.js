(() => {
  const el = id => document.getElementById('assistant-' + id);
  let target, connected = false, generating = false;
  const feedback = (text, error = false) => { el('feedback').textContent = text; el('feedback').hidden = !text; el('feedback').classList.toggle('error', error); };
  const controls = () => {
    el('generate').disabled = !connected || generating || !target;
    el('apply').disabled = generating || !el('proposal').value || !target;
    el('login').disabled = generating;
    el('logout').disabled = generating;
    el('generate').textContent = generating ? 'Proposition en cours…' : 'Proposer une reformulation';
    el('editor').setAttribute('aria-busy', String(generating));
  };
  async function status() {
    try {
      const result = await api('/api/assistant');
      connected = result.connected;
      el('account-title').textContent = connected ? (result.name || 'IA') + ' connecté' : 'Fournisseur déconnecté';
      el('status').textContent = connected ? [result.email, result.plan ? 'Plan ' + result.plan : ''].filter(Boolean).join(' · ') : result.error || (result.pending ? 'Termine la connexion dans ton navigateur, puis vérifie ici.' : result.available ? 'Connecte-toi pour travailler tes textes avec ton compte.' : 'Codex est indisponible. La version Mac inclut le service nécessaire.');
      el('login').hidden = connected || !result.available || result.pending;
      el('logout').hidden = !connected && !result.pending;
      el('refresh').hidden = !result.pending;
      if (connected || !result.pending) el('auth-link').hidden = true;
    } catch (error) { feedback(error.message, true); }
    controls();
  }
  async function show(fieldKey) {
    if (generating) { el('dialog').showModal(); return; }
    feedback(''); el('proposal').value = ''; el('instruction').value = ''; el('notes').hidden = true; target = null;
    if (fieldKey && current?.dossier && !lockedStatuses.includes(current.status)) {
      const node = [...document.querySelectorAll('textarea[data-answer]')].find(node => node.dataset.answer === fieldKey);
      const field = current.dossier.form.fields.find(field => field.key === fieldKey);
      if (node && field) target = {node, field, job: current.id, revision: current.revision, original: node.value};
    }
    el('editor').hidden = !target; el('empty').hidden = Boolean(target);
    if (target) { el('original').value = target.original; el('question').textContent = target.field.label || 'Ton message'; }
    controls(); el('dialog').showModal(); await status();
  }
  el('open').onclick = () => window.WorkspaceUI.openSettings();
  document.addEventListener('click', event => { const button = event.target.closest('[data-assist]'); if (button) show(button.dataset.assist); });
  el('close').onclick = () => el('dialog').close();
  el('refresh').onclick = status;
  el('login').onclick = () => { el('dialog').close(); window.WorkspaceUI.openSettings(); };
  el('logout').onclick = async () => {
    el('logout').disabled = true;
    try { await api('/api/assistant/logout', {method:'POST', body:'{}'}); feedback('Ton compte a été déconnecté d’Open Vitæ.'); await status(); el('dialog').close(); window.WorkspaceUI.showConnection(); }
    catch (error) { feedback(error.message, true); controls(); }
  };
  el('generate').onclick = async () => {
    if (!target || generating) return;
    if (!target.original.trim()) { feedback('Écris une première version avant de demander une reformulation.', true); return; }
    generating = true; el('proposal').value = ''; el('notes').hidden = true; controls(); feedback('Ton IA travaille sur ton texte. La réponse peut prendre une à deux minutes.');
    try {
      const result = await api('/api/jobs/' + encodeURIComponent(target.job) + '/suggestion', {method:'POST', body:JSON.stringify({field:target.field.key, revision:target.revision, text:target.original, instruction:el('instruction').value})});
      el('proposal').value = result.text; el('notes').textContent = result.notes; el('notes').hidden = !result.notes;
      feedback('Proposition prête. Vérifie les faits et le ton avant de l’utiliser.');
    } catch (error) { feedback(error.message, true); }
    finally { generating = false; controls(); }
  };
  el('apply').onclick = () => {
    if (!target || !el('proposal').value) return;
    if (current?.id !== target.job || current.revision !== target.revision || !target.node.isConnected || target.node.value !== target.original || lockedStatuses.includes(current.status)) {
      feedback('Le dossier ou le texte a changé. Rouvre l’assistant depuis la réponse à jour.', true); return;
    }
    if (target.node.maxLength > 0 && el('proposal').value.length > target.node.maxLength) { feedback('Cette proposition dépasse la limite du champ. Demande une version plus courte.', true); return; }
    target.node.value = el('proposal').value; target.node.dispatchEvent(new Event('input', {bubbles:true}));
    el('dialog').close(); target.node.focus(); message('Proposition insérée. Relis-la, puis enregistre tes réponses.');
  };
})();
