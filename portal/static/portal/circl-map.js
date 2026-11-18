/* Local-only map rendering. Company/source permission checks remain server-side. */
(() => {
  'use strict';
  const colors = {critical:'#b91446',high:'#c65316',medium:'#bf8a00',low:'#287fb0',unrated:'#775da2',no_open:'#647880'};
  const names = {critical:'Critical',high:'High',medium:'Medium / Review',low:'Low',unrated:'Unrated / informational',no_open:'No open problems recorded'};
  function element(tag,text) { const e=document.createElement(tag); if(text!==undefined)e.textContent=text; return e; }
  function link(text,url) { const a=element('a',text); a.href=url; return a; }
  function setupMap(container) {
    const map=L.map(container,{preferCanvas:true,scrollWheelZoom:false}).fitBounds([[49.44,5.73],[50.18,6.54]]);
    L.control.scale({imperial:false}).addTo(map);
    [[49.611,6.131,'Luxembourg'],[49.495,5.985,'Esch-sur-Alzette'],[49.867,6.159,'Diekirch'],[49.965,5.933,'Wiltz'],[50.055,6.031,'Clervaux']].forEach(([lat,lon,name])=>{
      L.marker([lat,lon],{interactive:false,keyboard:false,icon:L.divIcon({className:'map-place-label',html:element('span',name),iconSize:[110,18]})}).addTo(map);
    });
    function labels(){container.classList.toggle('map-hide-labels',map.getZoom()<8);}
    map.on('zoomend',labels);labels();
    map.attributionControl.setPrefix('Leaflet');
    fetch(container.dataset.outline || container.closest('[data-outline]').dataset.outline,{credentials:'same-origin'})
      .then(r=>{if(!r.ok)throw Error();return r.json();})
      .then(data=>L.geoJSON(data,{interactive:false,style:f=>({color:'#7f9398',weight:1,fillColor:f.properties.code==='LUX'?'#fbfaf1':'#e5e9df',fillOpacity:1})}).addTo(map).bringToBack())
      .catch(()=>{ const notice=element('p','Country outlines unavailable; company points still work.');container.after(notice); });
    return map;
  }
  const editor=document.querySelector('[data-location-editor]');
  if(editor && window.L) {
    const map=setupMap(editor), lat=document.querySelector('#id_latitude'),lon=document.querySelector('#id_longitude');
    let marker;
    function position(fit=false) {
      if(marker)map.removeLayer(marker);
      if(!lat.value.trim() || !lon.value.trim())return;
      const a=Number(lat.value),o=Number(lon.value);
      if(!Number.isFinite(a)||!Number.isFinite(o)||Math.abs(a)>90||Math.abs(o)>180)return;
      marker=L.circleMarker([a,o],{radius:9,color:'#172e45',fillColor:'#18716d',fillOpacity:1}).addTo(map);
      if(fit)map.setView([a,o],10);
    }
    map.on('click',event=>{lat.value=event.latlng.lat.toFixed(6);lon.value=event.latlng.lng.toFixed(6);position();});
    lat.addEventListener('change',()=>position(true));lon.addEventListener('change',()=>position(true));position(true);
  }
  const root=document.querySelector('[data-company-map]');
  if(!root)return;
  const status=root.querySelector('[data-map-status]');
  if(!window.L) { status.textContent='Map renderer unavailable. Use the company and problem lists.';return; }
  const map=setupMap(root.querySelector('[data-map-canvas]'));
  map.createPane('companyPoints').style.zIndex='450';
  const pointRenderer=L.canvas({pane:'companyPoints'});
  let markers=L.featureGroup().addTo(map),heat=null,payload=null,page=0,controller;
  const table=root.querySelector('[data-map-table]'),unlocated=root.querySelector('[data-map-unlocated]');
  function companyContent(point) {
    const box=element('div');box.append(link(point.name,point.company_url),element('p',names[point.level]));
    const problems=element('p');
    if(point.reviews)problems.append(link(point.reviews+' outstanding CVE reviews',point.reviews_url));
    if(point.reviews&&point.issues)problems.append(element('br'));
    if(point.issues)problems.append(link(point.issues+' other outstanding issues',point.issues_url));
    if(!point.reviews&&!point.issues)problems.append(element('span','No open problems recorded; coverage may be incomplete.'));
    box.append(problems,element('p',point.label));
    if(point.location_url)box.append(link('Position / correct company point →',point.location_url));
    return box;
  }
  function matching() {
    if(!payload)return [];
    const level=root.querySelector('[data-map-level]').value;
    const query=root.querySelector('[data-map-search]').value.toLocaleLowerCase();
    return payload.points.filter(p=>(level==='all'||p.level===level)&&p.name.toLocaleLowerCase().includes(query));
  }
  function renderTable(points) {
    table.replaceChildren();
    const pages=Math.max(1,Math.ceil(points.length/50));page=Math.min(page,pages-1);
    points.slice(page*50,page*50+50).forEach(p=>{
      const tr=element('tr'),company=element('td'),problems=element('td');company.append(link(p.name,p.company_url));
      const content=companyContent(p);problems.append(content.children[2]);
      tr.append(company,element('td',p.label),element('td',names[p.level]),problems);table.append(tr);
    });
    if(!points.length){const tr=element('tr'),td=element('td','No located companies match. Check unlocated companies below.');td.colSpan=4;tr.append(td);table.append(tr);}
    root.querySelector('[data-map-page]').textContent=`Page ${page+1} / ${pages} · ${points.length} companies`;
    root.querySelector('[data-map-previous]').disabled=page===0;
    root.querySelector('[data-map-next]').disabled=page>=pages-1;
  }
  function draw(fit=false) {
    markers.clearLayers();if(heat){map.removeLayer(heat);heat=null;}
    if(!payload)return;
    const points=matching(),groups=new Map();
    points.forEach(p=>{const key=p.lat.toFixed(4)+','+p.lon.toFixed(4);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(p);});
    groups.forEach(group=>{
      const worst=group.reduce((a,b)=>a.rank>=b.rank?a:b);
      const marker=L.circleMarker([worst.lat,worst.lon],{pane:'companyPoints',renderer:pointRenderer,radius:Math.min(18,7+Math.log2(group.length)*3),color:'#233c4a',weight:1.5,fillColor:colors[worst.level],fillOpacity:.88});
      marker.bindTooltip(element('span',`${group.length} ${group.length===1?'company':'companies'} · ${names[worst.level]}`));
      marker.bindPopup(()=>{
        const box=element('div');
        if(group.length>1)box.append(element('strong',group.length+' companies at this approximate point'));
        group.slice(0,30).forEach(p=>{box.append(companyContent(p),element('hr'));});
        if(group.length>30)box.append(element('p','First 30 shown. Use the searchable company table for every loaded company.'));
        return box;
      });marker.addTo(markers);
    });
    if(root.querySelector('[data-map-mode]').value==='heat'&&L.heatLayer) {
      const weighted=points.filter(p=>p.rank>0).map(p=>[p.lat,p.lon,Math.min(20,p.reviews+p.issues)*p.rank]);
      const peak=Math.max(1,...weighted.map(p=>p[2]));
      heat=L.heatLayer(weighted.map(p=>[p[0],p[1],p[2]/peak]),{radius:30,blur:22,max:1,maxZoom:8,minOpacity:.08}).addTo(map);
      heat._canvas.style.pointerEvents='none';
      markers.bringToFront();
    }
    if(fit&&points.length)map.fitBounds(markers.getBounds().pad(.15),{maxZoom:12});
    const s=payload.summary;
    status.textContent=`${s.shown} of ${s.located} located companies loaded · ${s.unlocated} unlocated (${s.missing_address} without an address; ${s.unlocated_with_problems} with open problems) · ${s.companies} permitted companies. ${points.length} match the filters.`;
    if(s.omitted)status.textContent+=` Limit ${payload.limit}: the highest-priority companies are shown; ${s.omitted} additional located companies are not shown.`;
    if(s.stale_manual)status.textContent+=` ${s.stale_manual} manual points invalidated by address changes; local lookup is used where available.`;
    renderTable(points);
  }
  async function load() {
    if(controller)controller.abort();controller=new AbortController();
    const active=controller;
    markers.clearLayers();if(heat){map.removeLayer(heat);heat=null;}payload=null;table.replaceChildren();unlocated.replaceChildren();
    status.textContent='Loading current permitted company locations…';
    root.querySelector('[data-map-page]').textContent='';
    root.querySelector('[data-map-previous]').disabled=true;root.querySelector('[data-map-next]').disabled=true;
    const timer=setTimeout(()=>active.abort(),15000);
    try {
      const response=await fetch(root.dataset.url,{credentials:'same-origin',cache:'no-store',signal:active.signal});
      if(!response.ok||response.redirected)throw Error();
      const data=await response.json();if(active!==controller)return;payload=data;
      payload.unlocated.forEach(p=>{const li=element('li');li.append(link(p.name,p.company_url),' · '+names[p.level]+' · '+(p.reviews+p.issues)+' open');if(p.location_url)li.append(' · ',link('Set company point',p.location_url));unlocated.append(li);});
      if(!payload.unlocated.length)unlocated.append(element('li','No unlocated companies.'));
      draw(true);
    } catch(error) {
      if(active===controller)status.textContent='Map data unavailable. Check your session and retry Refresh map; company/problem lists remain available.';
    } finally {clearTimeout(timer);}
  }
  root.querySelector('[data-map-reload]').addEventListener('click',load);
  root.querySelector('[data-map-fit]').addEventListener('click',()=>draw(true));
  root.querySelector('[data-map-mode]').addEventListener('change',()=>draw());
  root.querySelector('[data-map-level]').addEventListener('change',()=>{page=0;draw();});
  root.querySelector('[data-map-search]').addEventListener('input',()=>{page=0;draw();});
  root.querySelector('[data-map-previous]').addEventListener('click',()=>{page--;renderTable(matching());});
  root.querySelector('[data-map-next]').addEventListener('click',()=>{page++;renderTable(matching());});
  load();
})();
