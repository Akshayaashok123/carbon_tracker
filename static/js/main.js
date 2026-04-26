/**
 * Campus Carbon Tracker — main.js
 * 8-screen SPA with bottom nav
 */

// API key is kept server-side — autocomplete goes through /api/autocomplete proxy

// ── Session ─────────────────────────────────────────────────
let SESSION = { username: '', department: '' };
let lastResult = null;
let impactChart = null;
let allLbData   = [];

// ═══════════════════════════════════════════════════════════
//  FEATURE 1 — ANIMATED NUMBER COUNTER
//  Usage: animateCount(el, from, to, decimals, suffix, duration)
// ═══════════════════════════════════════════════════════════
function animateCount(el, from, to, decimals=1, suffix='', duration=900) {
  if (!el) return;
  const start = performance.now();
  const diff  = to - from;
  function step(now) {
    const elapsed = now - start;
    const progress = Math.min(elapsed / duration, 1);
    // Ease-out cubic
    const ease = 1 - Math.pow(1 - progress, 3);
    const val  = from + diff * ease;
    el.textContent = val.toFixed(decimals) + suffix;
    if (progress < 1) requestAnimationFrame(step);
    else el.textContent = to.toFixed(decimals) + suffix;
  }
  requestAnimationFrame(step);
}

// ═══════════════════════════════════════════════════════════
//  FEATURE 2 — CONFETTI BURST
//  Fires colourful confetti from a target element
// ═══════════════════════════════════════════════════════════
function fireConfetti(targetEl) {
  const colors = ['#667eea','#764ba2','#11998e','#38ef7d','#ffd200','#f7971e','#ff6b6b','#a78bfa'];
  const count  = 80;
  const canvas = document.createElement('canvas');
  canvas.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:99999;';
  canvas.width  = window.innerWidth;
  canvas.height = window.innerHeight;
  document.body.appendChild(canvas);
  const ctx = canvas.getContext('2d');

  // Get origin point
  const rect = targetEl ? targetEl.getBoundingClientRect() : null;
  const ox   = rect ? rect.left + rect.width / 2  : canvas.width  / 2;
  const oy   = rect ? rect.top  + rect.height / 2 : canvas.height / 3;

  const particles = Array.from({length: count}, () => ({
    x: ox, y: oy,
    vx: (Math.random() - 0.5) * 18,
    vy: (Math.random() - 1.2) * 16,
    color: colors[Math.floor(Math.random() * colors.length)],
    size: Math.random() * 8 + 4,
    rot: Math.random() * 360,
    rotV: (Math.random() - 0.5) * 8,
    shape: Math.random() > 0.5 ? 'rect' : 'circle',
    alpha: 1,
  }));

  let frame;
  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    let alive = false;
    particles.forEach(p => {
      p.x  += p.vx;
      p.y  += p.vy;
      p.vy += 0.5; // gravity
      p.vx *= 0.98;
      p.rot += p.rotV;
      p.alpha -= 0.018;
      if (p.alpha <= 0) return;
      alive = true;
      ctx.save();
      ctx.globalAlpha = Math.max(0, p.alpha);
      ctx.fillStyle   = p.color;
      ctx.translate(p.x, p.y);
      ctx.rotate(p.rot * Math.PI / 180);
      if (p.shape === 'rect') ctx.fillRect(-p.size/2, -p.size/2, p.size, p.size * 0.6);
      else { ctx.beginPath(); ctx.arc(0, 0, p.size/2, 0, Math.PI*2); ctx.fill(); }
      ctx.restore();
    });
    if (alive) frame = requestAnimationFrame(draw);
    else { cancelAnimationFrame(frame); canvas.remove(); }
  }
  frame = requestAnimationFrame(draw);
}

// ═══════════════════════════════════════════════════════════
//  FEATURE 3 — LIVE CO₂ PREVIEW ON CALCULATE SCREEN
// ═══════════════════════════════════════════════════════════
const CO2_RATES = {
  car_solo: 0.171, carpool: 0.068, motorcycle: 0.103,
  bus: 0.089, metro: 0.041, bicycle: 0.0, walk: 0.0,
};
const AVG_CAMPUS_KM = 15; // assumed distance when no location confirmed

