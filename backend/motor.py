# -*- coding: utf-8 -*-
# ARCHIVO GENERADO por tools/sync_motor.py a partir de app.py: no lo edites a mano.
# Motor del demostrador Streamlit, reutilizado sin cambios por la API móvil.
"""
Mi plan 70.3 — Demostrador Streamlit del TFM
=============================================
Planificación adaptativa de entrenamientos de alta carga mediante aprendizaje
automático: caso de estudio del triatlón de media distancia (113 km).

Usa los modelos XGBoost entrenados en el notebook (salidas/modelos/) y
reproduce el motor adaptativo: nivel del atleta (nuevo o experimentado),
macrociclo con fecha de competencia, reglas de tipo de semana (Tabla 7 del
TFM), validación de ritmos con el historial, plan semanal detallado, botón
«Actualizar mi día», glosario pedagógico y plan de competencia km a km.

Ejecución:  streamlit run app.py
Requisitos: streamlit, pandas, numpy, matplotlib (pip install -r requirements)
"""

import os
import re
import sqlite3
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
try:
    import matplotlib.pyplot as plt
except ImportError:
    plt = None
import st_shim as st

try:
    import plotly.graph_objects as go
    PLOTLY_OK = True
except ImportError:
    PLOTLY_OK = False

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

try:
    from stravalib.client import Client as StravaClient
    STRAVA_AVAILABLE = True
except ImportError:
    STRAVA_AVAILABLE = False

try:
    from garminconnect import Garmin
    GARMIN_AVAILABLE = True
except ImportError:
    GARMIN_AVAILABLE = False

# ----------------------------------------------------------------------------
# Configuración general y estilos
# ----------------------------------------------------------------------------
# (configuración de página y estilos de Streamlit omitidos en la API)


DB_PATH = 'salidas/triatlon.db'
PARQUET_DIR = 'salidas/parquet'

GARMIN_COLORS = {'Z1': '#9aa0a6', 'Z2': '#3b82f6', 'Z3': '#22a06b',
                 'Z4': '#f59e0b', 'Z5': '#ef4444'}

SEMANAS_MINIMAS = {'nuevo': 24, 'experimentado': 12}
CTL_OBJETIVO_70_3 = 70
SEMANA_ACTUAL_DEFAULT = 6
DIAS_ES = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']

# Strava OAuth (sincronización en vivo). Las credenciales van en .streamlit/secrets.toml
STRAVA_CLIENT_ID = st.secrets.get("strava_client_id", "")
STRAVA_CLIENT_SECRET = st.secrets.get("strava_client_secret", "")
# URL a la que Strava devuelve tras autorizar. En local es localhost; al desplegar
# en Streamlit Cloud, define `redirect_uri = "https://TU-APP.streamlit.app"` en Secrets.
STRAVA_REDIRECT_URI = st.secrets.get("redirect_uri", "http://localhost:8501")

# ----------------------------------------------------------------------------
# i18n: idioma de la interfaz (Español / English). El contenido dinámico
# (glosario, detalle de sesiones, explicaciones IA) permanece en español.
# ----------------------------------------------------------------------------
IDIOMAS = {'Español': 'es', 'English': 'en'}
idioma = 'es'  # se actualiza con el selector de la barra lateral

TR = {
    'sync_datos':   {'es': 'Sincronización de datos', 'en': 'Data source'},
    'de_donde':     {'es': '¿De dónde obtener datos?', 'en': 'Where to get data from?'},
    'opt_strava':   {'es': '📱 Strava (en vivo)', 'en': '📱 Strava (live)'},
    'opt_garmin':   {'es': '⌚ Garmin Connect', 'en': '⌚ Garmin Connect'},
    'tu_perfil':    {'es': 'Tu perfil', 'en': 'Your profile'},
    'nuevo':        {'es': 'Nuevo en triatlón', 'en': 'New to triathlon'},
    'experto':      {'es': 'Con experiencia', 'en': 'Experienced'},
    'sexo':         {'es': 'Sexo', 'en': 'Sex'},
    'hombre':       {'es': 'Hombre', 'en': 'Male'},
    'mujer':        {'es': 'Mujer', 'en': 'Female'},
    'tu_objetivo':  {'es': 'Tu objetivo', 'en': 'Your goal'},
    'fecha_inicio': {'es': 'Fecha de inicio del plan', 'en': 'Plan start date'},
    'reiniciar':    {'es': '🔄 Reiniciar', 'en': '🔄 Reset'},
    'tengo_fecha':  {'es': 'Ya tengo fecha de competencia', 'en': 'I have a race date'},
    'cuando_703':   {'es': '¿Cuándo es tu 70.3?', 'en': 'When is your 70.3?'},
    'hola':         {'es': '👋 ¡Hola, {n}! Bienvenido a tu plan de hoy.',
                     'en': '👋 Hi, {n}! Welcome to today’s plan.'},
    'h_hoy':        {'es': 'Cómo estás hoy', 'en': 'How you are today'},
    'h_forma':      {'es': 'Tu forma a lo largo de las semanas', 'en': 'Your fitness over the weeks'},
    'h_rumbo':      {'es': 'Tu rumbo hacia la carrera', 'en': 'Your road to race day'},
    'h_zonas':      {'es': 'Tus zonas, como las muestra tu reloj', 'en': 'Your zones, as your watch shows them'},
    'h_semana':     {'es': 'Tu semana, día a día', 'en': 'Your week, day by day'},
    'h_porque':     {'es': '¿Por qué este plan?', 'en': 'Why this plan?'},
    'h_progreso':   {'es': 'Tu progreso por disciplina', 'en': 'Your progress by discipline'},
    'm_fuente':     {'es': 'Fuente de datos', 'en': 'Data source'},
    'm_acts':       {'es': 'Actividades usadas', 'en': 'Activities used'},
    'm_modelos':    {'es': 'Modelos IA (XGBoost)', 'en': 'AI models (XGBoost)'},
}


def t(key, **kw):
    s = TR.get(key, {}).get(idioma) or TR.get(key, {}).get('es') or key
    return s.format(**kw) if kw else s

GLOSARIO = {
    'Body Battery': "Reserva de energía (0-100) que estima el reloj combinando HRV, estrés, sueño y actividad. Por debajo de 20-30, el cuerpo pide recuperación, no entrenamiento.",
    'HRV': "Variabilidad de la frecuencia cardiaca: los milisegundos que cambian entre latido y latido. Alta y estable = bien recuperado; si cae de golpe, fatiga, estrés o enfermedad.",
    'Estrés': "Índice 0-100 derivado de la HRV. Sostenido por encima de 70, el sistema nervioso está en alerta y asimila peor el entrenamiento.",
    'Sueño': "El sueño profundo es donde ocurre la reparación muscular y hormonal. Menos de ~1 h por noche de forma repetida frena la adaptación.",
    'Sleep Score': "Puntuación 0-100 que resume la CALIDAD del sueño (no las horas): combina sueño profundo y REM, despertares, duración y estabilidad de la FC. Excelente 90+, Buena 80-89, Regular 60-79, Mala <60. Puedes dormir muchas horas con un score bajo y amanecer cansado; por eso ajusta el entrenamiento aunque las horas parezcan suficientes.",
    'FC': "Frecuencia cardiaca, en pulsaciones por minuto (ppm). Es el cuentarrevoluciones del entrenamiento.",
    'CTL / ATL / TSB': "CTL = Fitness (forma acumulada de ~6 semanas, media exponencial de la carga). ATL = Fatiga (carga de los últimos ~7 días). TSB = Frescura = CTL − ATL. La referencia es 0: TSB positivo = descansado (fresco para competir); TSB negativo = cargado. Bandas orientativas: por encima de +25 demasiado fresco (riesgo de desentrenar); de +5 a +25 a punto para competir; de −10 a +5 en equilibrio/mantenimiento; de −30 a −10 carga productiva (estás construyendo forma, fatiga normal y buscada); por debajo de −30 sobrecarga (riesgo, toca aliviar). Importante: un TSB alto solo significa «a punto para competir» cuando llega tras un taper desde una CTL alta; si la CTL viene cayendo (parón, lesión o accidente), la fatiga baja más rápido que la forma y ese mismo TSB positivo es desentrenamiento («óxido»), no pico de forma. Por eso la app compara tu CTL con la de hace 4 semanas y con los días que llevas sin entrenar antes de decirte que estás a punto.",
    'Zonas Z1-Z5': "Intensidades por FC: Z1 muy suave (recuperar), Z2 aeróbico (la base, puedes hablar), Z3 medio (te cuesta hablar), Z4 umbral (frases cortas), Z5 máximo.",
    'D+': "Desnivel positivo acumulado: metros totales de subida de la ruta. Más D+ = más carga muscular y cardiaca al mismo ritmo. El plan te pide acumular cierto D+ en el fondo de bici (subir desarrolla fuerza y potencia) y algo en la tirada larga.",
    'fuerza / musculación': "Trabajo de gimnasio (sentadilla, peso muerto, zancadas, gemelos y core). 2 veces por semana mejora la ECONOMÍA (gastas menos energía al mismo ritmo), sube el umbral y previene lesiones. No te pone 'grande': te hace más eficiente y resistente. Se reduce cerca de la carrera para llegar fresco.",
    'core': "Músculos del tronco (abdomen, lumbares, glúteos). Un core fuerte estabiliza la postura al nadar, pedalear y correr ya cansado, y protege la espalda. Es lo que más se trabaja junto con las piernas.",
    'excéntrico / bajadas': "Cuando el músculo trabaja 'frenando' (p. ej. el cuádriceps al bajar una cuesta corriendo). Entrenarlo con BAJADAS controladas reduce las agujetas y evita que se te caiga el ritmo en la carrera del 70.3.",
    'efecto de sesión repetida': "Tras una sesión de bajadas, la siguiente daña mucho menos el músculo. Por eso se introducen descensos poco a poco en las tiradas largas: te 'vacunan' contra las agujetas del día de la carrera.",
    'brick': "Bici seguida inmediatamente de carrera. Entrena la transición T2: los primeros minutos con 'piernas de cemento' que sentirás el día del 70.3.",
    'series': "Repeticiones de un esfuerzo con recuperación entre ellas (ej. 6x800 m). Permiten acumular minutos a intensidades que de seguido no aguantarías.",
    'FTP': "Potencia máxima sostenible ~1 h en bici (vatios). Con potenciómetro, las series se hacen al 90-100% del FTP; sin él, por FC y velocidad.",
    'cadencia': "Pedaladas (rpm) o zancadas por minuto. En bici, 85-95 rpm protege las piernas para la carrera posterior; en cuestas, 70-75.",
    'taper': "Reducción del volumen (~50%) las 2-3 semanas previas a la carrera manteniendo toques de intensidad: la fatiga se va, la forma se queda.",
    'drafting': "Nadar a los pies de otro: legal en la natación y ahorra ~5% de energía.",
}

