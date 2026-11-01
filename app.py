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
import hashlib
import hmac
import html
import io
import os
import re
import secrets as pysecrets
import smtplib
import sqlite3
import string
from datetime import datetime, timedelta
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
    "instagram": "",
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
        h = {"apikey": SUPA_KEY, "Content-Type": "application/json"}
        # Las llaves antiguas (service_role) son JWT y van también en Authorization.
        # Las nuevas (sb_secret_...) solo van en "apikey".
        if SUPA_KEY.startswith("eyJ"):
            h["Authorization"] = f"Bearer {SUPA_KEY}"
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
            CREATE TABLE IF NOT EXISTS miembros(
                id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT UNIQUE, correo TEXT,
                clave_hash TEXT, estado TEXT DEFAULT 'pendiente', creado TEXT,
                codigo_hash TEXT, codigo_exp TEXT, codigo_intentos INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS publicaciones(
                id INTEGER PRIMARY KEY AUTOINCREMENT, autor TEXT, es_admin INTEGER DEFAULT 0,
                texto TEXT, imagen TEXT, tiene_foto INTEGER DEFAULT 0, creada TEXT);
            CREATE TABLE IF NOT EXISTS reacciones(
                id INTEGER PRIMARY KEY AUTOINCREMENT, pub_id INTEGER, usuario TEXT, tipo TEXT,
                UNIQUE(pub_id, usuario));
            """
        )
        return con

    # ---------- Ajustes ----------
    def ajustes(self):
        if USA_SUPABASE:
            filas = self._rest(
                "GET", "ajustes", {"select": "clave,valor", "clave": "neq.banner_b64"})
        else:
            con = self._db()
            filas = [dict(f) for f in con.execute(
                "SELECT clave, valor FROM ajustes WHERE clave != 'banner_b64'")]
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

    # ---------- Un ajuste suelto (p. ej. el banner, que es pesado) ----------
    def ajuste(self, clave):
        if USA_SUPABASE:
            f = self._rest("GET", "ajustes", {"select": "valor", "clave": f"eq.{clave}"})
            return f[0]["valor"] if f else ""
        con = self._db()
        f = con.execute("SELECT valor FROM ajustes WHERE clave=?", (clave,)).fetchone()
        con.close()
        return f["valor"] if f else ""

    def borrar_ajuste(self, clave):
        if USA_SUPABASE:
            self._rest("DELETE", "ajustes", {"clave": f"eq.{clave}"})
        else:
            con = self._db()
            con.execute("DELETE FROM ajustes WHERE clave=?", (clave,))
            con.commit()
            con.close()

    # ---------- Miembros ----------
    def miembros(self):
        """Lista SIN las claves cifradas."""
        if USA_SUPABASE:
            return self._rest(
                "GET", "miembros",
                {"select": "id,usuario,correo,estado,creado", "order": "id.asc"})
        con = self._db()
        filas = [dict(f) for f in con.execute(
            "SELECT id,usuario,correo,estado,creado FROM miembros ORDER BY id")]
        con.close()
        return filas

    def miembro(self, usuario):
        if USA_SUPABASE:
            f = self._rest("GET", "miembros", {"select": "*", "usuario": f"eq.{usuario}"})
            return f[0] if f else None
        con = self._db()
        f = con.execute("SELECT * FROM miembros WHERE usuario=?", (usuario,)).fetchone()
        con.close()
        return dict(f) if f else None

    def crear_miembro(self, usuario, correo, clave_hash):
        ahora = datetime.utcnow().isoformat()
        if USA_SUPABASE:
            self._rest("POST", "miembros", json=[{
                "usuario": usuario, "correo": correo, "clave_hash": clave_hash,
                "estado": "pendiente", "creado": ahora}])
        else:
            con = self._db()
            con.execute(
                "INSERT INTO miembros(usuario,correo,clave_hash,estado,creado) "
                "VALUES (?,?,?,'pendiente',?)", (usuario, correo, clave_hash, ahora))
            con.commit()
            con.close()

    def actualizar_miembro(self, usuario, **campos):
        if USA_SUPABASE:
            self._rest("PATCH", "miembros", {"usuario": f"eq.{usuario}"}, campos)
        else:
            con = self._db()
            cols = ", ".join(f"{k}=?" for k in campos)
            con.execute(f"UPDATE miembros SET {cols} WHERE usuario=?", (*campos.values(), usuario))
            con.commit()
            con.close()

    def borrar_miembro(self, usuario):
        if USA_SUPABASE:
            self._rest("DELETE", "miembros", {"usuario": f"eq.{usuario}"})
        else:
            con = self._db()
            con.execute("DELETE FROM miembros WHERE usuario=?", (usuario,))
            con.commit()
            con.close()

    # ---------- Publicaciones del grupo ----------
    def publicaciones(self, limite=20):
        if USA_SUPABASE:
            return self._rest("GET", "publicaciones", {
                "select": "id,autor,es_admin,texto,creada,tiene_foto",
                "order": "id.desc", "limit": limite})
        con = self._db()
        filas = [dict(f) for f in con.execute(
            "SELECT id,autor,es_admin,texto,creada,tiene_foto FROM publicaciones "
            "ORDER BY id DESC LIMIT ?", (limite,))]
        con.close()
        return filas

    def imagen_pub(self, pid):
        if USA_SUPABASE:
            f = self._rest("GET", "publicaciones", {"select": "imagen", "id": f"eq.{pid}"})
            return (f[0]["imagen"] or "") if f else ""
        con = self._db()
        f = con.execute("SELECT imagen FROM publicaciones WHERE id=?", (pid,)).fetchone()
        con.close()
        return (f["imagen"] or "") if f else ""

    def crear_pub(self, autor, es_admin, texto, imagen_b64=None):
        ahora = datetime.utcnow().isoformat()
        tiene = bool(imagen_b64)
        if USA_SUPABASE:
            self._rest("POST", "publicaciones", json=[{
                "autor": autor, "es_admin": bool(es_admin), "texto": texto,
                "imagen": imagen_b64, "tiene_foto": tiene, "creada": ahora}])
        else:
            con = self._db()
            con.execute(
                "INSERT INTO publicaciones(autor,es_admin,texto,imagen,tiene_foto,creada) "
                "VALUES (?,?,?,?,?,?)",
                (autor, 1 if es_admin else 0, texto, imagen_b64, 1 if tiene else 0, ahora))
            con.commit()
            con.close()

    def borrar_pub(self, pid):
        if USA_SUPABASE:
            self._rest("DELETE", "publicaciones", {"id": f"eq.{pid}"})
        else:
            con = self._db()
            con.execute("DELETE FROM reacciones WHERE pub_id=?", (pid,))
            con.execute("DELETE FROM publicaciones WHERE id=?", (pid,))
            con.commit()
            con.close()

    def reacciones(self, ids):
        if not ids:
            return []
        if USA_SUPABASE:
            lista = ",".join(str(int(i)) for i in ids)
            return self._rest("GET", "reacciones", {
                "select": "pub_id,usuario,tipo", "pub_id": f"in.({lista})"})
        con = self._db()
        marcas = ",".join("?" for _ in ids)
        filas = [dict(f) for f in con.execute(
            f"SELECT pub_id,usuario,tipo FROM reacciones WHERE pub_id IN ({marcas})", list(ids))]
        con.close()
        return filas

    def poner_reaccion(self, pid, usuario, tipo):
        if USA_SUPABASE:
            self._rest(
                "POST", "reacciones", {"on_conflict": "pub_id,usuario"},
                [{"pub_id": pid, "usuario": usuario, "tipo": tipo}],
                prefer="resolution=merge-duplicates")
        else:
            con = self._db()
            con.execute(
                "INSERT INTO reacciones(pub_id,usuario,tipo) VALUES (?,?,?) "
                "ON CONFLICT(pub_id,usuario) DO UPDATE SET tipo=excluded.tipo",
                (pid, usuario, tipo))
            con.commit()
            con.close()

    def quitar_reaccion(self, pid, usuario):
        if USA_SUPABASE:
            self._rest("DELETE", "reacciones", {"pub_id": f"eq.{pid}", "usuario": f"eq.{usuario}"})
        else:
            con = self._db()
            con.execute("DELETE FROM reacciones WHERE pub_id=? AND usuario=?", (pid, usuario))
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


@st.cache_data(ttl=300, show_spinner=False)
def cargar_banner_db():
    return DB.ajuste("banner_b64")


@st.cache_data(ttl=3600, max_entries=30, show_spinner=False)
def cargar_img_pub(pid):
    return DB.imagen_pub(pid)


def limpiar_cache():
    cargar_banner_db.clear()
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


def preparar_imagen(archivo_subido, tam=(1200, 900)):
    """Recorta a rectángulo 4:3 (horizontal), cuidando que se vea la escena, y comprime."""
    im = Image.open(archivo_subido)
    im = ImageOps.exif_transpose(im).convert("RGB")
    im = ImageOps.fit(im, tam, Image.LANCZOS, centering=(0.5, 0.4))
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


def enviar_mail(destino, asunto, cuerpo):
    """Envía un correo desde tu Gmail (requiere GMAIL_APP_PASSWORD en Secrets)."""
    clave = str(_secret("GMAIL_APP_PASSWORD"))
    origen = str(_secret("GMAIL_USER", "clubchesscalamari@gmail.com"))
    if not clave or not destino:
        return False
    try:
        m = EmailMessage()
        m["Subject"] = asunto
        m["From"] = origen
        m["To"] = destino
        m.set_content(cuerpo)
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as srv:
            srv.login(origen, clave)
            srv.send_message(m)
        return True
    except Exception:
        return False


def enviar_correo(nombre, contacto, mensaje, destino):
    """Aviso a tu Gmail cuando alguien escribe desde Contacto."""
    return enviar_mail(
        destino, f"♟️ Nuevo mensaje en la página — {nombre}",
        f"Nombre: {nombre}\nContacto: {contacto}\n\n{mensaje}")


def preparar_banner(archivo_subido):
    """Imagen de arriba: recorta a formato panorámico y comprime."""
    im = Image.open(archivo_subido)
    im = ImageOps.exif_transpose(im).convert("RGB")
    im = ImageOps.fit(im, (1600, 680), Image.LANCZOS, centering=(0.5, 0.5))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85, optimize=True)
    return base64.b64encode(buf.getvalue()).decode()


# ── Contraseñas: se guardan CIFRADAS (nadie, ni tú, puede leerlas) ──
def hash_clave(clave):
    sal = pysecrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), bytes.fromhex(sal), 200_000).hex()
    return f"{sal}${h}"


def verificar_clave(clave, guardado):
    try:
        sal, h = str(guardado).split("$")
        calc = hashlib.pbkdf2_hmac(
            "sha256", clave.encode("utf-8"), bytes.fromhex(sal), 200_000).hex()
        return hmac.compare_digest(calc, h)
    except Exception:
        return False


def validar_clave(c):
    """Devuelve un mensaje de error, o None si la contraseña es válida."""
    if len(c) < 8:
        return "La contraseña debe tener mínimo 8 caracteres."
    if not re.search(r"[a-z]", c):
        return "La contraseña debe tener al menos una letra minúscula."
    if not re.search(r"[A-Z]", c):
        return "La contraseña debe tener al menos una letra MAYÚSCULA."
    if not re.search(r"\d", c):
        return "La contraseña debe tener al menos un número."
    return None


def clave_temporal():
    alfabeto = string.ascii_letters.replace("l", "").replace("O", "") + "23456789"
    while True:
        c = "".join(pysecrets.choice(alfabeto) for _ in range(10))
        if validar_clave(c) is None:
            return c


def clave_admin_ok(pw):
    """La contraseña nueva (si la cambiaste) manda; si no, la de Secrets."""
    guardada = A.get("admin_hash", "")
    if guardada:
        return verificar_clave(pw, guardada)
    base = str(_secret("ADMIN_PASSWORD", ""))
    return bool(base) and hmac.compare_digest(pw.encode("utf-8"), base.encode("utf-8"))


def dias_desde(iso):
    try:
        return (datetime.utcnow() - datetime.fromisoformat(str(iso)[:26])).days
    except Exception:
        return 0


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
ss.setdefault("socio", None)          # usuario del miembro con sesión iniciada
ss.setdefault("vista_m", "login")
ss.setdefault("fallos_login", 0)
ss.setdefault("fallos_admin", 0)
ss.setdefault("fallos_pin", 0)
ss.setdefault("limite_pubs", 20)
ss.setdefault("confirmar_del", None)
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

/* Reacciones del grupo siempre en una fila (también en celular) */
[class*="st-key-r_"] [data-testid="stHorizontalBlock"] {{
  flex-direction: row !important; flex-wrap: nowrap !important; gap: .4rem; }}
[class*="st-key-r_"] [data-testid="stColumn"], [class*="st-key-r_"] [data-testid="column"] {{
  min-width: 0 !important; flex: 1 1 0 !important; width: auto !important; }}

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
try:
    banner = cargar_banner_db() or archivo_b64("banner.jpg")
except Exception:
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
# ZONA DE MIEMBROS (inscripción, inicio de sesión y grupo)
# ──────────────────────────────────────────────────────────────
NOMBRE_ADMIN = "👑 Administradora"
MSG_ESPERA = (
    "✅ ¡Solicitud enviada! Espera hasta 5 días a que el administrador autorice tu admisión. "
    "Cuando te acepten, podrás iniciar sesión con tu usuario y contraseña."
)


def ir_vista(v):
    ss.vista_m = v


def solicitar_codigo(usuario):
    """Envía un código de 6 dígitos al correo con el que el miembro se inscribió."""
    m = DB.miembro(usuario)
    if not m or m.get("estado") != "aprobado":
        return
    ahora = datetime.utcnow()
    if m.get("codigo_exp"):
        try:  # máximo un código cada 2 minutos
            if datetime.fromisoformat(m["codigo_exp"]) - timedelta(minutes=28) > ahora:
                return
        except Exception:
            pass
    codigo = f"{pysecrets.randbelow(1_000_000):06d}"
    DB.actualizar_miembro(
        usuario, codigo_hash=hash_clave(codigo),
        codigo_exp=(ahora + timedelta(minutes=30)).isoformat(), codigo_intentos=0)
    enviado = enviar_mail(
        m["correo"], "♟️ Club Chess Calamari — tu código para cambiar la contraseña",
        f"Hola {usuario},\n\nTu código es: {codigo}\n\n"
        "Vale por 30 minutos. Escríbelo en la página, en Miembros → ¿Olvidaste tu contraseña?\n"
        "Si no fuiste tú, ignora este mensaje.\n\nClub Chess Calamari ♟️")
    if not enviado:
        DB.agregar_mensaje(
            usuario, m["correo"],
            "Pidió recuperar su contraseña, pero el envío de correos no está activado. "
            "Entra a Admin → Miembros y usa «Restablecer contraseña».")


def usar_codigo(usuario, codigo, nueva):
    m = DB.miembro(usuario)
    if not m or not m.get("codigo_hash") or not m.get("codigo_exp"):
        return False
    try:
        vence = datetime.fromisoformat(m["codigo_exp"])
    except Exception:
        return False
    if vence < datetime.utcnow():
        return False
    if not verificar_clave(codigo.strip(), m["codigo_hash"]):
        n = int(m.get("codigo_intentos") or 0) + 1
        if n >= 5:  # tras 5 errores el código se anula
            DB.actualizar_miembro(usuario, codigo_hash=None, codigo_exp=None, codigo_intentos=0)
        else:
            DB.actualizar_miembro(usuario, codigo_intentos=n)
        return False
    DB.actualizar_miembro(
        usuario, clave_hash=hash_clave(nueva), codigo_hash=None, codigo_exp=None,
        codigo_intentos=0)
    return True


def vista_login():
    st.markdown("#### 🔑 Iniciar sesión")
    with st.form("f_login"):
        u = st.text_input("Usuario")
        p = st.text_input("Contraseña", type="password")
        entrar = st.form_submit_button("Entrar")
    if entrar:
        if ss.fallos_login >= 6:
            st.error("Demasiados intentos. Espera un rato y vuelve a intentarlo.")
        else:
            try:
                m = DB.miembro(u.strip().lower())
            except Exception as e:
                st.error(f"No pude conectar: {e}")
                return
            if not m or not verificar_clave(p, m.get("clave_hash", "")):
                ss.fallos_login += 1
                st.error("Usuario o contraseña incorrectos.")
            elif m["estado"] == "pendiente":
                st.info("⏳ Tu solicitud sigue en revisión. El administrador te responderá en un plazo de hasta 5 días.")
            elif m["estado"] == "rechazado":
                st.error("Tu solicitud no fue aprobada. Si crees que es un error, escribe al administrador aquí abajo.")
            else:
                ss.socio = m["usuario"]
                ss.fallos_login = 0
                st.rerun()
    st.button("¿Olvidaste tu contraseña?", key="b_olvide", on_click=ir_vista, args=("olvide",))


def vista_inscribir():
    st.markdown("#### 📝 Solicitud de inscripción")
    st.caption(
        "Usuario: de 4 a 20 caracteres (letras minúsculas, números o guion bajo _). "
        "Contraseña: mínimo 8 caracteres, con una mayúscula, una minúscula y un número."
    )
    with st.form("f_insc"):
        u = st.text_input("Usuario")
        correo = st.text_input("Correo (para recuperar tu contraseña)")
        p1 = st.text_input("Contraseña", type="password")
        p2 = st.text_input("Repite la contraseña", type="password")
        acepto = st.checkbox(
            "Acepto que el club guarde mi usuario y correo para gestionar mi membresía. "
            "Si soy menor de edad, mi acudiente me autoriza."
        )
        enviar = st.form_submit_button("Enviar solicitud")
    if not enviar:
        return
    u = u.strip().lower()
    correo = correo.strip().lower()
    if not re.fullmatch(r"[a-z0-9_]{4,20}", u):
        st.error("El usuario debe tener de 4 a 20 caracteres: letras minúsculas, números o _.")
    elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", correo):
        st.error("Escribe un correo válido.")
    elif validar_clave(p1):
        st.error(validar_clave(p1))
    elif p1 != p2:
        st.error("Las contraseñas no coinciden.")
    elif not acepto:
        st.error("Debes aceptar el uso de tus datos para inscribirte.")
    else:
        try:
            existentes = DB.miembros()
            if any(m["usuario"] == u for m in existentes):
                st.error("Ese usuario ya existe. Elige otro.")
                return
            if any(m["correo"].lower() == correo and m["estado"] != "rechazado" for m in existentes):
                st.error("Ese correo ya tiene una solicitud o una cuenta.")
                return
            DB.crear_miembro(u, correo, hash_clave(p1))
            enviar_mail(
                A["correo"], f"♟️ Nueva solicitud de inscripción — {u}",
                f"El usuario «{u}» ({correo}) pidió entrar a la zona de miembros.\n"
                "Revísalo en la página: Admin → Miembros.")
            st.success(MSG_ESPERA)
        except Exception as e:
            st.error(f"No se pudo enviar la solicitud: {e}")


def vista_olvide():
    st.markdown("#### 🔁 Recuperar mi contraseña")
    st.caption("Escribe tu usuario y te enviamos un código al correo con el que te inscribiste.")
    with st.form("f_cod1"):
        u = st.text_input("Tu usuario")
        env = st.form_submit_button("Enviar código a mi correo")
    if env and u.strip():
        try:
            solicitar_codigo(u.strip().lower())
        except Exception:
            pass
        st.success(
            "Si el usuario existe y ya fue aprobado, enviamos un código a su correo "
            "(revisa también spam). Vale por 30 minutos. Si no llega, escribe al administrador."
        )
    st.markdown("**Ya tengo mi código**")
    with st.form("f_cod2"):
        u2 = st.text_input("Usuario", key="u_cod2")
        cod = st.text_input("Código de 6 dígitos")
        n1 = st.text_input("Nueva contraseña", type="password", key="n1_cod")
        n2 = st.text_input("Repite la nueva contraseña", type="password", key="n2_cod")
        ok = st.form_submit_button("Cambiar mi contraseña")
    if ok:
        if validar_clave(n1):
            st.error(validar_clave(n1))
        elif n1 != n2:
            st.error("Las contraseñas no coinciden.")
        else:
            try:
                if usar_codigo(u2.strip().lower(), cod, n1):
                    st.success("¡Listo! Ya puedes iniciar sesión con tu nueva contraseña.")
                else:
                    st.error("Código incorrecto o vencido. Pide uno nuevo.")
            except Exception as e:
                st.error(f"No se pudo cambiar: {e}")
    st.button("← Volver a iniciar sesión", key="b_volver", on_click=ir_vista, args=("login",))


def pantalla_acceso():
    c1, c2 = st.columns(2)
    if c1.button("🔑 Iniciar sesión", key="b_login", use_container_width=True):
        ss.vista_m = "login"
    if c2.button("📝 Inscribirme", key="b_insc", use_container_width=True):
        ss.vista_m = "inscribir"
    if ss.vista_m == "inscribir":
        vista_inscribir()
    elif ss.vista_m == "olvide":
        vista_olvide()
    else:
        vista_login()
    st.divider()
    st.markdown("#### ✉️ Escribir algo al administrador")
    with st.form("f_admin_msg", clear_on_submit=True):
        nom = st.text_input("Tu nombre o usuario")
        cont = st.text_input("Tu correo o WhatsApp (para responderte)")
        msg = st.text_area("Mensaje", height=100)
        env = st.form_submit_button("Enviar al administrador")
    if env:
        if nom.strip() and cont.strip() and msg.strip():
            try:
                DB.agregar_mensaje(nom.strip(), cont.strip(), msg.strip())
                enviar_correo(nom.strip(), cont.strip(), msg.strip(), A["correo"])
                st.success("¡Mensaje enviado! El administrador te responderá pronto.")
            except Exception as e:
                st.error(f"No se pudo enviar: {e}")
        else:
            st.warning("Completa tu nombre, tu contacto y el mensaje.")


def reaccionar(pid, usuario, tipo, actual):
    try:
        if actual == tipo:
            DB.quitar_reaccion(pid, usuario)
        else:
            DB.poner_reaccion(pid, usuario, tipo)
    except Exception:
        st.toast("No se pudo guardar tu reacción.")


def borrar_publicacion(pid):
    try:
        DB.borrar_pub(pid)
        cargar_img_pub.clear()
    except Exception:
        st.toast("No se pudo borrar.")


def mas_publicaciones():
    ss.limite_pubs += 20


def cambiar_clave_miembro(usuario):
    with st.expander("🔐 Cambiar mi contraseña"):
        with st.form("f_cambio_m", clear_on_submit=True):
            actual = st.text_input("Contraseña actual", type="password")
            n1 = st.text_input("Nueva contraseña", type="password")
            n2 = st.text_input("Repite la nueva contraseña", type="password")
            ok = st.form_submit_button("Guardar contraseña")
        if ok:
            m = DB.miembro(usuario)
            if not m or not verificar_clave(actual, m["clave_hash"]):
                st.error("La contraseña actual no es correcta.")
            elif validar_clave(n1):
                st.error(validar_clave(n1))
            elif n1 != n2:
                st.error("Las contraseñas no coinciden.")
            else:
                DB.actualizar_miembro(usuario, clave_hash=hash_clave(n1))
                st.success("Contraseña actualizada.")


def mostrar_grupo(yo, soy_admin):
    if ss.socio:
        a, b = st.columns([3, 1])
        a.success(f"¡Hola, {yo}! Bienvenido al grupo del club 🏆")
        if b.button("Salir", key="b_salir"):
            ss.socio = None
            st.rerun()
        cambiar_clave_miembro(ss.socio)
    else:
        st.success("Estás viendo el grupo como administradora 👑 (puedes borrar publicaciones).")

    # Avisos importantes (los publica la administradora desde Admin → Avisos)
    try:
        for av in DB.avisos():
            st.markdown(
                f'<div class="tarjeta"><h3>📢 {esc(av["titulo"])}</h3>'
                f'<p style="white-space:pre-line">{esc(av["cuerpo"])}</p>'
                f'<small>📅 {fecha_bonita(av.get("creado"))}</small></div>',
                unsafe_allow_html=True)
    except Exception:
        pass

    st.markdown("#### 💬 Conversación del grupo")
    with st.form("f_pub", clear_on_submit=True):
        texto = st.text_area("Escribe algo para el grupo (puedes usar emojis 😀♟️)", height=90, max_chars=1000)
        foto = st.file_uploader("Foto (opcional)", type=["jpg", "jpeg", "png", "webp"])
        publicar = st.form_submit_button("Publicar 💬")
    if publicar:
        if not texto.strip() and not foto:
            st.warning("Escribe algo o elige una foto.")
        else:
            try:
                img = preparar_imagen(foto, (1000, 750)) if foto else None
                DB.crear_pub(yo, soy_admin, texto.strip(), img)
                st.rerun()
            except Exception as e:
                st.error(f"No se pudo publicar: {e}")

    if st.button("🔄 Actualizar conversación", key="b_act"):
        st.rerun()
    try:
        pubs = DB.publicaciones(ss.limite_pubs)
        reacs = DB.reacciones([p["id"] for p in pubs])
    except Exception as e:
        st.error(f"No pude cargar la conversación: {e}")
        return
    if not pubs:
        st.info("Todavía no hay publicaciones. ¡Escribe la primera! ✨")
    for p in pubs:
        de_esta = [r for r in reacs if r["pub_id"] == p["id"]]
        n_like = sum(1 for r in de_esta if r["tipo"] == "like")
        n_dis = sum(1 for r in de_esta if r["tipo"] == "dislike")
        mia = next((r["tipo"] for r in de_esta if r["usuario"] == yo), None)
        with st.container(border=True):
            marca = "👑 " if p.get("es_admin") else ""
            st.markdown(
                f"**{marca}{esc(p['autor'])}** · <small>{fecha_bonita(p.get('creada'))}</small>",
                unsafe_allow_html=True)
            if p.get("texto"):
                st.markdown(
                    f'<div style="white-space:pre-wrap">{esc(p["texto"])}</div>',
                    unsafe_allow_html=True)
            if p.get("tiene_foto"):
                try:
                    st.image(base64.b64decode(cargar_img_pub(p["id"])), use_container_width=True)
                except Exception:
                    st.caption("(no se pudo cargar la foto)")
            with st.container(key=f"r_{p['id']}"):
                c1, c2, c3 = st.columns(3)
                c1.button(
                    f"👍 {n_like}", key=f"lk_{p['id']}", on_click=reaccionar,
                    args=(p["id"], yo, "like", mia),
                    type="primary" if mia == "like" else "secondary", use_container_width=True)
                c2.button(
                    f"👎 {n_dis}", key=f"dl_{p['id']}", on_click=reaccionar,
                    args=(p["id"], yo, "dislike", mia),
                    type="primary" if mia == "dislike" else "secondary", use_container_width=True)
                if soy_admin or (p["autor"] == yo and not p.get("es_admin")):
                    c3.button(
                        "🗑️", key=f"dp_{p['id']}", on_click=borrar_publicacion,
                        args=(p["id"],), use_container_width=True)
    if len(pubs) >= ss.limite_pubs:
        st.button("Ver publicaciones anteriores", key="b_mas", on_click=mas_publicaciones)


def zona_miembros():
    st.markdown("### 🔒 Zona de miembros")
    if ss.admin_ok:
        mostrar_grupo(NOMBRE_ADMIN, True)
        return
    if ss.socio:
        try:  # si te eliminaron o rechazaron mientras estaba conectado
            m = DB.miembro(ss.socio)
        except Exception:
            m = None
        if not m or m.get("estado") != "aprobado":
            ss.socio = None
        else:
            mostrar_grupo(ss.socio, False)
            return
    pantalla_acceso()


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
        if A.get("instagram"):
            ig = A["instagram"].strip()
            url_ig = ig if ig.startswith("http") else f"https://instagram.com/{ig.lstrip('@')}"
            st.link_button("📸 Instagram", url_ig)
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
    zona_miembros()


# ──────────────────────────────────────────────────────────────
# PESTAÑA: ADMIN
# ──────────────────────────────────────────────────────────────
with t_admin:
    st.markdown("### ⚙️ Panel de administración")
    clave_admin = str(_secret("ADMIN_PASSWORD", ""))
    if not clave_admin and not A.get("admin_hash"):
        st.error(
            "Falta la contraseña de administrador. Agrega ADMIN_PASSWORD en "
            "Settings → Secrets de Streamlit."
        )
    elif not ss.admin_ok:
        with st.form("form_admin"):
            pw = st.text_input("Contraseña de administrador", type="password")
            ok = st.form_submit_button("Entrar")
        if ok:
            if ss.fallos_admin >= 6:
                st.error("Demasiados intentos. Espera un rato y vuelve a intentarlo.")
            elif clave_admin_ok(pw):
                ss.admin_ok = True
                ss.fallos_admin = 0
                st.rerun()
            else:
                ss.fallos_admin += 1
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

        try:
            lista_m = DB.miembros()
            falta_sql = False
        except Exception:
            lista_m = []
            falta_sql = True

        total_corazones = sum(int(f.get("corazones") or 0) for f in fotos_adm)
        sin_leer = sum(1 for m in msgs if not m.get("leido"))
        n_pend = sum(1 for m in lista_m if m["estado"] == "pendiente")
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("👀 Visitas", A.get("visitas", 0))
        m2.metric("❤️ Corazones", total_corazones)
        m3.metric("📸 Fotos", len(fotos_adm))
        m4.metric("✉️ Sin leer", sin_leer)
        m5.metric("⏳ Por aprobar", n_pend)

        p_msg, p_miem, p_fotos, p_avisos, p_datos, p_colores, p_cuenta = st.tabs(
            ["✉️ Mensajes", "👥 Miembros", "📸 Fotos", "📢 Avisos", "📝 Datos y textos",
             "🎨 Colores e imagen", "🔐 Mi cuenta"]
        )

        # --- Miembros (aprobar, rechazar, eliminar, restablecer)
        with p_miem:
            if falta_sql:
                st.error(
                    "Falta crear las tablas de miembros. En Supabase → SQL Editor, pega y ejecuta "
                    "el archivo supabase_actualizacion.sql.")
            else:
                st.info(
                    "🔒 Por seguridad, las contraseñas se guardan **cifradas**: nadie (ni tú) puede "
                    "leerlas. Si un miembro la olvida, pulsa «Restablecer contraseña» y dale la temporal. "
                    "Para borrar mensajes ofensivos del grupo, entra a la pestaña **Miembros** estando "
                    "como administradora y usa el 🗑️ de cada publicación.")
                pend = [m for m in lista_m if m["estado"] == "pendiente"]
                aprob = [m for m in lista_m if m["estado"] == "aprobado"]
                rech = [m for m in lista_m if m["estado"] == "rechazado"]

                st.markdown(f"#### ⏳ Solicitudes pendientes ({len(pend)})")
                if not pend:
                    st.caption("No hay solicitudes pendientes.")
                for m in pend:
                    with st.container(border=True):
                        st.write(f"**{m['usuario']}** · {m['correo']}")
                        st.caption(
                            f"Solicitó el {fecha_bonita(m['creado'])} · lleva "
                            f"{dias_desde(m['creado'])} día(s). No se vence: respondes cuando puedas.")
                        a1, a2 = st.columns(2)
                        if a1.button("✅ Aceptar", key=f"ac_{m['id']}"):
                            DB.actualizar_miembro(m["usuario"], estado="aprobado")
                            enviar_mail(
                                m["correo"], "♟️ ¡Bienvenido al Club Chess Calamari!",
                                f"Hola {m['usuario']}, tu solicitud fue aprobada. Ya puedes iniciar "
                                "sesión en la pestaña Miembros con tu usuario y contraseña.")
                            st.rerun()
                        if a2.button("❌ Rechazar", key=f"re_{m['id']}"):
                            DB.actualizar_miembro(m["usuario"], estado="rechazado")
                            enviar_mail(
                                m["correo"], "Club Chess Calamari — tu solicitud",
                                f"Hola {m['usuario']}, por ahora no pudimos aprobar tu solicitud. "
                                "Puedes escribirnos desde la página si tienes dudas.")
                            st.rerun()

                st.markdown(f"#### ✅ Miembros del grupo ({len(aprob)})")
                if not aprob:
                    st.caption("Aún no hay miembros aprobados.")
                for m in aprob:
                    with st.container(border=True):
                        st.write(f"**{m['usuario']}** · {m['correo']}")
                        b1, b2 = st.columns(2)
                        if b1.button("🔁 Restablecer contraseña", key=f"rs_{m['id']}"):
                            temp = clave_temporal()
                            DB.actualizar_miembro(m["usuario"], clave_hash=hash_clave(temp))
                            enviado = enviar_mail(
                                m["correo"], "♟️ Club Chess Calamari — contraseña temporal",
                                f"Hola {m['usuario']}, tu contraseña temporal es: {temp}\n"
                                "Entra en Miembros y cámbiala en «Cambiar mi contraseña».")
                            st.success(
                                f"Contraseña temporal de {m['usuario']}: **{temp}** "
                                + ("(también se envió a su correo)." if enviado
                                   else "(no se pudo enviar por correo: cópiala y dísela tú)."))
                        if ss.confirmar_del == m["usuario"]:
                            st.warning(f"¿Eliminar a {m['usuario']} del grupo?")
                            d1, d2 = st.columns(2)
                            if d1.button("Sí, eliminar", key=f"si_{m['id']}"):
                                DB.borrar_miembro(m["usuario"])
                                ss.confirmar_del = None
                                st.rerun()
                            if d2.button("Cancelar", key=f"no_{m['id']}"):
                                ss.confirmar_del = None
                                st.rerun()
                        elif b2.button("🗑️ Eliminar del grupo", key=f"el_{m['id']}"):
                            ss.confirmar_del = m["usuario"]
                            st.rerun()

                if rech:
                    st.markdown(f"#### ❌ Rechazados ({len(rech)})")
                for m in rech:
                    with st.container(border=True):
                        st.write(f"**{m['usuario']}** · {m['correo']}")
                        r1, r2 = st.columns(2)
                        if r1.button("✅ Aceptar ahora", key=f"ra_{m['id']}"):
                            DB.actualizar_miembro(m["usuario"], estado="aprobado")
                            st.rerun()
                        if r2.button("🗑️ Borrar registro", key=f"rb_{m['id']}"):
                            DB.borrar_miembro(m["usuario"])
                            st.rerun()

        # --- Mi cuenta (cambiar contraseña de administradora con PIN)
        with p_cuenta:
            st.markdown("#### 🔐 Cambiar mi contraseña de administradora")
            pin_real = str(_secret("ADMIN_PIN", ""))
            if not pin_real:
                st.warning(
                    "Para cambiar tu contraseña desde aquí necesitas un PIN. Agrégalo en Streamlit → "
                    "Settings → Secrets, con una línea así:  ADMIN_PIN = \"tu-pin\"")
            else:
                with st.form("f_admin_clave", clear_on_submit=True):
                    pin = st.text_input("PIN de seguridad", type="password")
                    n1 = st.text_input("Nueva contraseña", type="password")
                    n2 = st.text_input("Repite la nueva contraseña", type="password")
                    cambiar = st.form_submit_button("Cambiar contraseña")
                if cambiar:
                    if ss.fallos_pin >= 3:
                        st.error("Demasiados intentos con el PIN. Cierra y vuelve a abrir la página.")
                    elif not hmac.compare_digest(pin.encode("utf-8"), pin_real.encode("utf-8")):
                        ss.fallos_pin += 1
                        st.error("PIN incorrecto.")
                    elif validar_clave(n1):
                        st.error(validar_clave(n1))
                    elif n1 != n2:
                        st.error("Las contraseñas no coinciden.")
                    else:
                        DB.guardar_ajuste("admin_hash", hash_clave(n1))
                        limpiar_cache()
                        ss.fallos_pin = 0
                        st.success("¡Contraseña cambiada! Úsala la próxima vez que entres.")
                st.caption(
                    "Si algún día olvidas la nueva contraseña: en Supabase → Table Editor → tabla "
                    "«ajustes», borra la fila «admin_hash» y volverá a servir la contraseña de Secrets.")

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
                instagram = st.text_input(
                    "Instagram (tu usuario, ej: clubchesscalamari, o el enlace)", A.get("instagram", ""))
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
                guardar = st.form_submit_button("💾 Guardar todo")
            if guardar:
                try:
                    for k, v in {
                        "correo": correo, "instagram": instagram, "telefono": telefono, "whatsapp": whatsapp,
                        "direccion": direccion, "referencia": referencia, "maps_link": maps_link,
                        "fundadora": fundadora, "lema": lema, "bienvenida": bienvenida,
                        "clases": clases,
                    }.items():
                        DB.guardar_ajuste(k, v)
                    limpiar_cache()
                    st.success("¡Datos guardados!")
                    st.rerun()
                except Exception as e:
                    st.error(f"No se pudo guardar: {e}")

        # --- Colores
        with p_colores:
            st.markdown("#### 🖼️ Imagen de arriba (la del tablero)")
            st.caption("Sube la imagen que quieras ver arriba. Se recorta en formato panorámico.")
            nuevo_banner = st.file_uploader(
                "Nueva imagen de arriba", type=["jpg", "jpeg", "png", "webp"], key="up_banner")
            if nuevo_banner:
                st.image(nuevo_banner, caption="Así la recibirá la página (se recortará un poco)")
            if st.button("💾 Usar esta imagen arriba"):
                if not nuevo_banner:
                    st.warning("Primero elige una imagen.")
                else:
                    DB.guardar_ajuste("banner_b64", preparar_banner(nuevo_banner))
                    limpiar_cache()
                    st.rerun()
            if st.button("↩️ Volver a la imagen original de arriba"):
                DB.borrar_ajuste("banner_b64")
                limpiar_cache()
                st.rerun()
            st.divider()
            st.markdown("#### 🎨 Colores")
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
