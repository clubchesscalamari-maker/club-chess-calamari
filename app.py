# -*- coding: utf-8 -*-
"""
♟️ Club Chess Calamari — Página web hecha con Streamlit
-------------------------------------------------------
Funciones:
  • Mensajes de contacto (precios, dudas) que llegan a tu bandeja en el panel Admin
    (y opcionalmente a tu Gmail).
  • Zona de miembros con contraseña (torneos y avisos importantes).
  • Galería tipo Facebook: foto con texto y emojis arriba, flechas y deslizar con el dedo.
  • Corazoncitos ❤️ para cualquier visitante + conteo por foto.
  • Contador de visitas (lo ves en Admin).
  • Panel Admin: editar correo, número, textos; subir, editar y borrar fotos;
    cambiar colores de la página.

Guarda los datos en Supabase (gratis) si lo configuras en "Secrets".
Si no, usa una base local temporal (se puede borrar cuando Streamlit reinicie la app).
"""

import base64
import html
import io
import os
import smtplib
import sqlite3
from datetime import datetime
from email.message import EmailMessage
from urllib.parse import quote

import requests
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, ImageOps

# ──────────────────────────────────────────────────────────────
# CONFIGURACIÓN GENERAL
# ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Club Chess Calamari",
    page_icon="♟️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

CARPETA = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(CARPETA, "imagenes")
DB_LOCAL = os.path.join(CARPETA, "datos_club.db")

DEFAULTS = {
    "correo": "clubchesscalamari@gmail.com",
    "telefono": "",
    "whatsapp": "",
    "direccion": "Parque del barrio El Recreo, Esq. Carrera 80A, Dg. 31f, El Recreo, Cartagena de Indias, Bolívar",
    "referencia": "Al lado de la Parroquia Asunción Santa María Virgen - El Recreo (Carrera 80C)",
    "maps_link": "https://maps.app.goo.gl/tnEbsH6HjbafNpTUA",
    "fundadora": "Miladys Acosta",
    "lema": "Donde la historia y la estrategia se encuentran",
    "bienvenida": (
        "♟️ ¡Bienvenido al Club Chess Calamari! Somos un club donde se dictan clases de "
        "ajedrez para niños, jóvenes y adultos, en el corazón del barrio El Recreo, en "
        "Cartagena. Aquí aprendemos, jugamos torneos y compartimos la pasión por el ajedrez. 👑"
    ),
    "clases": (
        "📚 Clases de ajedrez para todos los niveles.\n\n"
        "💰 Precios y horarios: escríbenos desde la pestaña Contacto y te respondemos.\n\n"
        "🏆 Participamos y organizamos torneos durante el año."
    ),
    "color_fondo": "#FFFFFF",
    "color_principal": "#1D4ED8",
    "clave_miembros": "",
    "visitas": "0",
    "fotos_iniciales": "no",
}

FOTOS_INICIALES = [
    ("foto1.jpg", "♟️ Clases al aire libre en el parque El Recreo 🌳"),
    ("foto2.jpg", "🌿 Aprendiendo y jugando bajo los árboles 👦👧"),
    ("foto3.jpg", "🏠 Montando el tablero para empezar la clase ♟️"),
    ("foto4.jpg", "🏆 Torneo en sala: ¡concentración total! 🤔"),
    ("foto5.jpg", "🇨🇴 Torneo infantil con la camiseta de Colombia 💛💙❤️"),
    ("foto6.jpg", "🌙 Torneo nocturno en el parque ✨"),
    ("foto7.jpg", "👑 Partidas de adultos: ¡cada jugada cuenta! ⏱️"),
]


# ──────────────────────────────────────────────────────────────
# CAPA DE DATOS (Supabase si hay Secrets, SQLite local si no)
# ──────────────────────────────────────────────────────────────
def _secret(nombre, defecto=""):
    try:
        return st.secrets.get(nombre, defecto)
    except Exception:
        return defecto


SUPA_URL = str(_secret("SUPABASE_URL")).rstrip("/")
SUPA_KEY = str(_secret("SUPABASE_KEY"))
USA_SUPABASE = bool(SUPA_URL and SUPA_KEY)