# ----------------------------------------------------------------------------
# Biblioteca de ejercicios y términos de las sesiones: qué es, cómo se hace y el
# error típico. Se detectan en el texto de cada sesión para explicarlos ahí mismo.
# ----------------------------------------------------------------------------
# (clave, emoji, título, patrones que lo detectan, qué es, cómo se hace, claves/errores, búsqueda de vídeo)
EJERCICIOS = [
    ('sentadilla', '🏋️', 'Sentadilla', [r'sentadilla'],
     'Ejercicio básico de piernas: cuádriceps, glúteos y zona media. Es la base de la fuerza para pedalear y correr.',
     'Pies a la anchura de los hombros y puntas un poco abiertas. Baja llevando la cadera atrás y abajo, como '
     'para sentarte, con el pecho alto y la espalda recta, hasta que los muslos queden paralelos al suelo. '
     'Sube empujando con todo el pie. Si empiezas, hazla con una mancuerna sujeta al pecho (sentadilla goblet).',
     'Rodillas en la línea de los pies (que no se vayan hacia dentro) y talones siempre apoyados.',
     'sentadilla goblet técnica'),
    ('rumano', '🏋️', 'Peso muerto rumano', [r'peso muerto rumano'],
     'Bisagra de cadera que fortalece isquiotibiales, glúteos y zona lumbar; protege la parte posterior del muslo al correr.',
     'De pie, con la barra o dos mancuernas delante de los muslos y las rodillas algo flexionadas (no cambian '
     'en todo el ejercicio). Lleva la cadera hacia atrás deslizando el peso pegado a las piernas hasta media '
     'tibia o hasta notar tensión detrás del muslo. Vuelve empujando la cadera hacia delante y apretando glúteos.',
     'La espalda no se redondea y no se convierte en sentadilla: se mueve la cadera, no las rodillas.',
     'peso muerto rumano técnica'),
    ('peso_muerto', '🏋️', 'Peso muerto', [r'peso muerto(?! rumano)'],
     'Levantar una barra del suelo con piernas y cadera: trabaja toda la cadena posterior y la zona media.',
     'Barra en el suelo sobre la mitad del pie. Agárrala a la anchura de los hombros, con la cadera más alta '
     'que las rodillas, la espalda recta y el pecho alto. Sube empujando el suelo con las piernas y extendiendo '
     'la cadera a la vez, con la barra pegada al cuerpo. Baja por el mismo camino.',
     'Aprende la técnica con poco peso; la espalda nunca se redondea.',
     'peso muerto técnica principiantes'),
    ('zancada', '🦵', 'Zancadas', [r'zancada'],
     'Ejercicio a una pierna: cuádriceps, glúteo y equilibrio, el mismo apoyo unilateral que al correr.',
     'Da un paso largo hacia delante y baja hasta que las dos rodillas formen unos 90°, con la de atrás cerca '
     'del suelo y el tronco erguido. Empuja con el talón de delante para volver. Alterna las piernas.',
     'La rodilla de delante no se va hacia dentro; el paso, lo bastante largo para no cargarla.',
     'zancadas técnica'),
    ('gemelos', '🦶', 'Elevación de gemelos', [r'gemelo'],
     'Fortalece gemelos y sóleo, y prepara el tendón de Aquiles para el impacto de la carrera.',
     'De pie con la punta del pie sobre un escalón. Sube sobre las puntas lo más alto que puedas, aguanta 1 s '
     'y baja despacio hasta que el talón quede por debajo del escalón. Haz una serie con la rodilla estirada y '
     'otra con la rodilla algo flexionada.',
     'La bajada lenta (3 s) es la parte que más protege el tendón.',
     'elevación de gemelos en escalón'),
    ('prensa', '🏋️', 'Prensa de piernas', [r'prensa'],
     'Máquina de empuje con las piernas: fuerza de cuádriceps y glúteos con la espalda apoyada.',
     'Pies a la anchura de la cadera en el centro de la plataforma. Baja controlando hasta que la rodilla forme '
     'unos 90° y empuja de nuevo sin bloquear del todo las rodillas.',
     'La zona lumbar no se despega del respaldo al bajar.',
     'prensa de piernas técnica'),
    ('plancha', '🧱', 'Plancha', [r'plancha'],
     'Ejercicio isométrico de zona media: mantiene el tronco estable cuando nadas, pedaleas o corres cansado.',
     'Apoyado en los antebrazos y las puntas de los pies, con el cuerpo en línea recta de la cabeza a los '
     'talones. Aprieta abdomen y glúteos y aguanta de 20 a 45 s. La plancha lateral se hace de costado, '
     'apoyado en un antebrazo.',
     'La cadera no cae ni sube: si se hunde, termina la serie.',
     'plancha abdominal técnica'),
    ('pallof', '🎗️', 'Pallof press', [r'pallof'],
     'Ejercicio de zona media «anti-rotación»: enseña al tronco a no girar, lo que ahorra energía al correr y pedalear.',
     'Ata una banda elástica (o usa una polea) a la altura del pecho, a tu lado. Sujeta el asa con las dos '
     'manos pegada al esternón y sepárate un paso para que la banda tire. Estira los brazos al frente, aguanta '
     '2 s sin dejar que el tronco gire hacia la banda y vuelve al pecho. De 8 a 12 repeticiones por lado.',
     'Lo importante no es empujar, es que el tronco no se mueva: pies firmes y glúteos apretados.',
     'pallof press banda elástica'),
    ('anti_rotacion', '🎗️', 'Core anti-rotación', [r'anti-rotaci'],
     'Ejercicios de zona media que entrenan a resistir el giro del tronco, como el pallof press o la plancha.',
     'Elige uno o dos: pallof press, plancha, plancha lateral o «bird-dog» (a cuatro patas, estira a la vez el '
     'brazo y la pierna contrarios sin mover la espalda).',
     'Movimientos lentos y controlados; calidad antes que repeticiones.',
     'ejercicios core antirotación'),
    ('puente', '🍑', 'Puente de glúteo', [r'puente de gl'],
     'Activa los glúteos, que estabilizan la cadera en cada zancada y en el pedaleo.',
     'Tumbado boca arriba, rodillas flexionadas y pies apoyados. Eleva la cadera apretando los glúteos hasta '
     'alinear rodillas, cadera y hombros; aguanta 2 s y baja despacio. Para progresar, hazlo a una pierna.',
     'Empuja con los talones y no arquees la zona lumbar al subir.',
     'puente de glúteo técnica'),
    ('pliometria', '⚡', 'Saltos explosivos (pliometría)', [r'salto', r'pliometr', r'explosiv'],
     'Saltos cortos y rápidos que mejoran la «reactividad» del músculo y del tendón: más economía de carrera.',
     'Sentadilla con salto, saltos a un cajón bajo o saltitos de tobillo. Despega lo más rápido posible y '
     'aterriza suave, con las rodillas alineadas. Pocas repeticiones (3-6) con descanso completo entre series.',
     'Busca calidad y rapidez, no cansancio. Si aterrizas «pesado», para.',
     'pliometría corredores principiantes'),
    ('movilidad', '🧘', 'Movilidad de cadera y tobillo', [r'movilidad'],
     'Ejercicios suaves de rango de movimiento que sueltan la cadera y el tobillo después de muchas horas de bici y carrera.',
     'Círculos de cadera, estiramiento del psoas en posición de zancada y «rodilla a la pared» para el tobillo '
     '(con el pie a un palmo de la pared, lleva la rodilla a tocarla sin levantar el talón). De 5 a 10 min.',
     'Sin rebotes ni dolor: el estiramiento se nota, pero no duele.',
     'movilidad cadera tobillo corredores'),
    ('bilateral', '🏊', 'Respiración bilateral', [r'bilateral'],
     'Respirar alternando los dos lados, normalmente cada 3 brazadas.',
     'Saca la boca de lado al final de la brazada, con media cara dentro del agua, y suelta el aire por la '
     'nariz mientras tienes la cara sumergida. Respira a un lado, cuenta tres brazadas y respira al otro.',
     'Equilibra la brazada, ayuda a nadar recto y en el agua abierta te deja respirar por el lado sin olas ni sol.',
     'respiración bilateral crol'),
    ('tecnica_nado', '🏊', 'Técnica de brazada y patada', [r'técnica de brazada', r'brazada y pies'],
     'Ejercicios técnicos («drills») que corrigen un solo detalle cada vez.',
     'Algunos ejemplos en tramos de 25-50 m: brazada a un brazo; «catch-up» (una mano espera a la otra delante '
     'antes de tirar); «dedos arrastrando» (roza el agua con los dedos al recobrar, con el codo alto) y patada '
     'con tabla. Nada despacio y piensa solo en el detalle del ejercicio.',
     'Patada corta desde la cadera, no desde la rodilla.',
     'ejercicios técnica crol triatlón'),
    ('series', '🔁', 'Series', [r'\d+x\d+', r'series'],
     'Repeticiones de un esfuerzo con recuperación entre ellas: acumulas más tiempo a intensidad alta del que aguantarías seguido.',
     'Calienta 10-15 min suave. Haz cada repetición al ritmo o la zona indicados (por ejemplo, 5x4 min en Z4 = '
     'cinco veces cuatro minutos) y recupera trotando, pedaleando o nadando suave el tiempo indicado. Termina '
     'con 10 min suaves.',
     'Todas las repeticiones al mismo ritmo: si la última sale mucho peor, saliste demasiado rápido.',
     'entrenamiento por series zonas'),
    ('brick', '🔗', 'Brick (bici + carrera)', [r'brick'],
     GLOSARIO['brick'],
     'Termina la bici, cambia de calzado en menos de 2-3 min (como en la T2) y sal a correr al ritmo indicado. '
     'Los primeros minutos notarás las piernas pesadas: acorta la zancada, sube la cadencia y deja que la FC se asiente.',
     'Prepara la ropa y las zapatillas de correr antes de salir en bici.',
     'entrenamiento brick triatlón'),
    ('cadencia', '🔄', 'Cadencia', [r'cadencia', r'rpm'],
     GLOSARIO['cadencia'],
     'Cuenta las pedaladas de una pierna en 30 s y multiplica por dos, o míralo en el ciclocomputador. Usa '
     'desarrollos más ligeros si vas por debajo del objetivo.',
     'Una cadencia alta cansa menos las piernas para la carrera posterior.',
     'cadencia pedaleo triatlón'),
    ('bajadas', '⛰️', 'Bajadas controladas', [r'bajada', r'descenso'],
     GLOSARIO['excéntrico / bajadas'],
     'Corre las bajadas con pasos cortos y rápidos, el tronco ligeramente adelantado y el pie apoyando bajo el '
     'cuerpo, sin frenar con el talón. Empieza con bajadas suaves y pocas.',
     'Las primeras veces habrá agujetas: es el músculo adaptándose.',
     'técnica correr cuesta abajo'),
    ('desnivel', '⛰️', 'Desnivel positivo (D+)', [r'd\+', r'desnivel'],
     GLOSARIO['D+'],
     'Elige una ruta con subidas; tu reloj o Strava muestran los metros acumulados. Sube sentado y a tu zona, '
     'sin cebarte.',
     'Mejor varias subidas moderadas que una sola muy dura.',
     'entrenar en cuestas ciclismo'),
    ('z2', '💚', 'Zona 2 (Z2)', [r'\bz2\b', r'z1-z2'],
     'Intensidad aeróbica suave, la base del triatlón de larga distancia: puedes mantener una conversación.',
     'Mantén la FC dentro del rango que te indica la sesión. Si sube, baja el ritmo aunque te parezca muy lento.',
     'El error más común es ir demasiado rápido en los días suaves.',
     'entrenar zona 2 frecuencia cardiaca'),
]


def ayudas_sesion(texto):
    """Ejercicios y términos que aparecen en el texto de una sesión (sin repetir)."""
    s = str(texto).lower()
    vistos, out = set(), []
    for e in EJERCICIOS:
        if e[0] in vistos:
            continue
        if any(re.search(p, s) for p in e[3]):
            vistos.add(e[0])
            out.append(e)
    # El peso muerto rumano incluye las palabras «peso muerto»: basta con explicar el rumano
    return out


def url_video(busqueda):
    from urllib.parse import quote_plus
    return 'https://www.youtube.com/results?search_query=' + quote_plus(busqueda)


def md_ejercicio(e):
    _k, emo, tit, _p, que, como, clave, vid = e
    return (f"**{emo} {tit}** — {que}\n\n"
            f"**Cómo se hace:** {como}\n\n"
            f"**Clave:** {clave} · [▶ Ver vídeos]({url_video(vid)})")


def html_ayudas(texto, max_items=4):
    """Bloque plegable «¿Cómo se hace?» para las tarjetas de la semana."""
    items = ayudas_sesion(texto)[:max_items]
    if not items:
        return ''
    cuerpo = ''.join(
        f'<div class="ej"><b>{emo} {tit}</b> — {que} <br><i>Cómo:</i> {como} '
        f'<a href="{url_video(vid)}" target="_blank">▶ vídeo</a></div>'
        for _k, emo, tit, _p, que, como, _c, vid in items)
    return (f'<details class="ayuda"><summary>📖 Cómo se hace ({len(items)})</summary>'
            f'{cuerpo}</details>')


# ----------------------------------------------------------------------------
# Utilidades de formato
# ----------------------------------------------------------------------------
ESTADO_PLAN_PATH = '.plan_estado.json'


def fecha_hoy():
    """Fecha de referencia del plan: la real o, en el modo demo, la fecha simulada."""
    sim = st.session_state.get('fecha_sim')
    if sim is not None:
        return pd.Timestamp(sim).normalize()
    return pd.Timestamp.today().normalize()


def md_a_html(txt):
    """Escapa el texto y convierte **negritas** a HTML (tarjetas de sesión)."""
    import html as _html
    s = _html.escape(str(txt), quote=False)
    return re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', s)



def _estado_plan_load():
    """Carga el dict {user_key: fecha_inicio_iso} persistido (o {})."""
    try:
        import json
        with open(ESTADO_PLAN_PATH, encoding='utf-8') as f:
            data = json.load(f)
        # Compatibilidad con el formato antiguo (clave única 'fecha_inicio')
        if 'fecha_inicio' in data and isinstance(data['fecha_inicio'], str):
            return {'demo': data['fecha_inicio']}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def leer_inicio_plan(user_key='demo'):
    """Fecha de inicio persistida PARA ESE USUARIO (o None si no hay)."""
    d = _estado_plan_load().get(user_key)
    try:
        return date.fromisoformat(d) if d else None
    except Exception:
        return None


def guardar_inicio_plan(d, user_key='demo'):
    """Fija la fecha de inicio del plan de ese usuario. Es el ANCLA del plan:
    no cambia sola al pasar los días; solo se reescribe al reiniciar el plan."""
    try:
        import json
        data = _estado_plan_load()
        data[user_key] = pd.Timestamp(d).date().isoformat()
        with open(ESTADO_PLAN_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f)
    except Exception:
        pass


# ----------------------------------------------------------------------------
# Configuración persistente del plan
# ----------------------------------------------------------------------------
# Streamlit borra st.session_state al recargar la página o al abrirla en otro dispositivo,
# y obligaba a configurar el plan cada día. Dos capas de persistencia, sin base de datos:
#  1) El ENLACE: la configuración (fechas, perfil, sexo, demo, tiempos) se escribe en la
#     URL en cada ejecución. Guardar la página en favoritos o en la pantalla de inicio del
#     móvil conserva el plan, y el mismo enlace lo abre igual en otro dispositivo.
#  2) La CUENTA DE STRAVA: se guarda también en el servidor, asociada al id del deportista,
#     y se recupera al conectar Strava desde cualquier dispositivo. En Streamlit Community
#     Cloud ese fichero se pierde si la app se reinicia; el enlace no se pierde nunca.
CFG_PARAMS = ('ini', 'comp', 'meses', 'perfil', 'sexo', 'demo', 'tn', 'tb', 'tr', 'tt', 'to')


def _fecha_param(v):
    try:
        return date.fromisoformat(str(v)[:10])
    except Exception:
        return None


def aplicar_config(cfg):
    """Vuelca una configuración guardada (dict de textos) en st.session_state.
    Debe llamarse antes de crear los widgets de configuración."""
    if not cfg:
        return False
    ss = st.session_state
    ini = _fecha_param(cfg.get('ini'))
    if ini and ini <= date.today():
        ss['inicio_plan_val'] = ini
        ss['inicio_fijado'] = True
    comp = _fecha_param(cfg.get('comp'))
    if comp:
        ss['fecha_comp_sel'] = comp
        ss['usa_fecha_sel'] = True
    elif str(cfg.get('meses', '')).isdigit():
        ss['meses_sel'] = min(max(int(cfg['meses']), 3), 12)
        ss['usa_fecha_sel'] = False
    if cfg.get('perfil') in ('nuevo', 'experimentado'):
        ss['perfil_tipo_sel'] = cfg['perfil']
    if cfg.get('sexo') in ('M', 'F'):
        ss['sexo_sel'] = cfg['sexo']
    if str(cfg.get('demo')) == '1':
        ss['modo_demo'] = True
    for k in ('tn', 'tb', 'tr', 'tt', 'to'):
        if re.fullmatch(r'\d{1,2}:\d{2}', str(cfg.get(k, ''))):
            ss['t_' + k] = str(cfg[k])
    return ini is not None or comp is not None


def config_desde_url():
    """Configuración guardada en el enlace. Tras autorizar en Strava, la URL de vuelta
    solo trae ?code=...; la configuración viaja en el parámetro state del OAuth."""
    src = {k: st.query_params.get(k) for k in st.query_params.keys()}
    if src.get('code') and src.get('state'):
        import urllib.parse
        src.update(dict(urllib.parse.parse_qsl(src['state'])))
    return {k: src[k] for k in CFG_PARAMS if src.get(k)}


def guardar_config_url(cfg):
    """Escribe la configuración en la URL (sin recargar la página)."""
    if st.query_params.get('code'):
        return                                   # el canje del OAuth limpia la URL
    actual = {k: st.query_params.get(k) for k in st.query_params.keys()}
    if actual != cfg:
        st.query_params.from_dict(cfg)


def enlace_plan(cfg):
    import urllib.parse
    base = (STRAVA_REDIRECT_URI or '').rstrip('/')
    return f"{base}/?{urllib.parse.urlencode(cfg)}"


def leer_config_servidor(user_key):
    d = _estado_plan_load().get('cfg_' + user_key)
    return d if isinstance(d, dict) else {}


def guardar_config_servidor(user_key, cfg):
    try:
        import json
        data = _estado_plan_load()
        if data.get('cfg_' + user_key) == cfg:
            return
        data['cfg_' + user_key] = cfg
        with open(ESTADO_PLAN_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f)
    except Exception:
        pass


def pace_run(v_kmh):
    if pd.isna(v_kmh) or v_kmh <= 0:
        return 'N/D'
    m = 60.0 / v_kmh
    s = int(round((m - int(m)) * 60))
    if s == 60:
        m, s = m + 1, 0
    return f"{int(m)}:{s:02d} min/km"


def pace_swim(v_kmh):
    if pd.isna(v_kmh) or v_kmh <= 0:
        return 'N/D'
    s = 360.0 / v_kmh
    return f"{int(s // 60)}:{int(s % 60):02d}/100 m"


def t2min(txt):
    p = [int(v) for v in str(txt).split(':')]
    return p[0] * 60 + p[1]


def min2t(m):
    h, mm = divmod(int(round(m)), 60)
    return f"{h}:{mm:02d}"


# ----------------------------------------------------------------------------
# Integración con Gemini API para explicaciones pedagógicas dinámicas
# ----------------------------------------------------------------------------
@st.cache_resource
def inicializar_gemini():
    """Inicializa Gemini API con clave de st.secrets."""
    if not GEMINI_AVAILABLE:
        return None
    try:
        api_key = st.secrets.get("gemini_api_key", os.getenv("GEMINI_API_KEY", ""))
        if not api_key:
            return None
        genai.configure(api_key=api_key)
        # 'gemini-pro' quedó descontinuado; se usa el modelo vigente (como en el v6),
        # con respaldo a otros nombres si la cuenta tiene distinta disponibilidad.
        for nombre in ('gemini-1.5-flash', 'gemini-1.5-flash-latest',
                       'gemini-1.5-pro', 'gemini-2.0-flash'):
            try:
                return genai.GenerativeModel(nombre)
            except Exception:
                continue
        return None
    except Exception:
        return None


