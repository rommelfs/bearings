'use strict';
(() => {
  document.querySelectorAll('[data-national-panel]').forEach(panel => {
    let controller;
    async function load() {
      if(controller)controller.abort();
      controller=new AbortController();const active=controller;
      const loading=document.createElement('p');loading.textContent='Loading current permitted data…';
      panel.replaceChildren(loading);panel.setAttribute('aria-busy','true');
      const timer=setTimeout(()=>active.abort(),12000);
      try {
        const response=await fetch(panel.dataset.url,{credentials:'same-origin',cache:'no-store',signal:active.signal});
        if(!response.ok||response.redirected)throw Error();
        const html=await response.text();
        if(active!==controller)return;
        // Authenticated, same-origin Django fragment; user-controlled fields are escaped server-side.
        panel.innerHTML=html;
      } catch(error) {
        if(active!==controller)return;
        const message=document.createElement('p');message.textContent='This section could not load in time or is unavailable. Missing results are not zero problems.';
        const retry=document.createElement('button');retry.type='button';retry.textContent='Retry section';retry.addEventListener('click',load);
        panel.replaceChildren(message,retry);
      } finally {clearTimeout(timer);if(active===controller)panel.setAttribute('aria-busy','false');}
    }
    load();
  });
})();