function updateLivePreview() {
  const previewEl = document.getElementById('livePreview');
  if (!previewEl) return;

  const transport  = document.getElementById('transport')?.value || 'car_solo';
  const food       = parseFloat(document.getElementById('food')?.value || 1.5);
  const electricity= parseFloat(document.getElementById('electricity')?.value || 4);

  // Use confirmed distance if available, otherwise show campus average estimate
  const oLat = document.getElementById('originLat')?.value;
  const dLat  = document.getElementById('destLat')?.value;
  const distKm = (oLat && dLat) ? null : AVG_CAMPUS_KM; // null = waiting for real calc

  const co2PerKm  = CO2_RATES[transport] || 0.171;
  const commuteCo2= (distKm || AVG_CAMPUS_KM) * co2PerKm;
  const elecCo2   = electricity * 0.3;
  const total     = commuteCo2 + food + elecCo2;
  const isEstimate= !oLat || !dLat;

  // Colour the preview based on footprint level
  const color = total < 3 ? '#11998e' : total < 6 ? '#f7971e' : '#e03131';
  const label = total < 3 ? '🟢 Low' : total < 6 ? '🟡 Medium' : '🔴 High';

  previewEl.style.display = 'block';
  previewEl.style.borderLeftColor = color;
  previewEl.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
      <span style="font-size:0.8em;font-weight:700;color:#475569;">
        <span class="live-dot"></span>Live Estimate
        ${isEstimate ? '<span style="font-size:0.82em;color:#94a3b8;font-weight:500"> (avg distance)</span>' : ''}
      </span>
      <span style="font-size:0.74em;color:${color};font-weight:800;background:${color}18;padding:3px 10px;border-radius:20px;">${label}</span>
    </div>
    <div style="font-size:2.2em;font-weight:900;color:${color};line-height:1;letter-spacing:-1px;" id="liveTotal">${total.toFixed(1)} <span style="font-size:0.45em;font-weight:700;">kg CO₂</span></div>
    <div style="display:flex;gap:10px;margin-top:10px;flex-wrap:wrap;">
      <span style="font-size:0.75em;background:#eef2ff;color:#4f46e5;padding:3px 9px;border-radius:20px;font-weight:700;">🚗 ${commuteCo2.toFixed(2)} kg</span>
      <span style="font-size:0.75em;background:#f0fdf4;color:#059669;padding:3px 9px;border-radius:20px;font-weight:700;">🍱 ${food.toFixed(2)} kg</span>
      <span style="font-size:0.75em;background:#fffbeb;color:#d97706;padding:3px 9px;border-radius:20px;font-weight:700;">💡 ${elecCo2.toFixed(2)} kg</span>
    </div>
    <div style="margin-top:10px;">
      <div style="height:6px;background:#f1f5f9;border-radius:3px;overflow:hidden;">
        <div style="height:100%;width:${Math.min(100,(total/10)*100)}%;background:linear-gradient(90deg,${color},${color}aa);border-radius:3px;transition:width .4s ease;"></div>
      </div>
      <div style="display:flex;justify-content:space-between;margin-top:3px;font-size:0.67em;color:#94a3b8;font-weight:500;">
        <span>0 kg</span><span>5 kg (avg)</span><span>10 kg</span>
      </div>
    </div>`;
}

// ── Bottom nav config ───────────────────────────────────────
const NAV_ITEMS = [
  { id:'dashboard',  icon:'🏠', label:'Home'       },
  { id:'calculate',  icon:'📝', label:'Log'        },
  { id:'leaderboard',icon:'🏆', label:'Rankings'   },
  { id:'deptbattle', icon:'⚔️', label:'Battle'     },
  { id:'badges',     icon:'🏅', label:'Badges'     },
  { id:'game',       icon:'🎮', label:'Game'       },
];

function buildNavs() {
  NAV_ITEMS.forEach(item => {
    const navEl = document.getElementById('nav-' + item.id);
    if (!navEl) return;
    navEl.innerHTML = NAV_ITEMS.map(n => `
      <button class="nav-btn ${n.id === item.id ? 'on' : ''}"
              onclick="showScreen('${n.id}')">
        <span class="nav-icon">${n.icon}</span>
        ${n.label}
      </button>`).join('');
  });
}

// ── Screen navigation ────────────────────────────────────────
function showScreen(name) {
  // screens use 'active' class to show/hide
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  const el = document.getElementById('s-' + name);
  if (el) el.classList.add('active');

  switch(name) {
    case 'dashboard':   loadDashboard();    break;
    case 'leaderboard': updateLeaderboard();break;
    case 'deptbattle':  loadDeptBattle();   break;
    case 'badges':      loadBadgesScreen(); break;
    case 'game':        initGame();         break;
  }
}

// ═══════════════════════════════════════════════════════════
//  S1 — LOGIN
// ═══════════════════════════════════════════════════════════
document.getElementById('loginBtn').addEventListener('click', () => {
  const name = document.getElementById('loginName').value.trim();
  const dept = document.getElementById('loginDept').value;
  const err  = document.getElementById('loginErr');   // new ID in HTML
  if (!name || !dept) {
    if (err) err.classList.remove('hidden');
    return;
  }
  if (err) err.classList.add('hidden');
  SESSION.username   = name;
  SESSION.department = dept;

  // Update all user chips (new IDs)
  const pill = `👤 ${name}`;
  ['dashChip','calcChip','badgesChip'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.textContent = pill;
  });
  const gl = document.getElementById('gameLabel');
  if (gl) gl.textContent = `${name} · ${dept}`;

  buildNavs();
  showScreen('dashboard');
});
document.getElementById('loginName').addEventListener('keydown', e => {
  if (e.key === 'Enter') document.getElementById('loginBtn').click();
});

// ═══════════════════════════════════════════════════════════
//  S2 — DASHBOARD
// ═══════════════════════════════════════════════════════════
async function loadDashboard() {
  try {
    const res  = await fetch(`/api/badges/${encodeURIComponent(SESSION.username)}`);
    const data = await res.json();
    const streak = data.streak || 0;
    const badges = data.badges || [];

    // Greeting
    const hour  = new Date().getHours();
    const greet = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';
    const dg = document.getElementById('dashGreet');
    const ds = document.getElementById('dashSub');
    if (dg) dg.textContent = `${greet}, ${SESSION.username}! 👋`;
    if (ds) ds.textContent = streak > 0 ? `You're on a ${streak}-day green streak! 🔥` : 'Start tracking your carbon footprint today.';

    // Streak banner
    const banner = document.getElementById('dashStreak');
    if (banner && streak > 0) {
      banner.classList.remove('hidden');
      const sn = document.getElementById('dashStreakNum');
      const sm = document.getElementById('dashStreakMsg');
      if (sn) animateCount(sn, 0, streak, 0, '', 600);
      if (sm) sm.textContent = streak >= 7 ? '⚡ On fire!' : streak >= 3 ? '🔥 Keep going!' : `${3-streak} more to 🔥`;
    }

    // Avg + days
    if (allLbData.length) {
      const me = allLbData.find(u => u.username === SESSION.username);
      if (me) {
        const da = document.getElementById('dashAvg');
        const dd = document.getElementById('dashDays');
        if (da) animateCount(da, 0, me.avg_carbon, 2, ' kg', 800);
        if (dd) animateCount(dd, 0, me.entries||0, 0, '', 600);
      }
    }

    // Badges preview
    const badgesEl = document.getElementById('dashBadges');
    if (badgesEl && badges.length) {
      badgesEl.innerHTML = badges.slice(0,6).map(b =>
        `<div class="bpill" data-tip="${b.desc}">${b.emoji} ${b.name}</div>`
      ).join('');
    }

    // Today's summary
    if (lastResult) {
      const card = document.getElementById('todayCard');
      const summ = document.getElementById('todaySummary');
      if (card) card.style.display = 'block';
      if (summ) summ.innerHTML = `
        <div class="bk-row"><span>Total CO₂</span><strong>${lastResult.total} kg</strong></div>
        <div class="bk-row"><span>Transport</span><strong>${lastResult.transport_label||'—'}</strong></div>
        <div class="bk-row"><span>Distance</span><strong>${lastResult.distance_km} km</strong></div>
      `;
    }
  } catch(e) { console.error('Dashboard load error:', e); }
}