@st.cache_data(ttl=3600)
def generar_explicacion_dia(atleta, dia_semana, decision, motivos, zonas, fase,
                            sesion_planificada=''):
    """Explica en vivo cómo queda la sesión de HOY tras el recálculo adaptativo."""
    model = inicializar_gemini()
    if not model:
        return None
    try:
        prompt = f"""Eres un entrenador personal de triatlón. En español, 2-3 frases,
        tono motivador y pedagógico, tuteando a {atleta}.

        Hoy es {dia_semana}, fase del plan: {fase}.
        Sesión que tenía planificada hoy: {sesion_planificada or 'no especificada'}.
        Métricas de esta mañana: {', '.join(motivos)}.
        El sistema recomienda: "{decision}".

        Dile EXACTAMENTE qué hacer hoy con esa sesión:
        - Si es DESCANSO HOY: justifica el descanso y qué hacer en su lugar (dormir, hidratar).
        - Si es SUAVIZAR HOY: indica reducir volumen y mantener todo en Z1-Z2
          ({zonas['hr']['Z1'][0]}-{zonas['hr']['Z2'][1]} ppm), sin series ni calidad.
        - Si es MANTENER: confirma que ejecute la sesión planificada tal cual.
        Conecta la lógica con sus métricas; no solo el qué, también el porqué."""
        response = model.generate_content(prompt)
        return response.text if response else None
    except Exception:
        return None


@st.cache_data(ttl=3600)
def generar_explicacion_plan(atleta, perfil_tipo, fase, semanas_restantes, ctl_actual,
                             tipo_semana='', motivo='', sesiones=None):
    """Genera justificación dinámica de por qué este plan es el ideal.
    El motor ya ha decidido el plan: el modelo de lenguaje solo lo explica y debe
    conservar exactamente todas las cifras que recibe."""
    model = inicializar_gemini()
    if not model:
        return None

    try:
        _fuerza = {
            'BASE': '2 sesiones de fuerza por semana (resistencia muscular de piernas y core)',
            'CONSTRUCCION': '2 sesiones de fuerza por semana (fuerza máxima y potencia de piernas y core)',
            'PICO': '1 sesión de fuerza de mantenimiento por semana',
            'TAPERING': '1 activación de fuerza ligera por semana',
            'COMPETENCIA': 'sin fuerza esta semana (solo competir y descansar)',
        }.get(fase, '2 sesiones de fuerza por semana')
        _ses_txt = '; '.join(f"{s['dia']}: {s['deporte']} {s['tipo']}"
                             + (f" {s['dur_min']} min" if s.get('dur_min') else '')
                             + (f" {s['km']} km" if s.get('km') else '')
                             for s in (sesiones or []) if s['deporte'] != 'Descanso')
        prompt = f"""Eres un entrenador de triatlón. Escribe una justificación breve (4-5 frases) de por qué
        el plan actual es ideal para {atleta}, un triatleta {perfil_tipo} que está en fase {fase}
        con {semanas_restantes} para la carrera y forma actual (CTL) de {ctl_actual:.0f}.
        El sistema ya decidió una semana de tipo {tipo_semana} por este motivo: {motivo}.
        Sesiones de la semana: {_ses_txt}.
        NO cambies ninguna cifra: usa exactamente los valores anteriores. Tú solo explicas, no decides.

        El plan, además de nadar/pedalear/correr, incluye {_fuerza}, y prescribe acumular DESNIVEL:
        subidas en el fondo de bici (para ganar fuerza y potencia) y bajadas controladas en la tirada
        larga (para acostumbrar el músculo y evitar agujetas el día de la carrera).

        Sé específico y pedagógico, con PALABRAS SENCILLAS (el atleta no es experto). Explica qué mejorará,
        por qué el ritmo es el adecuado para esta fase, y en una frase por qué la fuerza y el desnivel
        le ayudan a completar el 70.3."""

        response = model.generate_content(prompt)
        return response.text if response else None
    except Exception as e:
        return None


@st.cache_data(ttl=86400, show_spinner=False)
@st.cache_data(show_spinner=False, ttl=86400)
def generar_frase_dia(nombre, fase, semilla, fallback):
    """Frase motivadora del día, personalizada con Gemini (una por día).
    Si Gemini no está disponible, usa la frase de respaldo (lista curada)."""
    model = inicializar_gemini()
    if not model:
        return fallback
    try:
        prompt = (f"Genera UNA sola frase motivadora, original y potente (máximo 14 palabras), "
                  f"en español, para {nombre}, un triatleta que hoy entrena en fase {fase} de su "
                  f"plan hacia un 70.3. Tono inspirador, cercano y memorable —la frase que se "
                  f"llevará en la cabeza hoy—. Devuelve SOLO la frase, sin comillas ni explicación.")
        r = model.generate_content(prompt)
        s = (r.text or '').strip().strip('"').strip()
        return s if 3 < len(s) < 160 else fallback
    except Exception:
        return fallback


# ----------------------------------------------------------------------------
# Carga de datos persistidos (con respaldo de demostración)
# ----------------------------------------------------------------------------
@st.cache_data
def cargar_datos():
    datos = {}
    if os.path.exists(DB_PATH):
        con = sqlite3.connect(DB_PATH)
        for tabla in ('perfiles', 'planes_semanales', 'sesiones_plan',
                      'predicciones_ciclismo', 'predicciones_carrera'):
            try:
                datos[tabla] = pd.read_sql(f'SELECT * FROM {tabla}', con)
            except Exception:
                datos[tabla] = pd.DataFrame()
        con.close()
    else:
        datos = {t: pd.DataFrame() for t in ('perfiles', 'planes_semanales',
                                             'sesiones_plan', 'predicciones_ciclismo',
                                             'predicciones_carrera')}
    fp = os.path.join(PARQUET_DIR, 'fitness_fatiga.parquet')
    datos['fitness'] = pd.read_parquet(fp) if os.path.exists(fp) else pd.DataFrame()
    fa = os.path.join(PARQUET_DIR, 'actividades.parquet')
    datos['actividades'] = pd.read_parquet(fa) if os.path.exists(fa) else pd.DataFrame()
    return datos


def datos_demo():
    """Atleta sintético para explorar la app sin ejecutar el notebook."""
    perfil = pd.DataFrame([{'athlete': 'Demo', 'resting_hr': 52,
                            'pace_running_kmh': 10.5, 'pace_cycling_kmh': 24,
                            'pace_swimming_kmh': 2.8}])
    fechas = pd.date_range(end=fecha_hoy(), periods=120)
    rng = np.random.default_rng(7)
    fitness = pd.DataFrame({'athlete': 'Demo', 'date': fechas,
                            'CTL': np.linspace(35, 50, 120) + rng.normal(0, 1, 120),
                            'ATL': np.linspace(35, 55, 120) + rng.normal(0, 3, 120)})
    fitness['TSB'] = fitness['CTL'] - fitness['ATL']
    # Actividades con FECHA y las 3 disciplinas, con mejora gradual del ritmo
    # a lo largo de ~16 semanas (para ilustrar el progreso en el gráfico).
    filas = []
    hoy = fecha_hoy()
    base = {'RUNNING': (9.6, 11.2, 0.35, 162, 186),
            'CYCLING': (23.0, 28.0, 0.9, 150, 178),
            'SWIMMING': (2.55, 2.95, 0.08, 150, 170)}  # (v_ini, v_fin, ruido, hr, hrmax)
    for sport, (v0, v1, ns, hr, hrmax) in base.items():
        n = 16 if sport != 'SWIMMING' else 14
        for k in range(n):
            frac = k / max(n - 1, 1)
            d_ = hoy - pd.Timedelta(days=int((1 - frac) * 112))   # ~16 semanas atrás → hoy
            filas.append({'athlete': 'Demo', 'sport': sport, 'date': d_,
                          'avg_speed_kmh': (v0 + (v1 - v0) * frac) + rng.normal(0, ns),
                          'avg_hr': rng.normal(hr, 5), 'max_hr': rng.normal(hrmax, 4),
                          'moving_time': rng.normal(55, 12)})
    acts = pd.DataFrame(filas)
    return perfil, fitness, acts


def eventos_demo(sem_tot):
    """Dos incidencias guionizadas en la demo para ver reaccionar a las reglas de la
    Tabla 7: una semana sin entrenar (viaje) y otra de sobrecarga."""
    sobrecarga = max(int(round(sem_tot * 0.42)), 2)
    viaje = max(int(round(sem_tot * 0.67)), sobrecarga + 3)
    return {sobrecarga: 'sobrecarga', viaje: 'viaje'}


def acts_demo_progresivo(per, sexo='M', fecha_inicio=None):
    """Actividades de demostración que siguen el propio plan hasta la fecha de hoy
    (real o simulada en la demo).

    - Ocho semanas previas al plan con 4 sesiones suaves por semana: es el historial
      de partida, para que la CTL no arranque en cero.
    - Desde el inicio, cada semana reproduce la estructura del motor: las mismas
      sesiones de resistencia (de 3 a 6), con la rampa de volumen, las semanas de
      descarga cada cuatro y la reducción del tapering. Se omite alguna sesión al azar
      (adherencia del ~90 %), como ocurre con un deportista real.
    - Dos incidencias (eventos_demo): una semana de viaje sin entrenar y otra de
      sobrecarga, para que el tipo de semana cambie como lo haría en la realidad.
    - Cada semana el deportista cumple el tipo de semana que el sistema decide el lunes
      (en una semana de descanso no entrena; en mantenimiento repite el volumen).
    - Las velocidades mejoran poco a poco con el avance del plan.
    Así, al avanzar la fecha, la carga (CTL/ATL/TSB), el tipo de semana y el gráfico
    de progreso evolucionan igual que lo harían con datos reales."""
    hoy_ = fecha_hoy()
    sem_tot = max(int(per.get('semanas_totales', 24)), 1)
    nuevo = int(per.get('semanas_minimas', 24)) >= 24
    sx = 1.0 if sexo == 'M' else 0.93
    if fecha_inicio is not None:
        ini = pd.Timestamp(fecha_inicio).normalize()
    else:
        ini = hoy_ - pd.Timedelta(days=(int(per.get('semana_actual', 1)) - 1) * 7)
    rng = np.random.default_rng(7)
    vel = {'RUNNING': (9.4, 11.6, 0.30), 'CYCLING': (22.0, 29.5, 0.8),
           'SWIMMING': (2.5, 3.05, 0.07)}            # (v_ini, v_fin, ruido) en km/h
    hr_z2, hr_q, hr_max = 130, 152, 186

    # Sesiones de referencia del motor: (día de la semana, deporte, minutos en el pico)
    catalogo = [(5, 'CYCLING', 220), (3, 'SWIMMING', 55), (6, 'RUNNING', 120),
                (1, 'RUNNING', 55), (2, 'CYCLING', 85), (4, 'SWIMMING', 45)]
    filas = []

    def _sesion(fecha, sport, minutos, frac, intensa=False):
        v0, v1, ns = vel[sport]
        filas.append({'athlete': 'Demo', 'sport': sport, 'date': fecha,
                      'avg_speed_kmh': (v0 + (v1 - v0) * frac) * sx + rng.normal(0, ns),
                      'avg_hr': rng.normal(hr_q if intensa else hr_z2, 4),
                      'max_hr': rng.normal(hr_max, 3),
                      'moving_time': max(minutos * rng.uniform(0.85, 1.15), 15)})

    # Historial previo: 8 semanas, 4 sesiones suaves por semana (~2,5 h, como la semana 1)
    for w in range(-8, 0):
        lunes = ini + pd.Timedelta(days=w * 7)
        for dia, sport, mins in ((1, 'RUNNING', 30), (3, 'SWIMMING', 25),
                                 (5, 'CYCLING', 60), (6, 'RUNNING', 35)):
            f = lunes + pd.Timedelta(days=dia)
            if f <= hoy_:
                _sesion(f, sport, mins, 0.0)

    # Semanas del plan
    for w in range(sem_tot):
        lunes = ini + pd.Timedelta(days=w * 7)
        if lunes > hoy_:
            break
        sem = w + 1
        prog = sem / sem_tot
        sem_rest = sem_tot - sem + 1
        fase = ('COMPETENCIA' if sem_rest <= 1 else 'TAPERING' if sem_rest <= 3 else
                'PICO' if sem_rest <= 6 else 'CONSTRUCCION' if sem_rest <= 12 else 'BASE')
        f_ini = 3 if nuevo else 5
        n_ses = int(round(f_ini + (6 - f_ini) * min(prog * 1.3, 1.0)))
        n_ses = 3 if fase == 'COMPETENCIA' else n_ses - (fase == 'TAPERING')
        n_ses = int(min(max(n_ses, 3), 6))
        vol = (0.45 + 0.55 * min(prog / 0.85, 1.0)) \
            * {'BASE': 0.80, 'TAPERING': 0.55, 'COMPETENCIA': 0.35}.get(fase, 1.0) \
            * (0.80 if nuevo else 1.0)
        if sem % 4 == 0 and fase in ('BASE', 'CONSTRUCCION', 'PICO') and sem < sem_tot - 2:
            vol *= 0.6
        intensa = fase in ('CONSTRUCCION', 'PICO')
        # El deportista de la demo sigue lo que el sistema le prescribe: el lunes se
        # decide el tipo de semana con la carga acumulada hasta el domingo (Tabla 7)
        if filas:
            _prev = pd.DataFrame(filas)
            _fit = fitness_desde_actividades(_prev[_prev['date'] < lunes], 52, 190, sexo)
            if not _fit.empty:
                _fit = _fit[_fit['date'] < lunes]
            tipo, _ = decidir_tipo_semana(_fit)
        else:
            tipo = 'MANTENIMIENTO'
        if tipo == 'DESCANSO':
            continue
        if tipo == 'MANTENIMIENTO':
            prog_m = max(sem - 1, 1) / sem_tot
            vol *= (0.45 + 0.55 * min(prog_m / 0.85, 1.0)) / (0.45 + 0.55 * min(prog / 0.85, 1.0))
            intensa = False
        evento = eventos_demo(sem_tot).get(sem)
        if evento == 'viaje':
            continue
        if evento == 'sobrecarga':
            vol *= 1.8
            n_ses = 6
            intensa = True
        for dia, sport, pico in catalogo[:n_ses]:
            f = lunes + pd.Timedelta(days=dia)
            if eventos_demo(sem_tot).get(sem + 1) == 'viaje' and dia >= 3:
                continue                              # el viaje empieza el jueves anterior
            if f > hoy_ or (rng.random() < 0.10 and not evento):      # futuro o sesión no realizada
                continue
            _sesion(f, sport, max(pico * vol, 40 if dia == 6 else 20), prog,
                    intensa and (dia in (1, 2) or evento == 'sobrecarga'))
    if not filas:
        return pd.DataFrame(columns=['athlete', 'sport', 'date', 'avg_speed_kmh',
                                     'avg_hr', 'max_hr', 'moving_time'])
    return pd.DataFrame(filas)


# ----------------------------------------------------------------------------
# Integración Strava OAuth (sincronización de actividades en vivo)
# ----------------------------------------------------------------------------
@st.cache_resource
def init_strava_client():
    """Cliente Strava compartido (sin token hasta autenticar)."""
    if STRAVA_AVAILABLE and STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET:
        return StravaClient()
    return None


def _strava_client_id_int():
    """Strava exige client_id numérico (en secrets puede venir como texto)."""
    try:
        return int(STRAVA_CLIENT_ID)
    except (ValueError, TypeError):
        return STRAVA_CLIENT_ID


