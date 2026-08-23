(function(){
  const supported=['zh-CN','en-US','de-DE','ja-JP'];
  let locale=localStorage.getItem('isi.locale')||'zh-CN', pack={phrases:{}};
  const source = new WeakMap();
  function exactText(text){return String(text||'').trim();}
  function translateTextNode(n){
    if(!n || n.nodeType!==3) return;
    const original=source.get(n)||exactText(n.nodeValue);
    if(!original) return;
    if(!source.has(n)) source.set(n,original);
    const phrases=pack.phrases||{}; let translated=phrases[original]; if(!translated){const keys=Object.keys(phrases).sort((a,b)=>b.length-a.length); const key=keys.find(k=>original.endsWith(k)); translated=key ? original.slice(0,original.length-key.length)+phrases[key] : original;}
    const lead=(n.nodeValue.match(/^\s*/)||[''])[0], tail=(n.nodeValue.match(/\s*$/)||[''])[0];
    n.nodeValue=lead+translated+tail;
  }
  function walk(root){
    if(!root) return;
    const w=document.createTreeWalker(root,NodeFilter.SHOW_TEXT); let n; while(n=w.nextNode()) translateTextNode(n);
    root.querySelectorAll?.('[placeholder]').forEach(el=>{ if(!el.dataset.i18nPlaceholder) el.dataset.i18nPlaceholder=el.getAttribute('placeholder')||''; const s=el.dataset.i18nPlaceholder; el.placeholder=(pack.phrases||{})[s]||s; });
  }
  async function load(next){
    locale=supported.includes(next)?next:'zh-CN';
    try{pack=await fetch('/static/i18n/'+locale+'.json',{cache:'no-store'}).then(r=>r.json());}catch(e){pack={phrases:{}};}
    document.documentElement.lang=locale; localStorage.setItem('isi.locale',locale); walk(document.body);
    document.dispatchEvent(new CustomEvent('isi:locale',{detail:{locale}}));
  }
  const observer=new MutationObserver(ms=>ms.forEach(m=>m.addedNodes.forEach(n=>{if(n.nodeType===3)translateTextNode(n); else if(n.nodeType===1)walk(n);}))); 
  document.addEventListener('DOMContentLoaded',()=>{observer.observe(document.body,{childList:true,subtree:true});load(locale);const sel=document.getElementById('language-selector');if(sel){sel.value=locale;sel.addEventListener('change',e=>load(e.target.value));}});
  window.ISII18N={setLocale:load,getLocale:()=>locale,t:(s)=>(pack.phrases||{})[s]||s,supported};
})();
