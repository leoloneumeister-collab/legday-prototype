/* LegDay — interactive app prototype (vanilla JS port of the Claude Design Component) */
(function () {
  'use strict';

  var CY = '#0088b0', ON = '#e2f2f8', LN = 'rgba(32,30,29,.12)';

  var state = {
    screen: 'onboard',   // 'onboard' | 'home' | 'progress' | 'streak' | 'feed' | 'library' | 'coach' | 'goals' | 'profile'
    step: 0,
    sheet: false,
    entry: '',
    streak: 14,
    doneToday: false,
    toast: '',
    goal: 'Strength',
    freq: '4–5',
    remind: '07:00',
    filter: '20 min',
    cheered: {}
  };

  var root = document.getElementById('app-root');
  var handlers = {};
  var hid = 0;
  var toastTimer = null;

  function esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // Register a click handler for this render pass; returns the data attribute to embed.
  function act(fn) {
    var id = 'h' + (hid++);
    handlers[id] = fn;
    return 'data-act="' + id + '"';
  }

  function setState(patch) {
    for (var k in patch) state[k] = patch[k];
    render();
  }

  function say(msg) {
    clearTimeout(toastTimer);
    state.toast = msg;
    render();
    toastTimer = setTimeout(function () {
      state.toast = '';
      render();
    }, 2600);
  }

  function go(screen) {
    return function () { setState({ screen: screen, sheet: false }); };
  }

  function chip(active) {
    return active
      ? { bg: ON, fg: '#00657f', bd: CY }
      : { bg: '#fff', fg: '#201e1d', bd: LN };
  }

  /* — onboarding — */

  var steps = [
    { title: 'What are you here for?', sub: 'It sets the plan. You can change it later.', key: 'goal', opts: ['Strength', 'Consistency', 'Weight'], cta: 'Continue' },
    { title: 'How many days a week?', sub: 'Be honest. A kept streak beats a big plan.', key: 'freq', opts: ['2–3', '4–5', '6+'], cta: 'Continue' },
    { title: 'When should we nudge you?', sub: 'One reminder a day, no more.', key: 'remind', opts: ['07:00', '12:30', '18:30'], cta: 'Start my streak' }
  ];

  function renderOnboard() {
    var st = steps[Math.min(state.step, 2)];
    var dots = [0, 1, 2].map(function (i) {
      return '<div style="height:3px;flex:1;border-radius:2px;background:' + (i <= state.step ? CY : '#e6ebee') + '"></div>';
    }).join('');
    var opts = st.opts.map(function (o) {
      var c = chip(state[st.key] === o);
      return '<div ' + act(function () { setState(pick(st.key, o)); }) + ' style="cursor:pointer;padding:16px 18px;border-radius:14px;font-size:17px;border:1px solid ' + c.bd + ';background:' + c.bg + ';color:' + c.fg + '">' + esc(o) + '</div>';
    }).join('');
    var next = act(function () {
      if (state.step < 2) setState({ step: state.step + 1 });
      else setState({ screen: 'home', step: 0 });
    });
    return '<div style="flex:1;display:flex;flex-direction:column;padding:56px 26px 30px;animation:fadeIn .3s ease">' +
      '<div style="display:flex;gap:6px">' + dots + '</div>' +
      '<div style="font-size:30px;line-height:1.15;letter-spacing:-.02em;margin-top:38px">' + esc(st.title) + '</div>' +
      '<div style="font-size:16px;color:rgba(32,30,29,.5);margin-top:10px">' + esc(st.sub) + '</div>' +
      '<div style="display:flex;flex-direction:column;gap:10px;margin-top:28px">' + opts + '</div>' +
      '<div ' + next + ' style="margin-top:auto;cursor:pointer;text-align:center;font-size:17px;padding:15px;border-radius:999px;color:#fff;background:linear-gradient(140deg,#00a3d1,#0088b0)">' + esc(st.cta) + '</div>' +
      '</div>';
  }

  function pick(key, val) {
    var patch = {};
    patch[key] = val;
    return patch;
  }

  /* — screens — */

  function renderHome() {
    var todayTitle = state.doneToday ? 'Done for today' : 'Upper body';
    var todaySub = state.doneToday ? 'Streak safe. Legs on Thursday.' : '22 min · 5 exercises';
    var todayCta = state.doneToday ? 'Log something else' : 'Log it';
    return '<div style="display:flex;flex-direction:column;gap:16px;animation:fadeIn .25s ease">' +
      '<div style="display:flex;align-items:center">' +
        '<div style="font-size:26px;letter-spacing:-.02em">Tuesday</div>' +
        '<div ' + act(go('streak')) + ' style="margin-left:auto;cursor:pointer;font-size:14px;padding:6px 13px;border-radius:999px;background:#e2f2f8;color:#00657f">' + state.streak + ' days</div>' +
      '</div>' +
      '<div style="border-radius:20px;padding:22px 20px;background:linear-gradient(160deg,#dff1f9,#f4fbfd);display:flex;flex-direction:column;gap:8px">' +
        '<div style="font-size:13px;color:rgba(32,30,29,.5)">today</div>' +
        '<div style="font-size:24px;line-height:1.15">' + esc(todayTitle) + '</div>' +
        '<div style="font-size:15px;color:rgba(32,30,29,.55)">' + esc(todaySub) + '</div>' +
        '<div ' + act(function () { setState({ sheet: true }); }) + ' style="margin-top:12px;cursor:pointer;text-align:center;font-size:16px;padding:12px;border-radius:999px;color:#fff;background:linear-gradient(140deg,#00a3d1,#0088b0)">' + esc(todayCta) + '</div>' +
      '</div>' +
      '<div style="display:flex;gap:10px">' +
        ['Library', 'Coach', 'Goals'].map(function (label) {
          var target = label.toLowerCase();
          return '<div ' + act(go(target)) + ' class="hov-accent" style="flex:1;cursor:pointer;padding:14px;border-radius:14px;border:1px solid rgba(32,30,29,.1);font-size:15px;text-align:center">' + label + '</div>';
        }).join('') +
      '</div>' +
      '<div style="font-size:13px;color:rgba(32,30,29,.45);margin-top:4px">up next</div>' +
      '<div style="display:flex;flex-direction:column;gap:8px">' +
        '<div style="padding:15px 16px;border-radius:14px;border:1px solid rgba(32,30,29,.09);font-size:16px">Thu · Legs · 35 min</div>' +
        '<div style="padding:15px 16px;border-radius:14px;border:1px solid rgba(32,30,29,.09);font-size:16px">Sat · Easy walk</div>' +
      '</div>' +
    '</div>';
  }

  function renderProgress() {
    var onIdx = [0, 2, 3, 5, 7, 9, 10, 12, 14, 15, 17, 19, 20, 21, 23, 24, 26, 27];
    var heat = '';
    for (var i = 0; i < 28; i++) {
      var on = onIdx.indexOf(i) !== -1;
      var strong = on && i % 3 === 0;
      var bg = on ? (strong ? CY : '#a9dcec') : '#eef2f4';
      heat += '<div style="height:32px;border-radius:6px;background:' + bg + '"></div>';
    }
    var bars = ['32%', '54%', '44%', '72%', '66%', '92%'].map(function (h) {
      return '<div style="flex:1;border-radius:4px 4px 0 0;background:linear-gradient(180deg,#4fc0e0,#0088b0);height:' + h + '"></div>';
    }).join('');
    return '<div style="display:flex;flex-direction:column;gap:16px;animation:fadeIn .25s ease">' +
      '<div style="font-size:26px;letter-spacing:-.02em">Progress</div>' +
      '<div style="font-size:13px;color:rgba(32,30,29,.45)">consistency · last 4 weeks</div>' +
      '<div style="display:grid;grid-template-columns:repeat(7,1fr);gap:6px">' + heat + '</div>' +
      '<div style="border-radius:16px;border:1px solid rgba(32,30,29,.09);padding:18px 16px;display:flex;flex-direction:column;gap:10px">' +
        '<div style="font-size:13px;color:rgba(32,30,29,.45)">volume · kg per week</div>' +
        '<div style="height:92px;display:flex;align-items:flex-end;gap:8px">' + bars + '</div>' +
        '<div style="font-size:20px">18.2k <span style="font-size:14px;color:rgba(32,30,29,.45)">this month, up 8%</span></div>' +
      '</div>' +
      '<div style="border-radius:16px;border:1px solid rgba(32,30,29,.09);padding:18px 16px;display:flex;flex-direction:column;gap:10px">' +
        '<div style="font-size:13px;color:rgba(32,30,29,.45)">personal bests</div>' +
        '<div style="display:flex;font-size:16px"><span>Bench</span><span style="margin-left:auto;color:#0088b0">60 kg</span></div>' +
        '<div style="display:flex;font-size:16px"><span>Squat</span><span style="margin-left:auto;color:#0088b0">95 kg</span></div>' +
        '<div style="display:flex;font-size:16px"><span>5k</span><span style="margin-left:auto;color:#0088b0">26:41</span></div>' +
      '</div>' +
    '</div>';
  }

  function renderStreak() {
    var chain = '';
    for (var i = 0; i < 21; i++) {
      chain += '<div style="height:26px;border-radius:999px;background:' + (i < state.streak ? CY : '#eef2f4') + '"></div>';
    }
    var badgePct = Math.round(Math.min(state.streak / 21, 1) * 100) + '%';
    return '<div style="display:flex;flex-direction:column;gap:16px;align-items:center;animation:fadeIn .25s ease">' +
      '<div ' + act(go('home')) + ' style="align-self:flex-start;cursor:pointer;font-size:15px;color:rgba(32,30,29,.5)">← back</div>' +
      '<div style="font-size:76px;line-height:1;color:#0088b0;margin-top:8px">' + state.streak + '</div>' +
      '<div style="font-size:16px;color:rgba(32,30,29,.5);margin-top:-6px">days in a row</div>' +
      '<div style="display:grid;grid-template-columns:repeat(7,1fr);gap:8px;width:100%;margin-top:12px">' + chain + '</div>' +
      '<div style="width:100%;border-radius:16px;padding:18px 16px;background:linear-gradient(160deg,#dff1f9,#f6fbfd);display:flex;flex-direction:column;gap:6px;margin-top:8px">' +
        '<div style="font-size:17px">1 freeze left this month</div>' +
        '<div style="font-size:15px;color:rgba(32,30,29,.55)">Protects the chain on a rest day. Use it and the streak holds.</div>' +
      '</div>' +
      '<div style="width:100%;border-radius:16px;border:1px solid rgba(32,30,29,.09);padding:18px 16px;display:flex;flex-direction:column;gap:10px">' +
        '<div style="font-size:15px;color:rgba(32,30,29,.5)">next badge at 21 days</div>' +
        '<div style="height:6px;border-radius:3px;background:#eef2f4;overflow:hidden"><div style="height:100%;background:linear-gradient(90deg,#4fc0e0,#0088b0);width:' + badgePct + '"></div></div>' +
      '</div>' +
    '</div>';
  }

  function renderFeed() {
    var crew = [
      { rank: 1, name: 'Maya', count: 5, color: CY },
      { rank: 2, name: 'You', count: state.doneToday ? 5 : 4, color: CY },
      { rank: 3, name: 'Tom', count: 2, color: 'rgba(32,30,29,.5)' }
    ].map(function (p) {
      return '<div style="display:flex;align-items:center;gap:12px;font-size:17px">' +
        '<span style="font-size:13px;color:rgba(32,30,29,.4);width:12px">' + p.rank + '</span>' +
        '<span>' + esc(p.name) + '</span>' +
        '<span style="margin-left:auto;color:' + p.color + '">' + p.count + '</span>' +
      '</div>';
    }).join('');
    var feed = ['Maya', 'Tom'].map(function (who, i) {
      var meta = i === 0 ? 'day 30 streak' : 'day 6';
      var body = i === 0 ? 'Upper body · 42 min · new bench PB' : '5k easy · 28:10';
      var cheerLabel = state.cheered[who] ? 'Cheered ✓' : 'Cheer';
      var cheer = act(function () {
        state.cheered[who] = true;
        say('Sent ' + who + ' a cheer.');
      });
      return '<div style="border-radius:16px;border:1px solid rgba(32,30,29,.09);padding:16px;display:flex;flex-direction:column;gap:8px">' +
        '<div style="display:flex;align-items:center;gap:10px">' +
          '<div style="width:32px;height:32px;border-radius:999px;background:#e2f2f8"></div>' +
          '<div style="display:flex;flex-direction:column">' +
            '<span style="font-size:16px">' + esc(who) + '</span>' +
            '<span style="font-size:13px;color:rgba(32,30,29,.45)">' + esc(meta) + '</span>' +
          '</div>' +
        '</div>' +
        '<div style="font-size:15px;color:rgba(32,30,29,.6)">' + esc(body) + '</div>' +
        '<div ' + cheer + ' style="align-self:flex-start;cursor:pointer;font-size:14px;padding:5px 12px;border-radius:999px;background:#f2f6f8;color:#00657f">' + cheerLabel + '</div>' +
      '</div>';
    }).join('');
    return '<div style="display:flex;flex-direction:column;gap:16px;animation:fadeIn .25s ease">' +
      '<div style="font-size:26px;letter-spacing:-.02em">Your crew</div>' +
      '<div style="border-radius:16px;border:1px solid rgba(32,30,29,.09);padding:18px 16px;display:flex;flex-direction:column;gap:12px">' +
        '<div style="font-size:13px;color:rgba(32,30,29,.45)">sessions this week</div>' + crew +
      '</div>' +
      '<div style="font-size:13px;color:rgba(32,30,29,.45)">activity</div>' + feed +
    '</div>';
  }

  function renderLibrary() {
    var filters = ['20 min', 'Upper', 'Home', 'No kit'].map(function (f) {
      var c = chip(state.filter === f);
      return '<div ' + act(function () { setState({ filter: f }); }) + ' style="cursor:pointer;font-size:14px;padding:6px 14px;border-radius:999px;border:1px solid ' + c.bd + ';background:' + c.bg + ';color:' + c.fg + '">' + esc(f) + '</div>';
    }).join('');
    var workouts = [
      { name: 'Push · 22 min', meta: '5 exercises · dumbbells' },
      { name: 'Full body express · 18 min', meta: '4 exercises · bodyweight' },
      { name: 'Legs · 35 min', meta: '6 exercises · barbell' },
      { name: 'Easy run · 30 min', meta: 'zone 2' }
    ].map(function (w) {
      var start = act(function () {
        setState({ screen: 'home', sheet: true, entry: w.name.split(' · ')[0] });
      });
      return '<div ' + start + ' class="lib-card" style="cursor:pointer;border-radius:16px;border:1px solid rgba(32,30,29,.09);padding:16px;display:flex;flex-direction:column;gap:4px">' +
        '<div style="font-size:18px">' + esc(w.name) + '</div>' +
        '<div style="font-size:14px;color:rgba(32,30,29,.5)">' + esc(w.meta) + '</div>' +
      '</div>';
    }).join('');
    return '<div style="display:flex;flex-direction:column;gap:14px;animation:fadeIn .25s ease">' +
      '<div ' + act(go('home')) + ' style="cursor:pointer;font-size:15px;color:rgba(32,30,29,.5)">← back</div>' +
      '<div style="font-size:26px;letter-spacing:-.02em">Library</div>' +
      '<div style="display:flex;gap:8px;flex-wrap:wrap">' + filters + '</div>' +
      workouts +
    '</div>';
  }

  function renderCoach() {
    var replies = ['Yes, keep it', 'Make it lighter', 'I need fewer days'].map(function (r) {
      return '<div ' + act(function () { say('Noted. Plan updated.'); }) + ' style="cursor:pointer;padding:15px 16px;border-radius:14px;border:1px solid ' + LN + ';background:#fff;font-size:16px">' + esc(r) + '</div>';
    }).join('');
    return '<div style="display:flex;flex-direction:column;gap:14px;animation:fadeIn .25s ease">' +
      '<div ' + act(go('home')) + ' style="cursor:pointer;font-size:15px;color:rgba(32,30,29,.5)">← back</div>' +
      '<div style="font-size:26px;letter-spacing:-.02em">Weekly check-in</div>' +
      '<div style="border-radius:18px;padding:20px 18px;background:linear-gradient(160deg,#dff1f9,#f6fbfd);font-size:17px;line-height:1.5">You hit 4 of 5 sessions and added 5 kg on bench. Same plan next week?</div>' +
      replies +
      '<div style="font-size:14px;color:rgba(32,30,29,.4);margin-top:6px">Next check-in Monday.</div>' +
    '</div>';
  }

  function renderGoals() {
    var goalOpts = ['Strength', 'Consistency', 'Weight'].map(function (g) {
      var c = chip(state.goal === g);
      return '<div ' + act(function () { setState({ goal: g }); }) + ' style="cursor:pointer;font-size:15px;padding:8px 16px;border-radius:999px;border:1px solid ' + c.bd + ';background:' + c.bg + ';color:' + c.fg + '">' + esc(g) + '</div>';
    }).join('');
    return '<div style="display:flex;flex-direction:column;gap:14px;animation:fadeIn .25s ease">' +
      '<div ' + act(go('home')) + ' style="cursor:pointer;font-size:15px;color:rgba(32,30,29,.5)">← back</div>' +
      '<div style="font-size:26px;letter-spacing:-.02em">Your goal</div>' +
      '<div style="display:flex;gap:8px;flex-wrap:wrap">' + goalOpts + '</div>' +
      '<div style="border-radius:16px;border:1px solid rgba(32,30,29,.09);padding:16px;display:flex;flex-direction:column;gap:6px">' +
        '<div style="font-size:13px;color:rgba(32,30,29,.45)">target</div>' +
        '<div style="font-size:19px">Bench 80 kg by 1 December</div>' +
      '</div>' +
      '<div style="border-radius:16px;padding:18px 16px;background:linear-gradient(160deg,#dff1f9,#f6fbfd);display:flex;flex-direction:column;gap:10px">' +
        '<div style="font-size:17px">That is 4 sessions a week.</div>' +
        '<div style="height:6px;border-radius:3px;background:#fff;overflow:hidden"><div style="height:100%;width:45%;background:linear-gradient(90deg,#4fc0e0,#0088b0)"></div></div>' +
        '<div style="font-size:14px;color:rgba(32,30,29,.55)">45% there · 60 kg today</div>' +
      '</div>' +
      '<div ' + act(function () { say('Goal saved.'); }) + ' style="cursor:pointer;text-align:center;font-size:16px;padding:13px;border-radius:999px;color:#fff;background:linear-gradient(140deg,#00a3d1,#0088b0)">Save goal</div>' +
    '</div>';
  }

  function renderProfile() {
    var settings = [
      { label: 'Goals', value: state.goal, go: go('goals') },
      { label: 'Reminders', value: state.remind, go: function () { say('Reminder set for ' + state.remind + '.'); } },
      { label: 'Crew', value: '2 friends', go: go('feed') },
      { label: 'Coach', value: 'Weekly', go: go('coach') },
      { label: 'Plan', value: 'Free', go: function () { say('Plus is not wired up in this prototype.'); } }
    ].map(function (s) {
      return '<div ' + act(s.go) + ' class="set-row" style="cursor:pointer;padding:16px 2px;border-bottom:1px solid rgba(32,30,29,.08);display:flex;font-size:17px">' +
        '<span>' + esc(s.label) + '</span><span style="margin-left:auto;font-size:15px;color:rgba(32,30,29,.4)">' + esc(s.value) + '</span>' +
      '</div>';
    }).join('');
    return '<div style="display:flex;flex-direction:column;gap:16px;animation:fadeIn .25s ease">' +
      '<div style="display:flex;align-items:center;gap:14px">' +
        '<div style="width:56px;height:56px;border-radius:999px;background:linear-gradient(150deg,#dff1f9,#bfe6f2)"></div>' +
        '<div style="display:flex;flex-direction:column;gap:2px">' +
          '<div style="font-size:24px;letter-spacing:-.02em">Sam</div>' +
          '<div style="font-size:14px;color:rgba(32,30,29,.5)">' + state.streak + '-day streak · level 7</div>' +
        '</div>' +
      '</div>' +
      '<div style="display:flex;flex-direction:column">' + settings + '</div>' +
      '<div ' + act(function () { window.location.href = 'index.html'; }) + ' style="cursor:pointer;margin-top:6px;font-size:15px;color:rgba(32,30,29,.45)">Leave the prototype →</div>' +
    '</div>';
  }

  /* — chrome: tab bar, sheet, toast — */

  function renderTabs() {
    var tabDefs = [
      { label: 'Home', k: 'home' }, { label: 'Progress', k: 'progress' },
      { label: 'Crew', k: 'feed' }, { label: 'You', k: 'profile' }
    ];
    return '<div style="display:flex;border-top:1px solid rgba(32,30,29,.08);padding:10px 12px 26px;background:#fff">' +
      tabDefs.map(function (t) {
        var color = state.screen === t.k ? CY : 'rgba(32,30,29,.42)';
        return '<div ' + act(go(t.k)) + ' style="flex:1;cursor:pointer;text-align:center;font-size:14px;padding:6px 0;color:' + color + '">' + t.label + '</div>';
      }).join('') +
    '</div>';
  }

  function chipsHtml() {
    var words = state.entry.trim().split(/\s+/).filter(Boolean).slice(0, 4);
    return (words.length ? words : ['nothing yet']).map(function (w) {
      return '<div style="font-size:13px;padding:5px 12px;border-radius:999px;background:#e2f2f8;color:#00657f">' + esc(w) + '</div>';
    }).join('');
  }

  function renderSheet() {
    if (!state.sheet) return '';
    var dictate = act(function () { setState({ entry: 'bench 3x8 60kg, 10 min bike' }); });
    var save = act(function () {
      var first = !state.doneToday;
      state.sheet = false;
      state.entry = '';
      state.doneToday = true;
      if (first) state.streak += 1;
      say(first ? 'Logged. Day ' + state.streak + '.' : 'Added to today.');
    });
    return '<div ' + act(function () { setState({ sheet: false }); }) + ' style="position:absolute;inset:0;background:rgba(20,28,32,.34);z-index:12"></div>' +
      '<div style="position:absolute;left:0;right:0;bottom:0;z-index:13;background:#fff;border-radius:24px 24px 0 0;padding:14px 22px 30px;display:flex;flex-direction:column;gap:14px;animation:riseIn .28s cubic-bezier(.2,.8,.3,1)">' +
        '<div style="width:40px;height:4px;border-radius:2px;background:rgba(32,30,29,.16);align-self:center"></div>' +
        '<div style="font-size:20px;letter-spacing:-.01em">What did you do?</div>' +
        '<input id="entry-input" value="' + esc(state.entry) + '" placeholder="bench 3x8 60kg, 10 min bike" style="font-family:\'Source Serif 4\',serif;font-size:17px;padding:14px;border-radius:14px;border:1px solid rgba(32,30,29,.14);outline:none;background:#fafcfd">' +
        '<div id="entry-chips" style="display:flex;gap:8px;flex-wrap:wrap">' + chipsHtml() + '</div>' +
        '<div style="display:flex;gap:10px;margin-top:4px">' +
          '<div ' + dictate + ' style="cursor:pointer;padding:13px 20px;border-radius:999px;border:1px solid rgba(32,30,29,.14);font-size:16px">Dictate</div>' +
          '<div ' + save + ' style="flex:1;cursor:pointer;text-align:center;padding:13px;border-radius:999px;color:#fff;font-size:16px;background:linear-gradient(140deg,#00a3d1,#0088b0)">Save</div>' +
        '</div>' +
      '</div>';
  }

  function renderToast() {
    if (!state.toast) return '';
    return '<div style="position:absolute;left:20px;right:20px;bottom:100px;z-index:20;background:#201e1d;color:#fff;border-radius:14px;padding:14px 16px;font-size:15px;animation:riseIn .3s ease">' + esc(state.toast) + '</div>';
  }

  /* — top-level render — */

  var screens = {
    home: renderHome, progress: renderProgress, streak: renderStreak, feed: renderFeed,
    library: renderLibrary, coach: renderCoach, goals: renderGoals, profile: renderProfile
  };

  function render() {
    // Preserve focus/caret in the log input across full re-renders (e.g. toast expiring).
    var activeWasEntry = document.activeElement && document.activeElement.id === 'entry-input';
    var caret = activeWasEntry ? document.activeElement.selectionStart : null;

    handlers = {};
    hid = 0;

    var html;
    if (state.screen === 'onboard') {
      html = renderOnboard();
    } else {
      html = '<div style="flex:1;overflow-y:auto;padding:52px 22px 18px">' +
        (screens[state.screen] || renderHome)() +
      '</div>' + renderTabs();
    }
    html += renderSheet() + renderToast();
    root.innerHTML = html;

    if (activeWasEntry) {
      var input = document.getElementById('entry-input');
      if (input) {
        input.focus();
        if (caret !== null) input.setSelectionRange(caret, caret);
      }
    }
  }

  /* — event delegation — */

  root.addEventListener('click', function (e) {
    var el = e.target.closest('[data-act]');
    if (el && handlers[el.getAttribute('data-act')]) handlers[el.getAttribute('data-act')]();
  });

  // Typing updates state and the chips row only — no full re-render, so the input keeps focus.
  root.addEventListener('input', function (e) {
    if (e.target && e.target.id === 'entry-input') {
      state.entry = e.target.value;
      var chips = document.getElementById('entry-chips');
      if (chips) chips.innerHTML = chipsHtml();
    }
  });

  render();
})();
