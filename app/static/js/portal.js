"use strict";
const $ = (s, root=document) => root.querySelector(s);
const $$ = (s, root=document) => [...root.querySelectorAll(s)];
const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const state = {user:null, patients:[], appointments:[], visits:[], patient:null, view:"home", day:dayKey(new Date()), mode:"login", editor:null};
const statusNames={scheduled:"Agendada",confirmed:"Confirmada",completed:"Realizada",cancelled:"Cancelada",no_show:"No asistió"};
const tz="America/Santiago";
function parts(date){return Object.fromEntries(new Intl.DateTimeFormat("en-CA",{timeZone:"America/Santiago",year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hourCycle:"h23"}).formatToParts(date).map(p=>[p.type,p.value]));}
function dayKey(date){const p=parts(date);return `${p.year}-${p.month}-${p.day}`;}
function localInput(date){const p=parts(new Date(date));return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;}
function localISO(value){
  const target=Date.parse(value+":00Z"); let guess=target;
  for(let i=0;i<4;i++){const p=parts(new Date(guess));const wall=Date.parse(`${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}:00Z`);guess+=target-wall;}
  if(localInput(new Date(guess))!==value)throw new Error("Esta hora no existe por el cambio de horario en Chile. Elige otra hora.");
  return new Date(guess).toISOString();
}
function addDays(key,n){const d=new Date(key+"T12:00:00Z");d.setUTCDate(d.getUTCDate()+n);return d.toISOString().slice(0,10);}
function weekStart(key){const n=new Date(key+"T12:00:00Z").getUTCDay();return addDays(key,-((n+6)%7));}
function dateLabel(key, options={day:"numeric",month:"long",year:"numeric"}){return new Intl.DateTimeFormat("es-CL",{...options,timeZone:tz}).format(new Date(key+"T12:00:00Z"));}
function timeLabel(date){return new Intl.DateTimeFormat("es-CL",{timeZone:tz,hour:"2-digit",minute:"2-digit",hourCycle:"h23"}).format(new Date(date));}
function initials(name){return name.trim().split(/\s+/).slice(0,2).map(x=>x[0]).join("").toUpperCase();}
function fullName(p){return p?`${p.first_names} ${p.last_names}`:"Paciente";}
function empty(title,description="",action="",label=""){return `<div class="empty"><span class="empty-symbol"><svg class="icon" aria-hidden="true"><use href="/static/icons.svg#${action==="new-appointment"?"calendar":action==="new-patient"?"users":"file"}"></use></svg></span><strong>${esc(title)}</strong><p>${esc(description)}</p>${action?`<button class="button secondary small" data-action="${action}">${esc(label)}</button>`:""}</div>`;}
async function api(path, options={}){
  const response=await fetch(path,{...options,credentials:"same-origin",headers:{...(options.body instanceof FormData?{}:{"Content-Type":"application/json"}),...options.headers}});
  const body=response.status===204?null:await response.json().catch(()=>null);
  if(!response.ok){
    if(response.status===401&&state.user){state.user=null;showAuth("login");}
    const detail=body?.detail;throw new Error(Array.isArray(detail)?detail.map(e=>`${e.loc.slice(1).join(" · ")}: ${e.msg}`).join("\n"):detail||"No se pudo completar la solicitud. Inténtalo de nuevo.");
  }return body;
}
function notify(message,error=false){const el=$("#global-message");el.textContent=message;el.className="toast"+(error?" error":"");el.scrollIntoView({block:"nearest",behavior:"smooth"});}
function showAuth(mode){state.mode=mode;$("#loading").classList.add("hidden");$("#app-screen").classList.add("hidden");$("#auth-screen").classList.remove("hidden");setAuthMode(mode);}
function setAuthMode(mode){state.mode=mode;const register=mode==="register";$("#register-fields").classList.toggle("hidden",!register);$$("#register-fields input").forEach(x=>x.required=register);$("#register-tab").classList.toggle("active",register);$("#login-tab").classList.toggle("active",!register);$("#auth-title").textContent=register?"Crea tu cuenta.":"Qué bueno verte.";$("#auth-subtitle").textContent=register?"Crea tu cuenta profesional gratuita.":"Ingresa para continuar con tus pacientes.";$("#auth-submit").textContent=register?"Crear mi cuenta gratis ↗":"Ingresar a mi consulta ↗";$("#auth-error").textContent="";$("#register-note").textContent=register?"Sin tarjeta de crédito. Tu cuenta es gratuita.":"Tu espacio profesional, en un solo lugar.";$("[name=password]",$("#auth-form")).autocomplete=register?"new-password":"current-password";resetPasswordVisibility($("#auth-form"));history.replaceState(null,"",register?"/registro":"/ingresar");}
$("#login-tab").onclick=()=>setAuthMode("login");$("#register-tab").onclick=()=>setAuthMode("register");
$("#auth-form").onsubmit=async event=>{event.preventDefault();const btn=$("#auth-submit");btn.disabled=true;$("#auth-error").textContent="";try{const data=Object.fromEntries(new FormData(event.target));if(state.mode==="login"){delete data.full_name;delete data.specialty;}state.user=await api(`/api/auth/${state.mode==="register"?"register":"login"}`,{method:"POST",body:JSON.stringify(data)});event.target.reset();await enterApp();}catch(e){$("#auth-error").textContent=e.message;}finally{btn.disabled=false;}};
async function loadPatients(){let result=[],offset=0;while(true){const page=await api(`/api/patients?limit=200&offset=${offset}`);result.push(...page);if(page.length<200)break;offset+=200;}state.patients=result;}
async function loadWeek(){const start=weekStart(state.day);state.appointments=await api(`/api/appointments?${new URLSearchParams({start:localISO(start+"T00:00"),end:localISO(addDays(start,7)+"T00:00")})}`);}
async function enterApp(){await loadPatients();await loadWeek();$("#loading").classList.add("hidden");$("#auth-screen").classList.add("hidden");$("#app-screen").classList.remove("hidden");history.replaceState(null,"","/portal");renderUser();await showView("home");}
function renderUser(){const u=state.user;$("#user-name").textContent=u.full_name;$("#user-specialty").textContent=u.specialty;$("#user-avatar").textContent=initials(u.full_name);$("#today-label").textContent=dateLabel(dayKey(new Date()),{weekday:"long",day:"numeric",month:"long"}).toUpperCase();$("#greeting").textContent=`Hola, ${u.full_name.split(" ")[0]}.`;for(const field of $("#profile-form").elements){if(field.name&&Object.hasOwn(u,field.name))field.value=u[field.name]??"";}$("#profile-form [name=current_password]").value="";syncEmailConfirmation();}
async function showView(view){state.view=view;$$(".view").forEach(el=>el.classList.toggle("hidden",el.id!==`view-${view}`));$$("#app-nav button").forEach(el=>el.classList.toggle("active",el.dataset.view===(view==="record"?"patients":view)));if(view==="home")await renderHome();if(view==="patients")renderPatients();if(view==="agenda"){await loadWeek();renderAgenda();}if(view==="profile"){renderUser();resetPasswordForm();$("#password-status").textContent="";$("#password-form .form-message").textContent="";}}
function patientTable(list){if(!list.length)return empty("Todavía no hay pacientes","Agrega tu primer paciente para comenzar su historia.","new-patient","＋ Agregar paciente");return `<div class="table-wrap"><table><thead><tr><th>Paciente</th><th>RUT</th><th>Última atención</th><th></th></tr></thead><tbody>${list.map(p=>`<tr><td><div class="patient-name"><span class="avatar">${esc(initials(fullName(p)))}</span><div><strong>${esc(fullName(p))}</strong><small>${esc(p.email||p.phone||"Sin contacto registrado")}</small></div></div></td><td>${esc(p.rut)}</td><td>${p.last_visit_date?esc(dateLabel(p.last_visit_date,{day:"numeric",month:"short",year:"numeric"})):"Sin atenciones"}</td><td><button class="text-button" data-action="open-record" data-id="${p.id}">Ver ficha ↗</button></td></tr>`).join("")}</tbody></table></div>`;}
function renderPatients(){const q=$("#patient-search").value.trim().toLocaleLowerCase("es");const list=state.patients.filter(p=>`${fullName(p)} ${p.rut}`.toLocaleLowerCase("es").includes(q));$("#patient-table").innerHTML=list.length?patientTable(list):q?empty("No encontramos coincidencias","Prueba con otro nombre o RUT."):patientTable([]);$("#patient-count").textContent=`${list.length} de ${state.patients.length} pacientes`;}$("#patient-search").oninput=renderPatients;
function eventList(list){if(!list.length)return empty("Un espacio para tu próxima cita","Organiza tus horas y encuentra aquí a tus próximos pacientes.","new-appointment","＋ Agendar hora");return list.map(a=>{const p=state.patients.find(p=>p.id===a.patient_id);return `<div class="event-row"><div class="event-time">${esc(timeLabel(a.starts_at))}<small>hasta ${esc(timeLabel(a.ends_at))}</small></div><div class="event-info"><strong>${esc(fullName(p))}</strong><p>${esc(a.reason||"Atención clínica")}</p></div><div class="event-actions"><span class="badge ${a.status}">${statusNames[a.status]}</span><button class="text-button" data-action="open-record" data-id="${a.patient_id}">Ficha</button><button class="text-button" data-action="edit-appointment" data-id="${a.id}">Editar</button></div></div>`;}).join("");}
async function renderHome(){const stats=await api("/api/dashboard");$("#stat-patients").textContent=stats.patients;$("#stat-visits").textContent=stats.visits;const today=dayKey(new Date());let events=state.appointments;if(weekStart(state.day)!==weekStart(today)){events=await api(`/api/appointments?${new URLSearchParams({start:localISO(today+"T00:00"),end:localISO(addDays(today,1)+"T00:00")})}`);}const list=events.filter(a=>dayKey(new Date(a.starts_at))===today);$("#stat-today").textContent=list.filter(a=>!["cancelled","no_show"].includes(a.status)).length;$("#today-appointments").innerHTML=eventList(list);$("#recent-patients").innerHTML=patientTable(state.patients.slice(0,5));}
function renderAgenda(){$("#agenda-date").value=state.day;const start=weekStart(state.day);$("#week-strip").innerHTML=Array.from({length:7},(_,i)=>{const key=addDays(start,i);const count=state.appointments.filter(a=>dayKey(new Date(a.starts_at))===key&&!["cancelled","no_show"].includes(a.status)).length;return `<button class="day-button ${key===state.day?"active":""}" data-action="select-day" data-day="${key}"><small>${esc(dateLabel(key,{weekday:"short"}))}</small><strong>${Number(key.slice(-2))}</strong><span>${count} citas</span></button>`;}).join("");$("#agenda-day-title").textContent=dateLabel(state.day,{weekday:"long",day:"numeric",month:"long"});$("#agenda-events").innerHTML=eventList(state.appointments.filter(a=>dayKey(new Date(a.starts_at))===state.day));}
async function changeDay(key){state.day=key;try{await loadWeek();renderAgenda();}catch(e){notify(e.message,true);}}$("#agenda-date").onchange=e=>{if(e.target.value)changeDay(e.target.value);};$("#prev-week").onclick=()=>changeDay(addDays(state.day,-7));$("#next-week").onclick=()=>changeDay(addDays(state.day,7));$("#agenda-today").onclick=()=>changeDay(dayKey(new Date()));
const patientFields=[['first_names','Nombres','text',true],['last_names','Apellidos','text',true],['rut','RUT','text',true],['age','Edad','number',true],['birth_date','Fecha de nacimiento','date'],['first_visit_date','Fecha de ingreso / primera visita','date',true],['phone','Teléfono','tel'],['email','Correo electrónico','email'],['address','Dirección'],['occupation','Ocupación'],['emergency_contact','Contacto de emergencia'],['referral_source','Derivación'],['pre_existing_conditions','Antecedentes y condiciones preexistentes','textarea',true],['medications','Medicamentos','textarea'],['allergies','Alergias','textarea'],['pelvic_surgery_history','Antecedentes quirúrgicos','textarea'],['obstetric_history','Antecedentes obstétricos','textarea'],['gynecologic_history','Antecedentes ginecológicos','textarea'],['urinary_symptoms','Síntomas urinarios','textarea'],['bowel_symptoms','Síntomas intestinales','textarea'],['sexual_symptoms','Síntomas sexuales','textarea'],['pain_description','Descripción de dolor','textarea'],['red_flags','Alertas clínicas','textarea']];
const visitFields=[['visit_date','Fecha de atención','date',true],['pain_scale','Dolor (0 a 10)','number'],['chief_complaint','Motivo de consulta','textarea'],['objective_exam','Evaluación / examen objetivo','textarea'],['new_findings','Hallazgos y evolución','textarea',true],['clinical_assessment','Evaluación clínica','textarea'],['treatment_plan','Plan de tratamiento','textarea'],['home_exercises','Ejercicios / indicaciones domiciliarias','textarea'],['recommendations','Recomendaciones','textarea'],['next_visit_date','Próxima atención sugerida','date']];
function inputField([name,label,type="text",required=false],value=""){const bounds=name==="age"?'min="0" max="120"':name==="pain_scale"?'min="0" max="10"':type==="text"?'maxlength="255"':"";return `<label class="${type==="textarea"?"span-2":""}">${esc(label)}${required?" *":""}${type==="textarea"?`<textarea name="${name}" ${required?'required minlength="3"':""}>${esc(value)}</textarea>`:`<input name="${name}" type="${type}" value="${esc(value)}" ${required?"required":""} ${bounds}>`}</label>`;}
function openEditor(title,html,editor){state.editor=editor;$("#editor-title").textContent=title;$("#editor-fields").innerHTML=html;$("#editor-error").textContent="";$("#editor").showModal();}
function editPatient(patient=null){const data=patient||{first_visit_date:dayKey(new Date())};openEditor(patient?"Editar ficha del paciente":"Agregar paciente",`<p class="select-help">Los campos con * son obligatorios. Registra solo la información necesaria para la atención.</p><div class="form-grid">${patientFields.map((f,i)=>(i===12?'<h3 class="form-section">Antecedentes clínicos</h3>':i===16?'<h3 class="form-section">Antecedentes específicos (opcionales)</h3>':"")+inputField(f,data[f[0]]??"")).join("")}<label class="check-label"><input name="consent_signed" type="checkbox" ${data.consent_signed?"checked":""}><span>El paciente otorgó su consentimiento para el registro de sus antecedentes. Marca solo si ya fue obtenido.</span></label></div>`,{type:"patient",id:patient?.id});}
async function openRecord(id){const patient=await api(`/api/patients/${id}`);const visits=await api(`/api/visits/patient/${id}`);const orders=await api(`/api/patients/${id}/medical-orders?limit=50`);state.patient=patient;state.visits=visits;state.orders=orders;state.moreOrders=orders.length===50;$("#record-header").innerHTML=`<div class="page-heading"><div><p class="eyebrow">HISTORIA CLÍNICA</p><h1>${esc(fullName(patient))}</h1><p class="muted">${esc(patient.rut)} · ${patient.age} años · Ingreso ${esc(dateLabel(patient.first_visit_date))}</p></div><div class="record-heading-actions"><button class="button secondary" data-action="patient-appointment">＋ Agendar hora</button></div></div>`;$("#record-details").innerHTML=`<dl class="record-details">${patientFields.filter(f=>!["first_names","last_names","rut","age","first_visit_date"].includes(f[0])).map(([name,label])=>`<dt>${esc(label)}</dt><dd>${esc(patient[name]||"Sin registro")}</dd>`).join("")}<dt>Consentimiento para registro</dt><dd>${patient.consent_signed?"Registrado":"Pendiente de registrar"}</dd></dl>`;$("#visit-list").innerHTML=visits.length?visits.map(v=>`<article class="visit-entry"><div class="visit-top"><h3>${esc(dateLabel(v.visit_date))}</h3><button class="text-button" data-action="edit-visit" data-id="${v.id}">Editar</button></div><dl>${visitFields.filter(f=>f[0]!=="visit_date"&&v[f[0]]!=null&&v[f[0]]!=="").map(([name,label])=>`<dt>${esc(label)}</dt><dd>${esc(name==="pain_scale"?`${v[name]} / 10`:name==="next_visit_date"?dateLabel(v[name]):v[name])}</dd>`).join("")}</dl></article>`).join(""):empty("Su historia comienza aquí","Registra la primera atención para dar continuidad al cuidado.","new-visit","＋ Registrar atención");renderMedicalOrders();await showView("record");}
function editVisit(visit=null){if(!state.patient)return;const data=visit||{visit_date:dayKey(new Date())};openEditor(visit?"Editar atención":"Registrar atención",`<p class="select-help">Paciente: ${esc(fullName(state.patient))}</p><div class="form-grid">${visitFields.map(f=>inputField(f,data[f[0]]??"")).join("")}</div>`,{type:"visit",id:visit?.id,patientId:state.patient.id});}
function editAppointment(appointment=null,patientId=null){if(!state.patients.length){notify("Agrega primero un paciente para poder agendar su hora.");showView("patients");return;}const data=appointment||{starts_at:localISO(state.day+"T"+state.user.work_start),ends_at:localISO(state.day+"T"+state.user.work_start),status:"scheduled"};const start=localInput(data.starts_at);const end=appointment?localInput(data.ends_at):localInput(new Date(new Date(data.starts_at).getTime()+state.user.appointment_minutes*60000));openEditor(appointment?"Editar cita":"Agendar hora",`<p class="select-help">Horarios de Chile (America/Santiago). Puedes programar excepciones a tu jornada habitual.</p><label>Buscar paciente<input id="appointment-patient-filter" type="search" placeholder="Filtrar por nombre o RUT"></label><label>Paciente *<select name="patient_id" required>${state.patients.map(p=>`<option value="${p.id}" ${p.id===(appointment?.patient_id||patientId)?"selected":""}>${esc(fullName(p))} · ${esc(p.rut)}</option>`).join("")}</select></label><div class="form-grid">${inputField(['starts_at','Inicio','datetime-local',true],start)}${inputField(['ends_at','Término','datetime-local',true],end)}<label class="span-2">Estado<select name="status">${Object.entries(statusNames).map(([key,label])=>`<option value="${key}" ${data.status===key?"selected":""}>${label}</option>`).join("")}</select></label>${inputField(['reason','Motivo de la cita','textarea'],data.reason||"")}</div>`,{type:"appointment",id:appointment?.id});$("#appointment-patient-filter").oninput=e=>{const q=e.target.value.toLowerCase();const select=$("select[name=patient_id]",$("#editor-form"));const previous=select.value;const matches=state.patients.filter(p=>`${fullName(p)} ${p.rut}`.toLowerCase().includes(q));select.innerHTML=matches.map(p=>`<option value="${p.id}">${esc(fullName(p))} · ${esc(p.rut)}</option>`).join("");if(matches.some(p=>String(p.id)===previous))select.value=previous;};}
$("#edit-patient").onclick=()=>editPatient(state.patient);$("#new-visit").onclick=()=>editVisit();$("#close-editor").onclick=$("#cancel-editor").onclick=()=>$("#editor").close();
$("#editor-form").onsubmit=async event=>{event.preventDefault();const btn=$("button[type=submit]",event.target);btn.disabled=true;$("#editor-error").textContent="";try{const edit=state.editor;let payload=Object.fromEntries(new FormData(event.target));let path,recordId;if(edit.type==="patient"){for(const [key,value] of Object.entries(payload))if(value==="")payload[key]=null;payload.age=Number(payload.age);payload.consent_signed=event.target.elements.consent_signed.checked;path=`/api/patients${edit.id?"/"+edit.id:""}`;}if(edit.type==="visit"){for(const [key,value] of Object.entries(payload))if(value==="")payload[key]=null;payload.patient_id=edit.patientId;payload.pain_scale=payload.pain_scale==null?null:Number(payload.pain_scale);path=`/api/visits${edit.id?"/"+edit.id:""}`;recordId=edit.patientId;}if(edit.type==="appointment"){payload.patient_id=Number(payload.patient_id);payload.starts_at=localISO(payload.starts_at);payload.ends_at=localISO(payload.ends_at);path=`/api/appointments${edit.id?"/"+edit.id:""}`;}const saved=await api(path,{method:edit.id?"PUT":"POST",body:JSON.stringify(payload)});if(edit.type==="patient")recordId=saved.id;$("#editor").close();await loadPatients();await loadWeek();if(recordId)await openRecord(recordId);else await showView(state.view);notify("Cambios guardados correctamente.");}catch(e){$("#editor-error").textContent=e.message;}finally{btn.disabled=false;}};
$("#profile-form").onsubmit=async event=>{event.preventDefault();const btn=$("button[type=submit]",event.target);btn.disabled=true;const error=$(".form-message",event.target);error.textContent="";try{const data=Object.fromEntries(new FormData(event.target));data.appointment_minutes=Number(data.appointment_minutes);state.user=await api("/api/auth/profile",{method:"PUT",body:JSON.stringify(data)});renderUser();notify("Perfil actualizado.");}catch(e){error.textContent=e.message;}finally{btn.disabled=false;}};