// ═══════════════════════════════════════════════════════════
//  AUTOCOMPLETE
// ═══════════════════════════════════════════════════════════
function attachAutocomplete(inputId, dropdownId, statusId, latId, lonId) {
  const input    = document.getElementById(inputId);
  const dropdown = document.getElementById(dropdownId);
  const statusEl = document.getElementById(statusId);
  const latInput = document.getElementById(latId);
  const lonInput = document.getElementById(lonId);
  let debounceTimer = null, focusIndex = -1;

  const typeIcon = t => ({'establishment':'🏢','premise':'🏠','route':'🛣️',
    'sublocality':'🏘️','locality':'🏙️','transit_station':'🚉'}[t] || '📍');
  const esc = s => String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

  function close() { dropdown.classList.add('hidden'); focusIndex = -1; }

  function confirm(label, lat, lon) {
    input.value = label; latInput.value = lat; lonInput.value = lon;
    input.classList.add('ok'); input.classList.remove('bad');
    statusEl.textContent = '✅'; close();
  }

  async function fetch_suggestions(q) {
    dropdown.innerHTML = '<div class="ac-msg">🔍 Searching…</div>';
    dropdown.classList.remove('hidden');
    try {
      // Calls Flask proxy — OLA Maps key stays server-side
      const r = await fetch(`/api/autocomplete?q=${encodeURIComponent(q)}`);
      const results = await r.json();
      if (!results.length) { dropdown.innerHTML='<div class="ac-msg">No results found.</div>'; return; }
      focusIndex = -1;
      dropdown.innerHTML = results.map(p => `
        <div class="ac-row"
          data-lat="${p.lat}"
          data-lon="${p.lon}"
          data-label="${esc(p.label)}">
          <span>${typeIcon(p.type)}</span>
          <div>
            <div class="ac-m">${esc(p.main)}</div>
            <div class="ac-s">${esc(p.sub)}</div>
          </div>
        </div>`).join('');
      statusEl.textContent = '';
      dropdown.querySelectorAll('.ac-row').forEach(item => {
        item.addEventListener('mousedown', e => {
          e.preventDefault();
          confirm(item.dataset.label, item.dataset.lat, item.dataset.lon);
        });
      });
    } catch { statusEl.textContent = '❌'; }
  }

  input.addEventListener('input', () => {
    latInput.value=''; lonInput.value='';
    input.classList.remove('ok','bad');
    statusEl.textContent='';
    clearTimeout(debounceTimer);
    const q = input.value.trim();
    if (q.length < 3) { close(); return; }
    statusEl.textContent='⏳';
    debounceTimer = setTimeout(() => fetch_suggestions(q), 320);
  });

  input.addEventListener('keydown', e => {
    const items = [...dropdown.querySelectorAll('.ac-row')];
    if (!items.length) return;
    if (e.key==='ArrowDown')  { e.preventDefault(); focusIndex=Math.min(focusIndex+1,items.length-1); }
    else if(e.key==='ArrowUp'){ e.preventDefault(); focusIndex=Math.max(focusIndex-1,0); }
    else if(e.key==='Enter' && focusIndex>=0){ e.preventDefault(); items[focusIndex].dispatchEvent(new Event('mousedown')); return; }
    else if(e.key==='Escape'){ close(); return; }
    items.forEach((el,i)=>el.classList.toggle('hi',i===focusIndex));
  });

  input.addEventListener('blur', () => {
    setTimeout(() => {
      if (!latInput.value && input.value.trim()) {
        input.classList.add('bad'); statusEl.textContent='⚠️';
      }
      close();
    }, 180);
  });

  document.addEventListener('click', e => {
    if (!input.contains(e.target) && !dropdown.contains(e.target)) close();
  });
}

attachAutocomplete('origin',      'originDrop', 'originSt', 'originLat', 'originLon');
attachAutocomplete('destination', 'destDrop',   'destSt',   'destLat',   'destLon');

// ── Live preview: update on any form input change ────────
['transport','food','electricity'].forEach(id => {
  document.getElementById(id)?.addEventListener('change', updateLivePreview);
  document.getElementById(id)?.addEventListener('input',  updateLivePreview);
});
// Also update when location is confirmed (hidden inputs change)
document.getElementById('originLat')?.addEventListener('change', updateLivePreview);
document.getElementById('destLat')?.addEventListener('change',   updateLivePreview);

// Initial render
updateLivePreview();

// ═══════════════════════════════════════════════════════════
//  S3 — CALCULATE FORM
// ═══════════════════════════════════════════════════════════
const receiptInput = document.getElementById('receiptUpload');
if (receiptInput) {
  receiptInput.addEventListener('change', async e => {
    const file = e.target.files[0];
    if (!file) return;
    const fd = new FormData(); fd.append('file', file);
    const food = document.getElementById('food');
    food.disabled = true;
    try {
      const r = await fetch('/api/ocr-receipt', { method:'POST', body:fd });
      const d = await r.json();
      if (d.carbon_value) food.value = d.carbon_value;
    } catch {}
    finally { food.disabled = false; }
  });
}

