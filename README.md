# Mi plan 70.3 · app Android

App móvil del TFM «Planificación adaptativa de entrenamientos de alta carga mediante aprendizaje automático: caso de estudio del triatlón de media distancia (113 km)».

La app hace lo mismo que el demostrador de Streamlit, porque usa el mismo motor:

- fases del macrociclo;
- tipo de semana según la Tabla 7, decidido con el TSB medio de la semana anterior;
- curvas de forma, fatiga y frescura (CTL/ATL/TSB);
- plan semanal con fuerza y desnivel;
- ajuste del día con sueño, Body Battery y estrés;
- zonas y ritmos, y modelos XGBoost de transferencia;
- plan de carrera km a km;
- conexión con Strava;
- modo demo con simulador de días.

La interfaz está rediseñada para el móvil, con cinco pestañas: Hoy, Semana, Forma, Carrera y Perfil.

```
backend/            API FastAPI (Python)
  motor.py          motor del TFM, GENERADO desde app.py (no editar a mano)
  st_shim.py        sustituto mínimo de Streamlit para ejecutar el motor
  main.py           endpoints /api/plan, /api/strava/*, /api/ejercicios, /api/health
  modelos/          modelos XGBoost y preprocesadores (sin datos de deportistas)
  tests/            pruebas automáticas
mobile/             app Capacitor (HTML/CSS/JS sin dependencias)
  www/              interfaz: index.html, styles.css, app.js, config.js
  assets/           icono y pantalla de arranque
  scripts/          ajuste del proyecto Android (deep link de Strava)
tools/sync_motor.py regenera backend/motor.py desde el app.py de Streamlit
render.yaml         despliegue de la API en Render
.github/workflows/  compilación del APK y pruebas de la API
```

## 1. Subir el código al repositorio nuevo

Copia el contenido de esta carpeta (`app_movil`) en la raíz de tu repositorio nuevo y súbelo a GitHub. La carpeta `.github` también tiene que subirse; en Windows está oculta. Nunca subas archivos `.parquet` ni `.db` con datos de deportistas. El `.gitignore` ya los excluye.

## 2. Desplegar la API (Render, plan gratuito)

1. Entra en render.com con tu cuenta de GitHub y pulsa **New → Blueprint**. Elige el repositorio: Render leerá `render.yaml`.
2. Cuando te las pida, rellena estas variables:
   - `STRAVA_CLIENT_ID` y `STRAVA_CLIENT_SECRET`: las mismas de la app de Streamlit.
   - `GEMINI_API_KEY`: opcional. Si no la pones, la app usa textos y frases propias.
3. Cuando termine, abre `https://<tu-servicio>.onrender.com/api/health`. Debe responder `"ok": true` y `"modelos": true`.

En el plan gratuito, el servicio se duerme tras 15 minutos sin uso. La primera carga del día tarda entre 30 y 60 segundos, y la app lo avisa con "Despertando el servidor…".

## 3. Strava

No hay que cambiar nada en Strava. La app usa como dirección de vuelta `miplan703://miplan703.streamlit.app`, cuyo dominio coincide con el **Authorization Callback Domain** que ya tienes (`miplan703.streamlit.app`). Así funcionan a la vez la web y el móvil.

Si al autorizar Strava muestra un error de `redirect_uri`, hay otra opción: pon como dominio de callback el de la API de Render, define en Render `STRAVA_MOBILE_REDIRECT` y cambia `STRAVA_REDIRECT` en `mobile/www/config.js`. En ese caso, la web de Streamlit dejaría de poder conectar con Strava.

Por la política de la API de Strava, cuando los datos vienen de Strava la API **no los envía a Gemini**: usa textos propios. Para cambiarlo, define `GEMINI_CON_STRAVA=1`.

## 4. Compilar el APK (GitHub Actions)

1. En GitHub, entra en **Settings → Secrets and variables → Actions → Variables** y crea `API_URL` con la URL de Render, por ejemplo `https://miplan703-api.onrender.com`.
2. Entra en **Actions → APK Android → Run workflow**. El flujo también se lanza solo cada vez que cambias algo en `mobile/`.
3. Al terminar, unos 6 minutos después, el APK está en **Releases → apk-latest → miplan703.apk** y también en los Artifacts de la ejecución.
4. En el teléfono Android, descarga `miplan703.apk`, ábrelo y permite "instalar apps de origen desconocido".

El APK está firmado en modo depuración. Sirve para uso personal y demostraciones, pero no para Google Play: publicarlo allí requiere una firma de release y una cuenta de desarrollador.

Si cambias de servidor sin recompilar, puedes hacerlo dentro de la app: **Perfil → Servidor**.

## 5. Mantener el motor sincronizado

Si mejoras el motor en el `app.py` de Streamlit, actualiza la API así:

```
python tools/sync_motor.py ruta/a/app.py
python -m pytest backend/tests
```

## 6. Probar en el ordenador

```
cd backend && pip install -r requirements.txt && uvicorn main:app --port 8000
cd mobile/www && python -m http.server 8080
```

Después abre `http://localhost:8080` y, en **Perfil → Servidor**, escribe `http://localhost:8000`.

## Qué se guarda y dónde

- **En el teléfono:** la configuración (fechas, perfil, sexo, último 70.3), el registro matinal del día, el último plan (para verlo sin conexión) y la sesión de Strava (refresh token). Para borrarlo todo: **Perfil → Borrar mis datos de este teléfono**.
- **En el servidor:** nada. La API calcula el plan en cada petición y no almacena datos de los deportistas.