def get_strava_auth_url():
    """URL de autorización de Strava."""
    client = init_strava_client()
    if not client:
        return None
    import urllib.parse
    return client.authorization_url(
        client_id=_strava_client_id_int(),
        redirect_uri=STRAVA_REDIRECT_URI,
        scope=['activity:read_all'],
        # auto: si ya autorizaste la app, Strava vuelve directamente sin preguntar,
        # así reconectar cada día es un solo toque
        approval_prompt='auto',
        # la configuración del plan viaja por el OAuth y se restaura a la vuelta
        state=urllib.parse.urlencode(config_desde_url()) or None,
    )


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_strava_athlete_id(access_token):
    """Id numérico del deportista en Strava: clave estable para guardar su plan
    (el token de acceso cambia en cada conexión)."""
    try:
        client = init_strava_client()
        if not client:
            return None
        client.access_token = access_token
        return getattr(client.get_athlete(), 'id', None)
    except Exception:
        return None


# --- Sesión de Strava recordada en el navegador -------------------------------------
# Streamlit pierde la sesión al recargar, y obligaba a pulsar «Conectar con Strava» en
# cada visita. Ahora el refresh token de Strava se guarda en una cookie de ESTE navegador
# (no en el servidor ni en el enlace, para que compartir el enlace no comparta la cuenta).
# Al volver, la app pide a Strava un token nuevo con él y entra sin pasar por la
# autorización. «Desconectar» borra la cookie.
COOKIE_STRAVA = 'mp703_strava'
COOKIE_DIAS = 60


def restaurar_strava_desde_cookie():
    """Reconecta Strava con el refresh token guardado en la cookie (una vez por sesión)."""
    ss = st.session_state
    if 'strava_token' in ss or ss.get('_rt_probado') or st.query_params.get('code'):
        return
    ss['_rt_probado'] = True
    if not (STRAVA_AVAILABLE and STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET):
        return
    try:
        rt = st.context.cookies.get(COOKIE_STRAVA)
    except Exception:
        rt = None
    if not rt or not re.fullmatch(r'[A-Za-z0-9]{20,80}', rt):
        return
    try:
        tok = StravaClient().refresh_access_token(client_id=_strava_client_id_int(),
                                                  client_secret=STRAVA_CLIENT_SECRET,
                                                  refresh_token=rt)
    except Exception:
        ss['_cookie_borrar'] = True          # token revocado o caducado: se olvida
        return
    ss['strava_token'] = tok.get('access_token')
    ss['strava_refresh_token'] = tok.get('refresh_token') or rt
    ss['strava_expires_at'] = tok.get('expires_at')
    ss['fuente_sel'] = 'strava'
    try:
        ss['actividades_strava'] = fetch_strava_activities(ss['strava_token'],
                                                           days=ss.get('dias_sync', 90))
    except Exception:
        pass


def sincronizar_cookie_strava():
    """Escribe (o borra) la cookie en el navegador cuando cambia el refresh token."""
    ss = st.session_state
    js = None
    seguro = '; Secure' if str(STRAVA_REDIRECT_URI).startswith('https') else ''
    if ss.pop('_cookie_borrar', False):
        js = f"document.cookie='{COOKIE_STRAVA}=; path=/; max-age=0; SameSite=Lax{seguro}';"
        ss.pop('_rt_cookie', None)
    else:
        rt = ss.get('strava_refresh_token')
        if rt and re.fullmatch(r'[A-Za-z0-9]{20,80}', str(rt)) and ss.get('_rt_cookie') != rt:
            js = (f"document.cookie='{COOKIE_STRAVA}={rt}; path=/; "
                  f"max-age={COOKIE_DIAS * 86400}; SameSite=Lax{seguro}';")
            ss['_rt_cookie'] = rt
    if js:
        import streamlit.components.v1 as components
        components.html(f'<script>{js}</script>', height=0)


def desconectar_strava():
    """Borra la sesión de Strava de la app para poder cambiar de cuenta."""
    for k in ('strava_token', 'strava_refresh_token', 'strava_expires_at',
              'actividades_strava'):
        st.session_state.pop(k, None)
    st.session_state['_cookie_borrar'] = True     # y olvida la sesión en este navegador
    try:
        fetch_strava_athlete_name.clear()
        fetch_strava_athlete_id.clear()
        fetch_strava_activities.clear()
        init_strava_client.clear()
    except Exception:
        pass


def handle_strava_callback():
    """Captura el ?code=... que devuelve Strava y lo canjea por el token.

    Sin esto, la app vuelve a la pantalla inicial sin conectarse.
    """
    if 'strava_token' in st.session_state:
        return
    if not (STRAVA_AVAILABLE and STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET):
        return
    code = st.query_params.get('code')
    if not code:
        return
    client = init_strava_client()
    if not client:
        return
    try:
        token = client.exchange_code_for_token(
            client_id=_strava_client_id_int(),
            client_secret=STRAVA_CLIENT_SECRET,
            code=code,
        )
        if isinstance(token, dict):   # stravalib 2.x devuelve AccessInfo (dict)
            st.session_state['strava_token'] = token.get('access_token')
            st.session_state['strava_refresh_token'] = token.get('refresh_token')
            st.session_state['strava_expires_at'] = token.get('expires_at')
        else:
            st.session_state['strava_token'] = token
        # Deja la app en la fuente Strava y sincroniza ya, para que no se quede en Local
        st.session_state['fuente_sel'] = 'strava'
        try:
            st.session_state['actividades_strava'] = fetch_strava_activities(
                st.session_state['strava_token'], days=90)
        except Exception:
            pass
        st.query_params.clear()
        st.rerun()
    except Exception as e:
        st.error(f"❌ Error intercambiando código de Strava: {e}")


@st.cache_data(ttl=900, show_spinner=False)
def fetch_strava_activities(access_token, days=90):
    """Descarga actividades recientes de Strava y las normaliza al esquema
    que usa el motor (sport, avg_hr, max_hr, avg_speed_kmh, distance, date).
    """
    try:
        client = init_strava_client()
        if not client:
            return None
        client.access_token = access_token
        # stravalib 2.x exige un datetime en `after` (hace assert isinstance datetime);
        # pasar un epoch int o un date provoca el error de sincronización.
        activities = list(client.get_activities(
            after=datetime.now() - timedelta(days=days),
            limit=200,
        ))
        # Fallback: si no hay nada en la ventana de días, trae las más recientes
        if not activities:
            activities = list(client.get_activities(limit=30))

        sport_map = {
            'Run': 'RUNNING', 'TrailRun': 'RUNNING', 'VirtualRun': 'RUNNING',
            'Ride': 'CYCLING', 'VirtualRide': 'CYCLING', 'GravelRide': 'CYCLING',
            'MountainBikeRide': 'CYCLING',
            'Swim': 'SWIMMING',
        }

        def _sport(activity):
            st_obj = getattr(activity, 'sport_type', None)
            raw = (getattr(st_obj, 'root', None) or str(st_obj)) if st_obj else None
            return sport_map.get(raw, (raw or 'OTHER').upper())

        data = []
        for activity in activities:
            mt = activity.moving_time  # Duration(int): segundos en stravalib 2.x
            data.append({
                'sport': _sport(activity),
                'avg_hr': float(activity.average_heartrate) if activity.average_heartrate else np.nan,
                'max_hr': float(activity.max_heartrate) if activity.max_heartrate else np.nan,
                'avg_speed_kmh': float(activity.average_speed) * 3.6 if activity.average_speed else np.nan,
                'distance': float(activity.distance) / 1000 if activity.distance else np.nan,
                'moving_time': float(mt) / 60 if mt else np.nan,
                'date': activity.start_date,
            })
        return pd.DataFrame(data) if data else pd.DataFrame()
    except Exception as e:
        st.error(f"Error sincronizando Strava: {e}")
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_strava_athlete_name(access_token):
    """Devuelve el nombre de pila del atleta autenticado en Strava."""
    try:
        client = init_strava_client()
        if not client:
            return None
        client.access_token = access_token
        ath = client.get_athlete()
        return getattr(ath, 'firstname', None) or getattr(ath, 'username', None)
    except Exception:
        return None


def fitness_desde_actividades(acts, fc_rep, fc_max, sexo='M'):
    """Reconstruye la curva CTL/ATL/TSB (Performance Management Chart) a partir
    de las actividades reales, usando la carga de Banister (TRIMP).

    TRIMP = duración(min) · HRr · 0.64 · e^(1.92·HRr)  (HRr = reserva cardiaca usada)
    CTL = media exponencial 42 días (forma) · ATL = 7 días (fatiga) · TSB = CTL−ATL.
    Es la misma lógica del notebook, aplicada aquí en vivo sobre Strava.
    """
    if acts is None or acts.empty or 'date' not in acts.columns:
        return pd.DataFrame()
    df = acts.dropna(subset=['date']).copy()
    if df.empty:
        return pd.DataFrame()
    df['date'] = pd.to_datetime(df['date'], utc=True, errors='coerce').dt.tz_localize(None)
    df = df.dropna(subset=['date'])
    df['date'] = df['date'].dt.normalize()
    fcr = max(float(fc_max) - float(fc_rep), 1.0)
    # Coeficientes de Banister específicos por sexo (distinta respuesta de lactato)
    coef, k = (0.64, 1.92) if sexo == 'M' else (0.86, 1.67)

    def _trimp(row):
        dur = row.get('moving_time')
        if pd.isna(dur) or dur <= 0:
            return 0.0
        hr = row.get('avg_hr')
        ratio = 0.65 if pd.isna(hr) else float(np.clip((hr - fc_rep) / fcr, 0.1, 1.0))
        return float(dur) * ratio * coef * float(np.exp(k * ratio))

    df['trimp'] = df.apply(_trimp, axis=1)
    daily = df.groupby('date')['trimp'].sum()
    if daily.empty:
        return pd.DataFrame()
    idx = pd.date_range(daily.index.min(), max(fecha_hoy(), daily.index.max()), freq='D')
    daily = daily.reindex(idx, fill_value=0.0)
    ctl = daily.ewm(span=42, adjust=False).mean()
    atl = daily.ewm(span=7, adjust=False).mean()
    out = pd.DataFrame({'date': idx, 'CTL': ctl.values, 'ATL': atl.values})
    out['TSB'] = out['CTL'] - out['ATL']
    return out


# ----------------------------------------------------------------------------
# Inferencia con los modelos entrenados del notebook (XGBoost)
# ----------------------------------------------------------------------------
MODELOS_DIR = 'salidas/modelos'


@st.cache_resource(show_spinner=False)
def cargar_modelos():
    """Carga los modelos .joblib del notebook si están presentes.
    Devuelve None si falta joblib/sklearn/xgboost o algún archivo.
    """
    try:
        import joblib
        req = ['xgb_run2cyc.joblib', 'xgb_cyc2run.joblib', 'preprocesadores.joblib']
        paths = {f: os.path.join(MODELOS_DIR, f) for f in req}
        if not all(os.path.exists(p) for p in paths.values()):
            return None
        modelos = {
            'run2cyc': joblib.load(paths['xgb_run2cyc.joblib']),
            'cyc2run': joblib.load(paths['xgb_cyc2run.joblib']),
            'pp': joblib.load(paths['preprocesadores.joblib']),
        }
        # Si el notebook guardó también el formato propio de XGBoost, se usa ese:
        # no depende de la versión de joblib ni de Python con que se guardó.
        import xgboost as _xgb
        for clave, nombre in (('run2cyc', 'xgb_run2cyc.json'), ('cyc2run', 'xgb_cyc2run.json')):
            ruta = os.path.join(MODELOS_DIR, nombre)
            if os.path.exists(ruta):
                m = _xgb.XGBRegressor()
                m.load_model(ruta)
                modelos[clave] = m
        return modelos
    except Exception:
        return None


def estado_modelos():
    """Diagnóstico legible del estado de los modelos, sin cargarlos."""
    import importlib.util
    faltan_lib = [m for m in ('joblib', 'sklearn', 'xgboost')
                  if importlib.util.find_spec(m) is None]
    req = ['xgb_run2cyc.joblib', 'xgb_cyc2run.joblib', 'preprocesadores.joblib']
    faltan_arch = [f for f in req if not os.path.exists(os.path.join(MODELOS_DIR, f))]
    if faltan_lib:
        libs = ' '.join('scikit-learn' if m == 'sklearn' else m for m in faltan_lib)
        return ('sin_librerias', f'faltan librerías — pip install {libs}')
    if faltan_arch:
        return ('sin_archivos', f'faltan {len(faltan_arch)} de {len(req)} ficheros en salidas/modelos/')
    return ('activo', 'modelos del TFM cargados')


def features_atleta(acts, zonas, fitness, perfil_row, sexo='M'):
    """Construye el vector de características del atleta a partir de los datos
    disponibles (Strava o locales). Lo que no se conoce queda NaN: XGBoost lo
    maneja nativamente. Las velocidades de entrada a los modelos de transferencia
    son la velocidad SOSTENIDA (percentil 80 de las últimas 25 sesiones), igual
    que en el notebook."""
    f = {}
    fc_rep, fc_max = float(zonas['fc_rep']), float(zonas['fc_max'])
    fcr = max(fc_max - fc_rep, 1.0)
    coef_trimp, k_trimp = (0.64, 1.92) if sexo == 'M' else (0.86, 1.67)

    def g(s, k):
        try:
            return s.get(k, np.nan)
        except Exception:
            return np.nan

    for k in ('resting_hr', 'weight_kg', 'age', 'vo2max'):
        f[k] = g(perfil_row, k)
    # sexo como variable del modelo de transferencia real (1 = hombre, 0 = mujer)
    f['sexo_M'] = 1.0 if sexo == 'M' else 0.0

    if acts is not None and not acts.empty:
        cols = set(acts.columns)
        runs = acts[acts['sport'] == 'RUNNING'] if 'sport' in cols else acts.iloc[0:0]
        cyc = acts[acts['sport'] == 'CYCLING'] if 'sport' in cols else acts.iloc[0:0]
        swm = acts[acts['sport'] == 'SWIMMING'] if 'sport' in cols else acts.iloc[0:0]
        if 'avg_speed_kmh' in cols:
            def _sost(d, n=25, q=0.80):
                """Velocidad sostenida: p80 de las últimas n sesiones (como el notebook)."""
                if 'date' in d.columns:
                    d = d.assign(_f=pd.to_datetime(d['date'], utc=True, errors='coerce'))
                    d = d.sort_values('_f')
                s = d['avg_speed_kmh'].dropna()
                s = s[s > 0]
                return float(s.tail(n).quantile(q)) if not s.empty else np.nan
            if not runs.empty:
                f['pace_run_kmh'] = runs['avg_speed_kmh'].median()
                f['pace_running_kmh'] = f['pace_run_kmh']
                f['running_speed_kmh'] = _sost(runs)        # entrada del modelo directo
            if not cyc.empty:
                f['pace_cycling_kmh'] = _sost(cyc)          # entrada del modelo inverso
            if not swm.empty:
                f['swim_speed_kmh'] = _sost(swm)
        if 'avg_hr' in cols:
            f['avg_hr'] = acts['avg_hr'].mean()
            if not runs.empty:
                f['avg_hr_run'] = runs['avg_hr'].mean()
                f['fc_umbral_run'] = runs['avg_hr'].quantile(0.85)
            if not cyc.empty:
                f['fc_umbral_cyc'] = cyc['avg_hr'].quantile(0.85)
        if 'avg_cadence' in cols:
            f['avg_cadence'] = acts['avg_cadence'].mean()
        if 'moving_time' in cols:
            tmp = acts.dropna(subset=['moving_time']).copy()

            def _tr(r):
                hr, dur = r.get('avg_hr'), r.get('moving_time')
                if pd.isna(dur) or dur <= 0:
                    return 0.0
                ratio = 0.65 if pd.isna(hr) else float(np.clip((hr - fc_rep) / fcr, 0.1, 1.0))
                return float(dur) * ratio * coef_trimp * float(np.exp(k_trimp * ratio))

            tmp['trimp'] = tmp.apply(_tr, axis=1)
            f['training_load'] = tmp['trimp'].mean()
            if 'date' in cols:
                d = pd.to_datetime(acts['date'], utc=True, errors='coerce').dropna()
                wk = max((d.max() - d.min()).days / 7.0, 1.0) if len(d) > 1 else 1.0
            else:
                wk = max(len(acts) / 3.0, 1.0)
            f['weekly_trimp'] = tmp['trimp'].sum() / wk
            f['sessions_per_week'] = len(acts) / wk
            if 'avg_hr' in cols:
                a = acts.dropna(subset=['avg_hr']).copy()
                if not a.empty:
                    w = a['moving_time'].fillna(1.0).clip(lower=1.0)
                    tot = w.sum()
                    if tot > 0:
                        f['pct_z12'] = float(w[a['avg_hr'] <= zonas['hr']['Z2'][1]].sum() / tot * 100)
                        f['pct_z45'] = float(w[a['avg_hr'] >= zonas['hr']['Z4'][0]].sum() / tot * 100)

    if fitness is not None and not fitness.empty and {'CTL', 'TSB'} <= set(fitness.columns):
        f['ctl_current'] = float(fitness['CTL'].iloc[-1])
        f['tsb_current'] = float(fitness['TSB'].iloc[-1])
        f['ctl_cycling'] = f['ctl_current']
    return f