function syncEmailConfirmation(){
  const form=$("#profile-form");
  const changed=form.elements.email.value.trim().toLowerCase()!==state.user?.email.toLowerCase();
  $("#email-confirmation").classList.toggle("hidden",!changed);
  form.elements.current_password.required=changed;
  if(!changed){form.elements.current_password.value="";resetPasswordVisibility(form);}
}
$("#profile-form [name=email]").addEventListener("input",syncEmailConfirmation);
function setPasswordVisibility(button,reveal){
  const input=document.getElementById(button.dataset.passwordTarget);
  input.type=reveal?"text":"password";
  button.querySelector("use").setAttribute("href",`/static/icons.svg#${reveal?"eye-off":"eye"}`);
  button.setAttribute("aria-pressed",String(reveal));
  const label=input.name==="new_password"?"nueva contraseña":input.name==="confirm_password"?"confirmación de contraseña":input.name==="current_password"?"contraseña actual":"contraseña";
  const description=`${reveal?"Ocultar":"Mostrar"} ${label}`;
  button.setAttribute("aria-label",description);
  button.title=description;
}
function resetPasswordVisibility(form){
  $$("[data-password-target]",form).forEach(button=>setPasswordVisibility(button,false));
}
$$("[data-password-target]").forEach(button=>button.addEventListener("click",()=>{
  const input=document.getElementById(button.dataset.passwordTarget);
  setPasswordVisibility(button,input.type==="password");
}));
["#auth-form","#profile-form","#password-form"].forEach(selector=>{
  $(selector).addEventListener("reset",()=>resetPasswordVisibility($(selector)));
});
function resetPasswordForm(){
  const form=$("#password-form");form.reset();
  $$("[data-password-target]",form).forEach(button=>{
    const input=document.getElementById(button.dataset.passwordTarget);
    if(input.type==="text")button.click();
  });
}
$("#password-form").addEventListener("input",()=>{
  $("#password-status").textContent="";
  $("#password-form .form-message").textContent="";
});
$("#password-form").addEventListener("submit",async event=>{
  event.preventDefault();
  const form=event.target, button=$("button[type=submit]",form), error=$(".form-message",form);
  error.textContent="";$("#password-status").textContent="";
  const data=Object.fromEntries(new FormData(form));
  if(data.new_password!==data.confirm_password){error.textContent="La nueva contraseña y su confirmación no coinciden.";return;}
  if(data.new_password===data.current_password){error.textContent="La nueva contraseña debe ser diferente de la actual.";return;}
  button.disabled=true;
  try{
    await api("/api/auth/password",{method:"PUT",body:JSON.stringify(data)});
    resetPasswordForm();
    $("#password-status").textContent="Contraseña actualizada correctamente. Las otras sesiones quedaron cerradas.";
  }catch(e){error.textContent=e.message;}finally{button.disabled=false;}
});
$("#logout").onclick=async()=>{try{await api("/api/auth/logout",{method:"POST"});$("#editor").close();$("#order-upload-dialog").close();$("#order-view-dialog").close();state.orders=[];$("#medical-orders-list").innerHTML="";resetPasswordForm();$("#profile-form").reset();$("#password-status").textContent="";state.user=null;state.patients=[];state.appointments=[];state.patient=null;state.visits=[];$("#auth-form").reset();showAuth("login");history.replaceState(null,"","/ingresar");}catch(e){notify(e.message,true);}};
document.addEventListener("click",async event=>{const target=event.target.closest("[data-view],[data-action]");if(!target)return;try{if(target.dataset.view){await showView(target.dataset.view);return;}const id=Number(target.dataset.id);switch(target.dataset.action){case"new-patient":editPatient();break;case"open-record":await openRecord(id);break;case"new-visit":editVisit();break;case"edit-visit":editVisit(state.visits.find(v=>v.id===id));break;case"new-appointment":editAppointment();break;case"patient-appointment":editAppointment(null,state.patient.id);break;case"edit-appointment":{let a=state.appointments.find(a=>a.id===id);if(!a){const today=dayKey(new Date());const list=await api(`/api/appointments?${new URLSearchParams({start:localISO(today+"T00:00"),end:localISO(addDays(today,1)+"T00:00")})}`);a=list.find(a=>a.id===id);}if(a)editAppointment(a);break;}case"select-day":state.day=target.dataset.day;renderAgenda();break;}}catch(e){notify(e.message,true);}});

