# -*- coding: utf-8 -*-
"""Sustituto mínimo de Streamlit para ejecutar el motor de app.py dentro de la API.

El motor solo usa de Streamlit: cachés (@st.cache_data / @st.cache_resource),
secretos (st.secrets), el estado de sesión (la fecha simulada de la demo) y algunos
avisos (st.error). Aquí se implementan sin interfaz:

- session_state: un diccionario POR PETICIÓN (contextvars), para que la fecha
  simulada de un usuario no afecte a otro.
- secrets: variables de entorno (STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET,
  GEMINI_API_KEY...).
- cachés: memoria con caducidad; si los argumentos no se pueden usar como clave
  (p. ej. un DataFrame), simplemente no se cachea.
- cualquier otra función de Streamlit (markdown, error...) no hace nada.
"""
import contextvars
import functools
import logging
import os
import time

log = logging.getLogger('motor')

# ---------------------------------------------------------------- estado de sesión
_ss = contextvars.ContextVar('session_state', default=None)


class _SessionState:
    def _d(self):
        d = _ss.get()
        if d is None:
            d = {}
            _ss.set(d)
        return d

    def get(self, k, default=None):
        return self._d().get(k, default)

    def __getitem__(self, k):
        return self._d()[k]

    def __setitem__(self, k, v):
        self._d()[k] = v

    def __contains__(self, k):
        return k in self._d()

    def pop(self, k, default=None):
        return self._d().pop(k, default)

    def setdefault(self, k, v):
        return self._d().setdefault(k, v)

    def update(self, *a, **kw):
        self._d().update(*a, **kw)


session_state = _SessionState()


def nueva_sesion(**valores):
    """Inicia un estado de sesión limpio para la petición actual."""
    _ss.set(dict(valores))


# ---------------------------------------------------------------- secretos
_MAPA_SECRETOS = {'strava_client_id': 'STRAVA_CLIENT_ID',
                  'strava_client_secret': 'STRAVA_CLIENT_SECRET',
                  'redirect_uri': 'STRAVA_REDIRECT_URI',
                  'gemini_api_key': 'GEMINI_API_KEY'}


class _Secrets:
    def get(self, k, default=None):
        return os.getenv(_MAPA_SECRETOS.get(k, k.upper()), default) or default

    def __getitem__(self, k):
        v = self.get(k)
        if v is None:
            raise KeyError(k)
        return v

    def __contains__(self, k):
        return self.get(k) is not None


secrets = _Secrets()


class _QueryParams(dict):
    def from_dict(self, d):
        self.clear()
        self.update(d)


query_params = _QueryParams()


class _Context:
    cookies = {}
    headers = {}


context = _Context()


# ---------------------------------------------------------------- cachés
def _clave(fn, a, kw):
    try:
        k = (fn.__qualname__, a, tuple(sorted(kw.items())))
        hash(k)
        return k
    except TypeError:
        return None


def _cache(ttl=None):
    def deco(fn):
        memo = {}

        @functools.wraps(fn)
        def envoltura(*a, **kw):
            k = _clave(fn, a, kw)
            if k is None:
                return fn(*a, **kw)
            hit = memo.get(k)
            if hit and (ttl is None or time.time() - hit[0] < ttl):
                return hit[1]
            v = fn(*a, **kw)
            if len(memo) > 512:
                memo.clear()
            memo[k] = (time.time(), v)
            return v

        envoltura.clear = memo.clear
        return envoltura
    return deco


def cache_data(fn=None, *, ttl=None, show_spinner=None, **_):
    if callable(fn):
        return _cache(None)(fn)
    return _cache(ttl)


def cache_resource(fn=None, *, ttl=None, show_spinner=None, **_):
    if callable(fn):
        return _cache(None)(fn)
    return _cache(ttl)


# ---------------------------------------------------------------- avisos y resto
def error(msg, *a, **kw):
    log.error(str(msg))


def warning(msg, *a, **kw):
    log.warning(str(msg))


def __getattr__(nombre):            # st.markdown, st.caption... no hacen nada
    def _nada(*a, **kw):
        return None
    return _nada
