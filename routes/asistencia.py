from flask import Blueprint, render_template, redirect, url_for, flash, send_file
from db import get_connection
from gpt4all import GPT4All
from datetime import datetime, date, timedelta
import threading
import re
from psycopg2.extras import DictCursor
import pandas as pd
import io


asistencia_bp = Blueprint("asistencia", __name__, template_folder="../templates")

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

@asistencia_bp.route("/asistencias", methods=["GET"])
def listar_asistencias():
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        cur.execute("""
            SELECT
                a.id, a.fecha, a.hora_entrada, a.hora_salida, a.trabajador_id,
                TRIM(CONCAT_WS(' ', t.nombre, t.apellido)) AS trabajador_nombre,
                a.is_asistencia, a.justificado, a.procesado_ia,
                COALESCE(a.mensaje, '') AS mensaje_texto,
                COALESCE(a.categoria, '') AS categoria,
                a.fecha_inicio_inasistencia, a.fecha_fin_inasistencia, a.duracion_dias
            FROM asistencia a
            LEFT JOIN trabajador t ON t.id = a.trabajador_id
            ORDER BY a.fecha DESC, a.id DESC;
        """)
        asistencias = cur.fetchall()
        cur.close()
        return render_template("asistencia/lista.html", asistencias=asistencias)
    finally:
        if conn:
            conn.close()

@asistencia_bp.route("/asistencias/<int:asistencia_id>/procesar", methods=["POST"])
def procesar_asistencia(asistencia_id):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    try:
        cur.execute("""
            SELECT id, fecha, is_asistencia, justificado, procesado_ia, COALESCE(mensaje, '') as mensaje, trabajador_id
            FROM asistencia
            WHERE id = %s
            FOR UPDATE;
        """, (asistencia_id,))
        row = cur.fetchone()

        if not row:
            flash("Asistencia no encontrada.", "warning")
            conn.rollback()
            return redirect(url_for("asistencia.listar_asistencias"))

        if row['is_asistencia']:
            flash("No se procesa: es un registro de asistencia (no inasistencia).", "info")
            conn.rollback()
            return redirect(url_for("asistencia.listar_asistencias"))

        if row['procesado_ia']:
            flash("Ya fue procesado por IA.", "info")
            conn.rollback()
            return redirect(url_for("asistencia.listar_asistencias"))

        if not row['justificado']:
            mensaje_proc = "Inasistencia sin justificar por parte del trabajador."
            categoria = "otros"
            ini, fin, dur = row['fecha'], row['fecha'], 1
        else:
            mensaje_proc = resumir_mensaje(row['mensaje'] or "")
            categoria    = detectar_categoria(mensaje_proc)
            ini, fin, dur = calcular_rango(row['mensaje'] or mensaje_proc, fecha_dialogo=row['fecha'])

        cur.execute("""
            UPDATE asistencia
            SET mensaje = %s, categoria = %s, fecha_inicio_inasistencia = %s,
                fecha_fin_inasistencia = %s, duracion_dias = %s, procesado_ia = TRUE
            WHERE id = %s;
        """, (mensaje_proc, categoria, ini, fin, dur, asistencia_id))
        conn.commit()
        flash("Asistencia procesada con IA y métricas registradas.", "success")
    except Exception as e:
        try: conn.rollback()
        except: pass
        flash(f"Error al procesar: {e}", "danger")
    finally:
        try: cur.close(); conn.close()
        except: pass
    return redirect(url_for("asistencia.listar_asistencias"))

#  RUTA DE DESCARGA 
@asistencia_bp.route("/asistencias/descargar")
def descargar_asistencias():
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        
        cur.execute("""
            SELECT
                a.id,
                TRIM(CONCAT_WS(' ', t.nombre, t.apellido)) AS trabajador,
                a.fecha,
                a.hora_entrada,
                a.hora_salida,
                a.is_asistencia,
                a.is_atrasado,
                a.justificado,
                a.procesado_ia,
                a.mensaje,
                a.categoria,
                a.fecha_inicio_inasistencia,
                a.fecha_fin_inasistencia,
                a.duracion_dias
            FROM asistencia a
            LEFT JOIN trabajador t ON t.id = a.trabajador_id
            ORDER BY a.fecha DESC, a.id DESC;
        """)
        
        registros = cur.fetchall()
        cur.close()

        if not registros:
            flash("No hay datos para exportar.", "warning")
            return redirect(url_for("asistencia.listar_asistencias"))

        # Procesamiento de los datos para el formato del Excel
        datos_procesados = []
        for reg in registros:
            
            
            horas_trabajadas_str = "0:00:00" # Valor por defecto
            if reg['hora_entrada'] and reg['hora_salida']:
                # Combinamos la fecha con las horas para poder restarlas
                fecha_asistencia = reg['fecha']
                dt_entrada = datetime.combine(fecha_asistencia, reg['hora_entrada'])
                dt_salida = datetime.combine(fecha_asistencia, reg['hora_salida'])

                # Si la hora de salida es menor
                if dt_salida < dt_entrada:
                    dt_salida += timedelta(days=1)
                
                duracion = dt_salida - dt_entrada
                
                # Formateamos la duración a un string H:MM:SS
                total_seconds = int(duracion.total_seconds())
                hours, remainder = divmod(total_seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                horas_trabajadas_str = f"{hours}:{minutes:02d}:{seconds:02d}"

            datos_procesados.append({
                "ID": reg['id'],
                "Trabajador": reg['trabajador'],
                "Fecha": reg['fecha'],
                "Hora Entrada": reg['hora_entrada'],
                "Hora Salida": reg['hora_salida'],
                "Horas trabajadas": horas_trabajadas_str, 
                "Asistió": "Sí" if reg['is_asistencia'] else "No",
                "Atrasado": "Sí" if reg['is_atrasado'] else "No",
                "Justificado": "Sí" if reg['justificado'] else "No",
                "Procesado IA": "Sí" if reg['procesado_ia'] else "No",
                "Mensaje": reg['mensaje'],
                "Categoria": reg['categoria'],
                "Inicio Inasistencia": reg['fecha_inicio_inasistencia'],
                "Fin Inasistencia": reg['fecha_fin_inasistencia'],
                "Dias": reg['duracion_dias']
            })

        # Creación del archivo Excel con Pandas
        df = pd.DataFrame(datos_procesados)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Reporte Completo de Asistencias')
            worksheet = writer.sheets['Reporte Completo de Asistencias']
            # ajuste del ancho de las columnas
            for column_cells in worksheet.columns:
                max_length = 0
                column_letter = column_cells[0].column_letter
                for cell in column_cells:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = (max_length + 2)
                worksheet.column_dimensions[column_letter].width = adjusted_width
        output.seek(0)

        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'reporte_asistencias_completo_{date.today()}.xlsx'
        )
    except Exception as e:
        flash(f"Error al generar el reporte: {e}", "danger")
        print(f"Error detallado en descarga: {e}") 
        return redirect(url_for("asistencia.listar_asistencias"))
    finally:
        if conn:
            conn.close()