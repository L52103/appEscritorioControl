from flask import Blueprint, render_template, redirect, url_for, flash
from db import get_connection
from gpt4all import GPT4All
from datetime import datetime, date, timedelta
import threading
import re

asistencia_bp = Blueprint("asistencia", __name__, template_folder="../templates")

# _________________ Modulo IA _________________
_model = None
_model_lock = threading.Lock()

def get_model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                _model = GPT4All("mistral-7b-instruct-v0.1.Q4_0.gguf", device="cpu")
    return _model

def resumir_mensaje(mensaje: str) -> str:
    
    model = get_model()
    prompt = f"""
    eres un administrador que debe describir de la mejor manera la inasistencia de un empleado, Resume de forma breve y clara este mensaje en ESPAÑOL para usarlo como motivo en una tabla de inasistencias,
    corrigiendo errores ortográficos y manteniendo el contexto: "{mensaje}".
    Solo responde con el texto resumido en español, sin explicaciones, y omite groserías si las hay, no coloques comillas y de ser posible resume el texto inicial para hacerlo mas simple sin perder contexto.
    """
    with _model_lock:
        with model.chat_session():
            out = model.generate(prompt, max_tokens=50, temp=0.0)
    out = (out or "").strip()
    return out or "Inasistencia sin justificar por parte del trabajador."

def detectar_categoria(mensaje_resumido: str) -> str:
    m = (mensaje_resumido or "").lower()
    if any(x in m for x in ['accidente', 'choque', 'lesión', 'lesion','herida', 'golpe', 'corte', 'caida']):
        return 'accidente'
    if any(x in m for x in ['médico', 'medico','medica', 'hospital', 'doctor', 'licencia', 'medicamento', 'inyección', 'vacuna', 'médica']):
        return 'medico'
    if any(x in m for x in ['familiar', 'familia', 'compromiso familiar', 'duelo','padre', 'madre', 'hermano', 'hermana', 'hijo', 'hija', 'abuelo', 'abuela' ]):
        return 'asunto familiar'
    if any(x in m for x in ['personal', 'asunto personal', 'trámite', 'tramite', 'permiso', 'problema']):
        return 'asunto personal'
    return 'otros'

NUMEROS_PALABRA = {
    "un": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10
}

def extraer_fechas(mensaje: str, anio_por_defecto: int):
    fechas_txt = re.findall(r'(\d{1,2}/\d{1,2}(?:/\d{2,4})?)', mensaje or "")
    fechas = []
    for f in fechas_txt:
        try:
            if len(f.split('/')) == 2:
                f = f"{f}/{anio_por_defecto}"
            fechas.append(datetime.strptime(f, "%d/%m/%Y").date())
        except Exception:
            continue
    return fechas

def extraer_dias(mensaje: str):
    msg = (mensaje or "").lower()
    m = re.search(r'(\d+)\s*d[ií]as?', msg)
    if m:
        return int(m.group(1))
    for palabra, valor in NUMEROS_PALABRA.items():
        if re.search(rf'\b{palabra}\s*d[ií]as?\b', msg):
            return valor
    return None

def calcular_rango(mensaje: str, fecha_dialogo: date):
    fechas = extraer_fechas(mensaje, fecha_dialogo.year)
    dias = extraer_dias(mensaje)

    if len(fechas) >= 2:
        f1, f2 = fechas[0], fechas[1]
        if f2 < f1:
            f1, f2 = f2, f1
        dur = (f2 - f1).days + 1
        return f1, f2, dur

    if len(fechas) == 1:
        f = fechas[0]
        return f, f, 1

    if dias and dias > 0:
        ini = fecha_dialogo
        fin = fecha_dialogo + timedelta(days=dias - 1)
        return ini, fin, dias

    return fecha_dialogo, fecha_dialogo, 1

# _________________ Lista _________________
@asistencia_bp.route("/asistencias", methods=["GET"])
def listar_asistencias():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            a.id,
            a.fecha,
            a.hora_entrada,
            a.hora_salida,
            a.trabajador_id,
            TRIM(CONCAT_WS(' ', t.nombre, t.apellido)) AS trabajador_nombre,

            a.is_asistencia,
            a.justificado,
            a.procesado_ia,

            COALESCE(a.mensaje, '') AS mensaje_texto,
            COALESCE(a.categoria, '') AS categoria,
            a.fecha_inicio_inasistencia,
            a.fecha_fin_inasistencia,
            a.duracion_dias
        FROM asistencia a
        LEFT JOIN trabajador t ON t.id = a.trabajador_id
        ORDER BY a.fecha DESC, a.id DESC;
    """)
    asistencias = cur.fetchall()
    cur.close(); conn.close()
    return render_template("asistencia/lista.html", asistencias=asistencias)



# _________________ Procesamiento _________________
@asistencia_bp.route("/asistencias/<int:asistencia_id>/procesar", methods=["POST"])
def procesar_asistencia(asistencia_id):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT id, fecha, is_asistencia, justificado, procesado_ia, COALESCE(mensaje, ''), trabajador_id
            FROM asistencia
            WHERE id = %s
            FOR UPDATE;
        """, (asistencia_id,))
        row = cur.fetchone()
        if not row:
            flash("Asistencia no encontrada.", "warning")
            conn.rollback()
            return redirect(url_for("asistencia.listar_asistencias"))

        _id, fecha_reg, is_asistencia, justificado, procesado_ia, mensaje_actual, trabajador_id = row

        if is_asistencia:
            flash("No se procesa: es un registro de asistencia (no inasistencia).", "info")
            conn.rollback()
            return redirect(url_for("asistencia.listar_asistencias"))

        if procesado_ia:
            flash("Ya fue procesado por IA.", "info")
            conn.rollback()
            return redirect(url_for("asistencia.listar_asistencias"))

        if not justificado:
            mensaje_proc = "Inasistencia sin justificar por parte del trabajador."
            categoria = "otros"
            ini, fin, dur = fecha_reg, fecha_reg, 1
        else:
            mensaje_proc = resumir_mensaje(mensaje_actual or "")
            categoria   = detectar_categoria(mensaje_proc)
            ini, fin, dur = calcular_rango(mensaje_actual or mensaje_proc, fecha_dialogo=fecha_reg)

        cur.execute("""
            UPDATE asistencia
            SET mensaje = %s,
                categoria = %s,
                fecha_inicio_inasistencia = %s,
                fecha_fin_inasistencia    = %s,
                duracion_dias             = %s,
                procesado_ia              = TRUE
            WHERE id = %s;
        """, (mensaje_proc, categoria, ini, fin, dur, asistencia_id))

        conn.commit()
        flash("Asistencia procesada con IA y métricas registradas.", "success")

    except Exception as e:
        try: conn.rollback()
        except Exception: pass
        flash(f"Error al procesar: {e}", "danger")
    finally:
        try: cur.close(); conn.close()
        except Exception: pass

    return redirect(url_for("asistencia.listar_asistencias"))