let orderPhoto=null, orderPreviewURL=null, viewedOrder=null;
state.orders=[];
function formatBytes(size){return size<1024*1024?`${Math.max(1,Math.round(size/1024))} KB`:`${(size/1024/1024).toFixed(1)} MB`;}
function renderMedicalOrders(){
  const list=$("#medical-orders-list");
  list.innerHTML=state.orders.length?`<div class="medical-orders-grid">${state.orders.map(order=>`<article class="medical-order"><button type="button" class="order-thumbnail" data-order-view="${order.id}" aria-label="Ver ${esc(order.title)}"><img src="/api/medical-orders/${order.id}/image?thumbnail=true" loading="lazy" alt="Vista previa de ${esc(order.title)}"></button><div class="medical-order-info"><h3>${esc(order.title)}</h3><p>${esc(order.document_date?dateLabel(order.document_date):dateLabel(dayKey(new Date(order.created_at))))} · ${esc(formatBytes(order.size_bytes))}</p><button type="button" class="text-button" data-order-view="${order.id}">Ver orden médica ↗</button></div></article>`).join("")}</div>`:empty("Aún no hay órdenes médicas","Agrega una foto de la orden o derivación para guardarla junto a su historia.");
  $("#more-medical-orders").classList.toggle("hidden",!state.moreOrders);
}
$("#more-medical-orders").onclick=async()=>{
  const button=$("#more-medical-orders");button.disabled=true;
  try{const page=await api(`/api/patients/${state.patient.id}/medical-orders?limit=50&offset=${state.orders.length}`);state.orders.push(...page);state.moreOrders=page.length===50;renderMedicalOrders();}catch(e){notify(e.message,true);}finally{button.disabled=false;}
};
function clearOrderPreview(){
  if(orderPreviewURL)URL.revokeObjectURL(orderPreviewURL);
  orderPreviewURL=null;orderPhoto=null;
  $("#order-preview-image").removeAttribute("src");
  $("#order-photo-preview").classList.add("hidden");
  $("#save-medical-order").disabled=true;
}
$("#add-medical-order").onclick=()=>{
  if(!state.patient)return;
  $("#order-upload-form").reset();clearOrderPreview();
  $("#order-upload-error").textContent="";
  $("#order-upload-form [name=title]").value="Orden médica";
  $("#order-upload-dialog").showModal();
};
$("#close-order-upload").onclick=$("#cancel-order-upload").onclick=()=>$("#order-upload-dialog").close();
$("#order-upload-dialog").addEventListener("close",clearOrderPreview);
function selectOrderPhoto(event){
  const file=event.target.files[0];if(!file)return;
  clearOrderPreview();$("#order-upload-error").textContent="";
  if(file.size>12*1024*1024){$("#order-upload-error").textContent="La foto supera el límite de 12 MB. Elige otra imagen.";return;}
  orderPhoto=file;orderPreviewURL=URL.createObjectURL(file);
  const image=$("#order-preview-image");image.classList.remove("hidden");
  $("#order-preview-fallback").classList.add("hidden");
  image.onerror=()=>{image.classList.add("hidden");$("#order-preview-fallback").classList.remove("hidden");};
  image.src=orderPreviewURL;
  $("#order-photo-info").textContent=`${file.name} · ${formatBytes(file.size)}`;
  $("#order-photo-preview").classList.remove("hidden");
  $("#save-medical-order").disabled=false;
}
$("#order-camera").onchange=$("#order-gallery").onchange=selectOrderPhoto;
$("#order-upload-form").onsubmit=async event=>{
  event.preventDefault();if(!orderPhoto||!state.patient)return;
  const form=event.target,button=$("#save-medical-order"),patientId=state.patient.id;
  const data=new FormData();data.append("photo",orderPhoto);data.append("title",form.elements.title.value.trim());
  if(form.elements.document_date.value)data.append("document_date",form.elements.document_date.value);
  if(form.elements.notes.value.trim())data.append("notes",form.elements.notes.value.trim());
  button.disabled=true;button.textContent="Optimizando y guardando…";$("#order-upload-error").textContent="";
  try{
    await api(`/api/patients/${patientId}/medical-orders`,{method:"POST",body:data});
    $("#order-upload-dialog").close();await openRecord(patientId);notify("Orden médica guardada en la ficha del paciente.");
  }catch(e){$("#order-upload-error").textContent=e.message;}finally{button.textContent="Guardar orden";button.disabled=!orderPhoto;}
};
function viewMedicalOrder(id){
  const order=state.orders.find(item=>item.id===id);if(!order)return;
  viewedOrder=order;$("#order-view-title").textContent=order.title;
  $("#order-view-meta").textContent=`${order.document_date?"Fecha de la orden: "+dateLabel(order.document_date):"Agregada el "+dateLabel(dayKey(new Date(order.created_at)))} · ${formatBytes(order.size_bytes)} · ${order.width} × ${order.height} px`;
  $("#order-view-image").src=`/api/medical-orders/${id}/image`;
  $("#order-view-notes").textContent=order.notes||"";
  $("#order-open-full").href=`/api/medical-orders/${id}/image`;
  $("#order-download").href=`/api/medical-orders/${id}/image?download=true`;
  $("#order-delete-confirm").classList.add("hidden");$("#order-view-error").textContent="";
  $("#order-view-dialog").showModal();
}
$("#medical-orders-list").addEventListener("click",event=>{const button=event.target.closest("[data-order-view]");if(button)viewMedicalOrder(Number(button.dataset.orderView));});
$("#close-order-view").onclick=()=>$("#order-view-dialog").close();
$("#order-view-dialog").addEventListener("close",()=>{$("#order-view-image").removeAttribute("src");viewedOrder=null;});
$("#delete-medical-order").onclick=()=>$("#order-delete-confirm").classList.remove("hidden");
$("#cancel-delete-order").onclick=()=>$("#order-delete-confirm").classList.add("hidden");
$("#confirm-delete-order").onclick=async()=>{
  if(!viewedOrder)return;
  const id=viewedOrder.id,patientId=state.patient.id,button=$("#confirm-delete-order");button.disabled=true;
  try{await api(`/api/medical-orders/${id}`,{method:"DELETE"});$("#order-view-dialog").close();await openRecord(patientId);notify("Orden médica eliminada.");}
  catch(e){$("#order-view-error").textContent=e.message;}finally{button.disabled=false;}
};
(async()=>{try{state.user=await api("/api/auth/me");await enterApp();}catch(e){if(state.user){$("#loading").classList.add("hidden");$("#app-screen").classList.remove("hidden");renderUser();notify(e.message,true);}else showAuth(location.pathname==="/registro"?"register":"login");}})();