document.getElementById('carbonForm').addEventListener('submit', async e => {
  e.preventDefault();
  const btn     = document.getElementById('submitBtn');
  const formErr = document.getElementById('formErr');
  const oLat    = document.getElementById('originLat').value;
  const dLat    = document.getElementById('destLat').value;
  formErr.classList.add('hidden');

  if (!oLat || !dLat) {
    formErr.textContent='⚠️ Please select both locations from the dropdown.';
    formErr.classList.remove('hidden');
    return;
  }

  btn.disabled=true; btn.textContent='Calculating…';
  const payload = {
    username:    SESSION.username,
    department:  SESSION.department,
    origin_lat:  oLat,
    origin_lon:  document.getElementById('originLon').value,
    dest_lat:    dLat,
    dest_lon:    document.getElementById('destLon').value,
    transport:   document.getElementById('transport').value,
    food:        parseFloat(document.getElementById('food').value),
    electricity: parseFloat(document.getElementById('electricity').value),
  };

  try {
    const res    = await fetch('/api/calculate', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const result = await res.json();
    if (result.error) throw new Error(result.error);
    lastResult = result;
    populateResults(result, payload);
    showScreen('results');
  } catch(err) {
    formErr.textContent = '❌ '+err.message;
    formErr.classList.remove('hidden');
  } finally {
    btn.disabled=false; btn.textContent='⚡ Calculate My Footprint';
  }
});

// ═══════════════════════════════════════════════════════════
//  S4 — RESULTS
// ═══════════════════════════════════════════════════════════
function populateResults(result, payload) {
  // Animated counters
  animateCount(document.getElementById('totalCarbon'), 0, result.total, 1, ' kg', 1100);

  // Breakdown list (built dynamically)
  const dots = ['#4f46e5','#059669','#7c3aed','#10b981','#f59e0b'];
  const rows = [
    ['🚦 Mode',        result.transport_label||'—', false],
    ['🗺️ Distance',   result.distance_km+' km',    false],
    ['🚗 Commute CO₂', null, result.breakdown.commute],
    ['🍱 Food CO₂',    null, result.breakdown.food],
    ['💡 Electricity', null, result.breakdown.electricity],
  ];
  const bl = document.getElementById('breakdownList');
  if (bl) {
    bl.innerHTML = rows.map(([label, val, num], i) => {
      const id = `bkval${i}`;
      const display = val || (num !== false ? num+' kg' : '—');
      return `<div class="bk-row">
        <span><span class="bk-dot" style="background:${dots[i]}"></span>${label}</span>
        <strong id="${id}">${display}</strong>
      </div>`;
    }).join('');
    // Animate numeric rows
    if (result.breakdown) {
      animateCount(document.getElementById('bkval2'), 0, result.breakdown.commute,   2, ' kg', 900);
      animateCount(document.getElementById('bkval3'), 0, result.breakdown.food,      2, ' kg', 900);
      animateCount(document.getElementById('bkval4'), 0, result.breakdown.electricity,2,' kg', 900);
    }
  }

  // Gallery
  if (result.equivalents) {
    const gg = document.getElementById('galleryGrid');
    if(gg) gg.innerHTML = result.equivalents.map(e =>
      `<div class="gal-card">
        <span class="gal-emoji">${e.emoji}</span>
        <span class="gal-val">${e.value}</span>
        <div class="gal-unit">${e.unit}</div>
        <div class="gal-lbl">${e.label}</div>
      </div>`).join('');
  }

  // Chart
  const canvas = document.getElementById('impactChart');
  if (canvas) {
    if (impactChart) impactChart.destroy();
    impactChart = new Chart(canvas.getContext('2d'), {
      type:'doughnut',
      data:{labels:['Commute','Food','Electricity'],
        datasets:[{data:[result.breakdown.commute,result.breakdown.food,result.breakdown.electricity],
          backgroundColor:['#4f46e5','#10b981','#f59e0b'],borderWidth:0}]},
      options:{cutout:'70%',plugins:{legend:{position:'bottom'}}}
    });
  }

  // Eco planner
  const eco = result.eco_planner;
  if (eco) {
    const routes=[
      {data:eco.fastest, icon:'⚡',label:'Fastest', cc:'#818cf8'},
      {data:eco.cheapest,icon:'💰',label:'Cheapest',cc:'#d97706'},
      {data:eco.greenest,icon:'🍃',label:'Greenest',cc:'#34d399'},
    ];
    const html = routes.filter(r=>r.data).map(r=>
      `<div class="eco-item">
        <div class="eco-top"><strong>${r.icon} ${r.label}</strong>
          <span style="font-weight:800;color:${r.cc}">${r.data.co2} kg CO₂</span></div>
        <span class="eco-meta">⏱️ ${r.data.time} mins · 📍 ${Math.round(r.data.dist)} km</span>
      </div>`).join('');
    const ro=document.getElementById('routeOptions');
    if(ro) ro.innerHTML=html||'<p style="color:#94a3b8;font-size:.84em">No alternatives for this route.</p>';
    const ec=document.getElementById('ecoCard'); if(ec) ec.style.display='block';
  }

  // Tips
  const tips=[];
  if(['car_solo','motorcycle'].includes(payload.transport)) tips.push('🚌 Switching to metro or bus could cut commute emissions by up to 75%!');
  if(result.breakdown.food>2) tips.push('🥗 Choosing a vegetarian meal once more per week saves ~1 kg CO₂.');
  if(result.breakdown.electricity>1.2) tips.push('💻 Unplug chargers and use dark mode to reduce electricity impact.');
  if(!tips.length) tips.push('🌟 Excellent! Your footprint is very low today. Keep it up!');
  const tc=document.getElementById('tipsContent'); if(tc) tc.innerHTML=tips.map(t=>`<div class="tip-box">${t}</div>`).join('');
  const tf=document.getElementById('tipsCard'); if(tf) tf.style.display='block';

  // Coach
  const cc2=document.getElementById('coachCard'); if(cc2) cc2.style.display='block';
  window._lastCoachPayload={username:SESSION.username,transport_label:result.transport_label,distance_km:result.distance_km,breakdown:result.breakdown,total:result.total,eco_planner:result.eco_planner||{}};
  fetchCoachAdvice(window._lastCoachPayload);
}

// Save button
document.getElementById('saveButton').addEventListener('click', async () => {
  if (!lastResult) return;
  const btn = document.getElementById('saveButton');
  btn.textContent='Saving…'; btn.disabled=true;
  try {
    const res = await fetch('/api/save-entry', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        username:   SESSION.username,
        department: SESSION.department,
        total:      lastResult.total,
        transport:  document.getElementById('transport').value,
        food_value: parseFloat(document.getElementById('food').value),
        elec_co2:   lastResult.breakdown.electricity,
      })
    });
    const status = await res.json();
    if (status.success) {
      btn.textContent='✅ Saved!';
      setTimeout(()=>{ btn.textContent='💾 Save & Earn Badges'; },2500);
      showStreakAndBadges(status);

      // 🎉 Fire confetti if any new badges were earned
      if ((status.new_badges||[]).length > 0) {
        fireConfetti(btn);
      }

      (status.new_badges||[]).forEach((b,i)=>setTimeout(()=>showToast(b),i*1200));
    }
  } catch(e){ alert('Error saving: '+e.message); }
  finally { btn.disabled=false; }
});

function showStreakAndBadges(status) {
  const card    = document.getElementById('saveReveal');
  const bannerEl= document.getElementById('saveReveal');
  const badgesEl= document.getElementById('saveReveal');
  card.style.display='block';
  const streak  = status.streak||0;
  const badges  = status.all_badges||[];

  // Streak bar colours
  const bg = streak>=7
    ? 'linear-gradient(135deg,#11998e,#38ef7d)'
    : streak>=3
    ? 'linear-gradient(135deg,#f7971e,#ffd200)'
    : 'linear-gradient(135deg,#ff6b35,#f7c59f)';

  const msg = streak===0 ? 'Log a green day (<5 kg) to start!'
    : streak<3  ? `${3-streak} more day${3-streak>1?'s':''} to 🔥`
    : streak<7  ? `${7-streak} more to ⚡ 7-day streak!`
    : '🌍 Amazing — keep it up!';

  bannerEl.innerHTML = `
    <div style="background:${bg};border-radius:12px;padding:14px 16px;display:flex;align-items:center;gap:14px;color:${streak>=7?'#064e3b':'#7c2d12'};">
      <div style="font-size:2.2em;animation:flicker 1.5s infinite alternate;">🔥</div>
      <div><strong id="streakCountAnim" style="font-size:1.8em;font-weight:800;display:block;line-height:1">0</strong><span style="font-size:0.8em;opacity:0.8">day streak</span></div>
      <div style="margin-left:auto;font-size:0.8em;font-weight:600;text-align:right">${msg}</div>
    </div>`;

  // Animate the streak number
  setTimeout(() => {
    const streakNumEl = document.getElementById('streakCountAnim');
    animateCount(streakNumEl, 0, streak, 0, '', 700);
  }, 50);

  badgesEl.innerHTML = badges.length
    ? badges.map(b=>`<div class="badge-pill" data-tip="${b.desc}">${b.emoji} ${b.name}</div>`).join('')
    : '<span style="color:#94a3b8;font-size:0.85em">No badges yet</span>';
}

