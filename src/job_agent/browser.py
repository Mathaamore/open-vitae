"""Read-only DOM inventory for public application forms."""

INVENTORY = r'''() => {
 const nodes = [...document.querySelectorAll('input,textarea,select')].filter(e => !['hidden','submit','button','reset'].includes(e.type));
 const label = e => (e.labels?.length ? [...e.labels].map(l=>l.innerText).join(' ') : e.getAttribute('aria-label') || e.parentElement?.querySelector('label')?.innerText || e.placeholder || e.name || e.id || '').trim();
 const fields=[], groups=new Map();
 nodes.forEach((e,index) => {
   const type=e.tagName.toLowerCase()==='select'?'select':e.type||'textarea';
   const key=(e.name||e.id||type)+'-'+index;
   if (['radio','checkbox'].includes(type) && e.name) {
     const groupKey=type+':'+e.name;
     if(!groups.has(groupKey)) {
       const parent=e.closest('fieldset');
       const f={key:groupKey,label:parent?.querySelector('legend')?.innerText || e.name,type,required:false,options:[]};
       groups.set(groupKey,f); fields.push(f);
     }
     const f=groups.get(groupKey); f.required ||= e.required || /\*\s*$/.test(f.label); const count=f.label.match(/select\s+(\d+)/i); if(count) f.selection_count=Number(count[1]); f.options.push({index,value:e.value==='on'?label(e):e.value,label:label(e)});
   } else {
     fields.push({key,label:label(e),type,index,language:e.closest('[lang]')?.getAttribute('lang') || '',required:e.required || /\*\s*$/.test(label(e)),accept:e.accept||'',
       options:e.tagName==='SELECT'?[...e.options].map(o=>({value:o.value,label:o.text})):[]});
   }
 });
 let appId=null; try{appId=JSON.parse(document.querySelector('#__NEXT_DATA__')?.textContent||'{}').props?.pageProps?.role?.id||null}catch{};
 return {url:location.href, applicationId:appId, fields,
   buttons:[...document.querySelectorAll('button,input[type=submit]')].map((b,index)=>({index,text:(b.innerText||b.value||'').trim(),type:b.type})),
   forms:[...document.forms].map(f=>({action:f.action,method:f.method})),
   customControls:document.querySelectorAll('[role=combobox]:not(select),[role=checkbox]:not(input),[role=radio]:not(input)').length};
}'''
