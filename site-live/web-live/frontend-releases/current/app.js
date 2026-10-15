const $ = id => document.getElementById(id);
const state = { config:null,csrf:null,email:null,signed:false,selected:null,mode:'result',poll:null,seq:0,sending:false,uploads:[],prefs:{theme:'dark',density:'comfortable',scale:1} };
const TERMINAL = new Set(['result_received','failed','blocked','blocked_runtime','interrupted_requires_reconcile','cancelled']);
const STATES = {awaiting_kelion:'În coadă',running_magistrala:'În execuție',result_received:'Rezultat primit',blocked:'Blocat',failed:'Eșuat',blocked_runtime:'Blocat',interrupted_requires_reconcile:'Necesită reconciliere',cancelled:'Anulat'};
const STEP = {running:'În lucru',completed:'Finalizat',failed:'Eșuat',unavailable:'Indisponibil',insufficient:'Insuficient'};
const idValid = x => /^web-[a-f0-9]{32}$/.test(String(x||''));
const attachValid = x => /^att-[a-f0-9]{32}$/.test(String(x||''));
const t = (id,text)=>{$(id).textContent=String(text ?? '');};
function message(s='',tone=''){t('message',s);$('message').dataset.tone=tone;}
function connection(label,kind='') {t('connection-text',label);$('connection').dataset.status=kind;}
async function api(path,data,extra={}) {
 const post=data!==undefined;
 let result,response;
 try{response=await fetch(path,{method:post?'POST':'GET',credentials:'same-origin',redirect:'error',headers:{...(post?{'Content-Type':'application/json'}:{}),...(state.csrf&&post?{'X-CSRF-Token':state.csrf}:{})},...(post?{body:JSON.stringify(data)}:{}),...extra});}
 catch{throw Error('Serverul nu poate fi contactat.');}
 try{result=await response.json();}catch{throw Error('Răspuns invalid al serviciului Kelion.');}
 if(!response.ok){let error=Error(result.error||'Cererea a eșuat ('+response.status+').');error.status=response.status;error.task_id=result.task_id;throw error;}
 return result;
}
function setEnabled(){
 const can=state.signed&&!state.sending;
 $('task').disabled=!can;
 $('send').disabled=!can||!$('task').value.trim();
 $('attach').disabled=!can;
 $('location').disabled=!can||!navigator.geolocation;
 $('call').disabled=true;
 $('camera').disabled=true;
 $('copy').disabled=!(state.selected&&typeof state.selected.output==='string'&&state.selected.output);
}
function signOut(reason=''){
 state.signed=false;state.csrf=null;state.email=null;
 state.selected=null;stopPoll();$('login').hidden=false;$('account').hidden=true;
 connection('Neconectat');setEnabled();renderTask();
 if(reason)message(reason,'error');
}
async function signedIn(data) {
 if(typeof data.email!=='string'||!data.csrf)throw Error('Sesiunea este incompletă.');
 state.signed=true;state.email=data.email;state.csrf=data.csrf;
 $('login').hidden=true;$('account').hidden=false;$('account').textContent=data.email.slice(0,2).toUpperCase();
 connection('Sesiune conectată','ready');setEnabled();message('');
 closeDrawer();await loadHistory(false).catch(e=>message('Istoric indisponibil: '+e.message,'error'));
}
async function googleLogin(){
 if(!state.config?.ready||!state.config?.clientId){message('Autentificarea Google nu este configurată.','error');return;}
 $('login').disabled=true;
 try{
  const {nonce}=await api('/auth/nonce',{});
  if(!nonce)throw Error('Nonce Google indisponibil.');
  if(!window.google?.accounts?.id)await new Promise((resolve,reject)=>{
   const script=document.createElement('script');script.src='https://accounts.google.com/gsi/client';
   script.onload=resolve;script.onerror=()=>reject(Error('Nu s-a încărcat serviciul Google.'));document.head.append(script);
  });
  openDrawer('Autentificare','Acces securizat');
  const parent=$('drawer-body');parent.replaceChildren();
  const title=el('p','Selectează contul Google autorizat pentru accesul la Kelion.');parent.append(title);
  const target=$('google');target.hidden=false;target.replaceChildren();parent.append(target);
  window.google.accounts.id.initialize({client_id:state.config.clientId,nonce,ux_mode:'popup',auto_select:false,
   callback:async response=>{try{await signedIn(await api('/auth/google',{credential:response.credential}));}catch(e){message(e.message,'error');}}});
  window.google.accounts.id.renderButton(target,{type:'standard',theme:'outline',size:'large',text:'signin_with'});
  message('Alege contul Google autorizat.');
 }catch(e){message(e.message,'error');}finally{$('login').disabled=false;}
}
function stopPoll(){state.seq++;if(state.poll)clearTimeout(state.poll);state.poll=null;}
function progressLine(step){
 const li=document.createElement('li');
 const label=[step.profile||step.surface||'Serviciu',STEP[step.status]||step.status||'Eveniment'].filter(Boolean).join(' · ');
 li.textContent=label;
 const small=document.createElement('small');
 small.textContent=[step.detail||step.reason||'',Number.isFinite(step.duration_ms)?step.duration_ms+' ms':''].filter(Boolean).join(' · ').slice(0,600);
 li.append(small);return li;
}
function renderTask(){
 const task=state.selected,empty=$('empty-artifact'),output=$('output'),events=$('progress'),warning=$('result-warning');
 output.hidden=true;events.hidden=true;warning.hidden=true;empty.hidden=true;
 t('task-id',task?.task_id?.slice(0,14)||'');
 t('task-state',task?STATES[task.state]||task.state||'Necunoscut':'Nicio lucrare');
 $('task-state').dataset.state=task?.state==='result_received'?'completed':task?.state==='failed'?'failed':'';
 const when=task?.created||0;t('result-time',when?new Date((when<1e11?when*1000:when)).toLocaleString('ro-RO'):'');
 if(!task){empty.hidden=false;t('monitor-caption','Rezultate și artefacte reale');setEnabled();return;}
 t('monitor-caption',state.mode==='activity'?'Pași confirmați de magistrală':'Rezultatul cererii selectate');
 if(state.mode==='activity'){
  events.replaceChildren();
  for(const step of Array.isArray(task.progress)?task.progress:[])if(step&&typeof step==='object')events.append(progressLine(step));
  if(events.childElementCount){events.hidden=false;}else{empty.hidden=false;empty.querySelector('h2').textContent='Fără evenimente raportate';empty.querySelector('p').textContent='Serverul nu a transmis încă activitate pentru această cerere.';}
 }else if(typeof task.output==='string'&&task.output.trim()&&task.result_retrieved===true){
  output.textContent=task.output;output.hidden=false;
 }else{empty.hidden=false;empty.querySelector('h2').textContent='Se așteaptă un rezultat';empty.querySelector('p').textContent='Nu există încă un artefact sau rezultat returnat de backend.';}
 const problem=task.failure||task.block_reason;
 if(problem){warning.textContent=String(problem).slice(0,1000);warning.hidden=false;}
 if(task.result_retrieved && !task.verified && !warning.hidden){} // provenance is shown through the backend receipt, never invented
 setEnabled();
}
async function chooseTask(id){
 if(!idValid(id))throw Error('Identificatorul cererii este invalid.');
 stopPoll();const turn=state.seq;
 const data=await api('/api/tasks/'+id);
 if(data.task_id!==id||turn!==state.seq)return;
 state.selected=data;renderTask();closeDrawer();
 if(!TERMINAL.has(data.state))pollTask(id,turn);
}
function pollTask(id,turn){
 if(turn!==state.seq)return;
 state.poll=setTimeout(async()=>{if(turn!==state.seq)return;
  try{
   const data=await api('/api/tasks/'+id);
   if(turn!==state.seq)return;
   if(data.task_id!==id)throw Error('Identificatorul răspunsului nu corespunde.');
   state.selected=data;renderTask();
   if(!TERMINAL.has(data.state))pollTask(id,turn);
   else loadHistory(false).catch(()=>{});
  }catch(e){if(e.status===401){signOut('Sesiunea a expirat.');return;}message(e.message,'error');}
 },3500);
}
let savedHistory=[];
async function loadHistory(open=true){
 if(!state.signed){if(open)openPanel('history');return;}
 const result=await api('/api/tasks');if(!Array.isArray(result.tasks))throw Error('Format invalid pentru istoric.');
 savedHistory=result.tasks.filter(x=>x&&idValid(x.task_id));
 if(open)openPanel('history');
}
function el(tag,value,classes=''){const n=document.createElement(tag);if(value!==undefined)n.textContent=value;if(classes)n.className=classes;return n;}
function drawerCard(title,body,action){
 const card=el('div','','drawer-card');card.append(el('h3',title),el('p',body));
 if(action){const b=el('button',action.label);b.type='button';b.onclick=action.onClick;card.append(b);}return card;
}
function openDrawer(title,kicker='KELION'){t('drawer-title',title);t('drawer-kicker',kicker);$('drawer').hidden=false;$('backdrop').hidden=false;$('drawer-close').focus();}
function closeDrawer(){$('drawer').hidden=true;$('backdrop').hidden=true;document.querySelectorAll('[data-panel]').forEach(n=>n.classList.toggle('chosen',n.dataset.panel==='home'));}
function openPanel(name){
 if(name==='home'){closeDrawer();return;}
 const titles={history:'Istoric de lucru',files:'Fișiere',agents:'Agenți DOTS',capabilities:'Capabilități',settings:'Preferințe',privacy:'Date și confidențialitate',account:'Cont'};
 openDrawer(titles[name]||'Kelion','KELION / '+name.toUpperCase());
 document.querySelectorAll('[data-panel]').forEach(n=>n.classList.toggle('chosen',n.dataset.panel===name));
 const panel=$('drawer-body');panel.replaceChildren();
 if(name==='history'){
  const r=el('button','Reîncarcă istoricul','drawer-action');r.onclick=()=>loadHistory(true).catch(e=>message(e.message,'error'));panel.append(r);
  if(!state.signed){panel.append(drawerCard('Acces necesar','Istoricul este disponibil după autentificarea Google.'));return;}
  if(!savedHistory.length){panel.append(drawerCard('Istoric gol','Nu există cereri vizibile în istoricul acestui cont.'));return;}
  const list=el('div','','drawer-list');
  for(const item of savedHistory){
   const b=el('button',item.task_id.slice(0,18));b.type='button';
   b.append(el('span',new Date(item.created).toLocaleString('ro-RO')+' · '+(item.delivery||'Înregistrat')));
   b.onclick=()=>chooseTask(item.task_id).catch(e=>message(e.message,'error'));list.append(b);
  }panel.append(list);
 }else if(name==='files'){
  panel.append(drawerCard('Fișiere stocate','Backendul permite încărcare în fragmente de 2 MiB, în limita de 512 MiB. Stocarea nu înseamnă analiză AI.'));
  if(!state.uploads.length){panel.append(drawerCard('Nicio încărcare în această sesiune','Lista completă a fișierelor nu este expusă prin API.'));return;}
  for(const item of state.uploads)panel.append(drawerCard(item.name,item.status+(item.sha?'; SHA256: '+item.sha:'')));
 }else if(name==='agents'){
  panel.append(drawerCard('Orchestrare DOTS','Profilurile sunt gestionate pe server. Acest frontend nu are încă un endpoint autorizat de catalog sau de status în timp real.'));
  const roles=[...new Set((state.selected?.progress||[]).map(x=>x.profile).filter(Boolean))];
  panel.append(drawerCard('Participare la cererea selectată',roles.length?roles.join(' · '):'Niciun agent identificat în evenimentele actuale.'));
 }else if(name==='capabilities'){
  const types=[
   ['Conversație text și sarcini',!!state.config?.ready,'POST /api/tasks'],
   ['Istoric de sarcini',!!state.config?.ready,'GET /api/tasks'],
   ['Stocare fișiere',!!state.config?.ready,'/api/attachments, fără analiză AI'],
   ['Locație GPS',!!navigator.geolocation,'Permisiune explicită în browser'],
   ['Apel vocal DOTS full-duplex',false,'Nu există contract vocal DOTS nativ'],
   ['Analiza AI a camerei',false,'Nu există endpoint pentru cadre'],
   ['Proiecte și spații',false,'Nu există endpoint de proiecte'],
   ['Căutare web / Deep Research',false,'Nu există endpoint dedicat'],
   ['Selectare modele / raționament',false,'Catalog indisponibil în API'],
   ['Agenți și subagenți',false,'Catalog neexpus prin API'],
   ['Automatizări și alerte',false,'Scheduler neexpus prin API'],
   ['Plugins și conectori',false,'Nu există registry/autorizare în API'],
   ['Generare și editare imagini',false,'Nu există serviciu vizual expus'],
   ['Cod / browser / Computer Use',false,'Nu există control UI autorizat']
  ];
  for(const [title,available,reason] of types)panel.append(drawerCard(title,(available?'API disponibil · ':'Neconectat · ')+reason));
 }else if(name==='settings'){
  panel.append(el('p','Preferințele vizuale funcționează local, fără a modifica setările backendului.'));
  for(const item of [{key:'theme',title:'Temă',values:[['dark','Întunecată'],['light','Luminoasă']]},{key:'density',title:'Densitate',values:[['comfortable','Confortabil'],['compact','Compact']]},{key:'scale',title:'Dimensiune text',values:[['0.9','Mic'],['1','Normal'],['1.1','Mare'],['1.2','Foarte mare']]}]){
   const label=el('label',item.title,'setting');const select=document.createElement('select');
   for(const [value,text] of item.values){const option=new Option(text,value);select.append(option);}
   select.value=String(state.prefs[item.key]);select.addEventListener('change',()=>{state.prefs[item.key]=item.key==='scale'?Number(select.value):select.value;applyPrefs();});label.append(select);panel.append(label);
  }
 }else if(name==='privacy'){
  panel.append(drawerCard('Cont și sesiune','Autentificarea folosește Google, cookie de sesiune cu acces restricționat și CSRF pentru acțiuni.'));
  panel.append(drawerCard('Microfon și cameră','Nu sunt activate și nu transmit cadre sau audio către DOTS fără integrarea nativă.'));
  panel.append(drawerCard('Locație','GPS se cere doar la apăsarea butonului Locație și se adaugă în mesaj doar după acordul browserului.'));
  panel.append(drawerCard('Fișiere','Fișierele se pot stoca pe server după autentificare; API-ul nu le oferă automat unui model AI.'));
 }else if(name==='account'){
  panel.append(drawerCard('Identitate',state.email||'Neautentificat'));
  const b=el('button','Deconectare','drawer-action');b.disabled=!state.signed;b.onclick=async()=>{try{await api('/auth/logout',{});signOut('Ai fost deconectat.');closeDrawer();}catch(e){message(e.message,'error');}};panel.append(b);
 }
}
function applyPrefs(){
 document.body.dataset.theme=state.prefs.theme;document.body.dataset.density=state.prefs.density;
 document.documentElement.style.setProperty('--scale',String(state.prefs.scale));
 try{localStorage.setItem('kelion-preferences-v1',JSON.stringify(state.prefs));}catch{}
}
function initPrefs(){
 try{const x=JSON.parse(localStorage.getItem('kelion-preferences-v1')||'{}');if(['dark','light'].includes(x.theme))state.prefs.theme=x.theme;if(['compact','comfortable'].includes(x.density))state.prefs.density=x.density;if([0.9,1,1.1,1.2].includes(x.scale))state.prefs.scale=x.scale;}catch{}
 applyPrefs();
}
async function uploadFiles(files){
 for(const file of files){
  if(!state.signed)break;
  if(file.size<1||file.size>512*1024*1024){message('Dimensiunea fișierului nu este acceptată: '+file.name,'error');continue;}
  const item={name:file.name,status:'Se încarcă',sha:''};state.uploads.push(item);
  openPanel('files');
  try{
   const meta=await api('/api/attachments',{filename:file.name,size:file.size});
   if(!attachValid(meta.id)||meta.received!==0)throw Error('Răspuns inițial de încărcare invalid.');
   let offset=0;
   while(offset<file.size){
    const chunk=file.slice(offset,Math.min(file.size,offset+2*1024*1024));
    const response=await fetch('/api/attachments/'+meta.id+'/chunk',{method:'POST',credentials:'same-origin',redirect:'error',headers:{'Content-Type':'application/octet-stream','X-CSRF-Token':state.csrf,'X-Upload-Offset':String(offset)},body:chunk});
    const data=await response.json().catch(()=>({error:'Răspuns invalid'}));
    if(!response.ok)throw Error(data.error||'Fragment respins ('+response.status+').');
    if(data.received!==offset+chunk.size)throw Error('Confirmarea fragmentului nu corespunde.');
    offset=data.received;item.status=Math.round(100*offset/file.size)+'%';openPanel('files');
   }
   const finished=await api('/api/attachments/'+meta.id+'/complete',{});
   if(finished.id!==meta.id||finished.state!=='stored'||finished.analyzed!==false||!finished.sha256)throw Error('Starea finală a fișierului nu este confirmată.');
   item.status='Stocat, neanalizat';item.sha=finished.sha256;
   message('Fișier stocat: '+file.name+' (nu a fost transmis pentru analiză AI).','success');
  }catch(e){item.status='Eroare: '+e.message;message('Fișierul '+file.name+': '+e.message,'error');}
  openPanel('files');
 }
}
async function geolocate(){
 if(!navigator.geolocation){message('GPS indisponibil în acest browser.','error');return;}
 message('Se solicită acces la locația dispozitivului…');
 navigator.geolocation.getCurrentPosition(pos=>{
  const {latitude,longitude,accuracy}=pos.coords;
  $('task').value=($('task').value.trim()+'\nLocație GPS autorizată: '+latitude.toFixed(6)+', '+longitude.toFixed(6)+'; precizie '+Math.round(accuracy)+' m.').trim();
  message('Locația a fost adăugată în mesaj. Verific-o înainte de trimitere.','success');setEnabled();
 },error=>message('Locația nu a fost acordată: '+error.message,'error'),{enableHighAccuracy:true,timeout:14000,maximumAge:0});
}
async function sendTask(event){
 event.preventDefault();if(!state.signed||state.sending)return;
 const text=$('task').value.trim();if(!text)return;
 state.sending=true;setEnabled();message('Se înregistrează sarcina…');
 try{
  const result=await api('/api/tasks',{task:text,input_mode:'text'});
  if(!idValid(result.task_id))throw Error('Serverul nu a confirmat ID-ul. Verifică istoricul înainte de retrimitere.');
  $('task').value='';stopPoll();state.selected=result;renderTask();setEnabled();
  message('Cererea este înregistrată. Verific statusul în monitor.','success');
  loadHistory(false).catch(()=>{});
  if(!TERMINAL.has(result.state))pollTask(result.task_id,state.seq);
 }catch(e){if(e.status===401)signOut('Sesiunea a expirat.');else message((e.task_id?'Trimitere neconfirmată ('+e.task_id+'). Verifică istoricul: ':'')+e.message,'error');}
 finally{state.sending=false;setEnabled();}
}
function bind(){
 document.querySelectorAll('[data-panel]').forEach(button=>button.addEventListener('click',()=>{if(button.dataset.panel==='history')loadHistory(true).catch(e=>message(e.message,'error'));else openPanel(button.dataset.panel);}));
 $('drawer-close').addEventListener('click',closeDrawer);$('backdrop').addEventListener('click',closeDrawer);
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('drawer').hidden)closeDrawer();});
 $('login').addEventListener('click',googleLogin);$('account').addEventListener('click',()=>openPanel('account'));
 $('compose').addEventListener('submit',sendTask);
 $('task').addEventListener('input',()=>{setEnabled();$('task').style.height='auto';$('task').style.height=Math.min(110,$('task').scrollHeight)+'px';});
 $('task').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();$('compose').requestSubmit();}});
 $('attach').addEventListener('click',()=>$('upload').click());
 $('upload').addEventListener('change',e=>{uploadFiles(Array.from(e.target.files||[]));e.target.value='';});
 $('location').addEventListener('click',geolocate);
 $('tab-result').addEventListener('click',()=>{state.mode='result';$('tab-result').classList.add('active');$('tab-activity').classList.remove('active');$('tab-result').setAttribute('aria-pressed','true');$('tab-activity').setAttribute('aria-pressed','false');renderTask();});
 $('tab-activity').addEventListener('click',()=>{state.mode='activity';$('tab-activity').classList.add('active');$('tab-result').classList.remove('active');$('tab-activity').setAttribute('aria-pressed','true');$('tab-result').setAttribute('aria-pressed','false');renderTask();});
 $('copy').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(state.selected.output);message('Rezultatul a fost copiat.','success');}catch{message('Copiere indisponibilă.','error');}});
 $('fullscreen').addEventListener('click',async()=>{const box=$('monitor-card');try{if(document.fullscreenElement)await document.exitFullscreen();else await box.requestFullscreen();}catch{message('Modul ecran complet nu este disponibil.','error');}});
}
(async function init(){
 initPrefs();bind();connection('Verificare');renderTask();message('');
 try{
  state.config=await api('/api/config');
  connection(state.config?.ready?'Servicii disponibile':'Autentificare neconfigurată',state.config?.ready?'ready':'error');
  if(!state.config?.ready){message('Serverul nu are autentificarea complet configurată.','error');return;}
  try{await signedIn(await api('/api/session'));}catch(e){if(e.status===401){signOut('Conectează-te cu contul Google autorizat.');}else{message('Sesiune neverificată: '+e.message,'error');}}
 }catch(e){connection('Server indisponibil','error');message(e.message,'error');}
})();
