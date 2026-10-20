# -*- coding: utf-8 -*-
"""Pruebas de la API: python -m pytest backend/tests  (o python backend/tests/test_api.py)."""
import json
import os
import sys
import warnings
from datetime import date, timedelta

warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

c = TestClient(main.app)
HOY = date.today()


def _plan(**kw):
    r = c.post('/api/plan', json=kw)
    assert r.status_code == 200, r.text[:400]
    d = r.json()
    json.dumps(d)                         # todo serializable
    return d


def test_health_y_ejercicios():
    h = c.get('/api/health').json()
    assert h['ok'] and h['modelos'] is True
    e = c.get('/api/ejercicios').json()
    assert len(e['ejercicios']) >= 15 and len(e['glosario']) >= 10


def test_168_dias_son_24_semanas():
    d = _plan(perfil='nuevo', sexo='M', inicio=str(HOY), competicion=str(HOY + timedelta(days=168)))
    assert d['fase']['semanas_restantes'] == 24 and d['fase']['dias_restantes'] == 168
    assert d['fase']['restante'] == '24 semanas (168 días)'
    assert d['fase']['semana_actual'] == 1 and d['fase']['nombre'] == 'Base'
    assert len(d['semana']['sesiones']) == 7 and d['sesion_hoy'] is not None
    assert d['camino']['dias_carrera'] == 168


def test_experimentado_con_objetivo():
    d = _plan(perfil='experimentado', sexo='F', inicio=str(HOY - timedelta(days=30)), meses=4,
              ultimo703=dict(nat='0:40', bici='2:50', run='2:00', total='5:40', objetivo='5:25'))
    assert d['objetivo'] and d['objetivo']['objetivo_total'] == '5:25'


def test_simulacion_completa_demo():
    ini, comp = HOY, HOY + timedelta(days=168)
    tipos, fases = set(), set()
    for dd in range(0, 169, 4):
        d = _plan(perfil='nuevo', sexo='M', inicio=str(ini), competicion=str(comp),
                  fecha_sim=str(ini + timedelta(days=dd)))
        assert d['hoy'] == str(ini + timedelta(days=dd))
        tipos.add(d['semana']['nombre'])
        fases.add(d['fase']['nombre'])
        # la frescura de la semana anterior y la de hoy son datos distintos y ambos existen
        assert d['forma']['tsb'] is not None
    assert {'Base', 'Construcción', 'Pico', 'Taper', '70.3'} <= fases
    assert len(tipos) >= 3, tipos
    final = _plan(perfil='nuevo', sexo='M', inicio=str(ini), competicion=str(comp), fecha_sim=str(comp))
    assert final['carrera'] and len(final['carrera']['segmentos']) == 15


def test_ajuste_del_dia():
    base = dict(perfil='nuevo', sexo='M', inicio=str(HOY), competicion=str(HOY + timedelta(days=120)))
    assert _plan(**base, matinal=dict(sueno=4, bb=15, stress=80))['ajuste']['decision'] == 'DESCANSO HOY'
    assert _plan(**base, matinal=dict(sueno=6, bb=40, stress=75))['ajuste']['decision'] == 'SUAVIZAR HOY'
    assert _plan(**base, matinal=dict(sueno=8, bb=80, stress=20))['ajuste']['decision'] == 'MANTENER'


def test_con_actividades_de_strava(monkeypatch=None):
    """Simula la respuesta de Strava (sin red) para recorrer la rama de datos reales."""
    import numpy as np
    import pandas as pd
    rng = np.random.default_rng(1)
    filas = []
    for k in range(60):
        dep = ['RUNNING', 'CYCLING', 'SWIMMING'][k % 3]
        filas.append({'sport': dep, 'avg_hr': rng.normal(140, 8), 'max_hr': rng.normal(178, 4),
                      'avg_speed_kmh': {'RUNNING': 10.5, 'CYCLING': 27, 'SWIMMING': 2.7}[dep],
                      'distance': 10, 'moving_time': 55,
                      'date': pd.Timestamp.now(tz='UTC') - pd.Timedelta(days=60 - k)})
    falso = pd.DataFrame(filas)
    orig_a, orig_n = main.M.fetch_strava_activities, main.M.fetch_strava_athlete_name
    main.M.STRAVA_AVAILABLE = True
    main.M.fetch_strava_activities = lambda token, days=90: falso
    main.M.fetch_strava_athlete_name = lambda token: 'Marco'
    try:
        d = _plan(perfil='nuevo', sexo='M', inicio=str(HOY - timedelta(days=14)),
                  competicion=str(HOY + timedelta(days=150)), strava_token='x' * 40,
                  fecha_sim=str(HOY + timedelta(days=40)))
        assert d['fuente'] == 'strava' and d['n_actividades'] == 60 and d['nombre'] == 'Marco'
        assert d['hoy'] == str(HOY)          # con datos reales no se simula la fecha
        assert d['demo'] is None
        main.M.fetch_strava_activities = lambda token, days=90: None
        r = c.post('/api/plan', json=dict(perfil='nuevo', sexo='M', inicio=str(HOY),
                                          competicion=str(HOY + timedelta(days=150)),
                                          strava_token='y' * 40))
        assert r.status_code == 401
    finally:
        main.M.fetch_strava_activities, main.M.fetch_strava_athlete_name = orig_a, orig_n


def test_errores():
    r = c.post('/api/plan', json=dict(perfil='nuevo', sexo='M', inicio=str(HOY),
                                      competicion=str(HOY - timedelta(days=3))))
    assert r.status_code == 422
    assert c.post('/api/plan', json=dict(perfil='otro', sexo='M', inicio=str(HOY))).status_code == 422


if __name__ == '__main__':
    for n, f in list(globals().items()):
        if n.startswith('test_'):
            f()
            print('OK', n)