def inferir_con_modelos(modelos, feats):
    """Aplica los modelos entrenados al vector de características."""
    out = {}
    pp = modelos['pp']
    try:
        fc = pp.get('feature_cols', [])
        if fc:
            row = np.array([[feats.get(c, np.nan) for c in fc]], dtype=float)
            v = float(modelos['run2cyc'].predict(row)[0]) if not np.isnan(row[0][0]) else np.nan
            if 10.0 < v < 50.0:                        # descarta salidas no plausibles
                out['bici_pred_kmh'] = v
                out['bici_cons_kmh'] = v * 0.85        # margen conservador del TFM
    except Exception:
        pass
    try:
        fr = pp.get('feat_cyc2run', [])
        if fr:
            row = np.array([[feats.get(c, np.nan) for c in fr]], dtype=float)
            v = float(modelos['cyc2run'].predict(row)[0]) if not np.isnan(row[0][0]) else np.nan
            if 5.0 < v < 20.0:
                out['run_pred_kmh'] = v
                out['run_cons_kmh'] = max(v - 0.5, 5.0)  # margen conservador del TFM
    except Exception:
        pass
    return out


# ----------------------------------------------------------------------------
# Motor (réplica ligera del notebook, secciones 7-8)
# ----------------------------------------------------------------------------
def calcular_zonas(perfil_row, acts, perfil_tipo='nuevo', pred_bici=np.nan, pred_run=np.nan):
    p = perfil_row
    fc_max = np.nan
    if not acts.empty and 'max_hr' in acts.columns:
        fc_max = acts['max_hr'].dropna().quantile(0.98)
    if pd.isna(fc_max):
        fc_max = 185.0
    fc_rep = p.get('resting_hr', np.nan)
    if pd.isna(fc_rep):
        fc_rep = 55.0
    # Zonas por % de FC MÁXIMA (convención por defecto de Garmin/Polar/Coros), para
    # que coincidan con lo que el atleta ve en su reloj. Antes se usaba % de FC de
    # reserva (Karvonen), que da valores ~15-20 ppm más altos y NO casaba con el
    # reloj: inflaba Z1/Z2 y dejaba fuera las carreras fáciles reales, lo que
    # estimaba un ritmo de rodaje demasiado lento.
    def _hr(lo, hi):
        return (int(fc_max * lo), int(fc_max * hi))

    hr = {'Z1': _hr(.50, .60), 'Z2': _hr(.60, .70), 'Z3': _hr(.70, .80),
          'Z4': _hr(.80, .90), 'Z5': _hr(.90, 1.0)}

    # ------------------------------------------------------------------
    # Ritmos por disciplina derivados del HISTORIAL REAL (modelo de coach):
    #   · ritmo FÁCIL  = mediana de actividades en banda aeróbica de FC
    #     (carrera 65-78 % FCmáx ≈ zona "Easy" de Daniels; bici 60-75 %).
    #   · ritmo UMBRAL = mediana en banda 83-92 % FCmáx (o p80 de velocidad).
    #   El resto de zonas se derivan del umbral, como en el sistema VDOT.
    #   Si no hay FC suficiente, se usan cuantiles de velocidad (robusto).
    # ------------------------------------------------------------------
    def _ritmos(d, easy=(0.65, 0.78), thr=(0.83, 0.92), q_thr=0.80, q_easy=0.35):
        if d is None or d.empty or 'avg_speed_kmh' not in d.columns:
            return np.nan, np.nan, 0
        s = d['avg_speed_kmh'].dropna()
        s = s[s > 0]
        if s.empty:
            return np.nan, np.nan, 0
        # Ventana RECIENTE (8 semanas) para el ritmo FÁCIL → refleja tu forma
        # ACTUAL: al re-sincronizar Strava cada semana, el ritmo sube con tu
        # progreso real. El UMBRAL se toma del histórico completo (necesita
        # esfuerzos fuertes, más escasos). Si hay poca data reciente, usa todo.
        d_rec = d
        if 'date' in d.columns:
            dt = pd.to_datetime(d['date'], utc=True, errors='coerce')
            ref = dt.max()
            if pd.notna(ref):
                m = dt >= (ref - pd.Timedelta(days=56))
                if m.sum() >= 4:
                    d_rec = d[m]
        v_e = v_t = np.nan
        n_e = 0
        if 'avg_hr' in d.columns and fc_max:
            if d_rec['avg_hr'].notna().sum() >= 3:
                pe = d_rec['avg_hr'] / fc_max
                e = d_rec.loc[pe.between(*easy), 'avg_speed_kmh'].dropna()
                n_e = len(e)
                if len(e) >= 3:
                    v_e = float(e.median())
            if d['avg_hr'].notna().sum() >= 5:
                pt = d['avg_hr'] / fc_max
                tt = d.loc[pt.between(*thr), 'avg_speed_kmh'].dropna()
                if len(tt) >= 3:
                    v_t = float(tt.median())
        if np.isnan(v_t):
            v_t = float(s.quantile(q_thr))
        if np.isnan(v_e):
            s_rec = d_rec['avg_speed_kmh'].dropna()
            s_rec = s_rec[s_rec > 0]
            v_e = float(min((s_rec if not s_rec.empty else s).quantile(q_easy), v_t * 0.85))
        v_e = float(min(v_e, v_t * 0.95))   # coherencia: fácil siempre < umbral
        return v_e, v_t, n_e

    runs = cyc = swims = pd.DataFrame()
    if not acts.empty and 'sport' in acts.columns:
        runs = acts[acts['sport'] == 'RUNNING']
        cyc = acts[acts['sport'] == 'CYCLING']
        swims = acts[acts['sport'] == 'SWIMMING']

    # CARRERA
    v_run_easy, v_run_thr, n_e_run = _ritmos(runs)
    if np.isnan(v_run_easy):
        v0 = p.get('pace_running_kmh', np.nan)
        v0 = 9.2 if pd.isna(v0) else v0
        v_run_thr, v_run_easy = v0 * 1.05, v0 * 0.90
        fuente_z2 = 'estimado a partir de tu perfil (sin FC en el historial)'
    elif n_e_run >= 3:
        fuente_z2 = f'validado con {n_e_run} carreras reales en banda aeróbica (65-78 % FCmáx)'
    else:
        fuente_z2 = 'estimado por cuantiles de velocidad de tu historial'
    if len(runs) < 6 and not pd.isna(pred_run):   # sin historial de carrera: modelo inverso
        v_run_thr, v_run_easy = pred_run * 1.05, pred_run * 0.90
        fuente_z2 = 'estimado con el modelo de transferencia (menos de 6 carreras en tu historial)'

    # CICLISMO
    v_bike_easy, v_bike_thr, _ = _ritmos(cyc, easy=(0.60, 0.75), thr=(0.83, 0.92))
    if np.isnan(v_bike_easy):
        vb = pred_bici if not pd.isna(pred_bici) else p.get('pace_cycling_kmh', np.nan)
        vb = 25.0 if pd.isna(vb) else vb
        v_bike_thr, v_bike_easy = vb, vb * 0.82

    # NATACIÓN (la FC en piscina es poco fiable → cuantiles de velocidad)
    if not swims.empty and 'avg_speed_kmh' in swims.columns:
        ss = swims['avg_speed_kmh'].dropna()
        ss = ss[ss > 0]
        v_nat_easy = float(ss.median()) if not ss.empty else np.nan
        v_nat_thr = float(ss.quantile(0.80)) if not ss.empty else np.nan
    else:
        v_nat_easy = v_nat_thr = np.nan
    if np.isnan(v_nat_easy):
        vn = p.get('pace_swimming_kmh', np.nan)
        vn = 2.6 if pd.isna(vn) else vn
        v_nat_easy, v_nat_thr = vn, vn * 1.08

    # ------------------------------------------------------------------
    # GUARDRAILS fisiológicos orientados al 70.3: un historial escaso o no
    # representativo (p. ej. pocas salidas de bici, todas muy lentas) no debe
    # producir objetivos imposibles para completar la prueba (90 km en bici no
    # se entrenan a 9 km/h). Son pisos suaves hacia las demandas de la carrera.
    # ------------------------------------------------------------------
    if len(cyc) < 6:   # casi sin historial de bici → objetivo orientado a la meta
        base_thr = pred_bici if not pd.isna(pred_bici) else 27.0
        v_bike_thr = max(v_bike_thr, base_thr)
        v_bike_easy = v_bike_thr * 0.82
    v_run_easy = max(v_run_easy, 7.0)                 # ≥ ~8:34/km (no objetivos de caminar)
    v_run_thr = max(v_run_thr, v_run_easy * 1.08)
    v_bike_easy = max(v_bike_easy, 18.0)              # piso de rodaje de bici para 70.3
    v_bike_thr = max(v_bike_thr, v_bike_easy * 1.08, 22.0)
    v_nat_easy = max(v_nat_easy, 2.2)
    v_nat_thr = max(v_nat_thr, v_nat_easy * 1.05)

    v_bici_obj = pred_bici if not pd.isna(pred_bici) else v_bike_thr * 0.95
    v_bici_obj = max(v_bici_obj, 22.0)                # ritmo de bici mínimo de carrera

    # Ritmo objetivo de carrera del 70.3: entre el fácil y el umbral (esfuerzo
    # sostenible de media-larga distancia). Garantiza fácil < objetivo < umbral.
    v_run_obj = float(min(v_run_thr * 0.96, v_run_easy * 1.04))

    return {'fc_max': int(fc_max), 'fc_rep': int(fc_rep), 'hr': hr,
            'fuente_z2': fuente_z2, 'perfil': perfil_tipo,
            'run_z2': v_run_easy, 'run_z3': v_run_thr * 0.92, 'run_z4': v_run_thr,
            'run_obj': v_run_obj, 'bici_obj': v_bici_obj, 'nat_obj': v_nat_easy,
            'bici_z2': v_bike_easy, 'bici_z4': v_bike_thr,
            'nat_z2': v_nat_easy, 'nat_z4': v_nat_thr}


