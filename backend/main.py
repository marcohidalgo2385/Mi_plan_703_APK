# -*- coding: utf-8 -*-
"""API de «Mi plan 70.3» para la app móvil.

Expone el MISMO motor del demostrador Streamlit (motor.py, generado desde app.py):
fases del macrociclo, reglas de la Tabla 7 (tipo de semana con el TSB medio de la
semana anterior), CTL/ATL/TSB, plan semanal, ajuste del día, zonas, modelos XGBoost
de transferencia, plan de carrera y sincronización con Strava.

Ejecutar en local:   uvicorn main:app --reload --port 8000
Variables de entorno (Render → Environment):
    STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET   credenciales de la API de Strava
    STRAVA_MOBILE_REDIRECT                   por defecto miplan703://miplan703.streamlit.app
    GEMINI_API_KEY                           opcional (frase y explicaciones)
    GEMINI_CON_STRAVA                        "1" para usar Gemini también con datos de
                                             Strava (por defecto no: política de Strava)
"""
import logging
import math
import os
import urllib.parse
from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import st_shim
import motor as M

logging.basicConfig(level=logging.INFO)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
M.MODELOS_DIR = os.path.join(BASE_DIR, 'modelos')
VERSION = '1.0.0'
REDIRECT_MOVIL = os.getenv('STRAVA_MOBILE_REDIRECT', 'miplan703://miplan703.streamlit.app')
GEMINI_CON_STRAVA = os.getenv('GEMINI_CON_STRAVA', '0') == '1'
_EXPLICACIONES = {}     # caché de la explicación del plan (Gemini), por día y semana

# Cliente de Strava NUEVO en cada llamada: el del motor era compartido (Streamlit) y en
# una API con varios usuarios a la vez no debe compartirse el token.
if M.STRAVA_AVAILABLE:
    M.init_strava_client = lambda: (M.StravaClient()
                                    if (M.STRAVA_CLIENT_ID and M.STRAVA_CLIENT_SECRET) else None)

app = FastAPI(title='Mi plan 70.3 API', version=VERSION)
# La app Android carga desde https://localhost (Capacitor); sin cookies, así que basta *
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'],
                   allow_headers=['*'])


# ============================================================================ modelos
class Matinal(BaseModel):
    sueno: float = Field(7.5, ge=0, le=14)
    bb: float = Field(70, ge=0, le=100)
    stress: float = Field(30, ge=0, le=100)
    sleep_score: Optional[float] = Field(None, ge=0, le=100)
    enfermo: bool = False


class Ultimo703(BaseModel):
    nat: str = '0:42'
    bici: str = '2:52'
    run: str = '2:01'
    total: str = '5:45'
    objetivo: str = '5:30'


class PlanIn(BaseModel):
    perfil: str = Field('nuevo', pattern='^(nuevo|experimentado)$')
    sexo: str = Field('M', pattern='^(M|F)$')
    inicio: date
    competicion: Optional[date] = None
    meses: Optional[int] = Field(None, ge=3, le=12)
    fecha_sim: Optional[date] = None          # solo demo: «viajar» por el plan
    strava_token: Optional[str] = None
    dias_sync: int = Field(90, ge=30, le=365)
    matinal: Optional[Matinal] = None
    ultimo703: Optional[Ultimo703] = None
    nombre: Optional[str] = None


class CodeIn(BaseModel):
    code: str


class RefreshIn(BaseModel):
    refresh_token: str


# ============================================================================ utilidades
def _num(v, nd=1):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return None if (math.isnan(v) or math.isinf(v)) else round(v, nd)


