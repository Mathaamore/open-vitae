(() => {
  const el = id => document.getElementById('assistant-' + id);
  let target, connected = false, generating = false;
  const feedback = (text, error = false) => { el('feedback').textContent = text; el('feedback').hidden = !text; el('feedback').classList.toggle('error', error); };
  const controls = () => {
    el('generate').disabled = !connected || generating || !target;
    el('apply').disabled = generating || !el('proposal').value || !target;
    el('login').disabled = generating;
    el('logout').disabled = generating;
    el('generate').textContent = generating ? t("assistant.writing_a_revision") : t("assistant.suggest_a_revision");
    el('editor').setAttribute('aria-busy', String(generating));
  };
  async function status() {
    try {
      const result = await api('/api/assistant');
      connected = result.connected;
      el('account-title').textContent = connected ? (result.name || 'IA') + ' connected' : t("workspace.ai_not_connected");
      el('status').textContent = connected ? [result.email, result.plan ? 'Plan ' + result.plan : ''].filter(Boolean).join(' · ') : result.error || (result.pending ? t("assistant.finish_signing_in_through_your_browser_then_check") : result.available ? t("assistant.connect_your_ai_to_get_a_suggested_revision") : t("assistant.the_chatgpt_connection_isn_t_available_use_another"));
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
    if (target) { el('original').value = target.original; el('question').textContent = target.field.label || t("app.your_message"); }
    controls(); el('dialog').showModal(); await status();
  }
  el('open').onclick = () => window.WorkspaceUI.openSettings();
  document.addEventListener('click', event => { const button = event.target.closest('[data-assist]'); if (button) show(button.dataset.assist); });
  el('close').onclick = () => el('dialog').close();
  el('refresh').onclick = status;
  el('login').onclick = () => { el('dialog').close(); window.WorkspaceUI.openSettings(); };
  el('logout').onclick = async () => {
    el('logout').disabled = true;
    try { await api('/api/assistant/logout', {method:'POST', body:'{}'}); feedback(t("assistant.ai_disconnected_your_application_materials_are_still_here")); await status(); el('dialog').close(); window.WorkspaceUI.showConnection(); }
    catch (error) { feedback(error.message, true); controls(); }
  };
  el('generate').onclick = async () => {
    if (!target || generating) return;
    if (!target.original.trim()) { feedback(t("assistant.write_a_first_draft_before_requesting_a_revision"), true); return; }
    generating = true; el('proposal').value = ''; el('notes').hidden = true; controls(); feedback(t("assistant.working_on_a_revision_your_current_text_is"));
    try {
      const result = await api('/api/jobs/' + encodeURIComponent(target.job) + '/suggestion', {method:'POST', body:JSON.stringify({field:target.field.key, revision:target.revision, text:target.original, instruction:el('instruction').value})});
      el('proposal').value = result.text; el('notes').textContent = result.notes; el('notes').hidden = !result.notes;
      feedback(t("assistant.revision_ready_check_the_facts_and_tone_before"));
    } catch (error) { feedback(error.message, true); }
    finally { generating = false; controls(); }
  };
  el('apply').onclick = () => {
    if (!target || !el('proposal').value) return;
    if (current?.id !== target.job || current.revision !== target.revision || !target.node.isConnected || target.node.value !== target.original || lockedStatuses.includes(current.status)) {
      feedback(t("assistant.this_answer_has_changed_open_revise_again_from"), true); return;
    }
    if (target.node.maxLength > 0 && el('proposal').value.length > target.node.maxLength) { feedback(t("assistant.the_revision_is_too_long_for_this_field"), true); return; }
    target.node.value = el('proposal').value; target.node.dispatchEvent(new Event('input', {bubbles:true}));
    el('dialog').close(); target.node.focus(); message(t("assistant.revision_added_to_the_editor_review_and_save"));
  };
})();
