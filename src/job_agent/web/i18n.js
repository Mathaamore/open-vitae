(() => {
  const english = globalThis.OV_COPY || {};
  const catalogs = {en: english};
  let locale = 'en';
  function t(key, values = {}) {
    const template = catalogs[locale]?.[key] ?? english[key] ?? key;
    return template.replace(/\{([a-zA-Z][a-zA-Z0-9_]*)\}/g, (match, name) => Object.hasOwn(values, name) ? String(values[name]) : match);
  }
  function apply(root = document) {
    root.querySelectorAll('[data-i18n]').forEach(node => {node.textContent = t(node.dataset.i18n);});
    for (const attr of ['placeholder', 'aria-label', 'title', 'alt', 'content']) {
      root.querySelectorAll(`[data-i18n-${attr}]`).forEach(node => node.setAttribute(attr, t(node.getAttribute(`data-i18n-${attr}`))));
    }
  }
  globalThis.t = t;
  globalThis.I18n = {
    get locale() {return locale;},
    register(language, copy) {catalogs[language] = {...copy};},
    setLocale(language) {locale = catalogs[language] ? language : 'en'; if (typeof document !== 'undefined') {document.documentElement.lang = locale; apply();}},
    apply,
  };
  if (typeof document !== 'undefined') apply();
})();