def calcular_fase(fecha_comp, perfil_tipo, fecha_inicio=None, semana_sim=None):
    """Calcula fase, semana actual y semanas restantes a partir de fechas reales.

    - semana_actual = semanas transcurridas desde la fecha de inicio + 1
      (si empiezas hoy, estás en la semana 1).
    - semanas_totales = de la fecha de inicio a la competencia.
    - semanas_restantes = de hoy a la competencia (determina la fase).
    - semana_sim: si se indica, FUERZA la semana actual (modo simulación/demo);
      las semanas restantes se derivan de ella, no del calendario.
    """
    sem_min = SEMANAS_MINIMAS[perfil_tipo]
    hoy = fecha_hoy()
    ini = hoy if fecha_inicio is None else pd.Timestamp(fecha_inicio).normalize()
    if ini > hoy:
        ini = hoy  # no permitir inicio en el futuro

    if fecha_comp:
        fc = pd.Timestamp(fecha_comp).normalize()
        sem_rest = max(int(np.ceil((fc - hoy).days / 7)), 0)
        sem_tot = max(int(np.ceil((fc - ini).days / 7)), 1)
    else:
        sem_tot = sem_min
        sem_rest = sem_tot

    if semana_sim:  # modo simulación: la semana la fija el usuario
        sem_actual = int(min(max(semana_sim, 1), sem_tot))
        sem_rest = max(sem_tot - sem_actual + 1, 0)   # incluye la semana en curso
    else:
        sem_actual = int((hoy - ini).days // 7) + 1
        sem_actual = min(max(sem_actual, 1), sem_tot)
    viable = sem_tot >= sem_min

    if sem_rest <= 1:
        fase = 'COMPETENCIA'
    elif sem_rest <= 3:
        fase = 'TAPERING'
    elif sem_rest <= 6:
        fase = 'PICO'
    elif sem_rest <= 12:
        fase = 'CONSTRUCCION'
    else:
        fase = 'BASE'
    # Días exactos hasta la prueba: se muestran junto a las semanas (redondeadas hacia
    # arriba) para que «24 semanas» y «168 días» se lean como la misma cuenta atrás
    dias_rest = (max((pd.Timestamp(fecha_comp).normalize() - hoy).days, 0)
                 if fecha_comp else sem_rest * 7)
    return {'fase': fase, 'semanas_restantes': sem_rest, 'semanas_totales': sem_tot,
            'semana_actual': sem_actual, 'plan_viable': viable, 'semanas_minimas': sem_min,
            'dias_restantes': dias_rest}


def txt_restante(per):
    """«24 semanas (168 días)»: semanas del plan y días exactos hasta la prueba."""
    s, d = int(per['semanas_restantes']), per.get('dias_restantes')
    base = f"{s} semana{'s' if s != 1 else ''}"
    return f"{base} ({d} día{'s' if d != 1 else ''})" if d is not None else base


def analizar_objetivo(anterior, objetivo_total, sem_prep):
    """anterior = dict con 'nat','bici','run','total' en 'h:mm'."""
    try:
        ant = {k: t2min(v) for k, v in anterior.items()}
        t_obj = t2min(objetivo_total)
    except Exception:
        return None
    mejora = ant['total'] - t_obj
    if mejora <= 0:
        return None
    transiciones = max(ant['total'] - (ant['nat'] + ant['bici'] + ant['run']), 4)
    reparto = {'nat': 0.15, 'bici': 0.50, 'run': 0.35}
    splits = {k: ant[k] - mejora * w for k, w in reparto.items()}
    mejora_pct = mejora / ant['total'] * 100
    return {'anterior_total': min2t(ant['total']), 'objetivo_total': objetivo_total,
            'mejora_min': round(mejora, 1), 'mejora_pct': round(mejora_pct, 1),
            'viable': mejora_pct <= max(sem_prep, 1) * 0.5,
            'transiciones_min': round(transiciones, 1),
            'splits_obj': {k: min2t(v) for k, v in splits.items()},
            'v_nat_obj': 1.9 / (splits['nat'] / 60),
            'v_bici_obj': 90 / (splits['bici'] / 60),
            'v_run_obj': 21.1 / (splits['run'] / 60)}


def sleep_score_label(score):
    """Etiqueta de calidad del sueño según el Sleep Score (estilo Garmin)."""
    if score is None:
        return ''
    if score >= 90:
        return 'Excelente'
    if score >= 80:
        return 'Buena'
    if score >= 60:
        return 'Regular'
    return 'Mala'


def actualizar_hoy(sesiones_hoy, z, sueno_h, body_battery, stress, enfermo,
                   sleep_score=None):
    graves, moderados = [], []
    if enfermo:
        graves.append('enfermedad o malestar')
    if body_battery < 20:
        graves.append(f'Body Battery muy baja ({body_battery:.0f})')
    if sueno_h < 5:
        graves.append(f'noche muy corta ({sueno_h:.1f} h)')
    # Sleep Score muy bajo: aunque las horas sean correctas, el sueño no reparó
    if sleep_score is not None and sleep_score < 40:
        graves.append(f'calidad de sueño muy mala (score {sleep_score:.0f}/100)')
    if not graves:
        if body_battery < 35:
            moderados.append(f'Body Battery baja ({body_battery:.0f})')
        if sueno_h < 6.5:
            moderados.append(f'sueño insuficiente ({sueno_h:.1f} h)')
        if sleep_score is not None and sleep_score < 60:
            moderados.append(f'calidad de sueño baja (score {sleep_score:.0f}/100, '
                             f'«{sleep_score_label(sleep_score)}»)')
        if stress > 70:
            moderados.append(f'estrés alto ({stress:.0f})')
    if graves:
        return ('DESCANSO HOY', graves,
                'Descanso completo: caminar suave, hidratarte y priorizar dormir. '
                'La sesión prevista se reprograma, no se pierde.')
    if moderados:
        partes = [f"{s['deporte']}: versión suave de {int(s['dur_min'] * 0.6)} min, "
                  f"todo en Z1-Z2 ({z['hr']['Z1'][0]}-{z['hr']['Z2'][1]} ppm), sin calidad."
                  for s in sesiones_hoy if s['deporte'] not in ('Descanso', 'Movilidad')]
        return ('SUAVIZAR HOY', moderados,
                ' '.join(partes) or 'Hoy ya era descanso: mantenlo.')
    return ('MANTENER', ['métricas en rango'],
            'Tus métricas de esta mañana están en tu rango: el plan sigue tal cual.')


def plan_competencia(z, objetivo=None):
    hr = z['hr']
    v_b = objetivo['v_bici_obj'] if objetivo else z['bici_obj']
    v_r = objetivo['v_run_obj'] if objetivo else z['run_obj']
    v_n = objetivo['v_nat_obj'] if objetivo else z['nat_obj']
    seg = [
        ('NATACIÓN 1,9 km', '0-300 m',
         'Salida controlada al 90%: deja pasar al grupo rápido y busca agua libre. No dispares la FC.'),
        ('NATACIÓN 1,9 km', '300-1.600 m',
         f'Crucero a {pace_swim(v_n)}. Pies de alguien un punto más rápido (drafting legal: ahorra ~5%).'),
        ('NATACIÓN 1,9 km', '1.600-1.900 m',
         'Aumenta el pataleo: sangre a las piernas antes de ponerte de pie. Visualiza la T1.'),
        ('T1', '—',
         f"Saldrás con la FC en {hr['Z4'][0]}+ ppm aunque no hayas apretado (estrés, neopreno, "
         f"horizontal→vertical). Camina rápido, no esprintes."),
        ('BICI 90 km', 'km 0-5',
         f"Arranque PROGRESIVO al 85% ({v_b * 0.85:.0f} km/h), 90-95 rpm. No persigas la FC: "
         f"espera a que baje de {hr['Z3'][0]} ppm. Bebe ya."),
        ('BICI 90 km', 'km 5-15',
         f"Sube hacia {v_b:.0f} km/h SOLO cuando la FC se asiente en {hr['Z2'][0]}-{hr['Z3'][0]} ppm. "
         f"Primera comida km 10-15."),
        ('BICI 90 km', 'km 15-70',
         f"Crucero {v_b:.0f} km/h, FC tope {hr['Z3'][1]} ppm. 60-90 g de carbohidrato/hora. "
         f"Subidas sentado aunque te adelanten: lo devuelves corriendo."),
        ('BICI 90 km', 'km 70-85',
         f"El tramo del juicio: si vas bien, MANTÉN {v_b:.0f} km/h — no subas. "
         f"Última comida sólida antes del km 80."),
        ('BICI 90 km', 'km 85-90',
         f"Afloja al 95% ({v_b * 0.95:.0f} km/h), cadencia 95-100 rpm: piernas sueltas para la T2."),
        ('T2', '—',
         'La FC sube al desmontar: normal. Cambio rápido sin pánico; gorra, dorsal y a correr.'),
        ('CARRERA 21,1 km', 'km 0-3',
         f"BRICK: piernas de cemento. Sal a {pace_run(v_r * 0.92)} aunque te sientas capaz de más: "
         f"la FC debe asentarse."),
        ('CARRERA 21,1 km', 'km 3-10',
         f"Ritmo objetivo {pace_run(v_r)}, FC tope {hr['Z3'][1]} ppm. Gel en el km 7-8."),
        ('CARRERA 21,1 km', 'km 10-16',
         f"Mantén {pace_run(v_r)}. Si la FC entra en Z4 ({hr['Z4'][0]}+) sin subir el ritmo, "
         f"afloja 10-15 s/km y reevalúa."),
        ('CARRERA 21,1 km', 'km 16-19',
         f"La parte dura. Permitido Z4 bajo ({hr['Z4'][0]}-{int((hr['Z4'][0] + hr['Z4'][1]) / 2)} ppm) "
         f"si las sensaciones acompañan."),
        ('CARRERA 21,1 km', 'km 19-21,1',
         'Vacía el tanque: todo lo que quede. La meta de un 70.3 se recuerda toda la vida.'),
    ]
    t_nat = 1.9 / v_n * 60
    t_bici = (5 / (v_b * 0.85) + 10 / (v_b * 0.95) + 70 / v_b + 5 / (v_b * 0.95)) * 60
    t_run = (3 / (v_r * 0.92) + 18.1 / v_r) * 60
    trans = objetivo['transiciones_min'] if objetivo else 8
    total = t_nat + trans + t_bici + t_run
    resumen = (f"Natación {min2t(t_nat)} + T1/T2 {min2t(trans)} + bici {min2t(t_bici)} "
               f"+ carrera {min2t(t_run)} = **{min2t(total)}**")
    return seg, resumen


def frecuencia_y_disciplinas(acts):
    """Sesiones/semana y disciplinas practicadas según el historial reciente."""
    if acts is None or getattr(acts, 'empty', True):
        return None, set()
    disc = set(acts['sport'].dropna().unique()) if 'sport' in acts.columns else set()
    if 'date' in acts.columns:
        d = pd.to_datetime(acts['date'], utc=True, errors='coerce').dropna()
        if len(d) > 1:
            semanas = max((d.max() - d.min()).days / 7.0, 1.0)
            return len(acts) / semanas, disc
    return None, disc


def factor_mejora(per, perfil_tipo):
    """Factor de mejora del ritmo según el avance del plan (mismo pulso, ritmo más
    rápido por adaptación aeróbica). Mayor en principiantes. Se usa tanto en los
    ritmos que se MUESTRAN como en los del plan, para que sean coherentes."""
    sem_tot = max(int(per.get('semanas_totales', 24)), 1)
    sem_idx = min(max(int(per.get('semana_actual', 1)), 1), sem_tot)
    prog = sem_idx / sem_tot
    tope = 0.10 if perfil_tipo == 'nuevo' else 0.05
    return 1.0 + tope * prog


NOMBRE_TIPO = {'DESCANSO': 'Descanso', 'REGENERATIVO': 'Regenerativa',
               'MANTENIMIENTO': 'Mantenimiento', 'CARGA': 'Carga'}


def decidir_tipo_semana(fitness, body_battery=None, stress=None):
    """Reglas en cascada de la Tabla 7 del TFM (la salud manda sobre la forma).

    El TSB se evalúa como MEDIA DE LOS ÚLTIMOS 7 DÍAS y no con el valor de un solo
    día: la simulación retrospectiva del TFM mostró que el TSB diario es demasiado
    volátil y prescribía descanso entre 4 y 7 semanas de cada 16.
    Body Battery y estrés solo se usan si el deportista los ha introducido."""
    tsb7 = np.nan
    if fitness is not None and not fitness.empty and 'TSB' in fitness.columns:
        _t = fitness['TSB'].dropna()
        if not _t.empty:
            tsb7 = float(_t.tail(7).mean())
    bb = np.nan if body_battery is None else float(body_battery)
    st_ = np.nan if stress is None else float(stress)
    if not np.isnan(tsb7) and tsb7 < -25:
        return 'DESCANSO', f'TSB medio de 7 días {tsb7:+.1f} (< −25): fatiga acumulada alta'
    if not np.isnan(bb) and bb < 20:
        return 'REGENERATIVO', f'Body Battery {bb:.0f} (< 20): la recuperación manda sobre la forma'
    if not np.isnan(tsb7) and tsb7 < -10:
        return 'MANTENIMIENTO', f'TSB medio de 7 días {tsb7:+.1f} (< −10): se consolida sin subir la carga'
    if not np.isnan(tsb7) and tsb7 > 10 and (np.isnan(st_) or st_ < 70):
        return 'CARGA', f'TSB medio de 7 días {tsb7:+.1f} (> +10): fresco para progresar'
    txt = f'TSB medio de 7 días {tsb7:+.1f}' if not np.isnan(tsb7) else 'sin datos de carga suficientes'
    return 'MANTENIMIENTO', f'{txt}: semana de mantenimiento'


def generar_plan_semanal(perfil_tipo, per, zonas, acts=None, sexo='M', tipo_semana='CARGA'):
    """Plan semanal ADAPTATIVO orientado a COMPLETAR un 70.3 (1,9-90-21,1 km).

    - Volúmenes reales que progresan hacia la distancia de carrera: el fondo de
      bici crece hasta acercarse a los 90 km y la tirada larga hacia los 21 km.
    - Incluye BRICK (bici+carrera encadenadas), la sesión clave del 70.3, en
      Construcción y Pico.
    - Frecuencia y carga suben de forma gradual según la semana y la fase.
    - Los ritmos objetivo PROGRESAN con las semanas (mismo pulso, ritmo más
      rápido) y salen de los datos del propio atleta y del modelo (que ya
      incluye el sexo); no se les aplica una penalización extra por sexo.
    - 1-2 bricks/semana en construcción y pico: largo el sábado y mini-brick en
      pico el miércoles, con la carrera del brick creciendo hacia la distancia.
    - tipo_semana (reglas de la Tabla 7): DESCANSO = sin sesiones estructuradas;
      REGENERATIVO = como máximo 3 sesiones cortas en Z1-Z2 (volumen x0,5, sin
      brick ni fuerza); MANTENIMIENTO = volumen de la semana anterior, sin
      sesiones de calidad; CARGA = progresión completa. En tapering y competición
      la fase sustituye a carga y mantenimiento, nunca a descanso ni a regenerativa.
    """
    orden_dias = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
    if tipo_semana == 'DESCANSO':
        plan = []
        for d in orden_dias:
            mov = d in ('Martes', 'Jueves', 'Sábado')
            plan.append({'dia': d, 'deporte': 'Movilidad' if mov else 'Descanso',
                         'tipo': 'recuperación', 'km': 0, 'dur_min': 20 if mov else 0,
                         'detalle': ('Semana de descanso: sin entrenamientos estructurados. '
                                     'Paseos suaves y 15-20 min de movilidad. La carga '
                                     'acumulada necesita asimilarse.')})
        meta = {'n_ses': 0, 'sem_idx': int(per.get('semana_actual', 1)),
                'sem_tot': int(per.get('semanas_totales', 24)), 'freq_act': None,
                'disciplinas': set(), 'nat_intro': False, 'tiene_brick': False,
                'tiene_mini_brick': False, 'descarga': False, 'n_fuerza': 0,
                'dplus_bike': 0, 'dplus_run': 0, 'tipo_semana': tipo_semana}
        return plan, meta
    fase = per.get('fase', 'BASE')
    sem_tot = max(int(per.get('semanas_totales', 24)), 1)
    sem_idx = int(per.get('semana_actual',
                          max(sem_tot - int(per.get('semanas_restantes', 0)), 1)))
    sem_idx = min(max(sem_idx, 1), sem_tot)
    prog = sem_idx / sem_tot  # avance del plan, 0→1

    freq_act, disciplinas = frecuencia_y_disciplinas(acts)
    if perfil_tipo == 'nuevo':
        f_ini = int(min(max(round(freq_act), 3), 4)) if freq_act else 3
        f_fin = 6
    else:
        f_ini = int(min(max(round(freq_act), 4), 6)) if freq_act else 5
        f_fin = 6
    n_ses = int(round(f_ini + (f_fin - f_ini) * min(prog * 1.3, 1.0)))
    if fase == 'TAPERING':
        n_ses -= 1
    if fase == 'COMPETENCIA':
        n_ses = 3
    n_ses = int(min(max(n_ses, 3), 6))

    # --- Volumen: rampa hacia el pico × fase × nivel del atleta ---
    # En MANTENIMIENTO la rampa no avanza: se repite el volumen de la semana anterior.
    prog_vol = prog
    if tipo_semana == 'MANTENIMIENTO' and fase not in ('TAPERING', 'COMPETENCIA'):
        prog_vol = max(sem_idx - 1, 1) / sem_tot
    ramp = 0.45 + 0.55 * min(prog_vol / 0.85, 1.0)    # 0.45 (inicio) → 1.0 (~85 % del plan)
    fase_mult = {'BASE': 0.80, 'CONSTRUCCION': 1.0, 'PICO': 1.0,
                 'TAPERING': 0.55, 'COMPETENCIA': 0.35}.get(fase, 1.0)
    nivel = 0.80 if perfil_tipo == 'nuevo' else 1.0
    vol = ramp * fase_mult * nivel
    intens = fase in ('CONSTRUCCION', 'PICO')

    # Semana de DESCARGA (recuperación) cada 4ª semana — patrón clásico 3:1.
    # Se reduce el volumen ~40 % y se baja la intensidad para asimilar la carga
    # acumulada (supercompensación) y prevenir el sobreentrenamiento.
    es_descarga = (sem_idx % 4 == 0) and fase in ('BASE', 'CONSTRUCCION', 'PICO') \
        and sem_idx < sem_tot - 2
    if es_descarga:
        vol *= 0.6
        intens = False
    # Tipo de semana (Tabla 7): mantenimiento sin calidad; regenerativa corta y suave
    if tipo_semana == 'MANTENIMIENTO':
        intens = False
    regenerativa = tipo_semana == 'REGENERATIVO'
    if regenerativa:
        vol *= 0.5
        intens = False
        n_ses = min(n_ses, 3)

    # Progresión de ritmos: a igual pulso, el ritmo mejora con las semanas por
    # adaptación aeróbica (la esencia de un plan de entrenamiento). El tope de
    # mejora es mayor en perfiles nuevos. Los ritmos base ya provienen de los
    # datos del propio atleta y del modelo (que incluye el sexo), por lo que NO
    # se aplica aquí un factor de sexo: hacerlo penalizaba dos veces a la mujer.
    mejora = factor_mejora(per, perfil_tipo)
    v_b2, v_b4 = zonas['bici_z2'] * mejora, zonas['bici_z4'] * mejora
    # Ritmos de carrera DIFERENCIADOS por tipo de sesión (no todos al mismo ritmo):
    #   fácil/rodaje y tirada larga = Z2; objetivo 70.3 (brick y final de la larga);
    #   tempo = Z3; series = Z4. Todos progresan con las semanas (factor mejora).
    v_run = zonas['run_z2'] * mejora        # fácil / rodaje / base de la tirada larga
    v_run3 = zonas['run_z3'] * mejora       # tempo (Z3)
    v_run4 = zonas['run_z4'] * mejora       # series (Z4)
    v_robj = zonas['run_obj'] * mejora      # ritmo OBJETIVO de carrera 70.3
    v_nat = zonas['nat_z2'] * mejora
    hrz2 = f"{zonas['hr']['Z2'][0]}-{zonas['hr']['Z2'][1]} ppm"
    rz2 = pace_run(v_run)
    robj = pace_run(v_robj)
    rz4 = pace_run(v_run4)
    nz2 = pace_swim(v_nat)

    def dur(peak):
        return max(int(round(peak * vol / 5.0) * 5), 20)   # min, múltiplos de 5
    def kb(m, v):
        return round(m / 60 * v, 1)
    def kr(m):
        return round(m / 60 * v_run, 1)
    def ks(m):
        return round(m / 60 * v_nat, 2)

    nat_intro = bool(disciplinas) and 'SWIMMING' not in disciplinas

    # --- Miércoles: bici de calidad (+ mini-BRICK de transición en PICO) ---
    # Segundo estímulo bici→carrera de la semana. Los expertos recomiendan 1-2
    # bricks por semana en construcción/pico: uno largo (sábado) y, en pico, un
    # mini-brick de transición (10-15 min) para reforzar el patrón neuromuscular.
    mie_bike = dur(85)
    # Mini-brick en TODA Construcción y Pico (no solo Pico): así hay 2 bricks/semana
    # (sábado largo + miércoles corto), dentro del rango 1-2/sem que recomiendan los
    # entrenadores en las fases específicas. La transición se corre a ritmo objetivo.
    mini_brick = max(int(round(15 * vol / 5.0) * 5), 10) if intens else 0   # 10-15 min
    if intens and mini_brick:
        mie = {'dia': 'Miércoles', 'deporte': 'Ciclismo', 'tipo': 'series Z4 + mini-BRICK',
               'dur_min': mie_bike + mini_brick, 'km': kb(mie_bike, v_b4),
               'detalle': (f'4x8 min en Z4 a ~{v_b4:.0f} km/h (4 min suaves entre series) y, '
                           f'al bajar de la bici, {mini_brick} min de transición a {robj} '
                           f'(ritmo objetivo). 2º estímulo bici→carrera de la semana.')}
    elif intens:
        mie = {'dia': 'Miércoles', 'deporte': 'Ciclismo', 'tipo': 'series Z4',
               'dur_min': mie_bike, 'km': kb(mie_bike, v_b4),
               'detalle': f'4x8 min en Z4 a ~{v_b4:.0f} km/h, 4 min suaves entre series.'}
    else:
        mie = {'dia': 'Miércoles', 'deporte': 'Ciclismo', 'tipo': 'rodaje Z2',
               'dur_min': mie_bike, 'km': kb(mie_bike, v_b2),
               'detalle': f'Rodaje a {v_b2:.0f} km/h en Z2, cadencia 85-95 rpm.'}
    if intens:
        mie['detalle'] += (' Si puedes, haz las series en una cuesta de 3-5 min al mismo Z4: '
                           'el trabajo en subida eleva la velocidad a VO2máx y la fuerza '
                           'específica de pedaleo.')

    # --- Sábado: FONDO de bici + BRICK de carrera ---
    # El brick NO se limita a Construcción/Pico: se introduce ya en Base tardío
    # (suave) y se mantiene casi todas las semanas, también en descarga (más corto,
    # porque es una sesión de ESPECIFICIDAD y técnica, no solo de carga). La carrera
    # del brick crece de ~15-20 min (Base) a ~45-50 min (Pico) — rango 30-60 min
    # recomendado para 70.3; 20 min en Pico no prepara una carrera de >2 h.
    bike_long = dur(220)                       # pico ≈ 3,5 h → cerca de los 90 km
    # Desnivel positivo (D+) objetivo del fondo. El trabajo en cuesta desarrolla
    # fuerza específica, potencia y velocidad a VO2máx (especificidad de un 70.3
    # con rampas). Escala 6→14 m/km con la fase y se reduce en descarga.
    dplus_bike = int(round(kb(bike_long, v_b2) * (6 + 8 * min(prog / 0.85, 1.0)) / 50.0) * 50)
    if es_descarga:
        dplus_bike = int(round(dplus_bike * 0.5 / 50.0) * 50)
    elev_bike = (f' Busca acumular ~{dplus_bike} m de desnivel positivo (D+): rodar en '
                 f'subida construye fuerza específica y potencia para afrontar el perfil '
                 f'del 70.3.')
    hay_brick = (fase in ('BASE', 'CONSTRUCCION', 'PICO')) and prog >= 0.25 and not regenerativa
    if hay_brick:
        brick_peak = 55 if intens else 30      # carrera del brick objetivo (min)
        brick_run = dur(brick_peak)
        clave = '🔑 ' if intens else ''
        modo = 'sesión clave del 70.3' if intens else 'brick introductorio suave'
        sab = {'dia': 'Sábado', 'deporte': 'Ciclismo',
               'tipo': 'fondo + BRICK' if intens else 'fondo + brick suave',
               'dur_min': bike_long + brick_run, 'km': kb(bike_long, v_b2),
               'detalle': (f'{clave}BRICK ({modo}): fondo de '
                           f'{kb(bike_long, v_b2):.0f} km de bici a {v_b2:.0f} km/h en Z2 '
                           f'({hrz2}) y, SIN parar, {brick_run} min de carrera a {robj} '
                           f'(ritmo OBJETIVO 70.3, {brick_run/60*v_robj:.1f} km) con "piernas '
                           f'de cemento": aquí ensayas tu ritmo de carrera con fatiga. Crece '
                           f'semana a semana. Come e hidrátate como en competencia.')}
    else:
        brick_run = 0
        sab = {'dia': 'Sábado', 'deporte': 'Ciclismo', 'tipo': 'fondo Z2',
               'dur_min': bike_long, 'km': kb(bike_long, v_b2),
               'detalle': (f'Fondo de {kb(bike_long, v_b2):.0f} km a {v_b2:.0f} km/h en Z2 '
                           f'({hrz2}). Construye la resistencia aeróbica de base hacia los 90 km; '
                           f'practica comida e hidratación de carrera.')}
    sab['detalle'] += elev_bike

    # --- Domingo: TIRADA LARGA orientada a distancia (tiempo en pie) ---
    # Construye hacia ~18 km en pico (recomendación 70.3: 16-20 km, no media maratón
    # completa), con tope de 140 min para no castigar a corredores lentos. Es
    # progresiva: arranca fácil (Z2) y termina los últimos km a ritmo objetivo.
    larga_km = 18.0 * min(prog_vol / 0.85, 1.0)
    larga_km *= {'TAPERING': 0.55, 'COMPETENCIA': 0.35}.get(fase, 1.0)
    if es_descarga:
        larga_km *= 0.7
    if regenerativa:
        larga_km *= 0.5
    larga_min = int(round(min(max(larga_km / max(v_run, 1) * 60, 40), 140) / 5) * 5)
    larga_km = round(larga_min / 60 * v_run, 1)
    finish_km = max(round(min(larga_km * 0.3, 6.0), 1), 1.0)
    # D+ de la tirada larga (4→10 m/km). Incluir bajadas controladas entrena la
    # musculatura excéntrica (cuádriceps) y, por el "efecto de sesión repetida"
    # (repeated bout effect), atenúa el daño muscular y protege la economía de
    # carrera el día del 70.3 — clave sobre todo para el perfil rodador/ciclista.
    dplus_run = int(round(larga_km * (4 + 6 * min(prog / 0.85, 1.0)) / 10.0) * 10)
    if es_descarga:
        dplus_run = int(round(dplus_run * 0.5 / 10.0) * 10)
    dom = {'dia': 'Domingo', 'deporte': 'Carrera', 'tipo': 'tirada larga progresiva',
           'dur_min': larga_min, 'km': larga_km,
           'detalle': (f'Tirada larga de {larga_km:.1f} km ({larga_min} min): arranca cómodo '
                       f'a {rz2} en Z2 ({hrz2}) y corre los últimos ~{finish_km:.0f} km a '
                       f'{robj} (ritmo objetivo del 70.3). Construye resistencia y enseña a '
                       f'tu cuerpo a correr a ritmo de carrera ya cansado, hacia los 21,1 km.'
                       f' Incluye ~{dplus_run} m de D+ con tramos de bajada controlada: correr '
                       f'en descenso entrena la musculatura excéntrica y, por el efecto de '
                       f'sesión repetida, reduce el daño muscular y las agujetas en carrera.')}

    catalogo = [
        ('Sábado', sab),
        ('Jueves', {'dia': 'Jueves', 'deporte': 'Natación', 'tipo': 'resistencia',
                    'dur_min': dur(55), 'km': ks(dur(55)),
                    'detalle': f'Series de resistencia a {nz2} (técnica y respiración bilateral). '
                               f'Construye los 1,9 km de la carrera.'
                               + (' Empieza por aquí: aún no registras natación.' if nat_intro else '')}),
        ('Domingo', dom),
        ('Martes', {'dia': 'Martes', 'deporte': 'Carrera',
                    'tipo': 'series Z4' if intens else 'rodaje Z2',
                    'dur_min': dur(55), 'km': kr(dur(55)),
                    'detalle': (f'Calienta y haz 5x4 min en Z4 a {rz4} (ritmo de series), '
                                f'2 min suaves entre repeticiones.'
                                if intens else f'Rodaje cómodo a {rz2} en Z2 ({hrz2}).')}),
        ('Miércoles', mie),
        ('Viernes', {'dia': 'Viernes', 'deporte': 'Natación', 'tipo': 'técnica',
                     'dur_min': dur(45), 'km': ks(dur(45)),
                     'detalle': f'Técnica de brazada y pies; series cortas a {nz2}.'}),
    ]
    por_dia = {dia: s for dia, s in catalogo[:n_ses]}

    # --- FUERZA / MUSCULACIÓN (piernas + core) ---------------------------------
    # La evidencia recomienda 2-3 sesiones/semana de fuerza para triatletas (mejora
    # economía, umbral y prevención de lesiones). Se periodiza: resistencia muscular
    # en Base, fuerza máxima + potencia en Construcción, mantenimiento en Pico y solo
    # activación en Taper. Se ubican en días sueltos (sin desplazar nado/bici/carrera)
    # y el viernes se limita a core/movilidad para no llegar con piernas cargadas al
    # brick del sábado.
    n_fuerza = {'BASE': 2, 'CONSTRUCCION': 2, 'PICO': 1,
                'TAPERING': 1, 'COMPETENCIA': 0}.get(fase, 1)
    if es_descarga:
        n_fuerza = min(n_fuerza, 1)
    if regenerativa:
        n_fuerza = 0
    fuerza_cfg = {
        'BASE': ('fuerza — resistencia muscular', 40,
                 'Circuito de piernas y core (2-3 vueltas de 12-15 rep): sentadilla, peso '
                 'muerto rumano, zancadas, gemelos y core anti-rotación (plancha, pallof). '
                 'Construye base estructural y previene lesiones.'),
        'CONSTRUCCION': ('fuerza — máxima + potencia', 40,
                 'Fuerza pesada de piernas (3-5 series de 4-6 rep a alta carga): sentadilla, '
                 'peso muerto, prensa, + core. Cierra con 2-3 saltos explosivos (pliometría '
                 'ligera). 2 veces/semana es lo que mejora economía y umbral.'),
        'PICO': ('fuerza — mantenimiento/potencia', 30,
                 'Mantenimiento: poco volumen y alta calidad (2 series de 3-5 rep explosivas) '
                 '+ core. Conserva la fuerza ganada sin restar frescura a las sesiones clave.'),
        'TAPERING': ('activación neuromuscular', 20,
                 'Activación corta y ligera, sin fatiga: movilidad, core y 2-3 saltos o '
                 'sentadillas explosivas para mantener el patrón neuromuscular fresco.'),
    }.get(fase)
    if fuerza_cfg and n_fuerza:
        f_tipo, f_dur, f_det = fuerza_cfg
        añadidas = 0
        for d in ('Lunes', 'Miércoles', 'Martes', 'Viernes'):
            if añadidas >= n_fuerza:
                break
            if d in por_dia:
                continue
            if d == 'Viernes':   # víspera del brick: solo core/movilidad
                s = {'dia': d, 'deporte': 'Fuerza', 'tipo': 'core + movilidad',
                     'dur_min': min(f_dur, 25), 'km': 0,
                     'detalle': ('Core y movilidad (sin piernas pesadas: mañana toca el brick): '
                                 'plancha, pallof, puente de glúteo y movilidad de cadera/tobillo.')}
            else:
                s = {'dia': d, 'deporte': 'Fuerza', 'tipo': f_tipo,
                     'dur_min': f_dur, 'km': 0, 'detalle': f_det}
            por_dia[d] = s
            añadidas += 1
        n_fuerza = añadidas
    else:
        n_fuerza = 0

    if fase == 'COMPETENCIA':
        por_dia['Domingo'] = {'dia': 'Domingo', 'deporte': 'Competencia', 'tipo': '70.3',
                              'km': 0, 'dur_min': 0,
                              'detalle': '¡Día de carrera! Aplica el plan km a km de más abajo.'}

    orden = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
    plan = []
    for dia in orden:
        if dia in por_dia:
            plan.append(por_dia[dia])
        else:
            plan.append({'dia': dia, 'deporte': 'Descanso', 'tipo': 'recuperación',
                         'km': 0, 'dur_min': 0,
                         'detalle': 'Descanso o 15 min de movilidad. La adaptación ocurre hoy.'})
    meta = {'n_ses': n_ses, 'sem_idx': sem_idx, 'sem_tot': sem_tot,
            'freq_act': freq_act, 'disciplinas': disciplinas, 'nat_intro': nat_intro,
            'tiene_brick': bool(hay_brick and brick_run),
            'tiene_mini_brick': bool(intens and mini_brick), 'descarga': es_descarga,
            'n_fuerza': n_fuerza, 'dplus_bike': dplus_bike, 'dplus_run': dplus_run,
            'tipo_semana': tipo_semana}
    return plan, meta


# ----------------------------------------------------------------------------
# Gráficos
# ----------------------------------------------------------------------------
def grafico_forma(fd):
    fig, ax = plt.subplots(figsize=(10, 3))
    fd = fd.tail(365)
    ax.plot(fd['date'], fd['CTL'], color='#21a366', lw=2, label='Fitness (CTL)')
    ax.plot(fd['date'], fd['ATL'], color='#f97316', lw=2, label='Fatiga (ATL)')
    ax.plot(fd['date'], fd['TSB'], color='#3b82f6', lw=1.6, ls='--', label='Frescura (TSB)')
    ax.axhline(0, color='#d8d5cd', lw=1)
    ax.legend(loc='upper left', frameon=False, fontsize=9, ncol=3)
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)
    ax.tick_params(labelsize=8, colors='#8a877f')
    fig.tight_layout()
    return fig


