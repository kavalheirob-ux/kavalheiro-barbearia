const $ = (id) => document.getElementById(id);

let state = {
  me: null,
  viewMode: "day",
  cursor: new Date(),
  services: [],
  clients: [],
  barbers: [],
  appts: [],
  schedule: null,
  installPrompt: null
};

function pad(n){ return String(n).padStart(2,"0"); }
function toLocalInput(dt){
  const d = new Date(dt);
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
function startOfDay(d){ return new Date(d.getFullYear(), d.getMonth(), d.getDate(), 0,0,0,0); }
function addDays(d, n){ const x = new Date(d); x.setDate(x.getDate()+n); return x; }
function fmtDateBR(d){ return `${pad(d.getDate())}/${pad(d.getMonth()+1)}/${d.getFullYear()}`; }
function fmtMoney(v){ return Number(v||0).toLocaleString("pt-BR",{style:"currency",currency:"BRL"}); }
function isoNoSeconds(d){ return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`; }
function dayISO(d){ return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`; }

function getRange(){
  const c = startOfDay(state.cursor);
  if(state.viewMode === "day"){
    const start = new Date(c.getFullYear(), c.getMonth(), c.getDate(), 0,0);
    const end = addDays(start, 1);
    return {start, end, title: `Dia — ${fmtDateBR(start)}`};
  }
  const day = c.getDay();
  const diff = (day === 0 ? -6 : 1 - day);
  const start = addDays(c, diff);
  const end = addDays(start, 7);
  return {start, end, title: `Semana — ${fmtDateBR(start)} até ${fmtDateBR(addDays(end,-1))}`};
}

async function api(path, opts){
  const res = await fetch(path, Object.assign({headers: {"Content-Type":"application/json"}}, opts||{}));
  const data = await res.json().catch(()=> ({}));
  if(!res.ok) throw new Error(data.error || `Erro (${res.status})`);
  return data;
}

function renderServiceSelect(selId, selected){
  const el = $(selId);
  if(!el) return;
  el.innerHTML = "";
  for(const s of state.services){
    const opt = document.createElement("option");
    opt.value = s.name;
    opt.textContent = `${s.name}${s.price!=null?` — ${fmtMoney(s.price)}`:""}`;
    el.appendChild(opt);
  }
  if(selected) el.value = selected;
}

function renderBarberSelect(selId, selectedId){
  const el = $(selId);
  if(!el) return;
  el.innerHTML = "";
  for(const b of state.barbers){
    const opt = document.createElement("option");
    opt.value = String(b.id);
    opt.textContent = b.name + (b.approved ? "" : " (pendente)");
    el.appendChild(opt);
  }
  if(selectedId) el.value = String(selectedId);
}

function renderFilters(){
  const el = $("barberFilter");
  if(!el) return;
  el.innerHTML = "";
  if(state.me.role === "admin"){
    const all = document.createElement("option");
    all.value = "0";
    all.textContent = "Todos os barbeiros";
    el.appendChild(all);
  }
  for(const b of state.barbers){
    const opt = document.createElement("option");
    opt.value = String(b.id);
    opt.textContent = b.name;
    el.appendChild(opt);
  }
  if(state.me.role === "admin") el.value = "0";
  else el.value = String(state.me.id);
}

function parseHHMM(s){
  const [h,m] = s.split(":").map(Number);
  return {h,m};
}

function buildSlotsForDay(schedule){
  const slots = [];
  if(!schedule || schedule.closed) return slots;
  const {open_time, close_time, slot_min, lunch_start, lunch_end} = schedule;
  const o = parseHHMM(open_time);
  const c = parseHHMM(close_time);
  const ls = lunch_start ? parseHHMM(lunch_start) : null;
  const le = lunch_end ? parseHHMM(lunch_end) : null;

  const start = new Date(state.cursor.getFullYear(), state.cursor.getMonth(), state.cursor.getDate(), o.h, o.m, 0, 0);
  const end = new Date(state.cursor.getFullYear(), state.cursor.getMonth(), state.cursor.getDate(), c.h, c.m, 0, 0);

  for(let t = new Date(start); t <= end; t = new Date(t.getTime() + slot_min*60000)){
    // last slot exactly at close is allowed only if minute == 0 and no overflow; we show up to close inclusive
    const hhmm = `${pad(t.getHours())}:${pad(t.getMinutes())}`;
    // hide slots that start at close (no duration) in UI:
    if(t.getTime() === end.getTime()) continue;

    // mark lunch slots as "blocked" in UI by adding but later rendering as blocked
    let isLunch = false;
    if(ls && le){
      const ltS = new Date(state.cursor.getFullYear(), state.cursor.getMonth(), state.cursor.getDate(), ls.h, ls.m,0,0);
      const ltE = new Date(state.cursor.getFullYear(), state.cursor.getMonth(), state.cursor.getDate(), le.h, le.m,0,0);
      if(t >= ltS && t < ltE) isLunch = true;
    }
    slots.push({hhmm, isLunch});
  }
  return slots;
}

function apptAt(dayDate, hhmm, barberId){
  const key = `${fmtDateBR(dayDate)} ${hhmm}`;
  return state.appts.filter(a => {
    if(barberId && a.barber_id !== barberId) return false;
    const d = new Date(a.start_at);
    const k = `${pad(d.getDate())}/${pad(d.getMonth()+1)}/${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
    return k === key;
  });
}

function cardFor(a){
  const statusClass = a.status === "Concluído" ? "ok" : (a.status === "Cancelado" ? "cancel" : (a.status==="Pendente"?"pending":"ag"));
  const who = (state.me.role === "admin" && Number($("barberFilter")?.value || 0) === 0) ? ` • ${a.barber_name}` : "";
  const pay = a.payment_method ? ` • ${a.payment_method}` : "";
  const price = a.price!=null ? ` • ${fmtMoney(a.price)}` : "";
  const src = a.created_by === "public" ? ` • <span class="badge text-bg-warning">online</span>` : "";
  return `<div class="appt ${statusClass}" data-id="${a.id}">
    <div class="t">${a.client_name}${who}${src}</div>
    <div class="s">${a.service_name}${price}${pay}</div>
    ${a.notes?`<div class="n">${a.notes}</div>`:""}
  </div>`;
}

function renderAgenda(){
  const {start, end, title} = getRange();
  $("rangeTitle").textContent = title;

  if(state.schedule){
    const badge = $("scheduleBadge");
    if(badge){
      badge.textContent = state.schedule.closed ? "FECHADO" : `⏰ ${state.schedule.open_time}-${state.schedule.close_time} • 🍽️ ${state.schedule.lunch_start}-${state.schedule.lunch_end}`;
    }
  }

  const slots = buildSlotsForDay(state.schedule);
  let days = [];
  if(state.viewMode === "day") days = [start];
  else for(let i=0;i<7;i++) days.push(addDays(start, i));

  const barberId = (state.me.role === "admin" && Number($("barberFilter")?.value || 0) === 0) ? null : Number($("barberFilter")?.value || state.me.id);

  let html = `<div class="table-responsive">
  <table class="table table-sm align-middle mb-0">
    <thead><tr>
      <th style="width:90px;">Hora</th>
      ${days.map(d => `<th>${fmtDateBR(d)}<div class="small text-muted">${["Dom","Seg","Ter","Qua","Qui","Sex","Sáb"][d.getDay()]}</div></th>`).join("")}
    </tr></thead>
    <tbody>`;

  // if week view, we still use same slots from cursor day; acceptable for now
  for(const s of slots){
    html += `<tr><td class="timecell">${s.hhmm}</td>`;
    for(const d of days){
      const appts = apptAt(d, s.hhmm, barberId);
      let cell = appts.length ? appts.map(cardFor).join("") : `<div class="empty">—</div>`;
      if(s.isLunch){
        cell = `<div class="empty">🍽️ Almoço</div>`;
      }
      html += `<td class="slot ${s.isLunch?"blocked":""}" data-date="${fmtDateBR(d)}" data-time="${s.hhmm}" data-blocked="${s.isLunch?1:0}">${cell}</td>`;
    }
    html += `</tr>`;
  }
  html += `</tbody></table></div>`;
  $("agenda").innerHTML = html;

  document.querySelectorAll(".slot").forEach(td => {
    td.addEventListener("click", (e) => {
      const appt = e.target.closest(".appt");
      if(appt){
        openEdit(Number(appt.dataset.id));
        return;
      }
      if(td.dataset.blocked === "1") return;
      if(state.schedule && state.schedule.closed) return;
      if(state.me.role !== "admin" && !state.me.approved) return;
      const [dd,mm,yyyy] = td.dataset.date.split("/").map(Number);
      const [hh,mi] = td.dataset.time.split(":").map(Number);
      const dt = new Date(yyyy, mm-1, dd, hh, mi);
      $("newStart").value = isoNoSeconds(dt);
      $("newError").classList.add("d-none");
      bootstrap.Modal.getOrCreateInstance($("#modalNew")).show();
    });
  });
}

async function loadSchedule(){
  const day = dayISO(state.cursor);
  state.schedule = await api(`/api/schedule?day=${encodeURIComponent(day)}`);
}

async function loadAppts(){
  const {start, end} = getRange();
  const qs = new URLSearchParams({
    start: isoNoSeconds(start),
    end: isoNoSeconds(end),
    status: $("statusFilter").value || "Todos"
  });
  const barberId = Number($("barberFilter")?.value || 0);
  if(barberId) qs.set("barber_id", String(barberId));
  state.appts = await api(`/api/appointments?${qs.toString()}`);
}

async function loadStats(){
  const card = $("cardDash");
  if(!card) return;

  const can = (state.me.role === "admin") || (state.me.approved && state.me.perms?.can_view_finance);
  if(!can){ card.style.display = "none"; return; }
  card.style.display = "block";

  const {start, end} = getRange();
  const qs = new URLSearchParams({start: isoNoSeconds(start), end: isoNoSeconds(end)});
  const barberId = Number($("barberFilter")?.value || 0);
  if(barberId) qs.set("barber_id", String(barberId));

  const st = await api(`/api/stats?${qs.toString()}`);
  $("kpiTotal").textContent = fmtMoney(st.total_done);
  $("kpiCount").textContent = String(st.count_done);
  $("kpiTicket").textContent = fmtMoney(st.ticket);

  const ag = st.by_status.find(x=>x.status==="Agendado")?.count || 0;
  $("kpiAg").textContent = String(ag);

  $("payBreakdown").innerHTML = (st.by_payment.length ? st.by_payment.map(p=>{
    return `<div class="d-flex justify-content-between border-bottom py-1">
      <div>${p.payment_method}</div>
      <div class="fw-semibold">${fmtMoney(p.total)} <span class="text-muted">(${p.count})</span></div>
    </div>`;
  }).join("") : `<div class="text-muted">Sem dados no período.</div>`);

  const cbox = $("commissionBox");
  if(cbox){
    if(state.me.role === "admin" && st.commissions && st.commissions.length){
      cbox.style.display = "block";
      $("commissionList").innerHTML = st.commissions.map(x=>`<div class="d-flex justify-content-between border-bottom py-1"><div>${x.barber_name}</div><div class="fw-semibold">${fmtMoney(x.total)} • Comissão: ${fmtMoney(x.commission)}</div></div>`).join("");
    }else{
      cbox.style.display = "none";
    }
  }
}

async function loadMeta(){
  state.services = await api("/api/services");
  state.clients = await api("/api/clients");
  state.barbers = await api("/api/barbers");

  renderServiceSelect("newService");
  renderServiceSelect("editService");

  if(state.me.role === "admin"){
    $("newBarberBox").style.display = "block";
    $("editBarberBox").style.display = "block";
    renderBarberSelect("newBarber", state.barbers[0]?.id);
    renderBarberSelect("editBarber", state.barbers[0]?.id);
  }

  const cardQuick = $("cardQuick");
  if(cardQuick){
    const allowAny = (state.me.role === "admin") || (state.me.approved && (state.me.perms?.can_manage_clients || state.me.perms?.can_manage_services));
    cardQuick.style.display = allowAny ? "block" : "none";
    $("boxClients").style.display = ((state.me.role==="admin") || (state.me.approved && state.me.perms?.can_manage_clients)) ? "block" : "none";
    $("boxServices").style.display = ((state.me.role==="admin") || (state.me.approved && state.me.perms?.can_manage_services)) ? "block" : "none";
  }

  // datalist clients
  let dl = document.getElementById("clientsDatalist");
  if(!dl){
    dl = document.createElement("datalist");
    dl.id = "clientsDatalist";
    document.body.appendChild(dl);
  }
  dl.innerHTML = state.clients.map(c => `<option value="${c.name}"></option>`).join("");
  $("newClient").setAttribute("list", "clientsDatalist");
  $("editClient").setAttribute("list", "clientsDatalist");

  renderFilters();
}

function showErr(elId, msg){
  const el = $(elId);
  if(!el) return;
  el.textContent = msg;
  el.classList.remove("d-none");
}

async function refresh(){
  await loadSchedule();
  await loadAppts();
  renderAgenda();
  await loadStats();
}

async function createAppt(){
  try{
    $("newError").classList.add("d-none");
    const payload = {
      start_at: $("newStart").value,
      duration_min: Number($("newDur").value),
      client_name: $("newClient").value,
      service_name: $("newService").value,
      price: $("newPrice").value,
      payment_method: $("newPay").value,
      status: $("newStatus").value,
      notes: $("newNotes").value
    };
    if(state.me.role === "admin"){
      payload.barber_id = Number($("newBarber").value || 0);
    }
    await api("/api/appointments", {method:"POST", body: JSON.stringify(payload)});
    bootstrap.Modal.getOrCreateInstance($("#modalNew")).hide();
    await loadMeta();
    await refresh();
  }catch(e){
    showErr("newError", e.message);
  }
}

function findAppt(id){ return state.appts.find(a=>a.id===id); }

async function openEdit(id){
  const a = findAppt(id);
  if(!a) return;
  if(state.me.role !== "admin" && !state.me.approved) return;

  $("editId").value = id;
  $("editStart").value = toLocalInput(a.start_at);
  const dur = Math.round((new Date(a.end_at) - new Date(a.start_at))/60000);
  $("editDur").value = String(dur);
  $("editClient").value = a.client_name;
  renderServiceSelect("editService", a.service_name);
  $("editPrice").value = a.price ?? "";
  $("editPay").value = a.payment_method ?? "";
  $("editStatus").value = a.status;
  $("editNotes").value = a.notes ?? "";
  $("editError").classList.add("d-none");

  if(state.me.role === "admin"){
    renderBarberSelect("editBarber", a.barber_id);
  }

  bootstrap.Modal.getOrCreateInstance($("#modalEdit")).show();
}

async function saveEdit(){
  try{
    $("editError").classList.add("d-none");
    const id = Number($("editId").value);
    const payload = {
      start_at: $("editStart").value,
      duration_min: Number($("editDur").value),
      client_name: $("editClient").value,
      service_name: $("editService").value,
      price: $("editPrice").value,
      payment_method: $("editPay").value,
      status: $("editStatus").value,
      notes: $("editNotes").value
    };
    if(state.me.role === "admin"){
      payload.barber_id = Number($("editBarber").value || 0);
    }
    await api(`/api/appointments/${id}`, {method:"PUT", body: JSON.stringify(payload)});
    bootstrap.Modal.getOrCreateInstance($("#modalEdit")).hide();
    await loadMeta();
    await refresh();
  }catch(e){
    showErr("editError", e.message);
  }
}

async function deleteAppt(){
  const id = Number($("editId").value);
  if(!confirm("Excluir esse agendamento?")) return;
  await api(`/api/appointments/${id}`, {method:"DELETE"});
  bootstrap.Modal.getOrCreateInstance($("#modalEdit")).hide();
  await refresh();
}

async function addService(){
  try{
    const name = $("svcName").value.trim();
    const price = $("svcPrice").value.trim();
    const dur = $("svcDur").value.trim() || "30";
    if(!name) return;
    await api("/api/services", {method:"POST", body: JSON.stringify({name, price: price===""?null:price, duration_min: Number(dur)})});
    $("svcName").value = ""; $("svcPrice").value = "";
    await loadMeta();
  }catch(e){
    alert(e.message);
  }
}

async function addClient(){
  try{
    const name = $("cliName").value.trim();
    const phone = $("cliPhone").value.trim();
    if(!name) return;
    await api("/api/clients", {method:"POST", body: JSON.stringify({name, phone})});
    $("cliName").value = ""; $("cliPhone").value = "";
    await loadMeta();
  }catch(e){
    alert(e.message);
  }
}

function setupInstall(){
  window.addEventListener("beforeinstallprompt", (e)=>{
    e.preventDefault();
    state.installPrompt = e;
    $("btnInstall").style.display = "inline-block";
  });
  $("btnInstall").addEventListener("click", async ()=>{
    if(!state.installPrompt) return;
    state.installPrompt.prompt();
    await state.installPrompt.userChoice;
    state.installPrompt = null;
    $("btnInstall").style.display = "none";
  });
}

function setupUI(){
  $("viewMode").addEventListener("change", async (e)=>{ state.viewMode = e.target.value; await refresh(); });
  $("statusFilter").addEventListener("change", async ()=>{ await refresh(); });
  $("barberFilter").addEventListener("change", async ()=>{ await refresh(); });

  $("btnPrev").addEventListener("click", async ()=>{ state.cursor = addDays(state.cursor, state.viewMode==="day"?-1:-7); await refresh(); });
  $("btnNext").addEventListener("click", async ()=>{ state.cursor = addDays(state.cursor, state.viewMode==="day"?1:7); await refresh(); });

  const btnRefresh = $("btnRefresh");
  if(btnRefresh) btnRefresh.addEventListener("click", refresh);

  $("btnCreate").addEventListener("click", createAppt);
  $("btnSaveEdit").addEventListener("click", saveEdit);
  $("btnDelete").addEventListener("click", deleteAppt);

  const btnAddSvc = $("btnAddSvc");
  if(btnAddSvc) btnAddSvc.addEventListener("click", addService);
  const btnAddCli = $("btnAddCli");
  if(btnAddCli) btnAddCli.addEventListener("click", addClient);

  const now = new Date();
  now.setSeconds(0,0);
  const m = now.getMinutes();
  now.setMinutes(m < 30 ? 30 : 0);
  if(m >= 30) now.setHours(now.getHours()+1);
  $("newStart").value = isoNoSeconds(now);
}

// Admin pages
async function initAdminUsers(){
  if(!location.pathname.startsWith("/admin/users")) return;
  const tbody = document.querySelector("#tblUsers tbody");
  const uErr = $("uErr"); const uOk = $("uOk");

  const refreshUsers = async ()=>{
    const users = await api("/api/users");
    tbody.innerHTML = "";
    for(const u of users){
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><input class="form-control form-control-sm" value="${u.display_name}" data-k="display_name"></td>
        <td class="text-muted">${u.username}</td>
        <td>${u.role}</td>
        <td><input type="checkbox" ${u.approved?"checked":""} data-k="approved"></td>
        <td><input type="checkbox" ${u.can_manage_clients?"checked":""} data-k="can_manage_clients"></td>
        <td><input type="checkbox" ${u.can_manage_services?"checked":""} data-k="can_manage_services"></td>
        <td><input type="checkbox" ${u.can_view_finance?"checked":""} data-k="can_view_finance"></td>
        <td><input type="checkbox" ${u.can_view_all_agendas?"checked":""} data-k="can_view_all_agendas"></td>
        <td><input type="checkbox" ${u.can_approve_bookings?"checked":""} data-k="can_approve_bookings"></td>
        <td><input class="form-control form-control-sm" value="${u.commission_percent ?? 0}" data-k="commission_percent" inputmode="decimal"></td>
        <td><input class="form-control form-control-sm" placeholder="nova senha" data-k="password"></td>
        <td><button class="btn btn-dark btn-sm">Salvar</button></td>
      `;
      tr.querySelector("button").addEventListener("click", async ()=>{
        uErr.classList.add("d-none"); uOk.classList.add("d-none");
        const payload = {id: u.id};
        tr.querySelectorAll("[data-k]").forEach(inp=>{
          const k = inp.dataset.k;
          if(inp.type === "checkbox") payload[k] = inp.checked;
          else payload[k] = inp.value.trim();
        });
        if(!payload.password) delete payload.password;
        try{
          await api("/api/users", {method:"PUT", body: JSON.stringify(payload)});
          uOk.textContent = "Salvo!";
          uOk.classList.remove("d-none");
          await refreshUsers();
        }catch(e){
          uErr.textContent = e.message;
          uErr.classList.remove("d-none");
        }
      });
      tbody.appendChild(tr);
    }
  };

  $("btnCreateUser").addEventListener("click", async ()=>{
    uErr.classList.add("d-none"); uOk.classList.add("d-none");
    try{
      const payload = {
        display_name: $("nuName").value.trim(),
        username: $("nuUser").value.trim(),
        password: $("nuPass").value.trim(),
        role: $("nuRole").value
      };
      await api("/api/users", {method:"POST", body: JSON.stringify(payload)});
      $("nuName").value=""; $("nuUser").value=""; $("nuPass").value="";
      uOk.textContent = "Usuário criado!";
      uOk.classList.remove("d-none");
      await refreshUsers();
    }catch(e){
      uErr.textContent = e.message;
      uErr.classList.remove("d-none");
    }
  });

  await refreshUsers();
}

async function initAdminConfig(){
  if(!location.pathname.startsWith("/admin/config")) return;
  const cOk = $("cOk"); const cErr = $("cErr");
  const cfg = await api("/api/config");
  $("open_time").value = cfg.open_time;
  $("close_time").value = cfg.close_time;
  $("slot_min").value = cfg.slot_min;
  $("lunch_start").value = cfg.lunch_start;
  $("lunch_end").value = cfg.lunch_end;

  $("btnSaveCfg").addEventListener("click", async ()=>{
    cOk.classList.add("d-none"); cErr.classList.add("d-none");
    try{
      await api("/api/config", {method:"PUT", body: JSON.stringify({
        open_time: $("open_time").value.trim(),
        close_time: $("close_time").value.trim(),
        slot_min: Number($("slot_min").value),
        lunch_start: $("lunch_start").value.trim(),
        lunch_end: $("lunch_end").value.trim()
      })});
      cOk.classList.remove("d-none");
    }catch(e){
      cErr.textContent = e.message;
      cErr.classList.remove("d-none");
    }
  });
}

async function initAdminOverrides(){
  if(!location.pathname.startsWith("/admin/overrides")) return;
  const tbody = document.querySelector("#tblOv tbody");
  const ovErr = $("ovErr");

  async function refreshOv(){
    const items = await api("/api/overrides");
    tbody.innerHTML = "";
    for(const o of items){
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${o.day}</td>
        <td>${o.closed ? "Sim" : "Não"}</td>
        <td>${(o.lunch_start||"—")} → ${(o.lunch_end||"—")}</td>
        <td><button class="btn btn-outline-danger btn-sm">Excluir</button></td>
      `;
      tr.querySelector("button").addEventListener("click", async ()=>{
        await api(`/api/overrides?id=${o.id}`, {method:"DELETE"});
        await refreshOv();
      });
      tbody.appendChild(tr);
    }
  }

  $("btnSaveOv").addEventListener("click", async ()=>{
    ovErr.classList.add("d-none");
    try{
      await api("/api/overrides", {method:"POST", body: JSON.stringify({
        day: $("ovDay").value,
        closed: $("ovClosed").checked,
        lunch_start: $("ovLunchStart").value.trim() || null,
        lunch_end: $("ovLunchEnd").value.trim() || null
      })});
      await refreshOv();
    }catch(e){
      ovErr.textContent = e.message;
      ovErr.classList.remove("d-none");
    }
  });

  await refreshOv();
}

async function initAdminLogs(){
  if(!location.pathname.startsWith("/admin/logs")) return;
  const tbody = document.querySelector("#tblLogs tbody");
  $("btnLoadLogs").addEventListener("click", async ()=>{
    const items = await api("/api/logs?limit=300");
    tbody.innerHTML = items.map(x=>`<tr><td>${x.at}</td><td>${x.actor}</td><td>${x.action}</td><td>${x.entity}</td><td>${x.entity_id||""}</td><td>${x.details||""}</td></tr>`).join("");
  });
  $("btnLoadLogs").click();
}

async function initAdminPending(){
  if(!location.pathname.startsWith("/admin/pending")) return;
  const tbody = document.querySelector("#tblPending tbody");
  const pErr = $("pErr");

  async function refresh(){
    pErr.classList.add("d-none");
    const items = await api("/api/pending");
    tbody.innerHTML = "";
    for(const a of items){
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${a.start_at.replace("T"," ")}</td>
        <td>${a.barber_name}</td>
        <td>${a.client_name} <span class="text-muted">${a.client_phone||""}</span></td>
        <td>${a.service_name}</td>
        <td>${a.price!=null?fmtMoney(a.price):"—"}</td>
        <td class="d-flex gap-2">
          <button class="btn btn-success btn-sm">Aprovar</button>
          <button class="btn btn-outline-danger btn-sm">Rejeitar</button>
        </td>
      `;
      const btnA = tr.querySelectorAll("button")[0];
      const btnR = tr.querySelectorAll("button")[1];
      btnA.addEventListener("click", async ()=>{
        try{ await api(`/api/pending/${a.id}/approve`, {method:"POST"}); await refresh(); }
        catch(e){ pErr.textContent=e.message; pErr.classList.remove("d-none"); }
      });
      btnR.addEventListener("click", async ()=>{
        try{ await api(`/api/pending/${a.id}/reject`, {method:"POST"}); await refresh(); }
        catch(e){ pErr.textContent=e.message; pErr.classList.remove("d-none"); }
      });
      tbody.appendChild(tr);
    }
  }

  $("btnLoadPending").addEventListener("click", refresh);
  $("btnLoadPending").click();
}

(async function init(){
  try{
    state.me = await api("/api/me");
  }catch(e){
    return;
  }
  setupInstall();

  if($("agenda")){
    setupUI();
    await loadMeta();
    await refresh();
  }

  await initAdminUsers();
  await initAdminConfig();
  await initAdminOverrides();
  await initAdminLogs();
  await initAdminPending();
})();