def _limpia(o):
    """Convierte numpy/pandas/sets a JSON."""
    if isinstance(o, dict):
        return {str(k): _limpia(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [_limpia(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        return _num(o, 3)
    if isinstance(o, (pd.Timestamp, date)):
        return pd.Timestamp(o).date().isoformat()
    return o


def _ejercicio(e):
    k, emo, tit, _p, que, como, clave, vid = e
    return {'id': k, 'emoji': emo, 'titulo': tit, 'que': que, 'como': como,
            'clave': clave, 'video': M.url_video(vid)}


def _camino(per, ini, comp, hoy):
    """Tramos del macrociclo (misma lógica que html_camino de la app web)."""
    sem_tot = max(int(per['semanas_totales']), 1)
    sem_act = int(per['semana_actual'])
    desfase = (sem_tot - sem_act + 1) - int(per['semanas_restantes'])

    def fase_sem(s):
        r = sem_tot - s + 1 - desfase
        return ('COMPETENCIA' if r <= 1 else 'TAPERING' if r <= 3 else 'PICO' if r <= 6
                else 'CONSTRUCCION' if r <= 12 else 'BASE')

    tramos = []
    for s in range(1, sem_tot + 1):
        f = fase_sem(s)
        if tramos and tramos[-1]['fase'] == f:
            tramos[-1]['hasta'] = s
        else:
            tramos.append({'fase': f, 'desde': s, 'hasta': s})
    info = {n: (c, d) for n, c, _ca, d in M.FASES_INFO}
    for t in tramos:
        nom = M.NOMBRE_FASE.get(t['fase'], t['fase'])
        t['nombre'] = nom
        t['color'], t['descripcion'] = info.get(nom, ('#1d6fa5', ''))
        t['inicio'] = (pd.Timestamp(ini) + pd.Timedelta(days=(t['desde'] - 1) * 7)).date().isoformat()
    pos = min(max((hoy - pd.Timestamp(ini)).days / 7.0, 0.0), float(sem_tot))
    return {'tramos': tramos, 'posicion_semanas': round(pos, 2), 'semanas_totales': sem_tot,
            'dias_carrera': max((pd.Timestamp(comp).normalize() - hoy).days, 0)}


def _banda_tsb(tsb, desentrenando, ctl, ctl_ref, perdida):
    if desentrenando:
        return ('aviso', 'Frescura por pérdida de forma',
                f'Tu fitness (CTL) ha caído de {ctl_ref:.0f} a {ctl:.0f} (−{perdida:.0f} %). '
                'Un TSB positivo aquí no significa estar a punto: es «óxido». Reconstruye de '
                'forma progresiva antes de exigirte o competir.')
    if tsb > 25:
        return 'aviso', 'Demasiado fresco', 'Riesgo de desentrenar si se mantiene.'
    if tsb > 5:
        return 'ok', 'Fresco', 'A punto para competir (zona de taper).'
    if tsb >= -10:
        return 'info', 'En equilibrio', 'Carga de mantenimiento.'
    if tsb >= -30:
        return 'info', 'Carga productiva', 'Estás construyendo forma; esta fatiga es normal y buscada.'
    return 'error', 'Sobrecarga', 'Fatiga alta: conviene aliviar para no arriesgar lesión.'


def _aviso_inactividad(dias):
    if dias is None or dias < 7:
        return None
    s = dias / 7.0
    if dias >= 56:
        return ('error', f'Llevas {dias} días (~{s:.0f} semanas) sin entrenar. La pérdida de forma '
                'es casi total: reinicia desde Base con una progresión suave (~10 %/semana). Si el '
                'parón fue por lesión o accidente, valida el alta médica antes de volver.')
    if dias >= 28:
        return ('aviso', f'Llevas {dias} días (~{s:.0f} semanas) sin entrenar. Al volver, reconstruye '
                'desde Base a un ~50-60 % de tu volumen previo y sube de forma gradual.')
    if dias >= 14:
        return ('aviso', f'Llevas {dias} días sin entrenar. El desentrenamiento ya está en curso: '
                'retoma pronto y de forma progresiva.')
    return ('info', f'Llevas {dias} días sin entrenar. Aún conservas la forma, pero vuelve a la '
            'rutina esta semana para no empezar a perder base.')


# ============================================================================ endpoints
@app.get('/')
@app.get('/api/health')
def health():
    return {'ok': True, 'version': VERSION, 'modelos': bool(M.cargar_modelos()),
            'strava': bool(M.STRAVA_AVAILABLE and M.STRAVA_CLIENT_ID and M.STRAVA_CLIENT_SECRET),
            'gemini': bool(M.inicializar_gemini())}


@app.get('/api/ejercicios')
def ejercicios():
    return {'ejercicios': [_ejercicio(e) for e in M.EJERCICIOS],
            'glosario': [{'termino': k, 'definicion': v} for k, v in M.GLOSARIO.items()]}


@app.post('/api/plan')
def plan(p: PlanIn):
    # --- estado de la petición (la fecha simulada solo existe en la demo) ---
    demo = not p.strava_token
    st_shim.nueva_sesion(fecha_sim=p.fecha_sim if (demo and p.fecha_sim) else None)
    hoy = M.fecha_hoy()
    perfil_df, fitness, acts = M.datos_demo()
    perfil_row = perfil_df.set_index('athlete').loc['Demo']
    pred_bici = 26.5

    ini = min(p.inicio, date.today())
    if p.competicion:
        comp = p.competicion
    else:
        comp = ini + timedelta(weeks=(p.meses or (6 if p.perfil == 'nuevo' else 3)) * 4)
    if comp <= ini:
        raise HTTPException(422, 'La fecha de la competición debe ser posterior al inicio del plan.')

    # --- datos: Strava (reales) o demo (siguen el propio plan) ---
    usando_strava = False
    nombre = p.nombre or 'triatleta'
    if p.strava_token:
        if not M.STRAVA_AVAILABLE:
            raise HTTPException(503, 'Strava no está disponible en el servidor.')
        a = M.fetch_strava_activities(p.strava_token, days=p.dias_sync)
        if a is None:
            raise HTTPException(401, 'Strava no aceptó el acceso. Vuelve a conectar tu cuenta.')
        if not a.empty:
            acts, usando_strava = a, True
        nombre = p.nombre or M.fetch_strava_athlete_name(p.strava_token) or nombre

    per = M.calcular_fase(comp, p.perfil, ini, None)
    if not usando_strava:
        acts = M.acts_demo_progresivo(per, p.sexo, ini)
    zonas = M.calcular_zonas(perfil_row, acts, p.perfil, pred_bici)
    fit_vivo = M.fitness_desde_actividades(acts, zonas['fc_rep'], zonas['fc_max'], p.sexo)
    if not fit_vivo.empty:
        fitness = fit_vivo

    # --- modelos XGBoost del TFM (mismas reglas de uso que la app web) ---
    modelos = M.cargar_modelos()
    infer = {}
    if modelos:
        infer = M.inferir_con_modelos(modelos, M.features_atleta(acts, zonas, fitness, perfil_row, p.sexo))
        n_dep = (acts['sport'].value_counts() if (acts is not None and not acts.empty
                                                  and 'sport' in acts.columns) else pd.Series(dtype=int))
        vb, vr = infer.get('bici_cons_kmh'), infer.get('run_cons_kmh')
        sin_bici = bool(vb) and n_dep.get('CYCLING', 0) < 6
        sin_run = bool(vr) and n_dep.get('RUNNING', 0) < 6
        if sin_bici or sin_run:
            zonas = M.calcular_zonas(perfil_row, acts, p.perfil, vb if sin_bici else pred_bici,
                                     vr if sin_run else np.nan)
        if vb:
            zonas['bici_obj'] = vb
        if sin_run:
            zonas['run_obj'] = vr
    objetivo = None
    if p.perfil == 'experimentado' and p.ultimo703:
        u = p.ultimo703
        objetivo = M.analizar_objetivo({'nat': u.nat, 'bici': u.bici, 'run': u.run, 'total': u.total},
                                       u.objetivo, per['semanas_restantes'])
        if objetivo:
            zonas['run_obj'] = objetivo['v_run_obj']
            zonas['bici_obj'] = objetivo['v_bici_obj']
            zonas['nat_obj'] = objetivo['v_nat_obj']

    # --- tipo de semana (Tabla 7) con la semana anterior cerrada ---
    mat = p.matinal
    lunes = hoy - pd.Timedelta(days=hoy.dayofweek)
    fit_dec = fitness
    if not fitness.empty and 'date' in fitness.columns:
        prev = fitness[pd.to_datetime(fitness['date']) < lunes]
        if len(prev) >= 7:
            fit_dec = prev
    tipo_semana, motivo = M.decidir_tipo_semana(fit_dec, mat.bb if mat else None,
                                                mat.stress if mat else None)
    nombre_semana = M.NOMBRE_TIPO[tipo_semana]
    if per['fase'] in ('TAPERING', 'COMPETENCIA') and tipo_semana in ('CARGA', 'MANTENIMIENTO'):
        nombre_semana = 'Tapering' if per['fase'] == 'TAPERING' else 'Carrera'
        motivo += '; en esta fase manda la puesta a punto para la prueba'

    # --- plan de la semana y sesión de hoy ---
    sesiones, meta = M.generar_plan_semanal(p.perfil, per, zonas, acts, p.sexo, tipo_semana)
    dia_hoy = M.DIAS_ES[hoy.dayofweek]
    for i, s in enumerate(sesiones):
        f = lunes + pd.Timedelta(days=i)
        s['fecha'] = f.date().isoformat()
        s['es_hoy'] = str(s['dia']).startswith(dia_hoy)
        s['pasado'] = f < hoy
        s['ayudas'] = [_ejercicio(e) for e in M.ayudas_sesion(f"{s['tipo']} {s['detalle']}")]
    ses_hoy = next((s for s in sesiones if s['es_hoy']), None)

    ajuste = None
    if mat:
        decision, motivos, detalle = M.actualizar_hoy([ses_hoy] if ses_hoy else [], zonas, mat.sueno,
                                                      mat.bb, mat.stress, mat.enfermo, mat.sleep_score)
        if not usando_strava or GEMINI_CON_STRAVA:
            txt = ''
            if ses_hoy:
                txt = f"{ses_hoy['deporte']} · {ses_hoy['tipo']}" + \
                      (f" · {ses_hoy['dur_min']} min" if ses_hoy['dur_min'] else '')
            detalle = M.generar_explicacion_dia(nombre, dia_hoy, decision, tuple(motivos), zonas,
                                                per['fase'], txt) or detalle
        ajuste = {'decision': decision, 'motivos': motivos, 'detalle': detalle,
                  'body_battery': mat.bb, 'estres': mat.stress, 'sueno': mat.sueno,
                  'sleep_score': mat.sleep_score,
                  'sleep_label': M.sleep_score_label(mat.sleep_score)}

    # --- forma: CTL/ATL/TSB, TSB de la semana anterior y avisos ---
    ctl = atl = tsb = tsb7 = None
    forma = {}
    if not fitness.empty:
        ctl = float(fitness['CTL'].iloc[-1])
        atl = float(fitness['ATL'].iloc[-1])
        tsb = float(fitness['TSB'].iloc[-1])
        t7 = fit_dec['TSB'].dropna().tail(7) if 'TSB' in fit_dec.columns else pd.Series(dtype=float)
        tsb7 = float(t7.mean()) if not t7.empty else None
        fdd = pd.to_datetime(fit_dec['date']).tail(7)
        sem_dec = f"{fdd.min():%d/%m}–{fdd.max():%d/%m}" if not fdd.empty else ''
        fd = fitness.copy()
        fd['date'] = pd.to_datetime(fd['date'])
        prev = fd[fd['date'] <= fd['date'].iloc[-1] - pd.Timedelta(days=28)]
        ctl_ref = float(prev['CTL'].iloc[-1]) if not prev.empty else float(fd['CTL'].iloc[0])
        perdida = ((ctl_ref - ctl) / ctl_ref * 100.0) if ctl_ref > 1e-6 else 0.0
        dias_inactivo = None
        if acts is not None and not acts.empty and 'date' in acts.columns:
            ad = pd.to_datetime(acts['date'], utc=True, errors='coerce').dt.tz_localize(None).dropna()
            if not ad.empty:
                dias_inactivo = int((hoy - ad.max().normalize()).days)
        desentrenando = (tsb > 0 and perdida >= 30.0) or (dias_inactivo is not None and dias_inactivo >= 14)
        nivel, titulo, texto = _banda_tsb(tsb, desentrenando, ctl, ctl_ref, perdida)
        ramp = (M.CTL_OBJETIVO_70_3 - ctl) / max(per['semanas_restantes'], 1)
        if per['fase'] in ('TAPERING', 'COMPETENCIA'):
            progreso = 'fase final: mantener, no construir'
        elif ramp <= 0:
            progreso = 'objetivo de forma alcanzado'
        elif ramp <= 3:
            progreso = 'en ruta'
        elif ramp <= 6:
            progreso = 'justo: evitar semanas perdidas'
        else:
            progreso = 'riesgo: forma lejos del objetivo'
        serie = fd.tail(120)
        forma = {'ctl': _num(ctl), 'atl': _num(atl), 'tsb': _num(tsb), 'tsb7': _num(tsb7),
                 'semana_decision': sem_dec, 'banda': {'nivel': nivel, 'titulo': titulo, 'texto': texto},
                 'desentrenando': bool(desentrenando), 'dias_inactivo': dias_inactivo,
                 'aviso_inactividad': _aviso_inactividad(dias_inactivo),
                 'ctl_objetivo': M.CTL_OBJETIVO_70_3,
                 'rampa': None if per['fase'] in ('TAPERING', 'COMPETENCIA') else _num(max(ramp, 0)),
                 'progreso': progreso,
                 'serie': {'fechas': [d.date().isoformat() for d in serie['date']],
                           'ctl': [_num(v) for v in serie['CTL']],
                           'atl': [_num(v) for v in serie['ATL']],
                           'tsb': [_num(v) for v in serie['TSB']]}}

    idx_prog, kpis_prog = M.progreso_semanal(acts, ini)
    progreso_disc = None
    if idx_prog is not None:
        progreso_disc = {'semanas': [int(i) for i in idx_prog.index],
                         'series': {c: [_num(v) for v in idx_prog[c]] for c in idx_prog.columns},
                         'kpis': {n: {'valor': (M.pace_swim(va) if n == 'Natación' else f'{va:.1f} km/h'),
                                      'mejora_pct': _num(pct)} for n, (va, pct) in kpis_prog.items()}}

    # --- zonas y ritmos (progresan con el plan) ---
    mej = M.factor_mejora(per, p.perfil)
    mej_pico = M.factor_mejora({'semana_actual': per['semanas_totales'],
                                'semanas_totales': per['semanas_totales']}, p.perfil)
    base_fase = per['fase'] == 'BASE'
    zonas_out = {
        'fc_max': zonas['fc_max'], 'fc_rep': zonas['fc_rep'],
        'hr': {k: list(v) for k, v in zonas['hr'].items()},
        'colores': M.GARMIN_COLORS, 'fuente': zonas['fuente_z2'],
        'ritmos': [
            {'lab': 'Z2 · ppm', 'val': f"{zonas['hr']['Z2'][0]}-{zonas['hr']['Z2'][1]}", 'off': False},
            {'lab': 'Z4 · ppm', 'val': f"{zonas['hr']['Z4'][0]}-{zonas['hr']['Z4'][1]}", 'off': base_fase},
            {'lab': 'Rodaje', 'val': M.pace_run(zonas['run_z2'] * mej), 'off': False},
            {'lab': 'Series', 'val': M.pace_run(zonas['run_z4'] * mej), 'off': base_fase},
            {'lab': 'Bici Z2', 'val': f"{zonas['bici_z2'] * mej:.0f} km/h", 'off': False},
            {'lab': 'Natación', 'val': M.pace_swim(zonas['nat_z2'] * mej), 'off': False}],
        'rodaje_hoy': M.pace_run(zonas['run_z2'] * mej), 'rodaje_pico': M.pace_run(zonas['run_z2'] * mej_pico),
        'modelos': {'bici_pred': _num(infer.get('bici_pred_kmh')), 'bici_cons': _num(infer.get('bici_cons_kmh')),
                    'run_pred': M.pace_run(infer['run_pred_kmh']) if infer.get('run_pred_kmh') else None,
                    'run_cons': M.pace_run(infer['run_cons_kmh']) if infer.get('run_cons_kmh') else None}}

    # --- carrera ---
    carrera = None
    if per['fase'] in ('COMPETENCIA', 'TAPERING'):
        seg, resumen = M.plan_competencia(zonas, objetivo)
        carrera = {'segmentos': [{'disciplina': d, 'tramo': t, 'texto': x} for d, t, x in seg],
                   'resumen': resumen.replace('**', '')}

    # --- textos: frase del día y por qué este plan ---
    usa_ia = (not usando_strava) or GEMINI_CON_STRAVA
    base = M.FRASES_DIA[hoy.dayofyear % len(M.FRASES_DIA)]
    frase = M.generar_frase_dia(nombre, per['fase'], hoy.toordinal(), base) if usa_ia else base
    frase = str(frase).strip()
    frase = frase[:1].upper() + frase[1:] + ('' if frase[-1:] in '.!?' else '.')
    explicacion = None
    if usa_ia:
        clave = (nombre, p.perfil, per['fase'], M.txt_restante(per), round(ctl or 50.0),
                 nombre_semana, motivo, hoy.date())
        if clave not in _EXPLICACIONES:
            if len(_EXPLICACIONES) > 256:
                _EXPLICACIONES.clear()
            _EXPLICACIONES[clave] = M.generar_explicacion_plan(
                nombre, p.perfil, per['fase'], M.txt_restante(per), ctl or 50.0,
                nombre_semana.lower(), motivo, [dict(s) for s in sesiones])
        explicacion = _EXPLICACIONES[clave]
    if not explicacion:
        explicacion = (f"Semana de {nombre_semana.lower()} ({motivo}). Plan para un atleta "
                       f"{'nuevo' if p.perfil == 'nuevo' else 'con experiencia'} en fase "
                       f"{M.NOMBRE_FASE.get(per['fase'], per['fase'])} con {M.txt_restante(per)} "
                       "para la competencia. La carga progresiva y la validación con tu historial "
                       "mantienen ritmos realistas. Además de nadar, pedalear y correr, incluye "
                       "fuerza de piernas y core (más eficiencia, menos lesiones) y desnivel: "
                       "subidas en bici para ganar potencia y bajadas en carrera para que el "
                       "músculo aguante el día del 70.3.")

    res_sem = {
        'sesiones': sum(1 for s in sesiones if s['deporte'] in ('Natación', 'Ciclismo', 'Carrera', 'Competencia')),
        'fuerza': sum(1 for s in sesiones if s['deporte'] == 'Fuerza'),
        'minutos': int(sum(int(s.get('dur_min') or 0) for s in sesiones)),
        'km_nat': _num(sum(s['km'] for s in sesiones if s['deporte'] == 'Natación'), 1),
        'km_bici': _num(sum(s['km'] for s in sesiones if s['deporte'] == 'Ciclismo'), 0),
        'km_carrera': _num(sum(s['km'] for s in sesiones if s['deporte'] in ('Carrera', 'Competencia')), 1)}

    demo_info = None
    if not usando_strava:
        ev = {v: k for k, v in M.eventos_demo(per['semanas_totales']).items()}
        demo_info = {'desde': ini.isoformat(), 'hasta': max(comp, ini).isoformat(),
                     'sobrecarga': ev.get('sobrecarga'), 'viaje': ev.get('viaje')}

    out = {
        'hoy': hoy.date().isoformat(), 'dia': dia_hoy, 'nombre': nombre,
        'fuente': 'strava' if usando_strava else 'demo',
        'n_actividades': int(len(acts)) if usando_strava else None,
        'frase': frase,
        'fase': {**per, 'nombre': M.NOMBRE_FASE.get(per['fase'], per['fase']),
                 'restante': M.txt_restante(per)},
        'camino': _camino(per, ini, comp, hoy),
        'competicion': comp.isoformat(), 'inicio': ini.isoformat(),
        'semana': {'tipo': tipo_semana, 'nombre': nombre_semana, 'motivo': motivo,
                   'meta': {k: v for k, v in meta.items() if k != 'disciplinas'},
                   'resumen': res_sem, 'sesiones': sesiones},
        'sesion_hoy': ses_hoy, 'ajuste': ajuste, 'forma': forma, 'progreso': progreso_disc,
        'zonas': zonas_out, 'carrera': carrera, 'objetivo': objetivo,
        'explicacion': explicacion, 'demo': demo_info,
        'plan_viable': per['plan_viable'],
    }
    return _limpia(out)


# ============================================================================ Strava
def _strava_ok():
    if not (M.STRAVA_AVAILABLE and M.STRAVA_CLIENT_ID and M.STRAVA_CLIENT_SECRET):
        raise HTTPException(503, 'Strava no está configurado en el servidor.')


@app.get('/api/strava/auth-url')
def strava_auth_url(redirect_uri: str = REDIRECT_MOVIL):
    """URL de autorización. La app la abre en el navegador; Strava vuelve a
    miplan703://... con ?code=, y la app la canjea en /api/strava/token."""
    _strava_ok()
    q = {'client_id': M._strava_client_id_int(), 'redirect_uri': redirect_uri,
         'response_type': 'code', 'approval_prompt': 'auto', 'scope': 'activity:read_all'}
    return {'url': 'https://www.strava.com/oauth/mobile/authorize?' + urllib.parse.urlencode(q),
            'url_web': 'https://www.strava.com/oauth/authorize?' + urllib.parse.urlencode(q)}


def _tokens(tok):
    return {'access_token': tok.get('access_token'), 'refresh_token': tok.get('refresh_token'),
            'expires_at': tok.get('expires_at')}


@app.post('/api/strava/token')
def strava_token(c: CodeIn):
    _strava_ok()
    try:
        tok = M.StravaClient().exchange_code_for_token(
            client_id=M._strava_client_id_int(), client_secret=M.STRAVA_CLIENT_SECRET, code=c.code)
    except Exception as e:
        raise HTTPException(400, f'Strava rechazó el código: {e}')
    out = _tokens(tok)
    out['nombre'] = M.fetch_strava_athlete_name(out['access_token'])
    return out


@app.post('/api/strava/refresh')
def strava_refresh(r: RefreshIn):
    _strava_ok()
    try:
        tok = M.StravaClient().refresh_access_token(
            client_id=M._strava_client_id_int(), client_secret=M.STRAVA_CLIENT_SECRET,
            refresh_token=r.refresh_token)
    except Exception as e:
        raise HTTPException(401, f'Strava no renovó el acceso: {e}')
    return _tokens(tok)