def grafico_forma_plotly(fd):
    """Curva CTL/ATL/TSB interactiva (Plotly), responsiva y con hover unificado."""
    fd = fd.tail(365)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=fd['date'], y=fd['CTL'], name='Fitness (CTL)',
                             mode='lines', line=dict(color='#21a366', width=2.4)))
    fig.add_trace(go.Scatter(x=fd['date'], y=fd['ATL'], name='Fatiga (ATL)',
                             mode='lines', line=dict(color='#f97316', width=2.4)))
    fig.add_trace(go.Scatter(x=fd['date'], y=fd['TSB'], name='Frescura (TSB)',
                             mode='lines', line=dict(color='#1d6fa5', width=1.8, dash='dot')))
    fig.add_hline(y=0, line=dict(color='#d8d5cd', width=1))
    fig.update_layout(height=300, margin=dict(l=8, r=8, t=10, b=8),
                      legend=dict(orientation='h', yanchor='bottom', y=1.0, x=0,
                                  font=dict(size=12)),
                      paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                      hovermode='x unified', font=dict(size=12, color='#5b6670'))
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=True, gridcolor='rgba(0,0,0,0.06)', zeroline=False)
    return fig


def grafico_progreso(acts):
    """Evolución del ritmo medio por disciplina a lo largo del tiempo, con su
    tendencia. Muestra el progreso del atleta y devuelve (fig, % mejora por disciplina)."""
    deps = [('RUNNING', 'Carrera', '#f59e0b'), ('CYCLING', 'Ciclismo', '#22a06b'),
            ('SWIMMING', 'Natación', '#3b82f6')]
    if acts is None or 'sport' not in acts.columns or 'date' not in acts.columns:
        return None, {}
    pres = [(s, n, c) for s, n, c in deps
            if not acts[acts['sport'] == s].dropna(subset=['avg_speed_kmh']).empty]
    if not pres:
        return None, {}
    fig, axes = plt.subplots(1, len(pres), figsize=(10, 2.7))
    if len(pres) == 1:
        axes = [axes]
    mejoras = {}
    for ax, (s, n, c) in zip(axes, pres):
        df = acts[acts['sport'] == s].dropna(subset=['avg_speed_kmh', 'date']).copy()
        df['date'] = pd.to_datetime(df['date'], utc=True, errors='coerce').dt.tz_localize(None)
        df = df.dropna(subset=['date']).sort_values('date')
        if len(df) < 2:
            ax.axis('off'); continue
        x, y = df['date'], df['avg_speed_kmh'].values
        ax.scatter(x, y, s=14, color=c, alpha=0.45)
        xi = (df['date'] - df['date'].min()).dt.days.values.astype(float)
        if xi.max() > 0:
            m, b = np.polyfit(xi, y, 1)
            ax.plot(x, m * xi + b, color=c, lw=2.2)
            y0, y1 = b, m * xi[-1] + b
            mejoras[n] = (y1 - y0) / y0 * 100 if y0 > 0 else 0.0
        ax.set_title(n, fontsize=10, color=c, fontweight='bold')
        ax.set_ylabel('km/h', fontsize=8)
        ax.tick_params(labelsize=7, colors='#8a877f')
        for sp in ('top', 'right'):
            ax.spines[sp].set_visible(False)
        for lbl in ax.get_xticklabels():
            lbl.set_rotation(30); lbl.set_ha('right')
    fig.tight_layout()
    return fig, mejoras


