# -*- coding: utf-8 -*-
"""Genera backend/motor.py a partir del app.py de Streamlit.

El motor de la app móvil es EL MISMO código del demostrador Streamlit (reglas de la
Tabla 7, CTL/ATL/TSB, plan semanal, zonas, modelos XGBoost, Strava...). Este script
copia todas las definiciones de app.py (todo lo que hay antes de la sección
«Interfaz»), quita lo que solo sirve para pintar en Streamlit y sustituye
`import streamlit as st` por un sustituto mínimo (st_shim.py). Así, si mejoras el
motor en app.py, basta con volver a ejecutar:

    python tools/sync_motor.py ruta/a/app.py
"""
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
origen = Path(sys.argv[1]) if len(sys.argv) > 1 else RAIZ.parent / 'app.py'
S = origen.read_text(encoding='utf-8')

# 1) Solo las definiciones: todo lo anterior a la sección de interfaz
corte = S.index('# Interfaz\n# ---')
defs = S[:S.rindex('# ---', 0, corte)]

# 2) Fuera la configuración de página y la hoja de estilos de Streamlit
ini = defs.index('st.set_page_config(')
fin = defs.index('""", unsafe_allow_html=True)', ini) + len('""", unsafe_allow_html=True)')
defs = defs[:ini] + '# (configuración de página y estilos de Streamlit omitidos en la API)\n' + defs[fin:]

# 3) Sustituto de Streamlit y matplotlib opcional
defs = defs.replace('import streamlit as st\n', 'import st_shim as st\n', 1)
defs = defs.replace('import matplotlib.pyplot as plt\n',
                    'try:\n    import matplotlib.pyplot as plt\nexcept ImportError:\n    plt = None\n', 1)

# 4) Frases del día (definidas en la interfaz): se copian tal cual
m = re.search(r'^FRASES_DIA = \[.*?^\]\n', S, flags=re.S | re.M)
frases = m.group(0) if m else 'FRASES_DIA = ["la constancia de hoy es la marca de tu próximo 70.3."]\n'

cab = ('# -*- coding: utf-8 -*-\n'
       '# ARCHIVO GENERADO por tools/sync_motor.py a partir de app.py: no lo edites a mano.\n'
       '# Motor del demostrador Streamlit, reutilizado sin cambios por la API móvil.\n')
salida = cab + defs.split('\n', 1)[1] + '\n\n# Frases del día (copiadas de la interfaz)\n' + frases
destino = RAIZ / 'backend' / 'motor.py'
destino.write_text(salida, encoding='utf-8')
print(f'motor.py generado desde {origen} ({salida.count(chr(10))} líneas)')
