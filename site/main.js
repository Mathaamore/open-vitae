// Release links are curated after notarization and clean-Mac acceptance, never guessed from /latest.
(async () => {
  try {
    const response = await fetch('release.json');
    if (!response.ok) return;
    const release = await response.json();
    if (release.verified !== true || !/^\d+\.\d+\.\d+$/.test(release.version)) return;
    const url = new URL(release.url);
    if (url.protocol !== 'https:' || url.hostname !== 'github.com' || url.search || url.hash || url.username || url.password || url.port || url.pathname !== `/Mathaamore/open-vitae/releases/download/v${release.version}/Open-vitae-Mac.dmg`) return;
    document.querySelectorAll('[data-download], #release-link').forEach(link => {link.href=url.href;link.textContent=t("release.download",{version:release.version});});
    document.querySelector('.compatibility').textContent=t('release.compatibility');
    document.querySelector('#availability-answer').textContent=t('release.faq',{version:release.version});
    document.querySelector('#release-status').textContent=t("release.available",{version:release.version});
  } catch { /* The development availability message remains usable offline. */ }
})();
if (!matchMedia('(prefers-reduced-motion: reduce)').matches && 'IntersectionObserver' in window) {
  const tagline = document.querySelector('.tagline');
  const words = [];
  const walker=document.createTreeWalker(tagline,NodeFilter.SHOW_TEXT);
  const textNodes=[];while(walker.nextNode())textNodes.push(walker.currentNode);
  for (const child of textNodes) {
    if (child.nodeType !== Node.TEXT_NODE) continue;
    const fragment = document.createDocumentFragment();
    child.textContent.split(/(\s+)/).forEach(word => {
      if (!word.trim()) {fragment.append(word);return;}
      const span=document.createElement('span');span.textContent=word;fragment.append(span);words.push(span);
    });
    child.replaceWith(fragment);
  }
  const observer=new IntersectionObserver(entries => {
    if (!entries.some(entry => entry.isIntersecting)) return;
    words.forEach((word,index)=>setTimeout(()=>word.classList.add('visible'),index*60));
    observer.disconnect();
  },{threshold:.5});
  observer.observe(tagline);
}