// ── AI Coach ─────────────────────────────────────────────
async function fetchCoachAdvice(payload) {
  const bubble = document.getElementById('coachBubble');
  bubble.className='coach-bubble loading';
  bubble.innerHTML=`<div class="typing-dots"><span></span><span></span><span></span></div><span>EcoBot is analysing your footprint…</span>`;
  try {
    const res  = await fetch('/api/coach',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const data = await res.json();
    bubble.className='coach-bubble';
    const text = data.message||data.error||'🌿 Could not get advice right now.';
    bubble.textContent='';
    let i=0;
    const t=setInterval(()=>{ bubble.textContent+=text[i++]; if(i>=text.length) clearInterval(t); },18);
  } catch {
    bubble.className='coach-bubble';
    bubble.textContent='⚠️ Ollama not running. Run: ollama serve';
  }
}

document.getElementById('coachRefresh').addEventListener('click', ()=>{
  if (window._lastCoachPayload) fetchCoachAdvice(window._lastCoachPayload);
});

// ── Toast notifications ──────────────────────────────────
function showToast(badge) {
  document.querySelectorAll('.toast').forEach(t=>t.remove());
  const t = document.createElement('div');
  t.className='toast';
  t.innerHTML=`
    <div class="toast-title">🎉 New Badge Unlocked!</div>
    <div class="toast-body">
      <div class="toast-emoji">${badge.emoji}</div>
      <div><div class="toast-name">${badge.name}</div><div class="toast-desc">${badge.desc}</div></div>
    </div>`;
  document.body.appendChild(t);
  setTimeout(()=>t.remove(),4200);
}

// ═══════════════════════════════════════════════════════════
//  S5 — LEADERBOARD
// ═══════════════════════════════════════════════════════════
async function updateLeaderboard(filterDept='all') {
  try {
    const res = await fetch('/api/leaderboard');
    allLbData = await res.json();
    renderLeaderboard(filterDept);
  } catch { console.error('Leaderboard error'); }
}

function renderLeaderboard(filterDept='all') {
  const data    = filterDept==='all' ? allLbData : allLbData.filter(u=>u.department===filterDept);
  const medals  = ['🥇','🥈','🥉'];
  const depts   = [...new Set(allLbData.map(u=>u.department).filter(Boolean))];

  // Pills
  const pills = document.getElementById('deptPills');
  if (pills) {
    pills.innerHTML = `<button class="pill ${filterDept==='all'?'on':''}" data-dept="all">🌍 All</button>`
      + depts.map(d=>`<button class="pill ${filterDept===d?'on':''}" data-dept="${d}">${d}</button>`).join('');
    pills.querySelectorAll('.pill').forEach(p=>p.addEventListener('click',()=>renderLeaderboard(p.dataset.dept)));
  }

  // Podium — FIXED: always put rank-1 in CENTER regardless of count
  const podium = document.getElementById('podium');
  if (podium) {
    const top3  = data.slice(0,3);
    // Build display order: [2nd, 1st, 3rd] for visual podium shape
    // But only include slots that have data
    let slots = [];
    if (top3.length === 1) slots = [{u:top3[0], cls:'p1', medal:'🥇'}];
    else if (top3.length === 2) slots = [
      {u:top3[1], cls:'p2', medal:'🥈'},
      {u:top3[0], cls:'p1', medal:'🥇'},
    ];
    else slots = [
      {u:top3[1], cls:'p2', medal:'🥈'},
      {u:top3[0], cls:'p1', medal:'🥇'},
      {u:top3[2], cls:'p3', medal:'🥉'},
    ];
    podium.innerHTML = slots.map(({u,cls,medal}) =>
      `<div class="p-step ${cls}">
        <div class="p-medal">${medal}</div>
        <div class="p-name">${u.username}</div>
        <div class="p-dept">${u.department||'—'}</div>
        <div class="p-co2">${u.avg_carbon} kg</div>
      </div>`
    ).join('');
  }

  // Table
  const body = document.getElementById('lbBody');
  if (!body) return;
  const maxCo2 = data.length ? Math.max(...data.map(u=>u.avg_carbon)):1;
  body.innerHTML = data.length===0
    ? `<tr><td colspan="6" style="text-align:center;color:#bbb;padding:24px">No entries yet</td></tr>`
    : data.map((u,i)=>{
        const barW = Math.round((u.avg_carbon/maxCo2)*100);
        return `<tr>
          <td><span class="rank-badge">${i<3?medals[i]:i+1}</span></td>
          <td><strong>${u.username}</strong></td>
          <td style="color:#64748b">${u.department||'—'}</td>
          <td>
            <div class="co2-bar-wrap">
              <div class="co2-bar" style="width:${barW}px"></div>
              <strong class="lb-co2-val" data-val="${u.avg_carbon}">0 kg</strong>
            </div>
          </td>
          <td style="color:#f7971e;font-weight:700">${u.streak?'🔥'+u.streak:'—'}</td>
          <td style="font-size:1.05em;letter-spacing:2px">${(u.badges||[]).slice(0,4).join(' ')||'—'}</td>
        </tr>`;
      }).join('');

  // Animate CO₂ values after render
  setTimeout(() => {
    document.querySelectorAll('.lb-co2-val').forEach(el => {
      const val = parseFloat(el.dataset.val);
      animateCount(el, 0, val, 2, ' kg', 800);
    });
  }, 50);
}

// ═══════════════════════════════════════════════════════════
//  S6 — DEPT BATTLE
// ═══════════════════════════════════════════════════════════
async function loadDeptBattle() {
  const podiumEl = document.getElementById('battlePodium');
  const barsEl   = document.getElementById('battleBars');
  const medals   = ['🥇','🥈','🥉'];
  const classes  = ['b1','b2','b3'];
  const colours  = ['#667eea','#11998e','#f7971e','#e03131','#764ba2','#0ca678','#f03e3e','#1971c2'];

  try {
    const res  = await fetch('/api/dept-battle');
    const data = await res.json();
    if (!data.length) {
      podiumEl.innerHTML = '<p style="color:rgba(255,255,255,0.5);width:100%;text-align:center">No data yet</p>';
      barsEl.innerHTML   = '<p style="color:#bbb;text-align:center;padding:16px">No department data yet.</p>';
      return;
    }

    // Dept Podium — FIXED: 2nd left, 1st center, 3rd right
    const top3  = data.slice(0,3);
    let dslots = [];
    if (top3.length===1) dslots=[{d:top3[0],cls:'d1',medal:'🥇'}];
    else if(top3.length===2) dslots=[{d:top3[1],cls:'d2',medal:'🥈'},{d:top3[0],cls:'d1',medal:'🥇'}];
    else dslots=[{d:top3[1],cls:'d2',medal:'🥈'},{d:top3[0],cls:'d1',medal:'🥇'},{d:top3[2],cls:'d3',medal:'🥉'}];
    podiumEl.innerHTML = dslots.map(({d,cls,medal})=>
      `<div class="d-step ${cls}">
        <div class="d-medal">${medal}</div>
        <div class="d-dept">${d.department}</div>
        <div class="d-co2">${d.avg_co2} kg</div>
        <div class="d-meta">${d.members} member${d.members!==1?'s':''} · 🔥${d.top_streak}</div>
      </div>`
    ).join('');

    // Bars
    const maxCo2 = Math.max(...data.map(d=>d.avg_co2))||1;
    barsEl.innerHTML = data.map((d,i)=>{
      const pct   = Math.round((d.avg_co2/maxCo2)*100);
      const color = colours[i%colours.length];
      return `<div class="dbar-row">
        <div class="dbar-name">${d.department}</div>
        <div class="dbar-bg"><div class="dbar-fill" style="width:${pct}%;background:${color}"></div></div>
        <div class="dbar-val">${d.avg_co2} kg</div>
      </div>
      <div class="dbar-meta">${d.members} member${d.members!==1?'s':''} &nbsp;·&nbsp; 🔥 ${d.top_streak} &nbsp;·&nbsp; 🏅 ${d.badges_count}</div>`;
    }).join('');

    // My rank
    const myRank = data.findIndex(d=>d.department===SESSION.department);
    const rankEl = document.getElementById('myDeptRank');
    if (myRank>=0 && rankEl) {
      rankEl.innerHTML = `<div class="my-rank-banner">Your department <strong>${SESSION.department}</strong> is ranked <strong>#${myRank+1}</strong> 🏫</div>`;
    }
  } catch(e) {
    barsEl.innerHTML=`<p style="color:#e03131;padding:16px">Error: ${e.message}</p>`;
  }
}

// ═══════════════════════════════════════════════════════════
//  S7 — BADGES SCREEN
// ═══════════════════════════════════════════════════════════
const ALL_BADGES = {
  'green_day':      ['🌱','Green Day',      'First day under 5 kg CO₂'],
  'streak_3':       ['🔥','3-Day Streak',   '3 consecutive green days'],
  'streak_7':       ['⚡','7-Day Streak',   '7 consecutive green days'],
  'streak_14':      ['🌟','14-Day Streak',  '14 consecutive green days'],
  'first_cyclist':  ['🚲','First Cyclist',  'Commuted by bicycle'],
  'frequent_rider': ['🚴','Frequent Rider', 'Cycled 5 times total'],
  'first_walker':   ['🚶','First Walker',   'Walked to campus'],
  'transit_lover':  ['🚇','Transit Lover',  'Used metro or bus 5 times'],
  'vegan_day':      ['🥗','Vegan Day',      'Chose a vegan meal'],
  'vegan_week':     ['🌿','Vegan Week',     '7 vegan meals total'],
  'low_energy':     ['💡','Energy Saver',   'Electricity under 1 kg CO₂'],
  'carbon_under2':  ['🏅','Ultra Green',    'Total under 2 kg CO₂ in a day'],
  'eco_warrior':    ['🌍','Eco Warrior',    'Logged 30 days total'],
  'century':        ['💯','Century',        'Logged 100 days total'],
  'carbon_positive':['🏆','Carbon Positive','Beat your real CO₂ in Carbon Catcher!'],
};

async function loadBadgesScreen() {
  try {
    const res  = await fetch(`/api/badges/${encodeURIComponent(SESSION.username)}`);
    const data = await res.json();
    const streak       = data.streak||0;
    const earnedBadges = data.badges||[];
    const earnedIds    = new Set(earnedBadges.map(b=>b.id));

    // Streak card
    const bg = streak>=7?'linear-gradient(135deg,#11998e,#38ef7d)':streak>=3?'linear-gradient(135deg,#f7971e,#ffd200)':'linear-gradient(135deg,#ff6b35,#f7c59f)';
    const tc = streak>=7?'#064e3b':'#7c2d12';
    document.getElementById('streakBigCard').style.background = bg;
    document.getElementById('streakBigCard').style.color      = tc;
    document.getElementById('sbNum').textContent     = streak;
    document.getElementById('sbMsg').textContent       =
      streak===0?'Start logging green days!':
      streak<3?`${3-streak} more to 🔥 badge`:
      streak<7?`${7-streak} more to ⚡ streak`:'🌍 Amazing streak!';

    // Progress
    document.getElementById('bProg').textContent =
      `${earnedBadges.length} of ${Object.keys(ALL_BADGES).length} badges earned`;

    // Earned grid
    const earnedGrid = document.getElementById('earnedGrid');
    if (earnedGrid) {
      earnedGrid.innerHTML = earnedBadges.length
        ? earnedBadges.map(b=>`
            <div class="b-card earned">
              <span class="b-emoji">${b.emoji}</span>
              <div class="b-name">${b.name}</div>
              <div class="b-desc">${b.desc}</div>
            </div>`).join('')
        : '<p style="color:#94a3b8;font-size:.84em;grid-column:1/-1">No badges yet!</p>';
    }

    // Locked grid
    const lockedGrid = document.getElementById('lockedGrid');
    if (lockedGrid) {
      lockedGrid.innerHTML = Object.entries(ALL_BADGES)
        .filter(([id])=>!earnedIds.has(id))
        .map(([id,[emoji,name,desc]])=>`
          <div class="b-card locked">
            <span class="b-emoji">${emoji}</span>
            <div class="b-name">${name}</div>
            <div class="b-desc">${desc}</div>
          </div>`).join('');
    }

  } catch(e) { console.error('Badges screen error:', e); }
}

// ═══════════════════════════════════════════════════════════
//  S8 — CARBON CATCHER GAME
// ═══════════════════════════════════════════════════════════
const GAME = {
  canvas:null,ctx:null,running:false,paused:false,
  animId:null,timerInterval:null,
  timeLeft:30,score:0,caughtKg:0,lives:3,level:1,
  tree:{x:260,y:310,w:60,h:55,speed:7},
  objects:[],particles:[],spawnTimer:0,spawnRate:55,
  keys:{left:false,right:false},realCO2:null,
};

const OBJ_TYPES=[
  {type:'co2', emoji:'☁️', w:44,h:36,points:10, kg:0.5,speed:2.5},
  {type:'co2', emoji:'🌫️',w:36,h:30,points:15, kg:0.3,speed:3.2},
  {type:'co2', emoji:'💨', w:30,h:26,points:20, kg:0.2,speed:4.0},
  {type:'car', emoji:'🚗', w:50,h:38,points:-20,kg:0,  speed:3.8},
  {type:'car', emoji:'🏭', w:44,h:44,points:-30,kg:0,  speed:2.8},
  {type:'bonus',emoji:'⭐',w:32,h:32,points:50, kg:1.0,speed:5.0},
];

function initGame() {
  GAME.canvas = document.getElementById('gameCanvas');
  if (!GAME.canvas) return;
  GAME.ctx = GAME.canvas.getContext('2d');
  const wrap = GAME.canvas.parentElement;
  const w = Math.min(560, (wrap.offsetWidth||360) - 4);
  GAME.canvas.width  = w;
  GAME.canvas.height = Math.round(w * 0.68);
  GAME.tree.x = w/2-30;
  GAME.tree.y = GAME.canvas.height - 65;
  GAME.realCO2 = lastResult ? lastResult.total : null;
  if (GAME.realCO2) document.getElementById('hudRealVal').textContent = GAME.realCO2+' kg';
  drawIdle();
}

function drawIdle() {
  const {ctx,canvas} = GAME;
  const g=ctx.createLinearGradient(0,0,0,canvas.height);
  g.addColorStop(0,'#0f0c29'); g.addColorStop(1,'#302b63');
  ctx.fillStyle=g; ctx.fillRect(0,0,canvas.width,canvas.height);
  ctx.fillStyle='#1a472a'; ctx.fillRect(0,canvas.height-25,canvas.width,25);
  drawTree(canvas.width/2-30, canvas.height-65, 1);
  ctx.fillStyle='rgba(255,255,255,0.85)'; ctx.font='bold 20px Segoe UI'; ctx.textAlign='center';
  ctx.fillText('🌳 Carbon Catcher', canvas.width/2, canvas.height/2-24);
  ctx.font='13px Segoe UI'; ctx.fillStyle='rgba(255,255,255,0.55)';
  ctx.fillText('Catch CO₂ · Dodge cars · Beat your footprint!', canvas.width/2, canvas.height/2+4);
}

function drawTree(x,y) {
  const {ctx}=GAME;
  ctx.fillStyle='#8B4513'; ctx.fillRect(x+22,y+36,16,20);
  [['#2d6a4f',30,36,0],['#40916c',38,28,8],['#52b788',46,20,14]].forEach(([c,w,h,o])=>{
    ctx.fillStyle=c; ctx.beginPath();
    ctx.moveTo(x+30,y+o); ctx.lineTo(x+30-w/2,y+o+h); ctx.lineTo(x+30+w/2,y+o+h);
    ctx.closePath(); ctx.fill();
  });
}

function startGame() {
  if (GAME.animId) cancelAnimationFrame(GAME.animId);
  if (GAME.timerInterval) clearInterval(GAME.timerInterval);
  Object.assign(GAME,{running:true,paused:false,timeLeft:30,score:0,caughtKg:0,lives:3,level:1,objects:[],particles:[],spawnTimer:0,spawnRate:55});
  GAME.tree.x = GAME.canvas.width/2-30;
  document.getElementById('gameOverlay').classList.remove('show');
  document.getElementById('startBtn').classList.add('hidden');
  document.getElementById('pauseBtn').classList.remove('hidden');
  updateHUD();
  GAME.timerInterval = setInterval(()=>{
    if(GAME.paused)return;
    GAME.timeLeft--;
    document.getElementById('hudTimer').textContent=GAME.timeLeft;
    if(GAME.timeLeft<=0) endGame();
  },1000);
  gameLoop();
}

function togglePause() {
  GAME.paused=!GAME.paused;
  document.getElementById('pauseBtn').textContent=GAME.paused?'▶ Resume':'⏸ Pause';
  if(!GAME.paused) gameLoop();
}

function gameLoop() {
  if(!GAME.running||GAME.paused)return;
  update(); draw();
  GAME.animId=requestAnimationFrame(gameLoop);
}

function update() {
  const{canvas,tree,keys}=GAME;
  if(keys.left&&tree.x>0)          tree.x-=tree.speed;
  if(keys.right&&tree.x<canvas.width-tree.w) tree.x+=tree.speed;
  GAME.spawnTimer++;
  if(GAME.spawnTimer>=GAME.spawnRate){
    GAME.spawnTimer=0; spawnObj();
    GAME.spawnRate=Math.max(22,55-Math.floor((30-GAME.timeLeft)*0.9));
  }
  GAME.objects=GAME.objects.filter(obj=>{
    obj.y+=obj.speed*(1+GAME.level*0.08);
    const treeTop=tree.y+5;
    if(obj.x+obj.w>tree.x+8&&obj.x<tree.x+tree.w-8&&obj.y+obj.h>treeTop&&obj.y<tree.y+tree.h){
      if(obj.type==='co2'||obj.type==='bonus'){
        GAME.score+=obj.points;
        GAME.caughtKg=Math.round((GAME.caughtKg+obj.kg)*10)/10;
        spawnParticles(obj.x+obj.w/2,obj.y,'#38ef7d','+'+obj.points);
      } else {
        GAME.lives--; GAME.score=Math.max(0,GAME.score+obj.points);
        spawnParticles(obj.x+obj.w/2,obj.y,'#ff6b6b',''+obj.points);
        if(GAME.lives<=0){endGame();return false;}
      }
      updateHUD(); return false;
    }
    return obj.y<=canvas.height;
  });
  GAME.particles=GAME.particles.filter(p=>{p.y-=p.vy;p.alpha-=0.025;return p.alpha>0;});
  GAME.level=1+Math.floor((30-GAME.timeLeft)/8);
}

function spawnParticles(x,y,color,text){
  for(let i=0;i<6;i++) GAME.particles.push({x:x+(Math.random()-.5)*20,y,vy:1.5+Math.random()*1.5,alpha:1,color,text:i===0?text:null});
}

function spawnObj(){
  const ws=[25,20,15,18,12,10];
  let r=Math.random()*ws.reduce((a,b)=>a+b,0),idx=0;
  for(const w of ws){if(r<w)break;r-=w;idx++;}
  idx=Math.min(idx,OBJ_TYPES.length-1);
  const t=OBJ_TYPES[idx];
  GAME.objects.push({...t,x:Math.random()*(GAME.canvas.width-t.w),y:-t.h});
}

function draw(){
  const{ctx,canvas,tree}=GAME;
  ctx.clearRect(0,0,canvas.width,canvas.height);
  const g=ctx.createLinearGradient(0,0,0,canvas.height);
  g.addColorStop(0,'#0f0c29');g.addColorStop(1,'#1a1a3e');
  ctx.fillStyle=g;ctx.fillRect(0,0,canvas.width,canvas.height);
  ctx.fillStyle='rgba(255,255,255,0.4)';
  for(let i=0;i<25;i++) ctx.fillRect((i*137+50)%canvas.width,(i*89+20)%(canvas.height*.6),1.5,1.5);
  ctx.fillStyle='#1a472a';ctx.fillRect(0,canvas.height-25,canvas.width,25);
  ctx.fillStyle='#2d6a4f';ctx.fillRect(0,canvas.height-27,canvas.width,4);
  ctx.textAlign='center';
  GAME.objects.forEach(obj=>{
    ctx.font=`${obj.w*.75}px serif`;
    ctx.fillText(obj.emoji,obj.x+obj.w/2,obj.y+obj.h*.8);
  });
  drawTree(tree.x,tree.y);
  ctx.font='16px serif';ctx.textAlign='left';
  for(let i=0;i<GAME.lives;i++) ctx.fillText('❤️',6+i*22,22);
  ctx.fillStyle='rgba(255,255,255,0.18)';ctx.fillRect(canvas.width-64,5,56,20);
  ctx.fillStyle='white';ctx.font='bold 11px Segoe UI';ctx.textAlign='center';
  ctx.fillText(`LVL ${GAME.level}`,canvas.width-36,19);
  ctx.textAlign='center';
  GAME.particles.forEach(p=>{
    ctx.globalAlpha=p.alpha;
    if(p.text){ctx.fillStyle=p.color;ctx.font='bold 15px Segoe UI';ctx.fillText(p.text,p.x,p.y);}
    else{ctx.fillStyle=p.color;ctx.fillRect(p.x,p.y,4,4);}
  });
  ctx.globalAlpha=1;
}

function updateHUD(){
  document.getElementById('hudCaught').textContent=GAME.caughtKg.toFixed(1);
  document.getElementById('hudScore').textContent=GAME.score;
  if(GAME.realCO2&&GAME.realCO2>0){
    const pct=Math.min(100,(GAME.caughtKg/GAME.realCO2)*100);
    const bar=document.getElementById('budgetBar');
    bar.style.width=pct+'%';
    bar.style.background=pct>=100?'linear-gradient(90deg,#ffd700,#ff9f1c)':'linear-gradient(90deg,#38ef7d,#11998e)';
  }
}

function endGame(){
  GAME.running=false;
  cancelAnimationFrame(GAME.animId);
  clearInterval(GAME.timerInterval);
  document.getElementById('startBtn').classList.remove('hidden');
  document.getElementById('pauseBtn').classList.add('hidden');
  const real=GAME.realCO2, caught=GAME.caughtKg, won=real&&caught>=real;
  document.getElementById('goEmoji').textContent  = !real?'🌳':won?'🏆':'🌿';
  document.getElementById('goTitle').textContent  = !real?`Score: ${GAME.score}!`:won?'Carbon Positive! 🎉':'Good effort!';
  document.getElementById('goSub').textContent    = !real
    ? `Absorbed ${caught} kg. Calculate your footprint to compare!`
    : won
    ? `You absorbed ${caught} kg — beating your real ${real} kg! You earn 🏆 a bonus badge!`
    : `You absorbed ${caught} kg of your real ${real} kg. Keep going!`;
  document.getElementById('goCaught').textContent=caught+' kg';
  document.getElementById('goScore').textContent=GAME.score;
  document.getElementById('gameOverlay').classList.add('show');
  if(won&&SESSION.username){
    fetch('/api/award-badge',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({username:SESSION.username,badge:'carbon_positive'})}).catch(()=>{});
  }
}