class Datos:
    """Interfaz única. Mismos métodos para Supabase y SQLite."""

    # ---------- Supabase ----------
    def _h(self, extra=None):
        h = {
            "apikey": SUPA_KEY,
            "Authorization": f"Bearer {SUPA_KEY}",
            "Content-Type": "application/json",
        }
        if extra:
            h.update(extra)
        return h

    def _rest(self, metodo, tabla, params=None, json=None, prefer=None):
        url = f"{SUPA_URL}/rest/v1/{tabla}"
        extra = {"Prefer": prefer} if prefer else None
        r = requests.request(
            metodo, url, headers=self._h(extra), params=params, json=json, timeout=25
        )
        r.raise_for_status()
        return r.json() if r.text else []

    # ---------- SQLite ----------
    def _db(self):
        con = sqlite3.connect(DB_LOCAL)
        con.row_factory = sqlite3.Row
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS ajustes(clave TEXT PRIMARY KEY, valor TEXT);
            CREATE TABLE IF NOT EXISTS fotos(
                id INTEGER PRIMARY KEY AUTOINCREMENT, texto TEXT, imagen TEXT,
                corazones INTEGER DEFAULT 0, creada TEXT);
            CREATE TABLE IF NOT EXISTS mensajes(
                id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, contacto TEXT,
                mensaje TEXT, creado TEXT, leido INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS avisos(
                id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT, cuerpo TEXT, creado TEXT);
            """
        )
        return con

    # ---------- Ajustes ----------
    def ajustes(self):
        if USA_SUPABASE:
            filas = self._rest("GET", "ajustes", {"select": "clave,valor"})
        else:
            con = self._db()
            filas = [dict(f) for f in con.execute("SELECT clave, valor FROM ajustes")]
            con.close()
        d = dict(DEFAULTS)
        d.update({f["clave"]: f["valor"] for f in filas})
        return d

    def guardar_ajuste(self, clave, valor):
        valor = str(valor)
        if USA_SUPABASE:
            self._rest(
                "POST", "ajustes", {"on_conflict": "clave"},
                [{"clave": clave, "valor": valor}],
                prefer="resolution=merge-duplicates",
            )
        else:
            con = self._db()
            con.execute("INSERT OR REPLACE INTO ajustes VALUES (?,?)", (clave, valor))
            con.commit()
            con.close()

    # ---------- Fotos ----------
    def fotos(self):
        """Lista liviana (sin la imagen)."""
        if USA_SUPABASE:
            return self._rest(
                "GET", "fotos",
                {"select": "id,texto,corazones,creada", "order": "id.asc"},
            )
        con = self._db()
        filas = [dict(f) for f in con.execute(
            "SELECT id, texto, corazones, creada FROM fotos ORDER BY id")]
        con.close()
        return filas

    def imagen(self, foto_id):
        if USA_SUPABASE:
            f = self._rest("GET", "fotos", {"select": "imagen", "id": f"eq.{foto_id}"})
            return f[0]["imagen"] if f else ""
        con = self._db()
        f = con.execute("SELECT imagen FROM fotos WHERE id=?", (foto_id,)).fetchone()
        con.close()
        return f["imagen"] if f else ""

    def agregar_foto(self, texto, imagen_b64):
        ahora = datetime.utcnow().isoformat()
        if USA_SUPABASE:
            self._rest("POST", "fotos", json=[
                {"texto": texto, "imagen": imagen_b64, "corazones": 0, "creada": ahora}])
        else:
            con = self._db()
            con.execute(
                "INSERT INTO fotos(texto,imagen,corazones,creada) VALUES (?,?,0,?)",
                (texto, imagen_b64, ahora))
            con.commit()
            con.close()

    def editar_foto(self, foto_id, texto):
        if USA_SUPABASE:
            self._rest("PATCH", "fotos", {"id": f"eq.{foto_id}"}, {"texto": texto})
        else:
            con = self._db()
            con.execute("UPDATE fotos SET texto=? WHERE id=?", (texto, foto_id))
            con.commit()
            con.close()

    def borrar_foto(self, foto_id):
        if USA_SUPABASE:
            self._rest("DELETE", "fotos", {"id": f"eq.{foto_id}"})
        else:
            con = self._db()
            con.execute("DELETE FROM fotos WHERE id=?", (foto_id,))
            con.commit()
            con.close()

    def sumar_corazon(self, foto_id, actuales):
        nuevo = int(actuales) + 1
        if USA_SUPABASE:
            self._rest("PATCH", "fotos", {"id": f"eq.{foto_id}"}, {"corazones": nuevo})
        else:
            con = self._db()
            con.execute("UPDATE fotos SET corazones=corazones+1 WHERE id=?", (foto_id,))
            con.commit()
            con.close()

    # ---------- Mensajes ----------
    def agregar_mensaje(self, nombre, contacto, mensaje):
        ahora = datetime.utcnow().isoformat()
        if USA_SUPABASE:
            self._rest("POST", "mensajes", json=[{
                "nombre": nombre, "contacto": contacto, "mensaje": mensaje,
                "creado": ahora, "leido": False}])
        else:
            con = self._db()
            con.execute(
                "INSERT INTO mensajes(nombre,contacto,mensaje,creado,leido) VALUES (?,?,?,?,0)",
                (nombre, contacto, mensaje, ahora))
            con.commit()
            con.close()

    def mensajes(self):
        if USA_SUPABASE:
            return self._rest("GET", "mensajes", {"select": "*", "order": "id.desc"})
        con = self._db()
        filas = [dict(f) for f in con.execute("SELECT * FROM mensajes ORDER BY id DESC")]
        con.close()
        return filas

    def marcar_leido(self, mid, leido=True):
        if USA_SUPABASE:
            self._rest("PATCH", "mensajes", {"id": f"eq.{mid}"}, {"leido": leido})
        else:
            con = self._db()
            con.execute("UPDATE mensajes SET leido=? WHERE id=?", (1 if leido else 0, mid))
            con.commit()
            con.close()

    def borrar_mensaje(self, mid):
        if USA_SUPABASE:
            self._rest("DELETE", "mensajes", {"id": f"eq.{mid}"})
        else:
            con = self._db()
            con.execute("DELETE FROM mensajes WHERE id=?", (mid,))
            con.commit()
            con.close()

    # ---------- Avisos para miembros ----------
    def avisos(self):
        if USA_SUPABASE:
            return self._rest("GET", "avisos", {"select": "*", "order": "id.desc"})
        con = self._db()
        filas = [dict(f) for f in con.execute("SELECT * FROM avisos ORDER BY id DESC")]
        con.close()
        return filas

    def agregar_aviso(self, titulo, cuerpo):
        ahora = datetime.utcnow().isoformat()
        if USA_SUPABASE:
            self._rest("POST", "avisos", json=[
                {"titulo": titulo, "cuerpo": cuerpo, "creado": ahora}])
        else:
            con = self._db()
            con.execute("INSERT INTO avisos(titulo,cuerpo,creado) VALUES (?,?,?)",
                        (titulo, cuerpo, ahora))
            con.commit()
            con.close()

    def borrar_aviso(self, aid):
        if USA_SUPABASE:
            self._rest("DELETE", "avisos", {"id": f"eq.{aid}"})
        else:
            con = self._db()
            con.execute("DELETE FROM avisos WHERE id=?", (aid,))
            con.commit()
            con.close()


DB = Datos()


# ──────────────────────────────────────────────────────────────
# CACHÉ Y UTILIDADES
# ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=30, show_spinner=False)
def cargar_ajustes():
    return DB.ajustes()


@st.cache_data(ttl=20, show_spinner=False)
def cargar_fotos():
    return DB.fotos()


@st.cache_data(ttl=3600, max_entries=40, show_spinner=False)
def cargar_imagen(foto_id):
    return DB.imagen(foto_id)


def limpiar_cache():
    cargar_ajustes.clear()
    cargar_fotos.clear()
    cargar_imagen.clear()


@st.cache_data(show_spinner=False)
def archivo_b64(nombre):
    ruta = os.path.join(IMG, nombre)
    if not os.path.exists(ruta):
        return ""
    with open(ruta, "rb") as f:
        return base64.b64encode(f.read()).decode()


def preparar_imagen(archivo_subido):
    """Recorta a rectángulo 4:3 (horizontal), cuidando que se vea la escena, y comprime."""
    im = Image.open(archivo_subido)
    im = ImageOps.exif_transpose(im).convert("RGB")
    im = ImageOps.fit(im, (1200, 900), Image.LANCZOS, centering=(0.5, 0.4))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=82, optimize=True)
    return base64.b64encode(buf.getvalue()).decode()


def sembrar_fotos_iniciales(a):
    """La primera vez, sube las 7 fotos de la carpeta imagenes/ a la galería."""
    if a.get("fotos_iniciales") == "si":
        return
    try:
        if not DB.fotos():
            for nombre, texto in FOTOS_INICIALES:
                b64 = archivo_b64(nombre)
                if b64:
                    DB.agregar_foto(texto, b64)
        DB.guardar_ajuste("fotos_iniciales", "si")
        limpiar_cache()
    except Exception as e:
        st.warning(f"No pude cargar las fotos iniciales: {e}")


def enviar_correo(nombre, contacto, mensaje, destino):
    """Aviso opcional a tu Gmail (requiere GMAIL_APP_PASSWORD en Secrets)."""
    clave = str(_secret("GMAIL_APP_PASSWORD"))
    origen = str(_secret("GMAIL_USER", destino))
    if not clave:
        return False
    try:
        m = EmailMessage()
        m["Subject"] = f"♟️ Nuevo mensaje en la página — {nombre}"
        m["From"] = origen
        m["To"] = destino
        m.set_content(f"Nombre: {nombre}\nContacto: {contacto}\n\n{mensaje}")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as s:
            s.login(origen, clave)
            s.send_message(m)
        return True
    except Exception:
        return False


def esc(t):
    return html.escape(str(t or ""))


def fecha_bonita(iso):
    try:
        return datetime.fromisoformat(str(iso)[:19]).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return ""


# ──────────────────────────────────────────────────────────────
# ESTADO DE LA SESIÓN
# ──────────────────────────────────────────────────────────────
ss = st.session_state
ss.setdefault("indice", 0)
ss.setdefault("mis_corazones", set())
ss.setdefault("admin_ok", False)
ss.setdefault("miembro_ok", False)
ss.setdefault("visita_contada", False)

try:
    A = cargar_ajustes()
except Exception as e:
    st.error(
        "No pude conectar con la base de datos. Revisa SUPABASE_URL y SUPABASE_KEY en Secrets. "
        f"Detalle: {e}"
    )
    st.stop()

sembrar_fotos_iniciales(A)

# Contar visita (una vez por sesión)
if not ss.visita_contada:
    ss.visita_contada = True
    try:
        actual = int(DB.ajustes().get("visitas", 0) or 0)
        DB.guardar_ajuste("visitas", actual + 1)
        cargar_ajustes.clear()
    except Exception:
        pass

AZUL = A.get("color_principal", "#1D4ED8")
FONDO = A.get("color_fondo", "#FFFFFF")


# ──────────────────────────────────────────────────────────────
# ESTILO / DECORACIÓN
# ──────────────────────────────────────────────────────────────
fondo_b64 = archivo_b64("fondo.jpg")
fondo_css = (
    f"background-image: url(data:image/jpeg;base64,{fondo_b64}); "
    "background-blend-mode: multiply; background-attachment: fixed; background-size: 900px auto;"
    if fondo_b64 else ""
)

BALCON_SVG = (
    "<svg viewBox='0 0 80 100' xmlns='http://www.w3.org/2000/svg'>"
    "<rect x='6' y='4' width='68' height='60' rx='3' fill='#1D4ED8' stroke='white' stroke-width='3'/>"
    "<rect x='16' y='12' width='48' height='44' fill='#0B1E5B' stroke='white' stroke-width='2'/>"
    "<line x1='40' y1='12' x2='40' y2='56' stroke='white' stroke-width='2'/>"
    "<rect x='2' y='64' width='76' height='6' fill='white'/>"
    "<g stroke='white' stroke-width='2'>"
    + "".join(f"<line x1='{x}' y1='70' x2='{x}' y2='94'/>" for x in range(8, 75, 8))
    + "</g><rect x='2' y='92' width='76' height='5' fill='white'/></svg>"
)

st.markdown(
    f"""
<style>
:root {{ --azul: {AZUL}; --azul-osc: #0B1E5B; }}
.stApp {{ background-color: {FONDO}; {fondo_css} }}
.block-container {{ padding-top: 0.6rem; max-width: 1150px; }}
header[data-testid="stHeader"] {{ background: transparent; }}

/* Barra superior con tablero en las esquinas */
.barra {{
  position: relative; background: #050B24; color: white; border-radius: 10px 10px 0 0;
  padding: 10px 150px; text-align: center; font-weight: 700; letter-spacing: 3px;
  font-size: 0.95rem; overflow: hidden; min-height: 44px;
}}
.barra::before, .barra::after {{
  content: ""; position: absolute; top: 0; width: 120px; height: 100%;
  background: repeating-conic-gradient(var(--azul) 0% 25%, #050B24 0% 50%) 0 0 / 30px 30px;
}}
.barra::before {{ left: 0; }} .barra::after {{ right: 0; }}
@media (max-width: 640px) {{
  .barra {{ padding: 10px 60px; font-size: .7rem; letter-spacing: 1px; }}
  .barra::before, .barra::after {{ width: 45px; background-size: 22px 22px; }}
}}
.banner img {{ width: 100%; display: block; border-radius: 0 0 14px 14px;
  border-bottom: 5px solid var(--azul); }}
.lema {{ text-align: center; font-family: Georgia, serif; font-size: 1.35rem;
  margin: 14px 0 4px; color: var(--azul-osc); font-weight: 700; }}

/* Pestañas */
div[data-baseweb="tab-list"] {{ gap: 4px; justify-content: center; flex-wrap: wrap;
  background: #050B24; border-radius: 10px; padding: 6px; margin: 10px 0 14px; }}
button[data-baseweb="tab"] {{ color: #dbe4ff !important; font-weight: 700; border-radius: 8px; }}
button[data-baseweb="tab"][aria-selected="true"] {{ background: var(--azul); color: white !important; }}
div[data-baseweb="tab-highlight"] {{ display: none; }}

/* Tarjetas con borde azul doble */
.tarjeta {{
  background: rgba(255,255,255,.93); border: 3px solid var(--azul); outline: 2px solid var(--azul);
  outline-offset: 3px; border-radius: 10px; padding: 16px 20px; margin: 10px 4px 14px;
  box-shadow: 0 4px 14px rgba(0,0,0,.12);
}}
.tarjeta h3 {{ margin-top: 0; color: var(--azul-osc); font-family: Georgia, serif; }}

/* Botones */
.stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {{
  background: var(--azul); color: white; border: 0; border-radius: 8px; font-weight: 700; }}
.stButton > button:hover, .stFormSubmitButton > button:hover {{ background: var(--azul-osc); color: white; }}

/* Carrusel: flechas sobre la imagen */
.st-key-carrusel {{ position: relative; max-width: 760px; margin: 0 auto; }}
.st-key-carrusel img {{ border-radius: 10px; border: 4px solid var(--azul); }}
.st-key-flecha_izq, .st-key-flecha_der {{
  position: absolute; top: 45%; z-index: 20; width: auto !important; }}
.st-key-flecha_izq {{ left: 8px; }} .st-key-flecha_der {{ right: 8px; }}
.st-key-flecha_izq button, .st-key-flecha_der button {{
  border-radius: 50% !important; width: 46px; height: 46px; font-size: 1.3rem; padding: 0;
  border: 2px solid white !important; box-shadow: 0 2px 8px rgba(0,0,0,.4); }}
.texto-foto {{ text-align: center; font-size: 1.2rem; font-weight: 600; margin: 4px 0 10px;
  color: var(--azul-osc); background: rgba(255,255,255,.85); border-radius: 8px; padding: 8px; }}

/* Pie con balcones */
.pie {{ background: #050B24; border-radius: 12px; padding: 14px; margin-top: 24px;
  display: flex; align-items: center; justify-content: center; gap: 18px; flex-wrap: wrap; color: #dbe4ff; }}
.pie .balcon {{ width: 54px; }}
.pie .info {{ text-align: center; font-size: .9rem; line-height: 1.6; }}
.pie a {{ color: #9db8ff; }}
</style>
""",
    unsafe_allow_html=True,
)


# ──────────────────────────────────────────────────────────────
# CABECERA
# ──────────────────────────────────────────────────────────────
banner = archivo_b64("banner.jpg")
st.markdown('<div class="barra">AJEDREZ · CARTAGENA · CLUB CHESS CALAMARI</div>', unsafe_allow_html=True)
if banner:
    st.markdown(
        f'<div class="banner"><img src="data:image/jpeg;base64,{banner}" alt="Club Chess Calamari"></div>',
        unsafe_allow_html=True,
    )
st.markdown(f'<div class="lema">♟️ {esc(A["lema"])} ♟️</div>', unsafe_allow_html=True)

t_inicio, t_clases, t_contacto, t_miembros, t_admin = st.tabs(
    ["🏠 Inicio", "♟️ Clases", "✉️ Contacto", "🔒 Miembros", "⚙️ Admin"]
)


# ──────────────────────────────────────────────────────────────
# GALERÍA (carrusel)
# ──────────────────────────────────────────────────────────────
def ir(delta):
    n = len(cargar_fotos())
    if n:
        ss.indice = (ss.indice + delta) % n


def dar_corazon(foto):
    if foto["id"] in ss.mis_corazones:
        return
    try:
        DB.sumar_corazon(foto["id"], foto.get("corazones", 0))
        ss.mis_corazones.add(foto["id"])
        cargar_fotos.clear()
    except Exception:
        st.toast("No se pudo guardar tu corazón, intenta de nuevo.")


def mostrar_carrusel():
    try:
        fotos = cargar_fotos()
    except Exception as e:
        st.error(f"No pude cargar las fotos: {e}")
        return
    if not fotos:
        st.info("Aún no hay fotos. ¡Pronto subiremos las primeras! 📸")
        return
    if ss.indice >= len(fotos):
        ss.indice = 0
    foto = fotos[ss.indice]

    st.markdown(f'<div class="texto-foto">{esc(foto["texto"])}</div>', unsafe_allow_html=True)
    with st.container(key="carrusel"):
        b64 = cargar_imagen(foto["id"])
        st.image(base64.b64decode(b64), use_container_width=True)
        st.button("◀", key="flecha_izq", on_click=ir, args=(-1,))
        st.button("▶", key="flecha_der", on_click=ir, args=(1,))

    c1, c2, c3 = st.columns([1, 1, 1])
    ya = foto["id"] in ss.mis_corazones
    with c2:
        st.button(
            f"{'❤️' if ya else '🤍'} {foto.get('corazones', 0)}",
            key=f"corazon_{foto['id']}", on_click=dar_corazon, args=(foto,),
            use_container_width=True, disabled=ya,
        )
    st.caption(f"Foto {ss.indice + 1} de {len(fotos)} · desliza con el dedo o usa las flechas")

    # Deslizar con el dedo (móvil): detecta el gesto y pulsa las flechas
    components.html(
        """
<script>
(function(){
  const doc = window.parent.document;
  if (doc.__calamariSwipe) return;
  doc.__calamariSwipe = true;
  let x0 = null, y0 = null;
  doc.addEventListener('touchstart', e => {
    if (!e.target.closest('.st-key-carrusel')) { x0 = null; return; }
    x0 = e.touches[0].clientX; y0 = e.touches[0].clientY;
  }, {passive:true});
  doc.addEventListener('touchend', e => {
    if (x0 === null) return;
    const dx = e.changedTouches[0].clientX - x0;
    const dy = e.changedTouches[0].clientY - y0;
    x0 = null;
    if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy) * 1.5) {
      const sel = dx < 0 ? '.st-key-flecha_der button' : '.st-key-flecha_izq button';
      const b = doc.querySelector(sel);
      if (b) b.click();
    }
  }, {passive:true});
})();
</script>
""",
        height=0,
    )


# ──────────────────────────────────────────────────────────────
# PESTAÑA: INICIO
# ──────────────────────────────────────────────────────────────
with t_inicio:
    st.markdown(
        f'<div class="tarjeta"><h3>♟️ Club Chess Calamari</h3>'
        f'<p style="white-space:pre-line">{esc(A["bienvenida"])}</p>'
        f'<p>👩‍🏫 <b>Fundadora:</b> {esc(A["fundadora"])}</p></div>',
        unsafe_allow_html=True,
    )
    st.markdown("### 📸 Momentos del club")
    mostrar_carrusel()


# ──────────────────────────────────────────────────────────────
# PESTAÑA: CLASES
# ──────────────────────────────────────────────────────────────
with t_clases:
    st.markdown(
        f'<div class="tarjeta"><h3>📚 Clases y precios</h3>'
        f'<p style="white-space:pre-line">{esc(A["clases"])}</p></div>',
        unsafe_allow_html=True,
    )


# ──────────────────────────────────────────────────────────────
# PESTAÑA: CONTACTO
# ──────────────────────────────────────────────────────────────
with t_contacto:
    col_a, col_b = st.columns([3, 2])
    with col_a:
        st.markdown("### ✉️ Escríbenos")
        st.write("Pregunta por precios, horarios o lo que quieras saber. ¡Te respondemos pronto! 😊")
        with st.form("form_contacto", clear_on_submit=True):
            nombre = st.text_input("Tu nombre")
            contacto = st.text_input("Tu correo o WhatsApp (para responderte)")
            mensaje = st.text_area("Tu mensaje", height=140)
            enviado = st.form_submit_button("Enviar mensaje ✉️")
        if enviado:
            if not nombre.strip() or not mensaje.strip() or not contacto.strip():
                st.warning("Por favor completa tu nombre, tu contacto y el mensaje.")
            else:
                try:
                    DB.agregar_mensaje(nombre.strip(), contacto.strip(), mensaje.strip())
                    enviar_correo(nombre.strip(), contacto.strip(), mensaje.strip(), A["correo"])
                    st.success("¡Mensaje enviado! Pronto te contactaremos. ♟️")
                except Exception as e:
                    st.error(f"No se pudo enviar. Escríbenos a {A['correo']}. ({e})")
    with col_b:
        st.markdown('<div class="tarjeta"><h3>📍 Datos del club</h3>', unsafe_allow_html=True)
        st.write(f"📧 **{A['correo']}**")
        if A.get("telefono"):
            st.write(f"📞 **{A['telefono']}**")
        if A.get("whatsapp"):
            num = "".join(c for c in A["whatsapp"] if c.isdigit())
            st.link_button("💬 Escribir por WhatsApp", f"https://wa.me/{num}")
        st.write(f"📍 {A['direccion']}")
        st.write(f"⛪ {A['referencia']}")
        if A.get("maps_link"):
            st.link_button("🗺️ Abrir en Google Maps", A["maps_link"])
        st.markdown("</div>", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────
# PESTAÑA: MIEMBROS
# ──────────────────────────────────────────────────────────────
with t_miembros:
    st.markdown("### 🔒 Zona de miembros")
    clave_real = str(A.get("clave_miembros") or _secret("CLAVE_MIEMBROS", "miembros2026"))
    if not ss.miembro_ok:
        st.write("Esta zona es solo para quienes pertenecen al club. Pide la clave a tu profesora. 🔑")
        with st.form("form_miembros"):
            clave = st.text_input("Clave de miembros", type="password")
            ok = st.form_submit_button("Entrar")
        if ok:
            if clave == clave_real:
                ss.miembro_ok = True
                st.rerun()
            else:
                st.error("Clave incorrecta.")
    else:
        st.success("¡Bienvenido al grupo del club! 🏆")
        try:
            avisos = DB.avisos()
        except Exception as e:
            avisos = []
            st.error(f"No pude cargar los avisos: {e}")
        if not avisos:
            st.info("Todavía no hay avisos publicados.")
        for av in avisos:
            st.markdown(
                f'<div class="tarjeta"><h3>{esc(av["titulo"])}</h3>'
                f'<p style="white-space:pre-line">{esc(av["cuerpo"])}</p>'
                f'<small>📅 {fecha_bonita(av.get("creado"))}</small></div>',
                unsafe_allow_html=True,
            )
        if st.button("Salir de la zona de miembros"):
            ss.miembro_ok = False
            st.rerun()


# ──────────────────────────────────────────────────────────────
# PESTAÑA: ADMIN
# ──────────────────────────────────────────────────────────────
with t_admin:
    st.markdown("### ⚙️ Panel de administración")
    clave_admin = str(_secret("ADMIN_PASSWORD", ""))
    if not clave_admin:
        st.error(
            "Falta la contraseña de administrador. Agrega ADMIN_PASSWORD en "
            "Settings → Secrets de Streamlit."
        )
    elif not ss.admin_ok:
        with st.form("form_admin"):
            pw = st.text_input("Contraseña de administrador", type="password")
            ok = st.form_submit_button("Entrar")
        if ok:
            if pw == clave_admin:
                ss.admin_ok = True
                st.rerun()
            else:
                st.error("Contraseña incorrecta.")
    else:
        if not USA_SUPABASE:
            st.warning(
                "⚠️ Estás en **modo temporal**: los datos se guardan en el servidor de Streamlit y "
                "pueden borrarse cuando la app se reinicie. Conecta Supabase (gratis) siguiendo la guía "
                "para que todo quede guardado para siempre."
            )

        try:
            msgs = DB.mensajes()
            fotos_adm = DB.fotos()
        except Exception as e:
            st.error(f"Error leyendo la base de datos: {e}")
            st.stop()

        total_corazones = sum(int(f.get("corazones") or 0) for f in fotos_adm)
        sin_leer = sum(1 for m in msgs if not m.get("leido"))
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("👀 Visitas", A.get("visitas", 0))
        m2.metric("❤️ Corazones", total_corazones)
        m3.metric("📸 Fotos", len(fotos_adm))
        m4.metric("✉️ Sin leer", sin_leer)

        p_msg, p_fotos, p_avisos, p_datos, p_colores = st.tabs(
            ["✉️ Mensajes", "📸 Fotos", "📢 Avisos miembros", "📝 Datos y textos", "🎨 Colores"]
        )

        # --- Mensajes
        with p_msg:
            if not msgs:
                st.info("Aún no hay mensajes.")
            for m in msgs:
                icono = "✅" if m.get("leido") else "🆕"
                with st.expander(f"{icono} {m['nombre']} — {fecha_bonita(m.get('creado'))}"):
                    st.write(m["mensaje"])
                    st.caption(f"Responder a: {m['contacto']}")
                    c1, c2 = st.columns(2)
                    if c1.button(
                        "Marcar como leído" if not m.get("leido") else "Marcar como no leído",
                        key=f"leido_{m['id']}",
                    ):
                        DB.marcar_leido(m["id"], not m.get("leido"))
                        st.rerun()
                    if c2.button("🗑️ Borrar", key=f"delmsg_{m['id']}"):
                        DB.borrar_mensaje(m["id"])
                        st.rerun()

        # --- Fotos
        with p_fotos:
            st.markdown("#### ➕ Subir fotos nuevas")
            with st.form("form_subir", clear_on_submit=True):
                archivos = st.file_uploader(
                    "Elige una o varias fotos", type=["jpg", "jpeg", "png", "webp"],
                    accept_multiple_files=True)
                texto_nuevo = st.text_area(
                    "Texto que aparecerá arriba de la foto (puedes usar emojis 🎉♟️🏆)",
                    placeholder="Ej: 🏆 ¡Felicitaciones a los campeones del torneo!")
                subir = st.form_submit_button("Publicar 📸")
            if subir:
                if not archivos:
                    st.warning("Elige al menos una foto.")
                else:
                    try:
                        for ar in archivos:
                            DB.agregar_foto(texto_nuevo.strip(), preparar_imagen(ar))
                        limpiar_cache()
                        st.success("¡Foto(s) publicada(s)!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"No se pudo subir: {e}")

            st.markdown("#### ✏️ Editar o borrar fotos")
            if not fotos_adm:
                st.info("No hay fotos publicadas.")
            for f in fotos_adm:
                with st.container(border=True):
                    ci, ct = st.columns([1, 2])
                    with ci:
                        st.image(base64.b64decode(cargar_imagen(f["id"])), use_container_width=True)
                        st.metric("❤️ Corazones", int(f.get("corazones") or 0))
                    with ct:
                        nuevo = st.text_area(
                            "Texto de la foto", value=f["texto"] or "", key=f"txt_{f['id']}", height=100)
                        b1, b2 = st.columns(2)
                        if b1.button("💾 Guardar texto", key=f"save_{f['id']}"):
                            DB.editar_foto(f["id"], nuevo.strip())
                            limpiar_cache()
                            st.success("Texto actualizado.")
                            st.rerun()
                        if b2.button("🗑️ Eliminar foto", key=f"del_{f['id']}"):
                            DB.borrar_foto(f["id"])
                            ss.indice = 0
                            limpiar_cache()
                            st.rerun()

        # --- Avisos
        with p_avisos:
            st.markdown("#### 📢 Publicar aviso para miembros")
            with st.form("form_aviso", clear_on_submit=True):
                titulo = st.text_input("Título", placeholder="🏆 Torneo de fin de mes")
                cuerpo = st.text_area("Información", placeholder="Fecha, hora, lugar, inscripción…")
                pub = st.form_submit_button("Publicar aviso")
            if pub:
                if titulo.strip() and cuerpo.strip():
                    DB.agregar_aviso(titulo.strip(), cuerpo.strip())
                    st.success("Aviso publicado.")
                    st.rerun()
                else:
                    st.warning("Escribe título e información.")
            for av in DB.avisos():
                with st.container(border=True):
                    st.write(f"**{av['titulo']}** — {fecha_bonita(av.get('creado'))}")
                    st.write(av["cuerpo"])
                    if st.button("🗑️ Borrar aviso", key=f"delav_{av['id']}"):
                        DB.borrar_aviso(av["id"])
                        st.rerun()

        # --- Datos y textos
        with p_datos:
            with st.form("form_datos"):
                st.markdown("#### 📞 Contacto")
                correo = st.text_input("Correo (Gmail)", A["correo"])
                telefono = st.text_input("Teléfono", A.get("telefono", ""))
                whatsapp = st.text_input(
                    "WhatsApp (con indicativo, ej: 573001234567)", A.get("whatsapp", ""))
                st.markdown("#### 📍 Ubicación")
                direccion = st.text_area("Dirección", A["direccion"], height=80)
                referencia = st.text_input("Referencia", A["referencia"])
                maps_link = st.text_input("Enlace de Google Maps", A["maps_link"])
                st.markdown("#### 📝 Textos de la página")
                fundadora = st.text_input("Fundadora", A["fundadora"])
                lema = st.text_input("Frase principal", A["lema"])
                bienvenida = st.text_area("Texto de bienvenida (Inicio)", A["bienvenida"], height=140)
                clases = st.text_area("Clases y precios", A["clases"], height=180)
                st.markdown("#### 🔑 Clave de la zona de miembros")
                clave_m = st.text_input(
                    "Clave de miembros", A.get("clave_miembros") or "miembros2026")
                guardar = st.form_submit_button("💾 Guardar todo")
            if guardar:
                try:
                    for k, v in {
                        "correo": correo, "telefono": telefono, "whatsapp": whatsapp,
                        "direccion": direccion, "referencia": referencia, "maps_link": maps_link,
                        "fundadora": fundadora, "lema": lema, "bienvenida": bienvenida,
                        "clases": clases, "clave_miembros": clave_m,
                    }.items():
                        DB.guardar_ajuste(k, v)
                    limpiar_cache()
                    st.success("¡Datos guardados!")
                    st.rerun()
                except Exception as e:
                    st.error(f"No se pudo guardar: {e}")

        # --- Colores
        with p_colores:
            c1, c2 = st.columns(2)
            nuevo_fondo = c1.color_picker("🎨 Color de fondo de la página", A["color_fondo"])
            nuevo_azul = c2.color_picker("🔷 Color principal (botones, bordes)", A["color_principal"])
            st.caption("El dibujo de piezas de ajedrez de fondo se mezcla con el color que elijas.")
            if st.button("💾 Guardar colores"):
                DB.guardar_ajuste("color_fondo", nuevo_fondo)
                DB.guardar_ajuste("color_principal", nuevo_azul)
                limpiar_cache()
                st.rerun()
            if st.button("↩️ Volver a los colores originales"):
                DB.guardar_ajuste("color_fondo", DEFAULTS["color_fondo"])
                DB.guardar_ajuste("color_principal", DEFAULTS["color_principal"])
                limpiar_cache()
                st.rerun()

        st.divider()
        if st.button("Cerrar sesión de administrador"):
            ss.admin_ok = False
            st.rerun()


# ──────────────────────────────────────────────────────────────
# PIE DE PÁGINA
# ──────────────────────────────────────────────────────────────
st.markdown(
    f"""
<div class="pie">
  <div class="balcon">{BALCON_SVG}</div>
  <div class="info">
    <b>Club Chess Calamari</b> ♟️<br>
    📍 {esc(A['direccion'])}<br>
    📧 <a href="mailto:{esc(A['correo'])}">{esc(A['correo'])}</a>
    · <a href="{esc(A['maps_link'])}" target="_blank">Ver en Google Maps</a>
  </div>
  <div class="balcon">{BALCON_SVG}</div>
</div>
""",
    unsafe_allow_html=True,
)

# Mapa incrustado
direccion_mapa = quote("Parque El Recreo, Cartagena de Indias, Colombia")
components.html(
    f'<iframe src="https://maps.google.com/maps?q={direccion_mapa}&output=embed" '
    'width="100%" height="260" style="border:0;border-radius:12px;" loading="lazy"></iframe>',
    height=275,
)
