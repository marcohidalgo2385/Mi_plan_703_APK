/* Mi plan 70.3 — app móvil (Capacitor, JavaScript sin dependencias).
 *
 * La lógica del entrenamiento NO vive aquí: la decide la API (el mismo motor del
 * demostrador Streamlit del TFM). Esta capa solo guarda la configuración del
 * deportista en el teléfono, pide el plan y lo presenta pensado para el móvil:
 *   Hoy · Semana · Forma · Carrera · Perfil.
 * Todo el texto que llega del servidor se escapa antes de pintarlo (esc).
 */
(function () {
  'use strict';

  // ------------------------------------------------------------------ entorno
  const CFG = window.MP_CONFIG || {};
  const Cap = window.Capacitor;
  const NATIVO = !!(Cap && Cap.isNativePlatform && Cap.isNativePlatform());
  const PL = (Cap && Cap.Plugins) || {};
  const $ = (s, el) => (el || document).querySelector(s);
  const $$ = (s, el) => Array.from((el || document).querySelectorAll(s));

  // ------------------------------------------------------------------ almacenamiento
  // localStorage (persistente en el WebView) con copia en Preferences si existe.
  const store = {
    get(k, d) {
      try { const v = localStorage.getItem('mp_' + k); return v == null ? d : JSON.parse(v); }
      catch (e) { return d; }
    },
    set(k, v) {
      try { localStorage.setItem('mp_' + k, JSON.stringify(v)); } catch (e) { /* lleno */ }
      if (PL.Preferences) PL.Preferences.set({ key: 'mp_' + k, value: JSON.stringify(v) }).catch(() => {});
    },
    del(k) {
      try { localStorage.removeItem('mp_' + k); } catch (e) { /* */ }
      if (PL.Preferences) PL.Preferences.remove({ key: 'mp_' + k }).catch(() => {});
    }
  };
  async function restaurarPreferencias() {
    // Si el sistema vació el localStorage, se recupera la copia de Preferences
    if (!PL.Preferences || localStorage.getItem('mp_cfg')) return;
    for (const k of ['cfg', 'strava', 'api', 'last', 'lastAt', 'matinal', 'ej']) {
      try {
        const r = await PL.Preferences.get({ key: 'mp_' + k });
        if (r && r.value != null) localStorage.setItem('mp_' + k, r.value);
      } catch (e) { /* */ }
    }
  }

  // ------------------------------------------------------------------ utilidades
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const pad = (n) => String(n).padStart(2, '0');
  const isoLocal = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const hoyISO = () => isoLocal(new Date());
  const aFecha = (iso) => { const [y, m, d] = String(iso).slice(0, 10).split('-').map(Number); return new Date(y, m - 1, d); };
  const sumaDias = (iso, n) => { const d = aFecha(iso); d.setDate(d.getDate() + n); return isoLocal(d); };
  const difDias = (a, b) => Math.round((aFecha(a) - aFecha(b)) / 86400000);
  const DIAS = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];
  const DIAS_C = ['D', 'L', 'M', 'X', 'J', 'V', 'S'];
  const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto',
    'septiembre', 'octubre', 'noviembre', 'diciembre'];
  const fLargo = (iso) => { const d = aFecha(iso); return `${DIAS[d.getDay()]} ${d.getDate()} de ${MESES[d.getMonth()]}`; };
  const fCorto = (iso) => { const d = aFecha(iso); return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}`; };
  const fNum = (iso) => { const d = aFecha(iso); return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()}`; };
  const cap1 = (s) => String(s || '').charAt(0).toUpperCase() + String(s || '').slice(1);
  const sig = (v, nd = 0) => (v == null ? '—' : (v > 0 ? '+' : '') + Number(v).toFixed(nd));
  const horas = (min) => `${Math.floor(min / 60)}:${pad(Math.round(min % 60))}`;
  const semanasTxt = (dias) => { const s = Math.ceil(dias / 7); return `${s} semana${s === 1 ? '' : 's'} (${dias} día${dias === 1 ? '' : 's'})`; };

  const DEP = {
    'Natación': { c: '#3b82f6', e: '🏊' }, 'Ciclismo': { c: '#22c55e', e: '🚴' },
    'Carrera': { c: '#f59e0b', e: '🏃' }, 'Fuerza': { c: '#a78bfa', e: '💪' },
    'Descanso': { c: '#64748b', e: '😴' }, 'Movilidad': { c: '#64748b', e: '🧘' },
    'Competencia': { c: '#ef4444', e: '🏁' }
  };
  const dep = (n) => DEP[n] || { c: '#64748b', e: '•' };
  const estiloDep = (n) => `--c:${dep(n).c};--cbg:${dep(n).c}33`;
  const COLOR_TIPO = { DESCANSO: '#ef4444', REGENERATIVO: '#f5a524', MANTENIMIENTO: '#38bdf8', CARGA: '#22c55e' };
  const MIN_SEM = { nuevo: 24, experimentado: 12 };

  const ICON = {
    hoy: '<path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z"/>',
    semana: '<rect x="3" y="5" width="18" height="16" rx="3"/><path d="M3 10h18M8 3v4M16 3v4"/>',
    forma: '<path d="M3 17l5-6 4 3 5-7 4 4"/><path d="M3 21h18"/>',
    carrera: '<path d="M5 21V4M5 4h11l-2 4 2 4H5"/>',
    perfil: '<circle cx="12" cy="8" r="4"/><path d="M4 21c1-4 4-6 8-6s7 2 8 6"/>',
    refresh: '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/>'
  };
  const svgI = (k) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICON[k]}</svg>`;

  // ------------------------------------------------------------------ estado
  const S = {
    cfg: store.get('cfg', null),          // configuración del plan
    strava: store.get('strava', null),    // tokens de Strava (solo en este teléfono)
    data: store.get('last', null),        // último plan recibido (sirve sin conexión)
    lastAt: store.get('lastAt', null),
    tab: 'hoy', sim: null, daySel: null, cargando: false, error: null,
    onb: null, ej: store.get('ej', null)
  };
  const api = () => String(store.get('api', CFG.API_URL || '')).replace(/\/+$/, '');

  // ------------------------------------------------------------------ red
  async function llamar(ruta, cuerpo, ms = 75000) {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), ms);
    try {
      const r = await fetch(api() + ruta, {
        method: cuerpo ? 'POST' : 'GET', signal: ctrl.signal,
        headers: cuerpo ? { 'Content-Type': 'application/json' } : {},
        body: cuerpo ? JSON.stringify(cuerpo) : undefined
      });
      let j = null;
      try { j = await r.json(); } catch (e) { /* sin cuerpo */ }
      if (!r.ok) {
        const msg = j && (typeof j.detail === 'string' ? j.detail : 'Datos no válidos');
        const err = new Error(msg || `Error ${r.status}`); err.status = r.status; throw err;
      }
      return j;
    } catch (e) {
      if (e.name === 'AbortError') { const er = new Error('El servidor no responde'); er.status = 0; throw er; }
      if (e.status == null) { const er = new Error('Sin conexión con el servidor'); er.status = 0; throw er; }
      throw e;
    } finally { clearTimeout(t); }
  }

  async function tokenStrava() {
    if (!S.strava || !S.strava.refresh_token) return null;
    const caduca = (Number(S.strava.expires_at) || 0) * 1000;
    if (caduca - Date.now() < 120000) {
      const r = await llamar('/api/strava/refresh', { refresh_token: S.strava.refresh_token }, 40000);
      S.strava = Object.assign({}, S.strava, r);
      store.set('strava', S.strava);
    }
    return S.strava.access_token;
  }

  function diaObjetivo() { return S.sim || hoyISO(); }

  async function cuerpoPlan() {
    const c = S.cfg;
    const b = { perfil: c.perfil, sexo: c.sexo, inicio: c.inicio, dias_sync: c.dias || 90, nombre: c.nombre || null };
    if (c.usaFecha) b.competicion = c.competicion; else b.meses = c.meses;
    if (c.perfil === 'experimentado' && c.u703) b.ultimo703 = c.u703;
    const m = store.get('matinal', null);
    if (m && m.fecha === diaObjetivo()) {
      b.matinal = { sueno: m.sueno, bb: m.bb, stress: m.stress, sleep_score: m.sleep_score, enfermo: !!m.enfermo };
    }
    if (c.modo === 'strava' && S.strava) b.strava_token = await tokenStrava();
    else if (S.sim) b.fecha_sim = S.sim;
    return b;
  }

  let avisoLento = null;
  async function cargar(silencioso) {
    if (!S.cfg) return;
    if (S.cargando) { S.pendiente = true; return; }
    S.cargando = true; S.error = null;
    $('#btnRefresh').classList.add('spin');
    if (!S.data) pintar();
    avisoLento = setTimeout(() => { const w = $('#wake'); if (w) w.hidden = false; }, 3500);
    try {
      let d;
      try {
        d = await llamar('/api/plan', await cuerpoPlan());
      } catch (e) {
        if (e.status === 401 && S.cfg.modo === 'strava' && S.strava) {
          S.strava.expires_at = 0;                      // fuerza la renovación y reintenta
          try { d = await llamar('/api/plan', await cuerpoPlan()); }
          catch (e2) {
            if (e2.status === 401) {
              toast('Strava pidió volver a conectar. Mientras, ves la demo.');
              S.strava = null; store.del('strava'); S.cfg.modo = 'demo'; store.set('cfg', S.cfg);
              d = await llamar('/api/plan', await cuerpoPlan());
            } else throw e2;
          }
        } else throw e;
      }
      S.data = d; S.lastAt = Date.now();
      if (!S.sim) { store.set('last', d); store.set('lastAt', S.lastAt); }
      if (d.nombre && d.fuente === 'strava' && !S.cfg.nombre) { S.cfg.nombre = d.nombre; store.set('cfg', S.cfg); }
    } catch (e) {
      S.error = e.message || 'Error';
      if (!silencioso) toast(S.error);
    } finally {
      clearTimeout(avisoLento);
      S.cargando = false;
      $('#btnRefresh').classList.remove('spin');
      pintar();
      if (S.pendiente) { S.pendiente = false; cargar(true); }
    }
  }

  // ------------------------------------------------------------------ Strava
  async function conectarStrava() {
    try {
      const r = await llamar('/api/strava/auth-url?redirect_uri=' + encodeURIComponent(CFG.STRAVA_REDIRECT), null, 60000);
      const url = NATIVO ? r.url : r.url_web;
      if (PL.Browser) await PL.Browser.open({ url, presentationStyle: 'popover' });
      else window.location.href = url;
    } catch (e) { toast(e.status === 503 ? 'El servidor aún no tiene configurado Strava.' : e.message); }
  }

  async function volverDeStrava(url) {
    let u;
    try { u = new URL(url); } catch (e) { return; }
    const code = u.searchParams.get('code');
    const error = u.searchParams.get('error');
    if (PL.Browser) PL.Browser.close().catch(() => {});
    if (error) { toast('No se autorizó el acceso a Strava.'); return; }
    if (!code) return;
    try {
      const r = await llamar('/api/strava/token', { code }, 60000);
      S.strava = r; store.set('strava', r);
      if (S.onb) { S.onb.d.modo = 'strava'; if (r.nombre) S.onb.d.nombre = r.nombre; pintarOnb(); }
      if (S.cfg) {
        S.cfg.modo = 'strava'; if (r.nombre) S.cfg.nombre = r.nombre; store.set('cfg', S.cfg);
        S.sim = null; cargar();
      }
      toast(`✅ Strava conectado${r.nombre ? ' · ' + r.nombre : ''}`);
    } catch (e) { toast('No se pudo conectar Strava: ' + e.message); }
  }

  function desconectarStrava() {
    S.strava = null; store.del('strava');
    if (S.cfg) { S.cfg.modo = 'demo'; store.set('cfg', S.cfg); }
    toast('Strava desconectado de este teléfono'); cargar();
  }

  // ------------------------------------------------------------------ avisos y hoja
  let tToast = null;
  function toast(msg) {
    const t = $('#toast'); t.textContent = msg; t.hidden = false;
    clearTimeout(tToast); tToast = setTimeout(() => { t.hidden = true; }, 3200);
  }
  function hoja(html) {
    $('#sheetBody').innerHTML = '<button class="x-close" data-act="cerrar" aria-label="Cerrar">✕</button>' + html;
    $('#sheet').hidden = false; $('#sheetBg').hidden = false; $('#sheet').scrollTop = 0;
  }
  function cerrarHoja() { $('#sheet').hidden = true; $('#sheetBg').hidden = true; }
  const hojaAbierta = () => !$('#sheet').hidden;

  function abrirEnlace(url) {
    if (PL.Browser) PL.Browser.open({ url }).catch(() => window.open(url, '_blank'));
    else window.open(url, '_blank', 'noopener');
  }

  function hojaEjercicio(e) {
    hoja(`<h2>${esc(e.emoji)} ${esc(e.titulo)}</h2>
      <div class="blk">${esc(e.que)}</div>
      <div class="blk"><b>Cómo se hace</b><br>${esc(e.como)}</div>
      <div class="blk"><b>Clave</b><br>${esc(e.clave)}</div>
      <button class="btn pri" data-act="video" data-url="${esc(e.video)}">▶ Ver vídeos de la técnica</button>`);
  }

  // ------------------------------------------------------------------ gráfico de líneas (SVG)
  function grafico(id, fechas, series, opt) {
    opt = opt || {};
    const W = 360, H = opt.h || 190, L = 30, R = 8, T = 10, B = 22;
    const vals = series.flatMap((s) => s.v.filter((x) => x != null));
    if (!vals.length) return '<div class="empty small">Sin datos todavía</div>';
    let lo = Math.min(...vals, opt.cero ? 0 : Infinity), hi = Math.max(...vals, opt.cero ? 0 : -Infinity);
    if (hi - lo < 10) { hi += 5; lo -= 5; }
    const n = fechas.length;
    const x = (i) => L + (W - L - R) * (n <= 1 ? 0 : i / (n - 1));
    const y = (v) => T + (H - T - B) * (1 - (v - lo) / (hi - lo));
    const paso = Math.max(Math.round((hi - lo) / 4 / 5) * 5, 5);
    let ejes = '';
    for (let v = Math.ceil(lo / paso) * paso; v <= hi; v += paso) {
      ejes += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="${v === 0 ? '#5b6b8c' : '#22304d'}" stroke-width="${v === 0 ? 1.2 : 1}"/>`
        + `<text x="${L - 5}" y="${y(v) + 3.5}" fill="#7183a3" font-size="9.5" text-anchor="end">${v}</text>`;
    }
    const nEt = Math.min(4, n);
    for (let k = 0; k < nEt; k++) {
      const i = Math.round((n - 1) * (nEt === 1 ? 0 : k / (nEt - 1)));
      const et = opt.etq ? opt.etq(fechas[i]) : fechas[i];
      ejes += `<text x="${x(i)}" y="${H - 6}" fill="#7183a3" font-size="9.5" text-anchor="${k === 0 ? 'start' : k === nEt - 1 ? 'end' : 'middle'}">${esc(et)}</text>`;
    }
    const lineas = series.map((s) => {
      let dd = '', abierto = false;
      s.v.forEach((v, i) => {
        if (v == null) { abierto = false; return; }
        dd += `${abierto ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`; abierto = true;
      });
      return `<path d="${dd}" fill="none" stroke="${s.c}" stroke-width="${s.w || 2.2}" ${s.dash ? 'stroke-dasharray="5 4"' : ''} stroke-linecap="round" stroke-linejoin="round"/>`;
    }).join('');
    return `<svg id="${id}" class="chart" viewBox="0 0 ${W} ${H}" data-n="${n}" data-l="${L}" data-r="${R}" data-w="${W}">
      ${ejes}${lineas}<line class="cur" x1="0" x2="0" y1="${T}" y2="${H - B}" stroke="#fff" stroke-width="1" opacity="0"/></svg>`;
  }
  function activarCursor(id, fn) {
    const svg = document.getElementById(id); if (!svg) return;
    const n = +svg.dataset.n, L = +svg.dataset.l, R = +svg.dataset.r, W = +svg.dataset.w;
    const cur = svg.querySelector('.cur');
    const mover = (ev) => {
      const r = svg.getBoundingClientRect();
      const px = ((ev.touches ? ev.touches[0].clientX : ev.clientX) - r.left) / r.width * W;
      const i = Math.max(0, Math.min(n - 1, Math.round((px - L) / (W - L - R) * (n - 1))));
      const xx = L + (W - L - R) * (n <= 1 ? 0 : i / (n - 1));
      cur.setAttribute('x1', xx); cur.setAttribute('x2', xx); cur.setAttribute('opacity', '.6');
      fn(i);
    };
    svg.addEventListener('pointerdown', mover); svg.addEventListener('pointermove', mover);
    svg.addEventListener('touchmove', mover, { passive: true });
  }

  // ------------------------------------------------------------------ pantallas
  function esqueleto() {
    return `<div class="sk" style="height:150px"></div><div class="sk" style="height:110px"></div>
      <div class="wake" id="wake" hidden>☕ Despertando el servidor… la primera carga del día puede tardar hasta un minuto.</div>
      <div class="sk" style="height:190px"></div><div class="kpis"><div class="sk" style="height:86px;margin:0"></div><div class="sk" style="height:86px;margin:0"></div></div>`;
  }

  function vHoy(d) {
    const f = d.fase, s = d.sesion_hoy, fo = d.forma || {}, r = d.semana.resumen;
    const nombre = S.cfg.nombre || d.nombre || 'triatleta';
    let h = `<div class="hero fade-in">
      <div class="hi">👋 ¡Hola, ${esc(nombre)}! · ${esc(cap1(fLargo(d.hoy)))}</div>
      <div class="q">${esc(d.frase)}</div>
      <div class="chips"><span>Semana ${f.semana_actual} de ${f.semanas_totales}</span>
        <span>${esc(f.restante)} para tu 70.3</span></div></div>`;
    if (!d.plan_viable) {
      h += `<div class="adj lv-aviso" style="margin:0 0 12px">⚠ Para un perfil ${S.cfg.perfil === 'nuevo' ? 'nuevo' : 'con experiencia'}
        se recomiendan al menos ${f.semanas_minimas} semanas y tu plan tiene ${f.semanas_totales}. Considera una
        carrera más lejana o plantea el objetivo como terminar bien.</div>`;
    }
    h += vCamino(d);
    if (s) {
      const km = Number(s.km || 0), dur = Number(s.dur_min || 0);
      const meta = dur ? [km ? `${km} km` : '', `${dur} min`].filter(Boolean).join(' · ') : 'Día de descanso y recuperación';
      const tit = s.tipo && String(s.tipo).toLowerCase().startsWith(String(s.deporte).toLowerCase())
        ? cap1(s.tipo) : `${s.deporte} · ${s.tipo}`;
      h += `<div class="today fade-in" style="${estiloDep(s.deporte)}">
        <div class="eyebrow">Tu sesión de hoy · ${esc(s.dia)}</div>
        <div class="sport"><div class="ico">${dep(s.deporte).e}</div>
          <div><div class="t">${esc(tit)}</div><div class="m">${esc(meta)}</div></div></div>
        <div class="d">${esc(s.detalle)}</div>
        ${s.ayudas && s.ayudas.length ? `<div class="chiprow">${s.ayudas.map((e, i) =>
          `<button class="chipb" data-act="ayuda" data-i="${i}">${esc(e.emoji)} ${esc(e.titulo)}</button>`).join('')}</div>` : ''}
        ${vAjuste(d.ajuste)}
        <div style="margin-top:12px"><button class="btn ${d.ajuste ? '' : 'pri'}" data-act="matinal">☀️ ${d.ajuste ? 'Cambiar mi registro de hoy' : '¿Cómo amaneciste? Ajusta tu día'}</button></div>
      </div>`;
    }
    const tsbHoy = fo.tsb != null ? ` · hoy ${sig(fo.tsb)}` : '';
    const ctlPct = fo.ctl != null ? Math.min(fo.ctl / (fo.ctl_objetivo || 70) * 100, 100) : 0;
    h += `<div class="kpis fade-in">
      <button class="kpi" data-act="kpi" data-k="semana" style="text-align:left">
        <div class="l">Semana de</div><div class="v ${d.semana.nombre.length > 9 ? 'sm' : ''}" style="color:${COLOR_TIPO[d.semana.tipo] || '#fff'}">${esc(d.semana.nombre)}</div>
        <div class="s">decidida por tu frescura ⓘ</div></button>
      <div class="kpi"><div class="l">Esta semana</div><div class="v num">${r.sesiones}${r.fuerza ? ` <span style="font-size:15px">+ ${r.fuerza} 💪</span>` : ''}</div>
        <div class="s">sesiones · ${horas(r.minutos)} h</div></div>
      <button class="kpi" data-act="kpi" data-k="ctl" style="text-align:left"><div class="l">Forma (CTL)</div>
        <div class="v num">${fo.ctl != null ? Math.round(fo.ctl) : '—'}</div><div class="s">objetivo ${fo.ctl_objetivo || 70}</div>
        <div class="bar"><i style="width:${ctlPct}%"></i></div></button>
      <button class="kpi" data-act="kpi" data-k="tsb" style="text-align:left"><div class="l">Frescura sem. ant.</div>
        <div class="v num">${fo.tsb7 != null ? sig(fo.tsb7) : '—'}</div>
        <div class="s">TSB medio ${esc(fo.semana_decision || '')}${tsbHoy}</div></button>
    </div>`;
    if (d.demo) {
      h += `<div class="card small muted">🎛️ <b style="color:var(--tx)">Modo demostración.</b> Usa la barra inferior para avanzar los días.
        En la semana ${d.demo.sobrecarga} el deportista entrena de más y en la ${d.demo.viaje} no entrena (viaje):
        mira cómo cambian la frescura, el tipo de semana y el plan.</div>`;
    }
    h += `<div class="card"><h3>💡 ¿Por qué este plan?</h3><div class="small muted">${esc(d.explicacion)}</div></div>`;
    return h;
  }

  function vAjuste(a) {
    if (!a) return '';
    const lv = { 'MANTENER': 'ok', 'SUAVIZAR HOY': 'aviso', 'DESCANSO HOY': 'error' }[a.decision] || 'info';
    return `<div class="adj lv-${lv}"><b>🔁 Tu día recalculado: ${esc(cap1(String(a.decision).toLowerCase()))}</b>
      ${esc(a.detalle)}<div class="tiny" style="margin-top:4px;opacity:.85">Motivos: ${esc((a.motivos || []).join(', '))}</div></div>`;
  }

  const CORTO = { 'Construcción': 'Constr.' };
  function rotulo(t, cuota) {
    if (cuota >= 0.3) return t.nombre;
    if (cuota >= 0.1) return CORTO[t.nombre] || t.nombre;
    return cuota >= 0.05 ? t.nombre.charAt(0) : '';
  }

  function vCamino(d) {
    const c = d.camino, f = d.fase, tot = c.semanas_totales;
    const pos = c.posicion_semanas, pct = pos / tot * 100;
    let segs = '', et = '';
    c.tramos.forEach((t) => {
      const n = t.hasta - t.desde + 1;
      const lleno = Math.min(Math.max((pos - (t.desde - 1)) / n, 0), 1) * 100;
      const ahora = t.fase === f.fase;
      segs += `<div class="seg ${ahora ? 'now' : ''}" style="flex:${n};background:${t.color}40">
        <div class="fill" style="width:${lleno}%;background:${t.color}"></div>
        <b style="color:${lleno > 45 ? '#0b1220' : '#fff'}">${t.fase === 'COMPETENCIA' ? '🏁' : esc(rotulo(t, n / tot))}</b></div>`;
      et += `<div style="flex:${n}">${n / tot >= 0.07 ? 's' + t.desde : ''}</div>`;
    });
    const i = c.tramos.findIndex((t) => t.fase === f.fase);
    const act = c.tramos[i] || {};
    const sig2 = c.tramos[i + 1];
    let sigTxt = '';
    if (sig2) {
      const en = sig2.desde - f.semana_actual;
      sigTxt = ` · Siguiente: <b>${esc(sig2.nombre)}</b> en ${en} semana${en === 1 ? '' : 's'} (${fCorto(sig2.inicio)})`;
    }
    return `<div class="card camino fade-in">
      <div class="head"><div><div class="eyebrow">Tu camino al 70.3</div>
        <div class="big">Semana ${f.semana_actual} <small>de ${tot}</small></div>
        <div class="fase-n" style="color:${act.color || '#fff'}">${esc(f.nombre === '70.3' ? 'Semana de carrera' : 'Fase ' + f.nombre)}</div></div>
        <div class="count"><b class="num">${c.dias_carrera}</b><span>días</span></div></div>
      <div class="track">${segs}<div class="pin" style="left:${pct}%"><i>HOY</i></div></div>
      <div class="weeks">${et}</div>
      <div class="foot"><b style="color:${act.color || '#fff'}">● ${esc(f.nombre)}:</b> ${esc(act.descripcion || '')}${sigTxt}</div></div>`;
  }

  function vSemana(d) {
    const w = d.semana, r = w.resumen, m = w.meta, f = d.fase;
    let h = `<div class="sec-t"><h2>Tu semana</h2><span>${esc(f.nombre)} · semana ${m.sem_idx} de ${m.sem_tot}</span></div>
      <div class="card" style="border-color:${COLOR_TIPO[w.tipo] || 'var(--line)'}">
        <div class="eyebrow">Semana de</div>
        <div style="font-size:22px;font-weight:900;color:${COLOR_TIPO[w.tipo] || '#fff'}">${esc(w.nombre)}</div>
        <div class="small muted">${esc(w.motivo)}</div></div>
      <div class="sum">
        <div><b class="num">${r.sesiones}${r.fuerza ? '+' + r.fuerza : ''}</b><span>sesiones</span></div>
        <div><b class="num">${horas(r.minutos)}</b><span>horas</span></div>
        <div><b class="num">${r.km_nat || 0}</b><span>km nado</span></div>
        <div><b class="num">${r.km_bici || 0}</b><span>km bici</span></div>
        <div><b class="num">${r.km_carrera || 0}</b><span>km carrera</span></div>
        <div><b class="num">${m.dplus_bike || 0}</b><span>m D+ bici</span></div></div>`;
    if (m.descarga) {
      h += `<div class="adj lv-info" style="margin:0 0 12px">🌙 <b>Semana de descarga.</b> Cada 4 semanas se reduce el volumen
        ~40 % y baja la intensidad para asimilar la carga. No es perder forma: es cuando el cuerpo se adapta.</div>`;
    }
    if (d.ajuste && d.ajuste.decision !== 'MANTENER') h += vAjuste(d.ajuste).replace('class="adj', 'style="margin:0 0 12px" class="adj');
    h += `<div class="days">${w.sesiones.map((s, i) =>
      `<button class="dayb ${s.es_hoy ? 'hoy' : ''} ${S.daySel === i ? 'sel' : ''}" data-act="dia" data-i="${i}" style="${estiloDep(s.deporte)}">
        ${DIAS_C[aFecha(s.fecha).getDay()]}<span class="tiny">${aFecha(s.fecha).getDate()}</span><i></i></button>`).join('')}</div>`;
    h += w.sesiones.map((s, i) => {
      const km = Number(s.km || 0), dur = Number(s.dur_min || 0);
      const meta = [km ? `${km} km` : '', dur ? `${dur} min` : ''].filter(Boolean).join(' · ');
      return `<div class="card ses ${s.pasado ? 'pasado' : ''}" id="ses${i}" style="${estiloDep(s.deporte)}">
        <div class="top2"><span class="dia">${esc(s.dia)} ${fCorto(s.fecha)}</span>${s.es_hoy ? '<span class="badge">HOY</span>' : ''}</div>
        <div class="dep">${dep(s.deporte).e} ${esc(s.deporte)}</div>
        <div class="tp">${esc(s.tipo)}</div>${meta ? `<div class="mt">${esc(meta)}</div>` : ''}
        <div class="dt">${esc(s.detalle)}</div>
        ${s.ayudas && s.ayudas.length ? `<div class="chiprow">${s.ayudas.slice(0, 5).map((e, k) =>
          `<button class="chipb" data-act="ayuda-s" data-i="${i}" data-k="${k}">${esc(e.emoji)} ${esc(e.titulo)}</button>`).join('')}</div>` : ''}
      </div>`;
    }).join('');
    const fq = m.freq_act ? `tu frecuencia actual (~${Math.round(m.freq_act)} sesiones/semana) y ` : 'tu perfil y ';
    h += `<div class="card"><details class="more"><summary>ⓘ Cómo se ha construido esta semana</summary>
      <div class="small muted">Tipo de semana: <b>${esc(w.nombre)}</b> — ${esc(w.motivo)}.<br><br>
      Carga progresiva: ${m.n_ses} sesiones de natación, bici y carrera${m.n_fuerza ? ` y ${m.n_fuerza} de fuerza` : ''},
      calculadas con ${fq}el avance del plan (semana ${m.sem_idx}/${m.sem_tot}).
      ${m.nat_intro ? '<br><br>🏊 Aún no registras natación: el plan la introduce desde ya.' : ''}
      ${m.n_fuerza ? `<br><br>💪 Fuerza de piernas y core y desnivel prescrito (~${m.dplus_bike} m en bici y ~${m.dplus_run} m en la tirada larga).` : ''}
      </div></details></div>`;
    return h;
  }

  function vForma(d) {
    const fo = d.forma;
    if (!fo || fo.ctl == null) return '<div class="empty"><div class="e">📈</div>Aún no hay datos de carga.</div>';
    const b = fo.banda;
    let h = `<div class="sec-t"><h2>Tu forma</h2><span>CTL · ATL · TSB</span></div>
      <div class="card lv-${b.nivel}" style="border:0">
        <div class="eyebrow" style="color:inherit;opacity:.8">Tu frescura hoy</div>
        <div style="font-size:26px;font-weight:900">TSB ${sig(fo.tsb, 1)} · ${esc(b.titulo)}</div>
        <div class="small">${esc(b.texto)}</div>
        ${fo.tsb7 != null ? `<div class="tiny" style="margin-top:8px;opacity:.9">El tipo de semana no se decide con este valor diario sino con la
          media de la semana anterior (${esc(fo.semana_decision)}): <b>${sig(fo.tsb7, 1)}</b>. Por eso pueden diferir.</div>` : ''}
      </div>`;
    if (fo.aviso_inactividad) h += `<div class="adj lv-${fo.aviso_inactividad[0]}" style="margin:0 0 12px">${esc(fo.aviso_inactividad[1])}</div>`;
    const se = fo.serie;
    h += `<div class="card"><h3>Forma, fatiga y frescura (120 días)</h3>
      ${grafico('gForma', se.fechas, [
        { v: se.ctl, c: '#ff6b35', w: 2.8 }, { v: se.atl, c: '#e83f6f', w: 1.6 }, { v: se.tsb, c: '#38bdf8', w: 1.6, dash: true }],
        { cero: true, etq: fCorto })}
      <div class="legend"><span><i style="background:#ff6b35"></i>Forma (CTL)</span><span><i style="background:#e83f6f"></i>Fatiga (ATL)</span>
        <span><i style="background:#38bdf8"></i>Frescura (TSB)</span></div>
      <div class="tip" id="tipForma">Desliza el dedo sobre el gráfico para ver cada día.</div></div>`;
    const pct = Math.min(fo.ctl / fo.ctl_objetivo * 100, 100);
    h += `<div class="card"><h3>🎯 Tu forma frente al objetivo</h3>
      <div style="display:flex;justify-content:space-between;align-items:baseline"><span style="font-size:24px;font-weight:900" class="num">CTL ${Math.round(fo.ctl)}</span>
      <span class="muted small">objetivo ${fo.ctl_objetivo}</span></div><div class="bar" style="height:10px"><i style="width:${pct}%"></i></div>
      <div class="small muted" style="margin-top:8px"><b style="color:var(--tx)">${esc(cap1(fo.progreso))}</b>${fo.rampa != null ? ` · rampa necesaria ${sig(fo.rampa, 1)}/semana` : ''}
      · faltan ${esc(d.fase.restante)} (${fNum(d.competicion)})</div></div>`;
    const p = d.progreso;
    if (p) {
      const cols = { 'Carrera': '#f59e0b', 'Ciclismo': '#22c55e', 'Natación': '#3b82f6' };
      const series = Object.keys(p.series).map((k) => ({ v: p.series[k], c: cols[k] || '#fff' }));
      h += `<div class="card"><h3>📈 Tu progreso por disciplina</h3>
        <div class="grid3" style="margin-bottom:10px">${Object.keys(p.kpis).map((k) => `<div class="chip">
          <div class="l" style="color:${cols[k]}">${esc(k)}</div><div class="v">${esc(p.kpis[k].valor)}</div>
          <div class="tiny" style="color:${p.kpis[k].mejora_pct > 0 ? '#86efac' : 'var(--tx3)'}">${sig(p.kpis[k].mejora_pct)}% vs inicio</div></div>`).join('')}</div>
        ${grafico('gProg', p.semanas, series, { h: 150, etq: (s) => 'sem ' + s })}
        <div class="tiny muted" style="margin-top:6px">Índice semanal de ritmo (semana 1 = 100) desde que empezaste el plan.</div></div>`;
    } else {
      h += `<div class="card small muted">📊 Tu evolución por disciplina aparecerá cuando acumules al menos 2 semanas de actividad desde el inicio del plan.</div>`;
    }
    return h;
  }

  function vCarrera(d) {
    const z = d.zonas, f = d.fase;
    const tot = z.hr.Z5[1] - z.hr.Z1[0];
    let h = `<div class="sec-t"><h2>Zonas y ritmos</h2><span>como en tu reloj</span></div>
      <div class="card"><div class="zbar">${['Z1', 'Z2', 'Z3', 'Z4', 'Z5'].map((k) =>
        `<div style="flex:${(z.hr[k][1] - z.hr[k][0]) / tot};background:${z.colores[k]}">${k}<br>${z.hr[k][0]}</div>`).join('')}</div>
      <div class="tiny muted">FC máx ${z.fc_max} · FC reposo ${z.fc_rep} ppm</div>
      <div class="grid3" style="margin-top:12px">${z.ritmos.map((c) => `<div class="chip ${c.off ? 'off' : ''}"><div class="l">${esc(c.lab)}</div><div class="v">${esc(c.val)}</div></div>`).join('')}</div>
      <div class="small muted" style="margin-top:10px">📈 Tu rodaje pasa de <b style="color:var(--tx)">${esc(z.rodaje_hoy)}</b> esta semana a
        <b style="color:var(--tx)">~${esc(z.rodaje_pico)}</b> en el pico (mismo pulso, más rápido).${f.fase === 'BASE' ? ' Z4 y series tachadas: en Base aún no se usan.' : ''}</div>
      <div class="tiny muted" style="margin-top:8px">✓ Origen de tus ritmos: ${esc(z.fuente)}.</div>
      ${z.modelos && z.modelos.bici_pred ? `<div class="adj lv-ok" style="margin-top:10px">🧠 <b>Modelos del TFM activos</b>
        bici estimada por XGBoost ${z.modelos.bici_pred} km/h (objetivo conservador ${z.modelos.bici_cons} km/h)${z.modelos.run_pred ? ` · carrera estimada ${esc(z.modelos.run_pred)} (conservador ${esc(z.modelos.run_cons)})` : ''}.</div>` : ''}
      </div>`;
    if (d.objetivo) {
      const o = d.objetivo;
      h += `<div class="adj lv-${o.viable ? 'ok' : 'aviso'}" style="margin:0 0 12px">${o.viable
        ? `✓ <b>Objetivo viable:</b> ${esc(o.anterior_total)} → ${esc(o.objetivo_total)} (−${Math.round(o.mejora_min)} min). Splits: natación ${esc(o.splits_obj.nat)} · bici ${esc(o.splits_obj.bici)} · carrera ${esc(o.splits_obj.run)}.`
        : `⚠ <b>Objetivo ambicioso</b> (${o.mejora_pct} %): el plan lo apunta, pero la estimación realista queda por encima. La mejora se concentra en la bici.`}</div>`;
    }
    h += `<div class="sec-t"><h2>Día de carrera</h2><span>${esc(fNum(d.competicion))}</span></div>`;
    if (d.carrera) {
      const col = (t) => t.startsWith('NAT') ? '#3b82f6' : t.startsWith('BICI') ? '#22c55e' : t.startsWith('CARR') ? '#f59e0b' : '#a78bfa';
      let prev = null;
      h += `<div class="card"><div class="small muted" style="margin-bottom:6px">La FC manda sobre el ritmo. Bici progresiva hasta recuperar pulsaciones tras la natación.</div><div class="tl">`;
      d.carrera.segmentos.forEach((s) => {
        if (s.disciplina !== prev) { prev = s.disciplina; h += `<div class="dis" style="--c:${col(s.disciplina)}">${esc(s.disciplina)}</div>`; }
        h += `<div class="it" style="--c:${col(s.disciplina)}"><div class="tr">${esc(s.tramo)}</div><div class="tx">${esc(s.texto)}</div></div>`;
      });
      h += `</div></div><div class="hero" style="padding:16px"><div class="hi">⏱ Tiempo estimado</div><div class="q" style="font-size:16px;margin:6px 0 0">${esc(d.carrera.resumen)}</div></div>`;
    } else {
      h += `<div class="card" style="text-align:center"><div style="font-size:40px">🔒</div>
        <h3>Tu plan de carrera km a km</h3><div class="small muted">Se desbloquea en las últimas semanas (taper y semana de la prueba),
        cuando tus ritmos ya estén asentados. Te quedan ${esc(f.restante)}.</div></div>`;
    }
    return h;
  }

  function vPerfil(d) {
    const c = S.cfg;
    const comp = c.usaFecha ? fNum(c.competicion) : `${c.meses} meses de plan`;
    let h = `<div class="sec-t"><h2>Tu perfil</h2><span>v${esc(CFG.VERSION || '')}</span></div>
      <div class="card"><div style="display:flex;gap:12px;align-items:center">
        <div class="logo-big" style="width:54px;height:54px;border-radius:17px;animation:none"><span style="font-size:17px">70.3</span></div>
        <div><div style="font-size:19px;font-weight:900">${esc(c.nombre || 'Triatleta')}</div>
        <div class="small muted">${c.perfil === 'nuevo' ? 'Nuevo en triatlón' : 'Con experiencia'} · ${c.sexo === 'M' ? 'Hombre' : 'Mujer'}</div></div></div>
        <div class="row2" style="margin-top:12px"><div class="chip"><div class="l">Inicio</div><div class="v">${fNum(c.inicio)}</div></div>
        <div class="chip"><div class="l">Tu 70.3</div><div class="v">${esc(comp)}</div></div></div>
        <div style="margin-top:12px"><button class="btn" data-act="editar">✏️ Editar mi plan</button></div></div>`;
    h += `<div class="eyebrow" style="margin:16px 4px 8px">Tus datos</div><div class="list">`;
    if (c.modo === 'strava' && S.strava) {
      h += `<div class="li"><div class="e" style="background:#fc4c0233">🟠</div><div class="x"><b>Strava conectado</b>
        <span>${d && d.n_actividades != null ? d.n_actividades + ' actividades sincronizadas' : 'sesión guardada en este teléfono'}</span></div></div>
        <div class="li"><div class="e">📆</div><div class="x"><b>Días a sincronizar</b><span>Historial que se usa para tu forma</span></div>
        <select class="inp" style="width:auto;padding:8px" data-act="dias">${[30, 60, 90, 180, 365].map((n) => `<option ${n === (c.dias || 90) ? 'selected' : ''}>${n}</option>`).join('')}</select></div>
        <button class="li" data-act="desconectar"><div class="e">🔓</div><div class="x"><b>Desconectar Strava</b><span>Vuelve al modo demostración</span></div><span class="ch">›</span></button>`;
    } else {
      h += `<button class="li" data-act="strava"><div class="e" style="background:#fc4c0233">🟠</div><div class="x"><b>Conectar con Strava</b>
        <span>Tu plan se adapta a tus entrenamientos reales</span></div><span class="ch">›</span></button>
        <div class="li"><div class="e">🧪</div><div class="x"><b>Modo demostración</b><span>Datos de ejemplo que siguen tu plan; puedes avanzar los días</span></div></div>`;
    }
    h += `</div><div class="eyebrow" style="margin:16px 4px 8px">Aprende</div><div class="list">
      <button class="li" data-act="biblio"><div class="e">📖</div><div class="x"><b>Ejercicios y técnica</b><span>Qué es y cómo se hace cada ejercicio</span></div><span class="ch">›</span></button>
      <button class="li" data-act="glosario"><div class="e">ⓘ</div><div class="x"><b>Glosario</b><span>CTL, TSB, zonas, brick, taper…</span></div><span class="ch">›</span></button></div>
      <div class="eyebrow" style="margin:16px 4px 8px">Aplicación</div><div class="list">
      <button class="li" data-act="servidor"><div class="e">🛰️</div><div class="x"><b>Servidor</b><span>${esc(api())}</span></div><span class="ch">›</span></button>
      <button class="li" data-act="acerca"><div class="e">🎓</div><div class="x"><b>Acerca de</b><span>TFM · VIU · Máster en Big Data y Ciencia de Datos</span></div><span class="ch">›</span></button>
      <button class="li" data-act="reset"><div class="e">🗑️</div><div class="x"><b style="color:#ffb4b4">Borrar mis datos de este teléfono</b><span>Configuración, Strava y registros</span></div></button></div>`;
    return h;
  }

  // ------------------------------------------------------------------ pintado general
  const TABS = [['hoy', 'Hoy'], ['semana', 'Semana'], ['forma', 'Forma'], ['carrera', 'Carrera'], ['perfil', 'Perfil']];
  function pintarTabs() {
    $('#tabs').innerHTML = '<svg width="0" height="0" style="position:absolute"><defs><linearGradient id="g" x1="0" x2="1" y1="0" y2="1">'
      + '<stop offset="0" stop-color="#ff6b35"/><stop offset=".55" stop-color="#e83f6f"/><stop offset="1" stop-color="#7c3aed"/></linearGradient></defs></svg>'
      + TABS.map(([k, n]) => `<button class="tab ${S.tab === k ? 'on' : ''}" data-tab="${k}">${svgI(k)}<span>${n}</span></button>`).join('');
  }

  function pintar() {
    if (!S.cfg) return;
    pintarTabs();
    const d = S.data;
    const pill = $('#srcPill');
    if (d) {
      pill.textContent = d.fuente === 'strava' ? 'Strava' : 'Demo';
      pill.className = 'pill' + (d.fuente === 'strava' ? ' strava' : '');
    } else pill.textContent = '';
    const net = $('#net');
    if (S.error && d) {
      const t = S.lastAt ? new Date(S.lastAt) : null;
      const cuando = t ? (isoLocal(t) === hoyISO() ? ' de las ' : ` del ${fCorto(isoLocal(t))} a las `) + pad(t.getHours()) + ':' + pad(t.getMinutes()) : '';
      net.textContent = `⚠ ${S.error}. Mostrando tu plan guardado${cuando}.`;
      net.hidden = false;
    } else net.hidden = true;

    const v = $('#view');
    if (!d) {
      v.innerHTML = S.error
        ? `<div class="empty"><div class="e">📡</div><b>No se pudo cargar tu plan</b><br><span class="small">${esc(S.error)}</span>
           <div style="margin-top:16px"><button class="btn pri" data-act="reintentar">Reintentar</button></div>
           <div style="margin-top:10px"><button class="btn ghost" data-act="servidor">Revisar servidor</button></div></div>`
        : esqueleto();
      if (S.cargando) setTimeout(() => { const w = $('#wake'); if (w && S.cargando) w.hidden = false; }, 3500);
      pintarSim();
      return;
    }
    const vistas = { hoy: vHoy, semana: vSemana, forma: vForma, carrera: vCarrera, perfil: vPerfil };
    try { v.innerHTML = vistas[S.tab](d); }
    catch (e) { console.error(e); v.innerHTML = `<div class="empty"><div class="e">🤕</div>No se pudo mostrar esta pantalla.<br><span class="tiny">${esc(e.message)}</span></div>`; }
    if (S.tab === 'forma' && d.forma && d.forma.serie) {
      const se = d.forma.serie;
      activarCursor('gForma', (i) => {
        $('#tipForma').innerHTML = `<b>${fCorto(se.fechas[i])}</b> · Forma ${Math.round(se.ctl[i])} · Fatiga ${Math.round(se.atl[i])} · Frescura ${sig(se.tsb[i])}`;
      });
    }
    pintarSim();
  }

  function pintarSim() {
    const d = S.data, el = $('#sim');
    const activo = d && d.demo && S.cfg && S.cfg.modo !== 'strava';
    $('#app').classList.toggle('has-sim', !!activo);
    document.body.classList.toggle('sim-on', !!activo);
    if (!activo) { el.hidden = true; return; }
    const dia = S.sim || hoyISO();
    const dif = difDias(dia, hoyISO());
    const rel = dif === 0 ? 'hoy' : (dif > 0 ? `+${dif} días` : `${dif} días`);
    el.innerHTML = `<button data-sim="-1" aria-label="Día anterior">◀</button>
      <div class="d"><b>${esc(cap1(DIAS[aFecha(dia).getDay()]).slice(0, 3))} ${fCorto(dia)} · ${rel}</b>
        <span class="muted">simulador · semana ${d.fase.semana_actual}/${d.fase.semanas_totales}</span></div>
      <button data-sim="1" aria-label="Día siguiente">▶</button><button data-sim="7" class="pri" aria-label="Semana siguiente">▶▶</button>
      <button data-sim="0" aria-label="Volver a hoy">Hoy</button>`;
    el.hidden = false;
  }

  let tSim = null;
  function moverSim(n) {
    const d = S.data; if (!d || !d.demo) return;
    const lo = d.demo.desde, hi = d.demo.hasta;
    let nuevo = n === 0 ? hoyISO() : sumaDias(S.sim || hoyISO(), n);
    if (nuevo < lo) nuevo = lo;
    if (nuevo > hi) nuevo = hi;
    S.sim = nuevo === hoyISO() ? null : nuevo;
    pintarSim();
    clearTimeout(tSim); tSim = setTimeout(() => cargar(true), 220);
  }

  // ------------------------------------------------------------------ registro matinal
  function hojaMatinal() {
    const m0 = store.get('matinal', null);
    const m = (m0 && m0.fecha === diaObjetivo()) ? m0 : { sueno: 7.5, bb: 70, stress: 30, sleep_score: 75, enfermo: false };
    const r = (id, lab, min, max, st, v, ayuda) => `<div class="f"><label for="${id}">${lab}</label>
      <div class="rng"><input type="range" id="${id}" min="${min}" max="${max}" step="${st}" value="${v}"><output class="num" for="${id}">${v}</output></div>
      ${ayuda ? `<div class="tiny muted">${ayuda}</div>` : ''}</div>`;
    hoja(`<h2>☀️ ¿Cómo amaneciste?</h2><div class="small muted" style="margin-bottom:14px">30 segundos con los datos de tu reloj.
      El plan de hoy se ajusta: mantener, suavizar o descansar.</div>
      ${r('mSueno', 'Horas de sueño', 0, 12, 0.25, m.sueno)}
      ${r('mScore', 'Sleep Score (calidad del sueño)', 0, 100, 1, m.sleep_score == null ? 75 : m.sleep_score, 'Mide la calidad, no las horas. Mala por debajo de 60.')}
      ${r('mBB', 'Body Battery', 0, 100, 1, m.bb, 'Por debajo de 20-30 el cuerpo pide recuperación.')}
      ${r('mSt', 'Estrés', 0, 100, 1, m.stress, 'Sostenido por encima de 70, se asimila peor el entrenamiento.')}
      <label class="sw f"><span><b>Me siento enfermo</b><br><span class="tiny muted">Malestar, fiebre o síntomas</span></span>
        <input type="checkbox" id="mEnf" ${m.enfermo ? 'checked' : ''}></label>
      <button class="btn pri" data-act="guardar-matinal">Recalcular mi día</button>
      ${m0 && m0.fecha === diaObjetivo() ? '<div style="margin-top:8px"><button class="btn ghost" data-act="borrar-matinal">Quitar el registro de hoy</button></div>' : ''}`);
    $$('#sheet input[type=range]').forEach((i) => i.addEventListener('input', () => { i.nextElementSibling.value = i.value; }));
  }

  // ------------------------------------------------------------------ onboarding
  function nuevoBorrador() {
    const hoy = hoyISO();
    return { paso: 0, d: { modo: S.strava ? 'strava' : null, perfil: 'nuevo', sexo: 'M', inicio: hoy,
      usaFecha: true, competicion: sumaDias(hoy, 24 * 7), meses: 6, nombre: '',
      u703: { nat: '0:42', bici: '2:52', run: '2:01', total: '5:45', objetivo: '5:30' } } };
  }

  function abrirOnb(editar) {
    if (editar && S.cfg) S.onb = { paso: 1, d: JSON.parse(JSON.stringify(S.cfg)), editar: true };
    else S.onb = store.get('onb', null) || nuevoBorrador();
    if (!S.onb.d.u703) S.onb.d.u703 = nuevoBorrador().d.u703;
    $('#onb').hidden = false; document.body.classList.add('onb-on'); pintarOnb();
  }

  function pintarOnb() {
    const o = S.onb, d = o.d, p = o.paso;
    store.set('onb', o);
    const dots = `<div class="dots">${[0, 1, 2, 3].map((i) => `<i class="${i === p ? 'on' : ''}"></i>`).join('')}</div>`;
    let h = '';
    if (p === 0) {
      h = `<div style="display:grid;place-items:center;margin:10px 0 6px"><div class="logo-big"><span>70.3</span></div></div>
        <h1 style="text-align:center">Tu plan de triatlón que se adapta a ti cada día</h1>
        <p class="lead" style="text-align:center">De la primera brazada a la meta de tu 70.3: 1,9 km nadando, 90 en bici y 21,1 corriendo.</p>
        <div class="feat"><div class="e">🧠</div><div><b>Decide con tu carga real</b><span>Forma, fatiga y frescura (CTL/ATL/TSB) eligen cada lunes si toca cargar, mantener o descansar.</span></div></div>
        <div class="feat"><div class="e">☀️</div><div><b>Ajusta tu día en 30 s</b><span>Sueño, Body Battery y estrés: mantener, suavizar o descansar.</span></div></div>
        <div class="feat"><div class="e">🏁</div><div><b>Llega a la meta</b><span>Fases Base → Construcción → Pico → Taper, y plan de carrera km a km.</span></div></div>
        <button class="btn pri" data-onb="sig" style="margin-top:12px">Empezar</button>`;
    } else if (p === 1) {
      const conectado = !!S.strava;
      h = `<h1>¿De dónde salen tus datos?</h1><p class="lead">Con Strava, el plan usa tus entrenamientos reales. Con la demo puedes probarlo todo y avanzar los días.</p>
        <button class="choice ${d.modo === 'strava' ? 'on' : ''}" data-onb="modo" data-v="strava"><span class="e">🟠</span>
          <span><b>Strava ${conectado ? '· conectado ✓' : ''}</b><span>${conectado ? 'Tu sesión queda guardada en este teléfono' : 'Conecta tu cuenta (solo lectura de actividades)'}</span></span></button>
        ${d.modo === 'strava' && !conectado ? '<button class="btn strava" data-onb="conectar" style="margin-bottom:10px">Conectar con Strava</button>' : ''}
        <button class="choice ${d.modo === 'demo' ? 'on' : ''}" data-onb="modo" data-v="demo"><span class="e">🧪</span>
          <span><b>Probar con la demo</b><span>Un deportista de ejemplo que sigue tu plan</span></span></button>
        <div class="f" style="margin-top:14px"><label for="oNom">¿Cómo te llamas? (opcional)</label>
          <input class="inp" id="oNom" maxlength="30" value="${esc(d.nombre || '')}" placeholder="Tu nombre"></div>`;
    } else if (p === 2) {
      h = `<h1>Tu perfil</h1><p class="lead">Cambia la duración mínima del plan y la progresión de los ritmos.</p>
        <div class="f"><span class="lab">Experiencia</span><div class="seg2">
          <button class="${d.perfil === 'nuevo' ? 'on' : ''}" data-onb="perfil" data-v="nuevo">Nuevo en triatlón</button>
          <button class="${d.perfil === 'experimentado' ? 'on' : ''}" data-onb="perfil" data-v="experimentado">Con experiencia</button></div>
          <div class="tiny muted" style="margin-top:6px">Plan mínimo: ${MIN_SEM[d.perfil]} semanas (${d.perfil === 'nuevo' ? '6' : '3'} meses).</div></div>
        <div class="f"><span class="lab">Sexo</span><div class="seg2">
          <button class="${d.sexo === 'M' ? 'on' : ''}" data-onb="sexo" data-v="M">Hombre</button>
          <button class="${d.sexo === 'F' ? 'on' : ''}" data-onb="sexo" data-v="F">Mujer</button></div>
          <div class="tiny muted" style="margin-top:6px">Ajusta el cálculo de la carga (TRIMP).</div></div>
        ${d.perfil === 'experimentado' ? `<div class="f"><span class="lab">🏁 Tu último 70.3 (opcional, h:mm)</span>
          <div class="row2">${[['nat', 'Natación'], ['bici', 'Bici'], ['run', 'Carrera'], ['total', 'Total']].map(([k, l]) =>
            `<div><span class="tiny muted">${l}</span><input class="inp" data-u="${k}" inputmode="numeric" value="${esc(d.u703[k])}"></div>`).join('')}</div>
          <div style="margin-top:8px"><span class="tiny muted">Objetivo</span><input class="inp" data-u="objetivo" inputmode="numeric" value="${esc(d.u703.objetivo)}"></div></div>` : ''}`;
    } else {
      const fin = d.usaFecha ? d.competicion : sumaDias(d.inicio, d.meses * 28);
      const dias = Math.max(difDias(fin, hoyISO()), 0);
      const semTot = Math.ceil(difDias(fin, d.inicio) / 7);
      const corto = semTot < MIN_SEM[d.perfil];
      h = `<h1>Tus fechas</h1><p class="lead">El inicio es el ancla del plan: la semana avanza sola día a día.</p>
        <div class="f"><label for="oIni">Inicio del plan</label><input class="inp" type="date" id="oIni" max="${hoyISO()}" value="${d.inicio}"></div>
        <label class="sw f"><b>Ya tengo fecha de competición</b><input type="checkbox" id="oUsa" ${d.usaFecha ? 'checked' : ''}></label>
        ${d.usaFecha ? `<div class="f"><label for="oComp">¿Cuándo es tu 70.3?</label><input class="inp" type="date" id="oComp" min="${sumaDias(d.inicio, 7)}" value="${d.competicion}"></div>`
          : `<div class="f"><label for="oMes">Meses de plan</label><div class="rng"><input type="range" id="oMes" min="3" max="12" value="${d.meses}"><output>${d.meses}</output></div></div>`}
        <div class="card" style="text-align:center"><div class="eyebrow">Hasta tu 70.3</div>
          <div style="font-size:24px;font-weight:900">${esc(semanasTxt(dias || 0))}</div>
          <div class="small muted">Plan de ${semTot} semanas · ${fNum(fin)}</div></div>
        ${corto ? `<div class="adj lv-aviso" style="margin:0 0 10px">⚠ Para tu perfil se recomiendan al menos ${MIN_SEM[d.perfil]} semanas. Puedes seguir, pero plantea el objetivo como terminar bien.</div>` : ''}`;
    }
    const puedeSeguir = p !== 1 || d.modo === 'demo' || (d.modo === 'strava' && S.strava);
    const nav = p === 0 ? '' : `<div class="nav2">
      <button class="btn sm" data-onb="atras">${o.editar && p === 1 ? 'Cancelar' : '←'}</button>
      <button class="btn pri" data-onb="${p === 3 ? 'crear' : 'sig'}" ${puedeSeguir ? '' : 'disabled style="opacity:.45"'}>${p === 3 ? (o.editar ? 'Guardar cambios' : '🚀 Crear mi plan') : 'Continuar'}</button></div>`;
    $('#onb').innerHTML = `<div class="wrap fade-in">${dots}${h}${nav}</div>`;
  }

  function leerOnb() {
    const d = S.onb.d;
    const nom = $('#oNom'); if (nom) d.nombre = nom.value.trim();
    $$('#onb [data-u]').forEach((i) => { d.u703[i.dataset.u] = i.value.trim(); });
    const ini = $('#oIni'); if (ini && ini.value) d.inicio = ini.value > hoyISO() ? hoyISO() : ini.value;
    const usa = $('#oUsa'); if (usa) d.usaFecha = usa.checked;
    const comp = $('#oComp'); if (comp && comp.value) d.competicion = comp.value;
    const mes = $('#oMes'); if (mes) d.meses = +mes.value;
    if (d.competicion <= sumaDias(d.inicio, 6)) d.competicion = sumaDias(d.inicio, MIN_SEM[d.perfil] * 7);
  }

  function accionOnb(el) {
    const o = S.onb, d = o.d, a = el.dataset.onb;
    leerOnb();
    if (a === 'sig') o.paso = Math.min(o.paso + 1, 3);
    else if (a === 'atras') {
      if (o.editar && o.paso === 1) { cerrarOnb(); return; }
      o.paso = Math.max(o.paso - 1, 0);
    } else if (a === 'modo') d.modo = el.dataset.v;
    else if (a === 'conectar') { conectarStrava(); return; }
    else if (a === 'perfil') {
      const antes = d.perfil; d.perfil = el.dataset.v;
      if (antes !== d.perfil && !o.editar) d.competicion = sumaDias(d.inicio, MIN_SEM[d.perfil] * 7);
    } else if (a === 'sexo') d.sexo = el.dataset.v;
    else if (a === 'crear') {
      if (d.modo === 'strava' && !S.strava) { o.paso = 1; pintarOnb(); toast('Conecta Strava o elige la demo'); return; }
      const re = /^\d{1,2}:\d{2}$/;
      if (d.perfil === 'experimentado' && !Object.values(d.u703).every((v) => re.test(v))) {
        o.paso = 2; pintarOnb(); toast('Escribe los tiempos como h:mm (por ejemplo 2:52)'); return;
      }
      S.cfg = { modo: d.modo, perfil: d.perfil, sexo: d.sexo, inicio: d.inicio, usaFecha: d.usaFecha,
        competicion: d.competicion, meses: d.meses, nombre: d.nombre, u703: d.u703, dias: d.dias || (S.cfg && S.cfg.dias) || 90 };
      store.set('cfg', S.cfg); store.del('onb');
      S.data = null; S.sim = null; S.tab = 'hoy';
      cerrarOnb(); $('#app').hidden = false; cargar();
      toast(o.editar ? 'Plan actualizado' : '¡Tu plan está listo! 💪');
      return;
    }
    pintarOnb();
  }
  function cerrarOnb() {
    S.onb = null; store.del('onb'); $('#onb').hidden = true; $('#onb').innerHTML = '';
    document.body.classList.remove('onb-on');
  }

  // ------------------------------------------------------------------ biblioteca, glosario, servidor
  async function datosEj() {
    if (S.ej) return S.ej;
    S.ej = await llamar('/api/ejercicios', null, 60000); store.set('ej', S.ej); return S.ej;
  }
  async function hojaBiblio() {
    hoja('<h2>📖 Ejercicios y técnica</h2><div class="sk" style="height:200px"></div>');
    try {
      const e = await datosEj();
      const lista = (q) => e.ejercicios.filter((x) => !q || (x.titulo + ' ' + x.que).toLowerCase().includes(q))
        .map((x) => `<button class="li" data-act="ej" data-id="${esc(x.id)}"><div class="e">${esc(x.emoji)}</div><div class="x"><b>${esc(x.titulo)}</b>
          <span>${esc(x.que.slice(0, 70))}${x.que.length > 70 ? '…' : ''}</span></div><span class="ch">›</span></button>`).join('');
      hoja(`<h2>📖 Ejercicios y técnica</h2><input class="search" id="qEj" placeholder="Buscar: pallof, peso muerto, brick…">
        <div class="list" id="lEj">${lista('')}</div>`);
      $('#qEj').addEventListener('input', (ev) => { $('#lEj').innerHTML = lista(ev.target.value.toLowerCase().trim()); });
    } catch (er) { hoja(`<h2>📖 Ejercicios</h2><div class="empty">${esc(er.message)}</div>`); }
  }
  async function hojaGlosario() {
    hoja('<h2>ⓘ Glosario</h2><div class="sk" style="height:200px"></div>');
    try {
      const e = await datosEj();
      hoja(`<h2>ⓘ Glosario</h2>${e.glosario.map((g) => `<div class="card"><h3>${esc(g.termino)}</h3><div class="small muted">${esc(g.definicion)}</div></div>`).join('')}`);
    } catch (er) { hoja(`<h2>ⓘ Glosario</h2><div class="empty">${esc(er.message)}</div>`); }
  }
  function hojaServidor() {
    hoja(`<h2>🛰️ Servidor</h2><div class="small muted" style="margin-bottom:12px">Dirección de la API que calcula tu plan (el motor del TFM).</div>
      <div class="f"><input class="inp" id="sUrl" value="${esc(api())}" inputmode="url" autocapitalize="off" spellcheck="false"></div>
      <div class="row2"><button class="btn" data-act="probar">Probar</button><button class="btn pri" data-act="guardar-url">Guardar</button></div>
      <div id="sRes" class="small" style="margin-top:12px"></div>
      <div style="margin-top:8px"><button class="btn ghost sm" data-act="url-defecto">Restaurar la predeterminada</button></div>`);
  }
  async function probarServidor() {
    const prev = store.get('api', null); const url = $('#sUrl').value.trim();
    store.set('api', url); $('#sRes').textContent = 'Conectando…';
    try {
      const h = await llamar('/api/health', null, 70000);
      $('#sRes').innerHTML = `✅ Conectado · v${esc(h.version)}<br>Modelos XGBoost: ${h.modelos ? '✓' : '✗'} · Strava: ${h.strava ? '✓' : 'sin configurar'} · Gemini: ${h.gemini ? '✓' : 'no'}`;
    } catch (e) { $('#sRes').textContent = '❌ ' + e.message; }
    if (prev == null) store.del('api'); else store.set('api', prev);
  }

  function hojaKpi(k) {
    const d = S.data; if (!d) return;
    const fo = d.forma || {};
    if (k === 'semana') {
      hoja(`<h2>Semana de ${esc(d.semana.nombre.toLowerCase())}</h2><div class="blk">${esc(d.semana.motivo)}.</div>
        <div class="blk small muted">Cada lunes, el sistema decide el tipo de semana con la <b>media del TSB de la semana anterior</b> (reglas de la Tabla 7 del TFM):
        por debajo de −25 descanso; Body Battery &lt; 20 regenerativa; por debajo de −10 mantenimiento; por encima de +10 carga. La salud manda sobre la forma.</div>`);
    } else {
      hoja(`<h2>${k === 'ctl' ? 'Forma (CTL)' : 'Frescura (TSB)'}</h2>
        ${k === 'tsb' ? `<div class="blk">Media de la semana anterior (${esc(fo.semana_decision)}): <b>${sig(fo.tsb7, 1)}</b>. Es la que decide el tipo de semana.
          El TSB de hoy (<b>${sig(fo.tsb, 1)}</b>) cambia a diario: sube los días de descanso y baja los de carga.</div>` :
          `<div class="blk">CTL ${Math.round(fo.ctl)} de ${fo.ctl_objetivo} recomendada para completar un 70.3 con garantías.</div>`}
        <div class="blk small muted">CTL = forma acumulada (~6 semanas). ATL = fatiga (~7 días). TSB = CTL − ATL: positivo, descansado; negativo, cargado.
        Un TSB alto solo significa «a punto» tras un taper desde una CTL alta; si la CTL cae por un parón, es desentrenamiento.</div>
        <button class="btn" data-act="ir-forma">Ver mi gráfico de forma</button>`);
    }
  }

  // ------------------------------------------------------------------ eventos
  function enlazar() {
    document.addEventListener('click', (ev) => {
      const t = ev.target.closest('[data-tab],[data-act],[data-sim],[data-onb]');
      if (!t) return;
      if (t.dataset.onb) { accionOnb(t); return; }
      if (t.dataset.tab) { S.tab = t.dataset.tab; window.scrollTo(0, 0); pintar(); return; }
      if (t.dataset.sim != null) { moverSim(+t.dataset.sim); return; }
      const a = t.dataset.act, d = S.data;
      if (a === 'cerrar') cerrarHoja();
      else if (a === 'ayuda') hojaEjercicio(d.sesion_hoy.ayudas[+t.dataset.i]);
      else if (a === 'ayuda-s') hojaEjercicio(d.semana.sesiones[+t.dataset.i].ayudas[+t.dataset.k]);
      else if (a === 'video') abrirEnlace(t.dataset.url);
      else if (a === 'matinal') hojaMatinal();
      else if (a === 'guardar-matinal') {
        store.set('matinal', { fecha: diaObjetivo(), sueno: +$('#mSueno').value, sleep_score: +$('#mScore').value,
          bb: +$('#mBB').value, stress: +$('#mSt').value, enfermo: $('#mEnf').checked });
        cerrarHoja(); cargar();
      } else if (a === 'borrar-matinal') { store.del('matinal'); cerrarHoja(); cargar(); }
      else if (a === 'kpi') hojaKpi(t.dataset.k);
      else if (a === 'ir-forma') { cerrarHoja(); S.tab = 'forma'; pintar(); }
      else if (a === 'dia') {
        S.daySel = +t.dataset.i; $$('.dayb').forEach((b, i) => b.classList.toggle('sel', i === S.daySel));
        const c = $('#ses' + t.dataset.i); if (c) window.scrollTo({ top: c.getBoundingClientRect().top + window.scrollY - 70, behavior: 'smooth' });
      } else if (a === 'editar') abrirOnb(true);
      else if (a === 'strava') conectarStrava();
      else if (a === 'desconectar') desconectarStrava();
      else if (a === 'biblio') hojaBiblio();
      else if (a === 'glosario') hojaGlosario();
      else if (a === 'ej') { const e = (S.ej.ejercicios || []).find((x) => x.id === t.dataset.id); if (e) hojaEjercicio(e); }
      else if (a === 'servidor') hojaServidor();
      else if (a === 'probar') probarServidor();
      else if (a === 'guardar-url') { store.set('api', $('#sUrl').value.trim()); S.ej = null; cerrarHoja(); toast('Servidor guardado'); cargar(); }
      else if (a === 'url-defecto') { store.del('api'); cerrarHoja(); toast('Servidor predeterminado'); cargar(); }
      else if (a === 'reintentar') cargar();
      else if (a === 'acerca') {
        hoja(`<h2>🎓 Mi plan 70.3</h2><div class="blk">App del Trabajo Fin de Máster «Planificación adaptativa de entrenamientos de alta carga mediante
          aprendizaje automático: caso de estudio del triatlón de media distancia (113 km)». Máster en Big Data y Ciencia de Datos (VIU).</div>
          <div class="blk small muted">El plan lo deciden los modelos (XGBoost de transferencia) y las reglas de carga (CTL/ATL/TSB, Tabla 7); los textos solo lo explican.
          No sustituye el consejo médico: si tienes una lesión o una enfermedad, consulta a un profesional.</div>
          <div class="tiny muted">Versión ${esc(CFG.VERSION || '')} · Servidor ${esc(api())}</div>`);
      } else if (a === 'reset') {
        if (window.confirm('¿Borrar la configuración, la conexión con Strava y tus registros de este teléfono?')) {
          ['cfg', 'strava', 'last', 'lastAt', 'matinal', 'onb', 'ej'].forEach(store.del);
          S.cfg = null; S.strava = null; S.data = null; S.sim = null;
          $('#app').hidden = true; abrirOnb(false);
        }
      }
    });
    document.addEventListener('change', (ev) => {
      if (ev.target.dataset && ev.target.dataset.act === 'dias') { S.cfg.dias = +ev.target.value; store.set('cfg', S.cfg); cargar(); }
      if (S.onb && ['oUsa', 'oIni', 'oComp', 'oMes'].includes(ev.target.id)) { leerOnb(); pintarOnb(); }
    });
    document.addEventListener('input', (ev) => {
      if (S.onb && ev.target.id === 'oMes') { ev.target.nextElementSibling.value = ev.target.value; }
    });
    $('#sheetBg').addEventListener('click', cerrarHoja);
    $('#btnRefresh').innerHTML = svgI('refresh');
    $('#btnRefresh').addEventListener('click', () => cargar());

    if (PL.App) {
      PL.App.addListener('appUrlOpen', (e) => volverDeStrava(e.url));
      PL.App.addListener('resume', () => {
        // Al volver a la app: si cambió el día o pasó media hora, se actualiza solo
        if (S.cfg && !S.sim && (!S.data || S.data.hoy !== hoyISO() || Date.now() - (S.lastAt || 0) > 1800000)) cargar(true);
      });
      PL.App.addListener('backButton', () => {
        if (hojaAbierta()) cerrarHoja();
        else if (S.onb && S.onb.paso > 0) accionOnb({ dataset: { onb: 'atras' } });
        else if (S.cfg && S.tab !== 'hoy') { S.tab = 'hoy'; pintar(); }
        else PL.App.exitApp();
      });
    }
  }

  // ------------------------------------------------------------------ arranque
  async function iniciar() {
    await restaurarPreferencias();
    S.cfg = store.get('cfg', null); S.strava = store.get('strava', null);
    S.data = store.get('last', null); S.lastAt = store.get('lastAt', null);
    if (PL.StatusBar) {
      PL.StatusBar.setBackgroundColor({ color: '#0b1220' }).catch(() => {});
      PL.StatusBar.setStyle({ style: 'DARK' }).catch(() => {});
    }
    enlazar();
    // Navegador (pruebas): Strava vuelve con ?code= en la propia URL
    if (!NATIVO && /[?&](code|error)=/.test(location.search)) {
      const u = location.href; history.replaceState(null, '', location.pathname); volverDeStrava(u);
    }
    if (S.cfg) { $('#app').hidden = false; pintar(); cargar(!!S.data); }
    else abrirOnb(false);
    setTimeout(() => $('#splash').classList.add('out'), 350);
    setTimeout(() => { $('#splash').hidden = true; }, 800);
  }

  // Exponer para pruebas automáticas
  window.__MP = { S, pintar, cargar, moverSim, abrirOnb, accionOnb, store };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
  else iniciar();
})();