def progreso_semanal(acts, desde=None):
    """Media SEMANAL del ritmo por disciplina + KPIs (ritmo actual y % de mejora).

    Solo considera actividades a partir de `desde` (fecha de inicio del plan), porque
    el gráfico refleja la evolución DESDE QUE EMPEZASTE el plan. Devuelve
    (df_indice, kpis): índice de progreso (primera semana = 100) por disciplina.
    """
    deps = [('RUNNING', 'Carrera'), ('CYCLING', 'Ciclismo'), ('SWIMMING', 'Natación')]
    if acts is None or 'sport' not in acts.columns or 'date' not in acts.columns:
        return None, {}
    a = acts.dropna(subset=['avg_speed_kmh']).copy()
    a['date'] = pd.to_datetime(a['date'], utc=True, errors='coerce').dt.tz_localize(None)
    a = a.dropna(subset=['date'])
    if desde is not None:
        a = a[a['date'] >= pd.Timestamp(desde).normalize()]   # solo desde el inicio del plan
    if a.empty:
        return None, {}
    # Semana DESDE EL INICIO (1, 2, 3…), no por calendario: así la semana 1 es
    # un único punto y el gráfico solo aparece con ≥2 semanas de actividad.
    inicio = a['date'].min()
    a['semana'] = ((a['date'] - inicio).dt.days // 7) + 1
    series, kpis = {}, {}
    for s, n in deps:
        d = a[a['sport'] == s]
        if d.empty:
            continue
        wk = d.groupby('semana')['avg_speed_kmh'].mean().sort_index()
        if len(wk) < 2:
            continue
        series[n] = wk
        v0, v1 = float(wk.iloc[0]), float(wk.iloc[-1])
        kpis[n] = (v1, (v1 - v0) / v0 * 100 if v0 > 0 else 0.0)
    if not series:
        return None, {}
    idx = pd.DataFrame({n: s / s.iloc[0] * 100 for n, s in series.items()})
    idx.index.name = 'Semana'
    return idx, kpis


def grafico_zonas(z):
    fig, ax = plt.subplots(figsize=(10, 1.9))
    for zona, (lo, hi) in z['hr'].items():
        ax.barh(0, hi - lo, left=lo, height=0.62, color=GARMIN_COLORS[zona])
        ax.text((lo + hi) / 2, 0, f"{zona}\n{lo}-{hi}", ha='center', va='center',
                color='white', fontsize=9, fontweight='bold')
    ax.set_xlim(z['hr']['Z1'][0] - 8, z['hr']['Z5'][1] + 8)
    ax.set_yticks([])
    ax.set_xlabel('pulsaciones por minuto (ppm)', fontsize=9)
    for s in ('top', 'right', 'left'):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    return fig


def grafico_zonas_plotly(z):
    """Barra de zonas de FC interactiva (Plotly): cada tramo Z1-Z5 con su rango."""
    fig = go.Figure()
    for zona, (lo, hi) in z['hr'].items():
        fig.add_trace(go.Bar(
            y=['FC'], x=[hi - lo], base=[lo], orientation='h', width=0.6,
            marker=dict(color=GARMIN_COLORS[zona]),
            text=[f"{zona}<br>{lo}-{hi}"], textposition='inside',
            insidetextanchor='middle', textfont=dict(color='white', size=12),
            hovertemplate=f"{zona}: {lo}-{hi} ppm<extra></extra>", showlegend=False))
    fig.update_layout(barmode='overlay', height=130, margin=dict(l=8, r=8, t=6, b=28),
                      paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                      font=dict(size=12, color='#5b6670'),
                      xaxis=dict(title='pulsaciones por minuto (ppm)',
                                 range=[z['hr']['Z1'][0] - 8, z['hr']['Z5'][1] + 8],
                                 showgrid=False),
                      yaxis=dict(showticklabels=False))
    return fig


# Macrociclo: color y carga relativa (0-1) de cada fase, con fines pedagógicos
FASES_INFO = [
    ('Base',         '#3b82f6', 0.55, 'volumen alto · intensidad baja'),
    ('Construcción', '#22a06b', 0.80, 'volumen alto · intensidad media (sube la carga)'),
    ('Pico',         '#ef4444', 1.00, 'intensidad máxima · volumen medio'),
    ('Taper',        '#f59e0b', 0.35, 'descarga: baja el volumen, llega la frescura'),
    ('70.3',         '#7c3aed', 0.25, 'día de carrera'),
]
NOMBRE_FASE = {'BASE': 'Base', 'CONSTRUCCION': 'Construcción', 'PICO': 'Pico',
               'TAPERING': 'Taper', 'COMPETENCIA': '70.3'}


MESES_ES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto',
            'septiembre', 'octubre', 'noviembre', 'diciembre']


def _aclarar(hex_color, f=0.82):
    """Mezcla un color con blanco (f = proporción de blanco), para los tramos futuros."""
    h = hex_color.lstrip('#')
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return '#{:02x}{:02x}{:02x}'.format(*(int(c + (255 - c) * f) for c in (r, g, b)))


def html_frase_dia(frase, nombre, per, fh):
    """Banner de la frase del día: grande, cálido y con la fecha, para empezar con energía."""
    frase = str(frase).strip()
    frase = frase[:1].upper() + frase[1:]
    if frase[-1:] not in '.!?':
        frase += '.'
    fecha_txt = f"{DIAS_ES[fh.dayofweek]} {fh.day} de {MESES_ES[fh.month - 1]}"
    return (
        '<div class="hero">'
        f'<div class="hero-eyebrow">👋 ¡Hola, {nombre}! · Tu frase de hoy · {fecha_txt}</div>'
        f'<div class="hero-q">{frase}</div>'
        '<div class="hero-by">💪 ¡A por ello!'
        f"<span>Semana {per['semana_actual']} de {per['semanas_totales']}</span>"
        f"<span>{txt_restante(per)} para tu 70.3</span></div>"
        '</div>')


def html_camino(per, fecha_inicio, fecha_comp, fh):
    """Línea de tiempo del macrociclo: tramos proporcionales a sus semanas, lo recorrido
    en color, la posición de hoy y la cuenta atrás hasta la prueba."""
    sem_tot = max(int(per['semanas_totales']), 1)
    sem_act = int(per['semana_actual'])
    # Mismo criterio que calcular_fase (semanas restantes), alineado con la semana actual
    desfase = (sem_tot - sem_act + 1) - int(per['semanas_restantes'])

    def fase_sem(s):
        r = sem_tot - s + 1 - desfase
        return ('COMPETENCIA' if r <= 1 else 'TAPERING' if r <= 3 else 'PICO' if r <= 6
                else 'CONSTRUCCION' if r <= 12 else 'BASE')

    tramos = []
    for s in range(1, sem_tot + 1):
        f = fase_sem(s)
        if tramos and tramos[-1][0] == f:
            tramos[-1][2] = s
        else:
            tramos.append([f, s, s])
    info = {n: (c, d) for n, c, _ca, d in FASES_INFO}
    ini = pd.Timestamp(fecha_inicio).normalize()
    dias_plan = max((pd.Timestamp(fecha_comp).normalize() - ini).days, 1)
    pos = min(max((fh - ini).days / 7.0, 0.0), float(sem_tot))       # en semanas
    pos_pct = pos / sem_tot * 100

    segs, etiquetas = '', ''
    for f, a, b in tramos:
        nom = NOMBRE_FASE.get(f, f)
        color, _d = info.get(nom, ('#1d6fa5', ''))
        n = b - a + 1
        lleno = min(max((pos - (a - 1)) / n, 0.0), 1.0) * 100
        actual = f == per['fase']
        clase = 'seg actual' if actual else ('seg hecho' if lleno >= 100 else 'seg')
        rotulo = '🏁' if f == 'COMPETENCIA' else nom
        segs += (f'<div class="{clase}" style="flex:{n};background:{_aclarar(color)}">'
                 f'<div class="fill" style="width:{lleno:.1f}%;background:{color}"></div>'
                 f'<b{" class=sombra" if actual else ""} style="color:'
                 f'{"#fff" if lleno >= 100 else ("#0B2A4A" if actual else color)};'
                 f'{("justify-content:" + ("flex-end" if lleno < 50 else "flex-start") + ";padding:0 12px") if actual else ""}">'
                 f'{rotulo}</b></div>')
        etiquetas += (f'<div style="flex:{n}">{"s" + str(a) if a == b else f"s{a}–{b}"}</div>')

    # Fase actual y la siguiente
    idx = next((i for i, t in enumerate(tramos) if t[0] == per['fase']), 0)
    nom_act = NOMBRE_FASE.get(per['fase'], per['fase'])
    color_act, desc_act = info.get(nom_act, ('#1d6fa5', ''))
    siguiente = ''
    if idx + 1 < len(tramos):
        f2, a2, _b2 = tramos[idx + 1]
        en = a2 - sem_act
        ini2 = ini + pd.Timedelta(days=(a2 - 1) * 7)
        siguiente = (f' · Siguiente: <b>{NOMBRE_FASE.get(f2, f2)}</b> en {en} '
                     f'semana{"s" if en != 1 else ""} ({ini2:%d/%m})')
    dias_carrera = max((pd.Timestamp(fecha_comp).normalize() - fh).days, 0)
    return (
        '<div class="camino">'
        '<div class="camino-head"><div>'
        '<div class="eyebrow">TU CAMINO AL 70.3</div>'
        f'<div class="big">Semana {sem_act} <span>de {sem_tot}</span> · '
        f'<b style="color:{color_act}">{nom_act}</b></div></div>'
        f'<div class="cuenta"><div class="num">{dias_carrera}</div>'
        f'<div class="lab">días para<br>tu 70.3 · {pd.Timestamp(fecha_comp):%d/%m/%Y}</div></div></div>'
        f'<div class="track">{segs}<div class="pin" style="left:{pos_pct:.1f}%"><i>HOY</i></div></div>'
        f'<div class="weeks">{etiquetas}</div>'
        f'<div class="camino-foot"><b style="color:{color_act}">● {nom_act}:</b> {desc_act}{siguiente}</div>'
        '</div>')


def grafico_fases(fase_actual, sem_actual, sem_tot):
    """Barra de macrociclo cuyos tramos respetan los MISMOS umbrales por semanas
    que definen la fase (base >12 sem, construcción 7-12, pico 4-6, taper 2-3,
    70.3 ≤1), de modo que el marcador SIEMPRE cae sobre la fase activa.
    El color y la altura de cada tramo representan la carga relativa de la fase.
    """
    sem_tot = max(int(sem_tot), 1)

    def frac(semanas_desde_inicio):
        return min(max(semanas_desde_inicio / sem_tot, 0.0), 1.0)

    # Fin de cada fase como fracción del plan (derivado de las semanas restantes)
    fin = {
        'Base': frac(sem_tot - 12),
        'Construcción': frac(sem_tot - 6),
        'Pico': frac(sem_tot - 3),
        'Taper': frac(sem_tot - 1),
        '70.3': 1.0,
    }
    ini = 0.0
    activa = NOMBRE_FASE.get(fase_actual, '')
    fig, ax = plt.subplots(figsize=(10, 1.5))
    for nom, color, carga, _desc in FASES_INFO:
        x1 = fin[nom]
        w = x1 - ini
        if w > 0.001:
            es_act = (nom == activa)
            # la altura de la barra refleja la carga relativa de la fase
            h = 0.25 + 0.55 * carga
            ax.barh(0, w, left=ini, height=h, color=color,
                    alpha=1.0 if es_act else 0.40,
                    edgecolor='#111111' if es_act else 'none',
                    linewidth=2.2 if es_act else 0)
            ax.text(ini + w / 2, 0, nom, ha='center', va='center', color='white',
                    fontsize=8.5, fontweight='bold')
        ini = x1
    pos = min(max(sem_actual / sem_tot, 0.0), 1.0)
    ax.plot([pos], [0.62], marker='v', color='#111111', markersize=12)
    ax.text(pos, 0.80, f'semana {sem_actual}', ha='center', fontsize=8.5, fontweight='bold')
    ax.set_xlim(0, 1)
    ax.set_ylim(-0.7, 1.05)
    ax.axis('off')
    fig.tight_layout()
    return fig




# Frases del día (copiadas de la interfaz)
FRASES_DIA = [
    "el plan no es el que más duele, sino el que sí cumples.",
    "la constancia de hoy es la marca de tu próximo 70.3.",
    "entrena por pulso, no por ego: la FC manda sobre el ritmo.",
    "cada Z2 bien hecha es un ladrillo de tu base aeróbica.",
    "descansar también es entrenar: la adaptación ocurre durmiendo.",
    "la transición se entrena; el día de la carrera no se improvisa.",
    "nada lento para correr rápido: la paciencia es velocidad diferida.",
    "el 70.3 se gana en la bici y se sufre corriendo: dosifica.",
    "mejor una semana sostenible que tres heroicas y una lesión.",
    "tu mejor sesión es la que te deja con ganas de la siguiente.",
]
