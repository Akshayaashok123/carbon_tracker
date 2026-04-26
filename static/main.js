(function () {
  // ── STATE ──────────────────────────────────────────────
  const SESSION = { username: "", department: "" };
  const selectedCoords = { origin: null, destination: null };
  let _lbCurrentTab = 'overall';

  // ── XSS SANITIZATION ──────────────────────────────────────
  function escapeHTML(str) {
    if (str == null) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  const GAME = {
    running: false, paused: false, duration: 45, score: 0, target: 14,
    timeLeft: 45, timerId: null, rafId: null, level: 1, combo: 0, maxCombo: 0,
    particles: [], powerups: [], shield: false, shieldTimer: 0, slowmo: false,
    slowmoTimer: 0, double: false, doubleTimer: 0, lives: 3, maxLives: 3,
    difficulty: "normal", highScore: parseInt(localStorage.getItem("eco_hs") || "0"),
    shake: 0, basket: { x: 370, y: 388, w: 90, h: 28, speed: 12 },
    tokens: [], moveLeft: false, moveRight: false, lastFrameTime: 0
  };

  const DIFF_CFG = {
    easy:   { spawnBase: 0.035, speedBase: 0.8, badBase: 0.15, livesMax: 5, target: 10 },
    normal: { spawnBase: 0.050, speedBase: 1.0, badBase: 0.25, livesMax: 3, target: 14 },
    hard:   { spawnBase: 0.070, speedBase: 1.4, badBase: 0.35, livesMax: 2, target: 20 }
  };

  const TOKEN_TYPES = {
    leaf:    { label: "🌿", pts: 1,  color: "#4ade80", r: 13, bad: false },
    solar:   { label: "☀️",  pts: 2,  color: "#facc15", r: 14, bad: false },
    recycle: { label: "♻️",  pts: 2,  color: "#34d399", r: 13, bad: false },
    bike:    { label: "🚲",  pts: 3,  color: "#60a5fa", r: 15, bad: false, rare: true },
    smoke:   { label: "💨",  pts: -1, color: "#94a3b8", r: 13, bad: true },
    car:     { label: "🚗",  pts: -2, color: "#f87171", r: 14, bad: true },
    factory: { label: "🏭",  pts: -3, color: "#9ca3af", r: 15, bad: true }
  };

  // ── SOUND ──────────────────────────────────────────────
  let _audioCtx = null;
  function playTone(f, d, t="sine", v=0.1) {
    try {
      if (!_audioCtx) _audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = _audioCtx.createOscillator();
      const gain = _audioCtx.createGain();
      osc.connect(gain); gain.connect(_audioCtx.destination);
      osc.frequency.value = f; osc.type = t;
      gain.gain.setValueAtTime(v, _audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, _audioCtx.currentTime + d);
      osc.start(); osc.stop(_audioCtx.currentTime + d);
    } catch(e) {}
  }
  const SFX = {
    catch: () => playTone(880, 0.1),
    bad:   () => playTone(150, 0.2, "sawtooth"),
    win:   () => [660, 880, 1100].forEach((f, i) => setTimeout(() => playTone(f, 0.2), i * 150)),
    pop:   () => playTone(600, 0.08, "sine", 0.05)
  };

  // ── UI ENGINE ──────────────────────────────────────────
  window.showScreen = function (screenId) {
    // Play transition sound
    if (typeof SFX !== "undefined") SFX.pop();

    // --- UNIVERSAL AUTHENTICATION & NAV GUARD ---
    const hasActiveSession = !!SESSION.username;
    
    // Always hide nav on onboarding screen, or if no session
    const nav = document.getElementById("mainNav");
    const isLoginScreen = (screenId === 'screen-onboarding');

    if (!hasActiveSession && !isLoginScreen) {
      console.log("🔒 Restricted Access: Redirecting to login");
      screenId = 'screen-onboarding';
    }

    if (nav) {
      if (isLoginScreen || !hasActiveSession) {
        nav.classList.add("hidden");
        nav.style.display = "none";
      } else {
        nav.classList.remove("hidden");
        nav.style.display = "flex";
      }
    }
    // ---------------------------------------------

    if (GAME.running && screenId !== 'screen-game') window.togglePause();
    
    document.querySelectorAll(".screen").forEach(s => {
      s.classList.remove("active");
      s.style.display = "none";
    });
    
    const target = document.getElementById(screenId);
    if (target) {
      target.style.display = "block";
      setTimeout(() => target.classList.add("active"), 10);
    }

    // Nav Management
    document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
    const activeNav = Array.from(document.querySelectorAll(".nav-item")).find(n => n.getAttribute("onclick")?.includes(screenId));
    if (activeNav) activeNav.classList.add("active");

    if (screenId === "screen-dashboard") loadDashboard();
    if (screenId === "screen-leaderboard") { _lbCurrentTab = 'overall'; loadLeaderboard('overall'); }
    if (screenId === "screen-badges") loadBadges();
    if (screenId === "screen-ecohub") loadEcoHub();
    if (screenId === "screen-activity") loadActivity();
    
    // ... existing logic ...
    
    window.updateUserAvatar();
    window.updateProfileUI(screenId);
  };

  window.updateProfileUI = function(screenId) {
    if (screenId !== 'screen-onboarding') return;
    
    const hasSession = !!SESSION.username;
    const form = document.getElementById("auth-form");
    const profile = document.getElementById("user-profile-info");
    
    if (hasSession && form && profile) {
      form.style.display = "none";
      profile.style.display = "block";
      document.getElementById("profile-name").textContent = SESSION.username;
      document.getElementById("profile-dept").textContent = SESSION.department;
      
      const avatar = document.getElementById("profile-avatar");
      if (avatar) {
        avatar.textContent = SESSION.username.charAt(0).toUpperCase();
        const h = [...SESSION.username].reduce((acc, c) => acc + c.charCodeAt(0), 0) % 360;
        avatar.style.background = `linear-gradient(135deg, hsl(${h}, 60%, 40%), hsl(${(h+30)%360}, 70%, 25%))`;
      }
    } else if (form && profile) {
      form.style.display = "block";
      profile.style.display = "none";
      
      // Auto-fill from local storage if available but not in session yet
      const savedUser = localStorage.getItem("eco_user");
      const savedDept = localStorage.getItem("eco_dept");
      if (savedUser && !document.getElementById("loginName").value) {
        document.getElementById("loginName").value = savedUser;
        document.getElementById("loginDept").value = savedDept || "Computer Science";
      }
    }
  };

  // ── ACTIVITY & MAPS ────────────────────────────────────
  let _activityMap = null;

  async function loadActivity() {
    const user = SESSION.username || localStorage.getItem("eco_user");
    if (!user) return;
    
    try {
      const res = await fetch("/api/strava/sync", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: user })
      });
      
      const feed = document.getElementById("activity-feed");
      const connectBtn = document.getElementById("stravaConnectBtn");
      const syncBtn = document.getElementById("stravaSyncBtn");

      if (res.status === 401) {
        if (feed) feed.innerHTML = `
          <div style='text-align:center; padding:40px; color:var(--text-dim);'>
             <h3>Not Connected</h3>
             <p>Please click 'Connect Strava' above to synchronize your real-life activities.</p>
          </div>`;
        if (connectBtn) connectBtn.style.display = "flex";
        if (syncBtn) syncBtn.style.display = "none";
        return;
      }
      
      const data = await res.json();
      
      // If logged in successfully
      if (connectBtn) connectBtn.style.display = "none";
      if (syncBtn) syncBtn.style.display = "flex";

      if (!data.success) throw new Error("Failed to load activity - " + data.error);
      
      const activities = data.activities || [];
      
      if (activities.length === 0) {
        if (feed) feed.innerHTML = "<p style='color:var(--text-dim)'>No recent activities recorded.</p>";
        return;
      }
      
      // Render activity feed
      if (feed) {
        feed.innerHTML = activities.map(act => `
          <div class="pulse-card" style="margin-bottom:15px; border-left: 4px solid var(--primary);">
            <div style="font-size:2rem;">${act.type === 'Run' ? '🏃' : '🚴'}</div>
            <div style="flex:1;">
              <h4 style="font-family:'Outfit'; font-size:1.2rem; font-weight:800; margin-bottom:5px;">${escapeHTML(act.name)}</h4>
              <p style="color:var(--text-dim); font-size:0.8rem; font-weight:600; margin:0;">
                ${formatEcoDate(act.date)} • ${act.distance_km} km • ${act.moving_time_min} min
              </p>
            </div>
            <div style="text-align:right;">
              <span style="color:var(--primary); font-size:1.4rem; font-weight:900;">+${act.carbon_saved.toFixed(1)}</span>
              <span style="display:block; font-size:0.6rem; color:var(--text-dim); text-transform:uppercase; font-weight:800;">KG CO2 Saved</span>
            </div>
          </div>
        `).join("");
      }
      
      // Initialize map with the most recent activity's polyline
      const latestAct = activities[0];
      if (latestAct && latestAct.polyline) {
        setTimeout(() => drawActivityMap(latestAct.polyline), 200); // Wait for DOM layout
      }
      
      if (data.rewarded_points) {
        // Just silently update local session cache if needed
      }
    } catch (err) {
      console.error(err);
      const feed = document.getElementById("activity-feed");
      if (feed) feed.innerHTML = "<p style='color:#f87171'>Could not load activity data.</p>";
    }
  }

  function drawActivityMap(encodedPolyline) {
    if (!document.getElementById("strava-map")) return;
    
    // Decode polyline string to [lat, lng] array
    const coords = decodeStravaPolyline(encodedPolyline);
    if (!coords || coords.length === 0) return;

    if (!_activityMap) {
      _activityMap = L.map("strava-map", {
        zoomControl: false,
        attributionControl: false
      });
      // Dark mode map tiles (CartoDB Dark Matter)
      L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        maxZoom: 19
      }).addTo(_activityMap);
    }
    
    // Clear previous layers
    _activityMap.eachLayer((layer) => {
      if (layer instanceof L.Polyline) {
        _activityMap.removeLayer(layer);
      }
    });

    // Draw glowing neon line
    const routeLine = L.polyline(coords, {
      color: '#4ADE80',
      weight: 5,
      opacity: 0.9,
      lineCap: 'round',
      lineJoin: 'round',
      className: 'neon-route' // You could add CSS for glow if needed
    }).addTo(_activityMap);
    
    // Fit map bounds to the route line
    _activityMap.fitBounds(routeLine.getBounds(), { padding: [40, 40] });
  }

  function decodeStravaPolyline(str, precision=5) {
    let index = 0, lat = 0, lng = 0, coordinates = [];
    const factor = Math.pow(10, precision);
    while (index < str.length) {
      let b, shift = 0, result = 0;
      do {
        b = str.charCodeAt(index++) - 63;
        result |= (b & 0x1f) << shift;
        shift += 5;
      } while (b >= 0x20);
      let dlat = ((result & 1) ? ~(result >> 1) : (result >> 1));
      lat += dlat;
      shift = 0; result = 0;
      do {
        b = str.charCodeAt(index++) - 63;
        result |= (b & 0x1f) << shift;
        shift += 5;
      } while (b >= 0x20);
      let dlng = ((result & 1) ? ~(result >> 1) : (result >> 1));
      lng += dlng;
      coordinates.push([lat / factor, lng / factor]);
    }
    return coordinates;
  }
  
  window.resyncActivities = function() {
    loadActivity();
  };

  // ── ECO HUB ────────────────────────────────────────────
  let _ecohubNews = [];
  let _ecohubEvents = [];
  let _ecohubMyInterests = [];
  let _ecohubCurrentFilter = 'all';

  async function loadEcoHub() {
    const user = SESSION.username || localStorage.getItem("eco_user") || "";
    try {
      // Fetch all data in parallel
      const fetches = [
        fetch("/api/eco-news").then(r => r.json()),
        fetch("/api/eco-events").then(r => r.json())
      ];
      if (user) {
        fetches.push(
          fetch(`/api/eco-events/my-interests/${encodeURIComponent(user)}`).then(r => r.json())
        );
      }
      const [newsData, eventsData, interestsData] = await Promise.all(fetches);

      _ecohubNews = newsData.news || [];
      _ecohubEvents = eventsData.events || [];
      _ecohubMyInterests = (interestsData && interestsData.interests) || [];

      // Update stats bar
      const totalEv = document.getElementById("ecohub-total-events");
      const totalAt = document.getElementById("ecohub-total-attendees");
      if (totalEv) totalEv.textContent = _ecohubEvents.length;
      if (totalAt) {
        const sum = _ecohubEvents.reduce((a, e) => a + (e.attendees || 0), 0);
        totalAt.textContent = sum.toLocaleString();
      }

      renderEcoHub(_ecohubCurrentFilter);
    } catch (err) {
      console.error("Eco Hub load error:", err);
      const newsGrid = document.getElementById("ecohub-news-grid");
      const eventsGrid = document.getElementById("ecohub-events-grid");
      if (newsGrid) newsGrid.innerHTML = "<p style='text-align:center; padding:40px; color:#f87171;'>Failed to load news.</p>";
      if (eventsGrid) eventsGrid.innerHTML = "<p style='text-align:center; padding:40px; color:#f87171;'>Failed to load events.</p>";
    }
  }

  function renderEcoHub(filter) {
    _ecohubCurrentFilter = filter;

    // Update filter pill UI
    document.querySelectorAll(".filter-pill").forEach(p => p.classList.remove("active"));
    const pills = document.querySelectorAll(".filter-pill");
    pills.forEach(p => {
      const onclick = p.getAttribute("onclick") || "";
      if (onclick.includes(`'${filter}'`)) p.classList.add("active");
    });

    const newsSection = document.getElementById("ecohub-news-section");
    const eventsSection = document.getElementById("ecohub-events-section");
    const newsGrid = document.getElementById("ecohub-news-grid");
    const eventsGrid = document.getElementById("ecohub-events-grid");

    // Determine what to show based on filter
    const showNews = (filter === 'all' || filter === 'news');
    const showEvents = (filter === 'all' || filter !== 'news');

    newsSection.style.display = showNews ? "block" : "none";
    eventsSection.style.display = showEvents ? "block" : "none";

    // Render news
    if (showNews && newsGrid) {
      newsGrid.innerHTML = _ecohubNews.map(n => `
        <div class="news-card" onclick="window.open('${escapeHTML(n.url)}', '_blank')">
          <span class="news-card-emoji">${escapeHTML(n.emoji)}</span>
          <p class="news-card-source">${escapeHTML(n.source)}</p>
          <h3 class="news-card-title">${escapeHTML(n.title)}</h3>
          <p class="news-card-summary">${escapeHTML(n.summary)}</p>
          <p class="news-card-date">${formatEcoDate(n.date)}</p>
        </div>
      `).join("");

      if (_ecohubNews.length === 0) {
        newsGrid.innerHTML = "<p style='text-align:center; padding:40px; color:var(--text-dim); grid-column:1/-1;'>No news articles available.</p>";
      }
    }

    // Render events
    if (showEvents && eventsGrid) {
      let filteredEvents = _ecohubEvents;
      if (filter !== 'all' && filter !== 'news') {
        filteredEvents = _ecohubEvents.filter(e => e.category === filter);
      }

      const BADGE_LABELS = {
        cleanup: 'Cleanup',
        workshop: 'Workshop',
        treePlant: 'Tree Planting',
        ecoRide: 'Eco Ride',
        seminar: 'Seminar'
      };

      eventsGrid.innerHTML = filteredEvents.map(evt => {
        const isInterested = _ecohubMyInterests.includes(evt.id);
        const intCount = (evt.interested_count || 0) + (evt.attendees || 0);
        const progress = evt.max_attendees ? Math.min(100, Math.round((intCount / evt.max_attendees) * 100)) : 0;

        return `
          <div class="event-card">
            <div class="event-card-header">
              <span class="event-card-emoji">${escapeHTML(evt.emoji)}</span>
              <span class="event-badge event-badge-${evt.category}">${BADGE_LABELS[evt.category] || escapeHTML(evt.category)}</span>
            </div>
            <h3 class="event-card-title">${escapeHTML(evt.title)}</h3>
            <p class="event-card-desc">${escapeHTML(evt.description)}</p>
            <div class="event-card-meta">
              <div class="event-meta-item"><span>📅</span> ${formatEcoDate(evt.date)} · ${escapeHTML(evt.time)}</div>
              <div class="event-meta-item"><span>📍</span> ${escapeHTML(evt.location)}</div>
              <div class="event-meta-item"><span>👥</span> ${escapeHTML(evt.organizer)}</div>
            </div>
            <div style="height:5px; background:rgba(255,255,255,0.05); border-radius:10px; margin-bottom:14px; overflow:hidden;">
              <div style="height:100%; width:${progress}%; background:var(--primary); border-radius:10px; transition:width 0.5s;"></div>
            </div>
            <div class="event-card-footer">
              <div class="event-attendees"><strong>${intCount}</strong> / ${evt.max_attendees} joined</div>
              <button class="btn-interested ${isInterested ? 'active' : ''}" id="interest-${evt.id}" onclick="markInterested('${evt.id}')">
                ${isInterested ? '✅ Interested' : '💚 I\'m Interested'}
              </button>
            </div>
          </div>
        `;
      }).join("");

      if (filteredEvents.length === 0) {
        eventsGrid.innerHTML = "<p style='text-align:center; padding:40px; color:var(--text-dim); grid-column:1/-1;'>No events in this category yet.</p>";
      }
    }
  }

  function formatEcoDate(dateStr) {
    try {
      const d = new Date(dateStr + 'T00:00:00');
      return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
    } catch { return dateStr; }
  }

  window.filterEcoHub = function(category) {
    renderEcoHub(category);
  };

  window.markInterested = async function(eventId) {
    const user = SESSION.username || localStorage.getItem("eco_user");
    if (!user) return alert("Please log in first.");

    const btn = document.getElementById(`interest-${eventId}`);
    if (btn) { btn.disabled = true; btn.style.opacity = '0.6'; }

    try {
      const res = await fetch("/api/eco-events/interest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ event_id: eventId, username: user })
      });
      const data = await res.json();
      if (data.success) {
        if (data.interested) {
          _ecohubMyInterests.push(eventId);
        } else {
          _ecohubMyInterests = _ecohubMyInterests.filter(id => id !== eventId);
        }
        renderEcoHub(_ecohubCurrentFilter);
      }
    } catch (err) {
      console.error("Interest toggle error:", err);
    } finally {
      if (btn) { btn.disabled = false; btn.style.opacity = '1'; }
    }
  };

  window.startApp = function () {
    const nameInp = document.getElementById("loginName");
    const deptInp = document.getElementById("loginDept");
    
    const rawName = nameInp?.value.trim();
    if (!rawName) {
      nameInp.style.borderColor = "#f87171";
      nameInp.placeholder = "Name is required!";
      return;
    }
    
    // Set Session State
    SESSION.username = rawName;
    SESSION.department = deptInp?.value;
    
    // Persistence
    localStorage.setItem("eco_user", rawName);
    localStorage.setItem("eco_dept", SESSION.department);
    
    // UI Unlock
    const nav = document.getElementById("mainNav");
    if (nav) {
      nav.classList.remove("hidden");
      nav.style.display = "flex";
      nav.style.opacity = "1";
    }
    
    // Play transition sound
    if (typeof SFX !== "undefined") SFX.catch();
    
    window.showScreen("screen-dashboard"); 
  };

  window.logout = function() {
    SESSION.username = "";
    SESSION.department = "";
    localStorage.removeItem("eco_user");
    localStorage.removeItem("eco_dept");
    window.showScreen("screen-onboarding");
  };

  window.redeemTree = async function() {
    const user = SESSION.username || localStorage.getItem("eco_user");
    if (!user) return;
    
    if (!confirm("Redeem 5,000 points to plant a tree and earn the Tree Planter badge?")) return;

    try {
      const res = await fetch("/api/redeem-tree", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: user })
      });
      const data = await res.json();
      if (data.success) {
        alert("🎉 Mission Accomplished! You've funded a reforestation action.");
        if (data.new_badge) {
          // Play win sound or show animation
          if (typeof SFX !== "undefined") SFX.win();
        }
        loadDashboard();
        loadBadges();
      } else {
        alert(data.error || "Failed to redeem points.");
      }
    } catch (err) {
      console.error("Redemption error:", err);
      alert("Error contacting server.");
    }
  };

  // ── DATA FETCHING ──────────────────────────────────────
  async function loadDashboard() {
    const user = SESSION.username || localStorage.getItem("eco_user");
    if (!user) return;

    try {
      // Fetch all required data in parallel
      const [badgeRes, lbRes, profileRes, adminRes] = await Promise.all([
        fetch(`/api/badges/${encodeURIComponent(user)}`),
        fetch("/api/leaderboard"),
        fetch(`/api/profile/${encodeURIComponent(user)}`),
        fetch("/api/admin")
      ]);
      const badgeData = await badgeRes.json();
      const lbData = await lbRes.json();
      const profileData = await profileRes.json();
      const adminData = await adminRes.json();
      const logs = profileData.daily_logs || [];
      const latestLog = logs.length > 0 ? logs[logs.length - 1] : null;

      // UI Updates: Stats — use real data from latest log
      document.getElementById("dash-total").textContent = latestLog ? latestLog.total.toFixed(1) : "0.0";
      const last7 = logs.slice(-7);
      const weekAvg = last7.length > 0 ? (last7.reduce((a, l) => a + l.total, 0) / last7.length).toFixed(1) : "0.0";
      document.getElementById("dash-avg-week").textContent = weekAvg;
      const campusAvgEl = document.getElementById("dash-campus-avg");
      if (campusAvgEl) campusAvgEl.textContent = `${(adminData.campus_avg || 0).toFixed(1)} kg`;

      // Category Progress — real breakdown from latest log
      const maxRef = 6;
      if (latestLog) {
        const commuteCO2 = Math.max(0, latestLog.total - (latestLog.food_value || 0) - (latestLog.elec_co2 || 0));
        document.getElementById("dash-commute").textContent = commuteCO2.toFixed(1);
        document.getElementById("dash-food").textContent = (latestLog.food_value || 0).toFixed(1);
        document.getElementById("dash-elec").textContent = (latestLog.elec_co2 || 0).toFixed(1);
        const commBar = document.getElementById("dash-commute-bar");
        const foodBar = document.getElementById("dash-food-bar");
        const elecBar = document.getElementById("dash-elec-bar");
        if (commBar) commBar.style.width = `${Math.min(100, (commuteCO2 / maxRef) * 100)}%`;
        if (foodBar) foodBar.style.width = `${Math.min(100, ((latestLog.food_value || 0) / maxRef) * 100)}%`;
        if (elecBar) elecBar.style.width = `${Math.min(100, ((latestLog.elec_co2 || 0) / maxRef) * 100)}%`;
      } else {
        document.getElementById("dash-commute").textContent = "0.0";
        document.getElementById("dash-food").textContent = "0.0";
        document.getElementById("dash-elec").textContent = "0.0";
      }
      // Update pulse circle dynamically
      const pulseCircle = document.getElementById("dash-pulse-ring");
      if (pulseCircle && latestLog) {
        const pct = Math.min(1, latestLog.total / 10);
        const offset = 283 - (283 * pct);
        pulseCircle.setAttribute("stroke-dashoffset", offset.toFixed(0));
      }

      const calDash = document.getElementById("dash-calories");
      const calWrap = document.getElementById("dash-calories-wrap");
      if (calDash && calWrap && badgeData.calories) {
        calDash.textContent = badgeData.calories;
        calWrap.style.display = "block";
      }

      // Mini Rankings
      const lbMini = document.getElementById("dash-lb-mini");
      if (lbMini && Array.isArray(lbData)) {
        lbMini.innerHTML = lbData.slice(0, 3).map((u, i) => `
          <div style="display:flex; justify-content:space-between; align-items:center; background:rgba(255,255,255,0.02); padding:12px 20px; border-radius:20px;">
            <div style="display:flex; align-items:center; gap:12px;">
              <span style="font-weight:900; font-size:0.8rem; opacity:0.5;">${i+1}</span>
              <div style="width:30px; height:30px; border-radius:50%; background:var(--primary); color:var(--navy); font-size:0.7rem; display:flex; align-items:center; justify-content:center; font-weight:900;">${escapeHTML(u.username.charAt(0))}</div>
              <span style="font-weight:800; font-size:0.9rem;">${escapeHTML(u.username)}</span>
            </div>
            <span style="font-weight:800; color:var(--primary); font-size:0.9rem;">${u.points || 0} pts</span>
          </div>
        `).join("");
      }

      // Mini Badges
      const badgesMini = document.getElementById("dash-badges-mini");
      if (badgesMini && badgeData.badges) {
        badgesMini.innerHTML = badgeData.badges.slice(-4).map(b => `
          <div style="width:50px; height:50px; border-radius:50%; background:rgba(125,228,192,0.1); display:flex; align-items:center; justify-content:center; font-size:1.5rem; border:1px solid rgba(125,228,192,0.2);">
            ${b.emoji}
          </div>
        `).join("");
      }

      // Render weekly trend chart
      renderTrendChart(logs.slice(-7));

      // Slow operations — fire and forget after UI is rendered
      setTimeout(() => {
        checkIntegrations().catch(() => {});
        loadEventSpotlight().catch(() => {});
      }, 300);

    } catch (err) { console.error(err); }
  }

  function renderTrendChart(logs) {
    const canvas = document.getElementById("trend-chart");
    const emptyMsg = document.getElementById("trend-empty-msg");
    if (!canvas) return;
    if (!logs || logs.length === 0) {
      canvas.style.display = "none";
      if (emptyMsg) emptyMsg.style.display = "block";
      return;
    }
    canvas.style.display = "block";
    if (emptyMsg) emptyMsg.style.display = "none";
    if (!window.Chart) return;
    if (window.trendChartInstance) window.trendChartInstance.destroy();

    const labels = logs.map(l => {
      try { return new Date(l.date+'T00:00:00').toLocaleDateString('en-IN',{day:'numeric',month:'short'}); }
      catch { return l.date; }
    });

    window.trendChartInstance = new Chart(canvas, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label: 'Daily CO\u2082 (kg)',
          data: logs.map(l => l.total),
          borderColor: '#4ade80',
          backgroundColor: 'rgba(74, 222, 128, 0.08)',
          fill: true, tension: 0.4,
          pointBackgroundColor: '#4ade80',
          pointBorderColor: '#050A0E',
          pointBorderWidth: 2, pointRadius: 5, borderWidth: 3,
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: 'rgba(15,25,35,0.95)', titleColor: '#4ade80',
            bodyColor: '#f0f0f0', borderColor: 'rgba(74,222,128,0.3)',
            borderWidth: 1, padding: 12, cornerRadius: 12,
            callbacks: { label: ctx => `${ctx.parsed.y.toFixed(1)} kg CO\u2082` }
          }
        },
        scales: {
          x: { grid:{color:'rgba(255,255,255,0.03)'}, ticks:{color:'#94a3b8',font:{size:11,weight:'600'}} },
          y: { grid:{color:'rgba(255,255,255,0.03)'}, ticks:{color:'#94a3b8',font:{size:11,weight:'600'}}, beginAtZero:true, suggestedMax:10 }
        }
      }
    });
  }


  async function loadEventSpotlight() {
    const spotlightContainer = document.getElementById("dash-spotlight-container");
    if (!spotlightContainer) return;

    try {
      const res = await fetch("/api/eco-events");
      const data = await res.json();
      const events = data.events || [];
      
      if (events.length === 0) return;

      // Pick the next upcoming event (events are sorted by date from API)
      const evt = events[0];
      const intCount = (evt.interested_count || 0) + (evt.attendees || 0);
      const progress = evt.max_attendees ? Math.min(100, Math.round((intCount / evt.max_attendees) * 100)) : 0;

      spotlightContainer.innerHTML = `
        <div class="card" style="padding:0; border-radius:40px; overflow:hidden; position:relative; min-height:280px; display:flex; align-items:flex-end; background: linear-gradient(0deg, rgba(2,12,10,1) 0%, rgba(2,12,10,0.4) 100%), url('/static/img/forest_hero.jpg'); background-size:cover; width:100%;">
          <div style="padding:40px; width:100%;">
            <div style="display:flex; gap:10px; margin-bottom:15px;">
              <span style="background:var(--primary); color:var(--navy); font-size:0.6rem; font-weight:900; padding:4px 10px; border-radius:99px; text-transform:uppercase;">🔥 Featured Event</span>
              <span style="color:var(--primary); font-size:0.7rem; font-weight:800;">${formatEcoDate(evt.date)}</span>
            </div>
            <div style="display:flex; justify-content:space-between; align-items:flex-end; gap:20px;">
              <div style="flex:1;">
                <h2 style="font-size:2rem; font-weight:900; margin-bottom:10px; line-height:1.2;">${evt.emoji} ${evt.title}</h2>
                <p style="color:var(--text-dim); font-size:0.85rem; max-width:400px; margin:0; overflow:hidden; text-overflow:ellipsis; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical;">${evt.description}</p>
              </div>
              <div style="text-align:right; min-width:180px;">
                <h2 style="font-size:2.8rem; color:var(--primary); font-weight:900; margin:0;">${progress}%</h2>
                <div style="width:180px; height:8px; background:rgba(255,255,255,0.1); border-radius:10px; margin:10px 0; overflow:hidden;">
                  <div style="width:${progress}%; height:100%; background:var(--primary);"></div>
                </div>
                <span style="font-size:0.75rem; color:var(--text-dim); font-weight:800;">${intCount} / ${evt.max_attendees} Joined</span>
                <br>
                <button onclick="showScreen('screen-ecohub')" style="background:none; border:none; color:var(--primary); font-weight:800; font-size:0.7rem; cursor:pointer; margin-top:10px; text-decoration:underline;">View Details →</button>
              </div>
            </div>
          </div>
        </div>
      `;
    } catch (err) {
      console.error("Spotlight load error:", err);
    }
  }

  async function checkIntegrations() {
    const syncCenter = document.getElementById("sync-center");
    const syncList = document.getElementById("sync-list");
    if (!syncCenter || !syncList) return;

    try {
      let syncItems = [];

      // Check Gmail
      const gmailRes = await fetch("/api/gmail/status");
      const gmailStatus = await gmailRes.json();
      
      if (gmailStatus.connected) {
        const ordersRes = await fetch("/api/gmail/orders");
        const ordersData = await ordersRes.json();
        if (ordersData.orders && ordersData.orders.length > 0) {
          ordersData.orders.slice(0, 3).forEach(order => {
            syncItems.push({
              source: 'Gmail',
              label: `${order.platform}: ${order.restaurant}`,
              impact: `${order.carbon_estimate}kg CO₂`,
              onSync: `logGmailOrder(${JSON.stringify(order).replace(/"/g, '&quot;')})`
            });
          });
        }
      }

      // Check Strava
      const stravaToken = localStorage.getItem('strava_access_token');
      if (stravaToken) {
        const stravaRes = await fetch(`/api/strava/activities?token=${stravaToken}`);
        const stravaData = await stravaRes.json();
        if (stravaData.activities && stravaData.activities.length > 0) {
          stravaData.activities.forEach(activity => {
             syncItems.push({
                source: 'Strava',
                label: `${activity.type}: ${activity.distance}km`,
                impact: 'Ready for calculation',
                onSync: `alert("Strava manual sync coming soon! 🚴")`
             });
          });
        }
      }

      if (syncItems.length > 0) {
        syncCenter.style.display = "block";
        syncList.innerHTML = syncItems.map(item => `
          <div style="display:flex; justify-content:space-between; align-items:center; background:rgba(255,255,255,0.03); padding:15px; border-radius:15px;">
            <div>
              <p style="font-size:0.6rem; text-transform:uppercase; color:var(--primary); font-weight:800; margin-bottom:4px;">Detected from ${item.source}</p>
              <p style="font-weight:800; font-size:0.9rem;">${item.label}</p>
              <small style="color:var(--text-dim);">${item.impact}</small>
            </div>
            <button onclick="${item.onSync}" style="background:var(--primary); color:var(--navy); border:none; padding:8px 15px; border-radius:99px; font-weight:900; font-size:0.75rem; cursor:pointer;">Sync Now</button>
          </div>
        `).join("");
      } else {
        syncCenter.style.display = "none";
      }
    } catch (err) { console.error("Sync error:", err); }
  }

  window.logGmailOrder = async (order) => {
    const user = SESSION.username || localStorage.getItem("eco_user");
    try {
      const res = await fetch("/api/gmail/log-order", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: user,
          department: SESSION.department || "General",
          ...order
        })
      });
      const data = await res.json();
      if (data.success) {
        alert(data.message);
        loadDashboard();
      }
    } catch (err) { alert("Failed to log order"); }
  };

  // ── LEADERBOARD ─────────────────────────────────────────

  // Inject lb-tab styles once
  (function injectLbStyles() {
    if (document.getElementById('lb-tab-styles')) return;
    const s = document.createElement('style');
    s.id = 'lb-tab-styles';
    s.textContent = `
      .lb-tab {
        padding: 10px 22px;
        border-radius: 99px;
        border: 1.5px solid rgba(125,228,192,0.25);
        background: rgba(255,255,255,0.04);
        color: var(--text-dim);
        font-size: 0.8rem;
        font-weight: 800;
        cursor: pointer;
        transition: all 0.2s;
        font-family: 'Outfit', sans-serif;
        letter-spacing: 0.04em;
      }
      .lb-tab:hover {
        border-color: var(--primary);
        color: var(--primary);
        background: rgba(74,222,128,0.08);
      }
      .lb-tab.active {
        background: linear-gradient(135deg, rgba(74,222,128,0.2), rgba(125,228,192,0.1));
        border-color: var(--primary);
        color: var(--primary);
        box-shadow: 0 0 16px rgba(74,222,128,0.2);
      }
      #lb-dept-tabs { padding-bottom: 4px; }
    `;
    document.head.appendChild(s);
  })();

  window.switchLbTab = function(dept) {
    _lbCurrentTab = dept;
    // Update tab active state
    document.querySelectorAll('.lb-tab').forEach(b => b.classList.remove('active'));
    const tabMap = {
      'overall': 'lb-tab-overall',
      'Computer Science': 'lb-tab-cs',
      'Engineering': 'lb-tab-eng',
      'Arts': 'lb-tab-arts',
      'Business': 'lb-tab-biz'
    };
    const activeBtn = document.getElementById(tabMap[dept]);
    if (activeBtn) activeBtn.classList.add('active');
    // Update label
    const labelEl = document.getElementById('lb-tab-label');
    const labelMap = {
      'overall': 'Overall Rankings',
      'Computer Science': 'Computer Science Department',
      'Engineering': 'Engineering Department',
      'Arts': 'Arts & Design Department',
      'Business': 'Business School'
    };
    if (labelEl) labelEl.textContent = `Showing: ${labelMap[dept] || dept}`;
    loadLeaderboard(dept);
  };

  async function loadLeaderboard(dept) {
    const list = document.getElementById("lb-list");
    if (!list) return;
    list.innerHTML = "<p style='text-align:center; padding:40px; color:var(--primary); opacity:0.5;'>Recalculating Rankings...</p>";

    try {
      const url = dept && dept !== 'overall'
        ? `/api/leaderboard?dept=${encodeURIComponent(dept)}`
        : '/api/leaderboard';

      const res = await fetch(url);
      const data = await res.json();

      if (!Array.isArray(data) || data.length === 0) {
        list.innerHTML = `<div style='text-align:center; padding:60px; color:var(--text-dim);'>
          <div style='font-size:3rem; margin-bottom:16px;'>🏜️</div>
          <p style='font-weight:800;'>No data yet for this department.</p>
          <p style='font-size:0.85rem; margin-top:8px;'>Be the first to log an activity!</p>
        </div>`;
        return;
      }

      const MEDALS = ["🥇", "🥈", "🥉"];
      list.innerHTML = data.map((u, idx) => {
        const avg = Number(u.avg_carbon || 0).toFixed(1);
        const name = escapeHTML(u.username || "User");
        const isSelf = (u.username || "").toLowerCase() === (SESSION.username || "").toLowerCase();
        const initial = escapeHTML((u.username || "U").charAt(0).toUpperCase());
        const pts = (u.points || 0).toLocaleString();

        const h = [...name].reduce((acc, c) => acc + c.charCodeAt(0), 0) % 360;
        const grad = `linear-gradient(135deg, hsl(${h}, 70%, 40%), hsl(${(h+40)%360}, 80%, 20%))`;

        const rankMedal = idx < 3
          ? `<div class="medal">${MEDALS[idx]}</div>`
          : `<div class="medal" style="font-size:0.8rem; font-weight:900;">${idx+1}</div>`;

        return `
          <div class="lb-item ${isSelf ? 'active-user' : ''}">
            <div class="user-avatar" style="background:${grad}; display:flex; align-items:center; justify-content:center; color:white; font-weight:900; font-size:1.5rem; font-family:'Outfit';">
              ${initial}
              ${rankMedal}
            </div>
            <div class="user-info">
              <div class="user-name">
                ${name}
                ${isSelf ? '<span class="badge-you">YOU</span>' : ''}
              </div>
              <div class="user-dept">${u.department || 'General'} · ${u.streak || 0}🔥 streak</div>
            </div>
            <div class="user-stat" style="text-align:right;">
              <span class="stat-val" style="color: ${isSelf ? '#4ade80' : 'var(--primary)'}">${avg}</span>
              <span class="stat-lbl">KG/DAY</span>
              <div style="font-size:0.65rem; color:var(--text-dim); margin-top:3px; font-weight:800;">${pts} pts</div>
            </div>
          </div>
        `;
      }).join("");
    } catch (err) {
      list.innerHTML = "<p style='text-align:center; padding:40px; color:#f87171;'>Grid Offline.</p>";
    }
  }

  window.updateUserAvatar = function() {
    const user = SESSION.username || localStorage.getItem("eco_user") || "A";
    const initial = user.charAt(0).toUpperCase();
    const h = [...user].reduce((acc, c) => acc + c.charCodeAt(0), 0) % 360;
    const grad = `linear-gradient(135deg, hsl(${h}, 60%, 40%), hsl(${(h+30)%360}, 70%, 25%))`;
    ['top-user-avatar', 'lb-user-avatar'].forEach(id => {
      const el = document.getElementById(id);
      if (el) { el.innerHTML = initial; el.style.background = grad; }
    });
  };


  async function loadBadges() {
    const grid = document.getElementById("badge-grid");
    const streakEl = document.getElementById("user-streak");
    const pointsEl = document.getElementById("user-points");
    if (!grid) return;
    const user = SESSION.username || localStorage.getItem("eco_user");
    if (!user) return;
    try {
      const res = await fetch(`/api/badges/${encodeURIComponent(user)}`);
      const data = await res.json();
      if (streakEl) streakEl.textContent = data.streak || 0;
      if (pointsEl) pointsEl.textContent = (data.points || 0).toLocaleString();
      const badges = data.badges || [];
      if (badges.length === 0) {
        grid.innerHTML = "<p style='grid-column:1/-1; text-align:center; padding:60px; color:var(--text-dim);'>No badges yet.</p>";
        return;
      }
      grid.innerHTML = badges.map(b => `
        <div class="achievement">
          <div class="icon">${b.emoji}</div>
          <h4 style="font-size:1rem; font-weight:800; margin-bottom:6px;">${b.name}</h4>
          <p style="font-size:0.7rem; color:var(--text-dim); line-height:1.4;">${b.desc}</p>
        </div>
      `).join("");
    } catch (err) { console.error(err); }
  }

  // ── CORE CALCULATOR ──────────────────────────────────
  window.calculateCarbon = async function () {
    const btn = document.getElementById("calcBtn");
    const loader = document.getElementById("loader-overlay");
    const uname = SESSION.username || localStorage.getItem("eco_user");
    if (!uname) return alert("Please log in first.");
    if (btn) btn.disabled = true;
    if (loader) loader.style.display = "flex";

    // 1. Calculate impact
    try {
      const payload = {
        username: uname,
        department: SESSION.department || "General",
        transport: document.getElementById("transportType").value,
        food: parseFloat(document.getElementById("foodType").value),
        electricity: parseFloat(document.getElementById("elecHours").value),
        origin: document.getElementById("originInp").value,
        destination: document.getElementById("destInp").value,
        origin_lat: selectedCoords.origin?.lat,
        origin_lon: selectedCoords.origin?.lon,
        dest_lat: selectedCoords.destination?.lat,
        dest_lon: selectedCoords.destination?.lon,
        smart_food_co2: parseFloat(document.getElementById("smartFoodImpact")?.value || 0),
        smart_food_calories: parseInt(document.getElementById("smartFoodCalories")?.textContent || 0)
      };

      const res = await fetch("/api/calculate", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      
      // Update basic result numbers
      document.getElementById("res-total").textContent = data.total.toFixed(1);
      document.getElementById("res-commute").textContent = data.breakdown.commute.toFixed(1);
      
      // Merge normal diet and smart food if both exist
      const totalFood = data.breakdown.food + (parseFloat(document.getElementById("smartFoodImpact")?.value || 0));
      document.getElementById("res-food").textContent = totalFood.toFixed(1);
      
      document.getElementById("res-elec").textContent = data.breakdown.electricity.toFixed(1);
      
      // Update calories
      const calBox = document.getElementById("res-calories-box");
      const calVal = document.getElementById("res-calories");
      if (data.calories > 0) {
        calBox.style.display = "block";
        calVal.textContent = data.calories;
      } else {
        calBox.style.display = "none";
      }
      
      // Update equivalents card
      if (data.equivalents) {
        document.getElementById('galleryGrid').innerHTML = data.equivalents.map(e => `
          <div style="background:rgba(255,255,255,0.02); border:1px solid rgba(125,228,192,0.1); border-radius:20px; padding:15px; text-align:center;">
            <span style="font-size:2rem; display:block; margin-bottom:8px;">${e.emoji}</span>
            <span style="font-weight:800; font-size:1.2rem; color:var(--primary); display:block;">${e.value}</span>
            <span style="font-size:0.6rem; color:var(--text-dim); text-transform:uppercase; font-weight:800;">${e.label}</span>
          </div>
        `).join('');
        document.getElementById('equiCard').style.display = 'block';
      }

      window.showScreen("screen-results");

      // 2. Save entry to award points/badges
      const saveRes = await fetch("/api/save-entry", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: uname, department: payload.department,
          total: data.total, transport: payload.transport,
          food_value: payload.food + (payload.smart_food_co2 || 0), 
          elec_co2: data.breakdown.electricity,
          calories: data.calories
        })
      });
      const saveData = await saveRes.json();
      
      // Display new badges if any
      const badgeSection = document.getElementById("new-badges-section");
      const badgeList = document.getElementById("new-badges-list");
      if (saveData.new_badges && saveData.new_badges.length > 0) {
        badgeList.innerHTML = saveData.new_badges.map(b => `
          <div class="achievement" style="min-width:140px; margin-right:10px; border:2px solid var(--primary);">
            <div class="icon">${b.emoji}</div>
            <h4 style="font-size:0.9rem; font-weight:800;">${b.name}</h4>
            <p style="font-size:0.6rem; color:var(--text-dim);">${b.desc}</p>
          </div>
        `).join("");
        badgeSection.style.display = "block";
        if (typeof SFX !== "undefined") SFX.win();
      } else {
        badgeSection.style.display = "none";
      }

      // 3. Fetch AI Coach Message
      document.getElementById("ecobot-msg").innerHTML = "<div class='loading-dots'><span>.</span><span>.</span><span>.</span></div> Fetching tips...";
      const coachRes = await fetch("/api/coach", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({...data, username: uname})
      });
      const coachData = await coachRes.json();
      document.getElementById("ecobot-msg").textContent = coachData.message || coachData.error || "Stay green! 🌿";

    } catch (err) { 
      console.error(err);
      alert("Connectivity error. Results may not have saved."); 
    } finally { 
      if (btn) btn.disabled = false; 
      if (loader) loader.style.display = "none"; 
    }
  };

  // ── GAME ENGINE ─────────────────────────────────────────
  const canvas = document.getElementById("game-canvas");
  const ctx = canvas ? canvas.getContext("2d") : null;

  function spawnToken() {
    const cfg = DIFF_CFG[GAME.difficulty];
    const isBad = Math.random() < cfg.badBase;
    const pool = Object.keys(TOKEN_TYPES).filter(k => TOKEN_TYPES[k].bad === isBad);
    const key = pool[Math.floor(Math.random() * pool.length)];
    const def = TOKEN_TYPES[key];
    GAME.tokens.push({ x: def.r + Math.random() * (canvas.width - def.r * 2), y: -def.r, r: def.r, vy: (1.5 + Math.random() * 2) * cfg.speedBase, ...def });
  }

  function drawGame() {
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    // Basket
    ctx.save();
    ctx.shadowBlur = 15; ctx.shadowColor = "#7de4c0";
    ctx.fillStyle = "#7de4c0";
    ctx.beginPath(); ctx.roundRect(GAME.basket.x, GAME.basket.y, GAME.basket.w, GAME.basket.h, 8); ctx.fill();
    ctx.restore();
    // Tokens
    GAME.tokens.forEach(t => {
      ctx.font = `${t.r * 1.8}px serif`; ctx.textAlign = "center"; ctx.fillText(t.label, t.x, t.y);
    });
    // Particles
    GAME.particles.forEach(p => {
      ctx.globalAlpha = p.life; ctx.fillStyle = p.color;
      ctx.beginPath(); ctx.arc(p.x, p.y, 2.5, 0, Math.PI * 2); ctx.fill();
    });
    ctx.globalAlpha = 1;
  }

  function spawnParticles(x, y, color, count = 10) {
    for (let i = 0; i < count; i++) {
      const angle = Math.random() * Math.PI * 2;
      GAME.particles.push({ x, y, vx: Math.cos(angle) * (Math.random() * 4 + 2), vy: Math.sin(angle) * (Math.random() * 4 + 2), life: 1.0, color });
    }
  }

  function updateGame() {
    if (!GAME.running || GAME.paused) return;
    if (GAME.moveLeft) GAME.basket.x -= GAME.basket.speed;
    if (GAME.moveRight) GAME.basket.x += GAME.basket.speed;
    GAME.basket.x = Math.max(0, Math.min(canvas.width - GAME.basket.w, GAME.basket.x));
    if (Math.random() < DIFF_CFG[GAME.difficulty].spawnBase) spawnToken();
    GAME.tokens = GAME.tokens.filter(t => {
      t.y += t.vy;
      const hitX = t.x > GAME.basket.x && t.x < GAME.basket.x + GAME.basket.w;
      const hitY = t.y + t.r > GAME.basket.y && t.y - t.r < GAME.basket.y + GAME.basket.h;
      if (hitX && hitY) {
        spawnParticles(t.x, t.y, t.color);
        if (t.bad) { GAME.lives--; SFX.bad(); if (GAME.lives <= 0) finishGame(); }
        else { GAME.score += t.pts; SFX.catch(); }
        updateHUD(); return false;
      }
      return t.y < canvas.height + 50;
    });
    GAME.particles.forEach(p => { p.x += p.vx; p.y += p.vy; p.life -= 0.04; });
    GAME.particles = GAME.particles.filter(p => p.life > 0);
    drawGame();
    GAME.rafId = requestAnimationFrame(updateGame);
  }

  function updateHUD() {
    document.getElementById("game-score").textContent = `Score: ${GAME.score}`;
    document.getElementById("game-lives").textContent = "❤️".repeat(Math.max(0, GAME.lives));
  }

  window.startGameRound = function () {
    GAME.running = true; GAME.paused = false;
    GAME.score = 0; GAME.lives = DIFF_CFG[GAME.difficulty].livesMax;
    GAME.tokens = []; GAME.timeLeft = 45;
    document.getElementById("game-target").textContent = `Target: ${DIFF_CFG[GAME.difficulty].target}`;
    updateHUD();
    if (GAME.timerId) clearInterval(GAME.timerId);
    GAME.timerId = setInterval(() => { if (!GAME.paused) { GAME.timeLeft--; document.getElementById("game-time").textContent = `⏱ ${GAME.timeLeft}s`; if (GAME.timeLeft <= 0) finishGame(); }}, 1000);
    if (GAME.rafId) cancelAnimationFrame(GAME.rafId);
    GAME.rafId = requestAnimationFrame(updateGame);
  };

  function finishGame() {
    GAME.running = false; clearInterval(GAME.timerId);
    const won = GAME.score >= DIFF_CFG[GAME.difficulty].target && GAME.lives > 0;
    document.getElementById("game-msg").textContent = won ? "🎉 mission Accomplished!" : "💀 Mission Failed.";
    if (won) { SFX.win(); fetch("/api/award-badge", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: SESSION.username, badge: "carbon_positive" }) }); }
  }

  window.setDifficulty = function(d) {
    GAME.difficulty = d;
    document.querySelectorAll('[id^="diff-"]').forEach(b => { b.style.borderColor = "var(--glass-border)"; b.style.color = "var(--text-dim)"; });
    document.getElementById(`diff-${d}`).style.borderColor = "var(--primary)";
    document.getElementById(`diff-${d}`).style.color = "var(--primary)";
  };

  window.togglePause = function() { GAME.paused = !GAME.paused; };

  // Controls
  window.addEventListener("keydown", e => { if (e.key === "ArrowLeft") GAME.moveLeft = true; if (e.key === "ArrowRight") GAME.moveRight = true; });
  window.addEventListener("keyup", e => { if (e.key === "ArrowLeft") GAME.moveLeft = false; if (e.key === "ArrowRight") GAME.moveRight = false; });

  // Autocomplete
  window.handleAutocomplete = async function (el, rid) {
    const q = el.value.trim(); if (q.length < 3) return;
    const res = await fetch(`/api/autocomplete?q=${encodeURIComponent(q)}`);
    const data = await res.json();
    const box = document.getElementById(rid);
    box.innerHTML = data.map((it, idx) => `<div class="autocomplete-item" data-idx="${idx}">${escapeHTML(it.label)}</div>`).join("");
    // Use event delegation for safe click handling
    box.onclick = function(e) {
      const item = e.target.closest('.autocomplete-item');
      if (!item) return;
      const i = parseInt(item.dataset.idx);
      const sel = data[i];
      if (sel) window.selectLocation(rid, sel.label, sel.lat, sel.lon);
    };
    box.style.display = "block";
  };
  window.selectLocation = (rid, l, lat, lon) => {
    document.getElementById(rid === "origin-results" ? "originInp" : "destInp").value = l;
    document.getElementById(rid).style.display = "none";
    const key = rid === "origin-results" ? "origin" : "destination";
    selectedCoords[key] = { lat, lon };
  };

  window.connectStrava = async () => {
    try {
      const btn = document.getElementById("stravaConnectBtnOnboarding");
      if (btn) btn.innerHTML = "Opening Strava...";
      window.location.href = "/api/strava/oauth";
    } catch (err) { alert("Failed to connect Strava"); }
  };

  window.connectGmail = async () => {
    try {
      const btn = document.getElementById("gmailConnectBtnOnboarding");
      if (btn) btn.innerHTML = "Opening Gmail...";
      const res = await fetch("/api/gmail/auth");
      const data = await res.json();
      if (data.url) {
        window.open(data.url, "Gmail Auth", "width=600,height=800");
      } else if (data.error) {
        alert(data.message || data.error);
      }
    } catch (err) { alert("Failed to connect Gmail"); }
  };

  // ── SMART FOOD LOGGING ──────────────────────────────────
  window.toggleFoodList = function() {
    const area = document.getElementById("foodListArea");
    area.style.display = area.style.display === "none" ? "block" : "none";
  };

  window.handleReceiptUpload = async function(input) {
    if (!input.files || !input.files[0]) return;
    const file = input.files[0];
    
    const status = document.getElementById("smartFoodStatus");
    const resultBox = document.getElementById("smartFoodResult");
    const calEl = document.getElementById("smartFoodCalories");
    const listEl = document.getElementById("detectedItemsList");
    
    resultBox.style.display = "block";
    status.innerHTML = "<div class='loading-dots'><span>.</span><span>.</span><span>.</span></div> Scanning Receipt...";
    
    const formData = new FormData();
    formData.append("file", file);
    
    try {
      const res = await fetch("/api/analyze-food-smart", {
        method: "POST",
        body: formData
      });
      const data = await res.json();
      renderSmartFoodResult(data);
    } catch (err) {
      status.textContent = "Error scanning receipt.";
    }
  };

  window.analyzeFoodList = async function() {
    const text = document.getElementById("foodListText").value.trim();
    if (!text) return alert("Please enter some food items.");
    
    const status = document.getElementById("smartFoodStatus");
    const resultBox = document.getElementById("smartFoodResult");
    
    resultBox.style.display = "block";
    status.innerHTML = "<div class='loading-dots'><span>.</span><span>.</span><span>.</span></div> Analyzing List...";
    
    try {
      const res = await fetch("/api/analyze-food-smart", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text })
      });
      const data = await res.json();
      renderSmartFoodResult(data);
    } catch (err) {
      status.textContent = "Error analyzing list.";
    }
  };

  function renderSmartFoodResult(data) {
    const status = document.getElementById("smartFoodStatus");
    const calEl = document.getElementById("smartFoodCalories");
    const listEl = document.getElementById("detectedItemsList");
    const impactEl = document.getElementById("smartFoodImpact");
    
    if (data.error && !data.items) {
      status.textContent = data.error;
      return;
    }
    
    status.textContent = "Analysis Complete!";
    calEl.textContent = `${data.total_calories} Cal`;
    impactEl.value = data.total_co2;
    
    listEl.innerHTML = data.items.map(i => `
      <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
        <span>${i.name}</span>
        <span style="opacity:0.6;">${i.calories} kcal | ${i.co2} kg</span>
      </div>
    `).join("");
    
    // Play subtle success chime
    if (typeof playTone === "function") playTone(600, 0.1);
  }

  // Init
  document.addEventListener("DOMContentLoaded", () => {
    const savedUser = localStorage.getItem("eco_user");
    if (savedUser) {
      if (document.getElementById("loginName")) document.getElementById("loginName").value = savedUser;
      if (document.getElementById("loginDept")) document.getElementById("loginDept").value = localStorage.getItem("eco_dept") || "Computer Science";
    }
    // Set initial screen
    window.showScreen("screen-onboarding");

    // Listen for OAuth callbacks from popups
    window.addEventListener('message', async (event) => {
      if (event.data === 'strava_connected') {
        const btn = document.getElementById("stravaConnectBtnOnboarding");
        if (btn) btn.innerHTML = "✅ Strava Linked";
        alert("Strava Account Linked! 🚴 Your activities will be synced.");
      }
      if (event.data === 'gmail_connected') {
        const btn = document.getElementById("gmailConnectBtnOnboarding");
        if (btn) btn.innerHTML = "✅ Gmail Linked";
        alert("Gmail Account Linked! 📧 Your food orders will be auto-calculated.");
      }
    });
  });

})();