// Keyboard
document.addEventListener('keydown',e=>{
  if(e.key==='ArrowLeft' ||e.key==='a') GAME.keys.left =true;
  if(e.key==='ArrowRight'||e.key==='d') GAME.keys.right=true;
});
document.addEventListener('keyup',e=>{
  if(e.key==='ArrowLeft' ||e.key==='a') GAME.keys.left =false;
  if(e.key==='ArrowRight'||e.key==='d') GAME.keys.right=false;
});

// Mobile buttons
['leftBtn','rightBtn'].forEach(id=>{
  const btn=document.getElementById(id);
  if(!btn)return;
  const dir=id==='leftBtn'?'left':'right';
  btn.addEventListener('pointerdown',()=>GAME.keys[dir]=true);
  btn.addEventListener('pointerup',  ()=>GAME.keys[dir]=false);
  btn.addEventListener('pointerleave',()=>GAME.keys[dir]=false);
});

// Touch swipe
let touchX=null;
document.getElementById('gameCanvas')?.addEventListener('touchstart',e=>{touchX=e.touches[0].clientX;},{passive:true});
document.getElementById('gameCanvas')?.addEventListener('touchmove',e=>{
  if(!touchX||!GAME.running)return;
  const dx=e.touches[0].clientX-touchX;
  GAME.tree.x=Math.max(0,Math.min(GAME.canvas.width-GAME.tree.w,GAME.tree.x+dx*.5));
  touchX=e.touches[0].clientX;
},{passive:true});

// ─── Init ────────────────────────────────────────────────
updateLeaderboard();