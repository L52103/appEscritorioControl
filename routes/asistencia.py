from flask import Blueprint, render_template, redirect, url_for, flash, send_file
from db import get_connection
from gpt4all import GPT4All
from datetime import datetime, date, timedelta
import threading
import re
from psycopg2.extras import DictCursor
import pandas as pd
import io
import numpy as np
import os

# LIBRERIAS DE MACHINE LEARNING 
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import LabelEncoder

asistencia_bp = Blueprint("asistencia", __name__)

# ==========================================
# 1. MÓDULO DE IA GENERATIVA (Chatbot)
# ==========================================
_model = None
_model_lock = threading.Lock()

def get_model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:

                modelo_rapido = "tinyllama-1.1b-chat-v1.0.Q4_0.gguf"

                if os.path.exists(modelo_rapido):
                    _model = GPT4All(modelo_rapido, device="cpu")

    return _model

def resumir_mensaje(mensaje: str) -> str:
    model = get_model()
    # Prompt corto para velocidad
    prompt = f"""
    Tarea: Resumir inasistencia para RRHH.
    Ejemplos:
    "Choqué" -> Accidente vehicular.
    "Fiebre" -> Salud.
    Mensaje: "{mensaje}"
    Resumen:
    """
    try:
        with _model_lock:
            with model.chat_session():
                out = model.generate(prompt, max_tokens=25, temp=0.1)
        limpio = (out or "").strip()
        if "Resumen:" in limpio: limpio = limpio.split("Resumen:")[-1].strip()
        return limpio or "Inasistencia sin detalle."
    except:
        return "Inasistencia sin justificar."

def detectar_categoria(mensaje_resumido: str) -> str:
    m = (mensaje_resumido or "").lower()
    cats = {
        'accidente': ['accidente', 'choque', 'lesión', 'caida', 'siniestro'],
        'medico': ['médico', 'doctor', 'salud', 'enfermedad', 'licencia', 'dolor', 'hospital'],
        'asunto familiar': ['familiar', 'hijo', 'funeral', 'duelo', 'madre', 'padre'],
        'asunto personal': ['personal', 'trámite', 'banco', 'mudanza', 'notaría']
    }
    for cat, kws in cats.items():
        if any(k in m for k in kws): return cat
    return 'otros'

# ==========================================
# 2. UTILIDADES (Fechas/Regex)
# ==========================================
NUMEROS_PALABRA = {"un": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5}

def extraer_fechas(mensaje: str, anio_por_defecto: int):
    fechas_txt = re.findall(r'(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)', mensaje or "")
    fechas = []
    for f in fechas_txt:
        try:
            f = f.replace('-', '/')
            if len(f.split('/')) == 2: f = f"{f}/{anio_por_defecto}"
            fechas.append(datetime.strptime(f, "%d/%m/%Y").date())
        except: continue
    return fechas

def extraer_dias(mensaje: str):
    msg = (mensaje or "").lower()
    m = re.search(r'(\d+)\s*d[ií]as?', msg)
    if m: return int(m.group(1))
    for p, v in NUMEROS_PALABRA.items():
        if re.search(rf'\b{p}\s*d[ií]as?\b', msg): return v
    return None

def calcular_rango(mensaje: str, fecha_dialogo: date):
    fechas = extraer_fechas(mensaje, fecha_dialogo.year)
    dias = extraer_dias(mensaje)
    if len(fechas) >= 2:
        f1, f2 = sorted(fechas)[:2]
        return f1, f2, (f2 - f1).days + 1
    if len(fechas) == 1:
        f = fechas[0]
        if dias and dias > 1: return f, f + timedelta(days=dias - 1), dias
        return f, f, 1
    if dias and dias > 0:
        return fecha_dialogo, fecha_dialogo + timedelta(days=dias - 1), dias
    return fecha_dialogo, fecha_dialogo, 1

# ==========================================
# 3. MÓDULO DE PREDICCIÓN (ML) - MEJORADO
# ==========================================
def entrenar_y_predecir_inasistencias():
    conn = get_connection()
    try:
        query = """
            SELECT trabajador_id, fecha, categoria, duracion_dias, 
                   EXTRACT(DOW FROM fecha) as dia_semana,
                   EXTRACT(MONTH FROM fecha) as mes
            FROM asistencia 
            WHERE is_asistencia = FALSE AND justificado = TRUE
            ORDER BY fecha ASC
        """
        df = pd.read_sql(query, conn)
        df_trabajadores = pd.read_sql("SELECT id, nombre, apellido FROM trabajador", conn)
        df_trabajadores['nombre_completo'] = df_trabajadores['nombre'] + " " + df_trabajadores['apellido']
    finally:
        conn.close()

    if df.empty: return []

    le_cat = LabelEncoder()
    rf_model = None
    
    if len(df) > 5:
        df['cat_encoded'] = le_cat.fit_transform(df['categoria'].astype(str))
        X = df[['trabajador_id', 'dia_semana', 'mes', 'cat_encoded']].fillna(0)
        y = df['duracion_dias'].fillna(1)
        rf_model = RandomForestRegressor(n_estimators=50, random_state=42)
        rf_model.fit(X, y)

    unique_workers = df['trabajador_id'].unique()
    resultados = []
    
    for tid in unique_workers:
        w_data = df[df['trabajador_id'] == tid].sort_values('fecha')
        nombre = df_trabajadores[df_trabajadores['id'] == tid]['nombre_completo'].iloc[0]
        
        # 1. CÁLCULO DE FECHA DE INICIO 
        riesgo_texto = "Bajo"
        promedio_dias_entre_faltas = 0
        fecha_inicio_estimada = None
        
        if len(w_data) >= 2:
            w_data['fecha'] = pd.to_datetime(w_data['fecha'])
            diferencias = w_data['fecha'].diff().dt.days.dropna()
            promedio_dias_entre_faltas = diferencias.mean()
            
            # Proyectamos la próxima fecha sumando el promedio a la última falta
            ultima_falta = w_data['fecha'].iloc[-1]
            fecha_inicio_estimada = ultima_falta + timedelta(days=promedio_dias_entre_faltas)
            
            # Lógica de Riesgo
            dias_restantes = (fecha_inicio_estimada - datetime.now()).days
            
            if fecha_inicio_estimada < datetime.now():
                riesgo_texto = "ALTO (Atrasado)"
                # Si ya pasó, asumimos que el riesgo es hoy
            elif dias_restantes < 7:
                riesgo_texto = "Alto"
            elif dias_restantes < 15:
                riesgo_texto = "Medio"
        else:
             fecha_inicio_estimada = datetime.now() + timedelta(days=30) # Default si no hay datos
             riesgo_texto = "Sin historial suficiente"

        # --- 2. CÁLCULO DE DURACIÓN (Días) ---
        dias_duracion_est = 1.0
        if rf_model:
            try:
                mañana = date.today() + timedelta(days=1)
                cat_moda = w_data['categoria'].mode()[0] if not w_data['categoria'].empty else 'otros'
                cat_code = le_cat.transform([cat_moda])[0] if cat_moda in le_cat.classes_ else 0
                dias_duracion_est = rf_model.predict(pd.DataFrame([[tid, mañana.weekday(), mañana.month, cat_code]], columns=['trabajador_id', 'dia_semana', 'mes', 'cat_encoded']))[0]
            except: dias_duracion_est = w_data['duracion_dias'].mean()
        else:
             dias_duracion_est = w_data['duracion_dias'].mean() if not w_data.empty else 1

        # 3. FORMATO DE SALIDA (Fechas Exactas) 
        duracion_entero = int(round(dias_duracion_est))
        if duracion_entero < 1: duracion_entero = 1
        
        # Calculamos Fecha Fin
        fecha_fin_estimada = fecha_inicio_estimada + timedelta(days=duracion_entero - 1)
        
        # String legible
        str_inicio = fecha_inicio_estimada.strftime("%d/%m/%Y")
        str_fin = fecha_fin_estimada.strftime("%d/%m/%Y")
        
        if duracion_entero > 1:
            rango_texto = f"{str_inicio} al {str_fin}"
        else:
            rango_texto = f"{str_inicio}"

        resultados.append({
            "Trabajador": nombre,
            "Estado Riesgo": riesgo_texto,
            "Fechas Exactas Estimadas": rango_texto, # Columna nueva limpia
            "Días Totales": duracion_entero,
            "Frecuencia Histórica": f"Falta cada {int(promedio_dias_entre_faltas)} días" if len(w_data) >= 2 else "N/A"
        })
        
    return resultados

# ==========================================
# 4. RUTAS
# ==========================================
@asistencia_bp.route("/asistencias", methods=["GET"])
def listar_asistencias():
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=DictCursor)
        cur.execute("""
            SELECT a.id, a.fecha, a.hora_entrada, a.hora_salida, 
                   TRIM(CONCAT_WS(' ', t.nombre, t.apellido)) AS trabajador_nombre,
                   a.is_asistencia, a.justificado, a.procesado_ia,
                   COALESCE(a.mensaje, '') AS mensaje_texto, COALESCE(a.categoria, '') AS categoria,
                   a.duracion_dias
            FROM asistencia a LEFT JOIN trabajador t ON t.id = a.trabajador_id
            ORDER BY a.fecha DESC, a.id DESC;
        """)
        return render_template("asistencia/lista.html", asistencias=cur.fetchall())
    finally: conn.close()

@asistencia_bp.route("/predicciones", methods=["GET"])
def dashboard_predicciones():
    try: return render_template("asistencia/predicciones.html", predicciones=entrenar_y_predecir_inasistencias())
    except Exception as e: return f"Error: {e}"

@asistencia_bp.route("/asistencias/<int:id>/procesar", methods=["POST"])
def procesar_asistencia(id):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    try:
        cur.execute("SELECT * FROM asistencia WHERE id = %s FOR UPDATE", (id,))
        row = cur.fetchone()
        if not row or row['is_asistencia'] or row['procesado_ia']: return redirect(url_for("asistencia.listar_asistencias"))
        
        msg = row['mensaje'] or ""
        if not row['justificado']:
            res, cat, ini, fin, dur = "Inasistencia sin justificar.", "otros", row['fecha'], row['fecha'], 1
        else:
            res = resumir_mensaje(msg)
            cat = detectar_categoria(res)
            ini, fin, dur = calcular_rango(msg, row['fecha'])

        cur.execute("UPDATE asistencia SET mensaje=%s, categoria=%s, fecha_inicio_inasistencia=%s, fecha_fin_inasistencia=%s, duracion_dias=%s, procesado_ia=TRUE WHERE id=%s", (res, cat, ini, fin, dur, id))
        conn.commit(); flash("Procesado.", "success")
    except Exception as e: conn.rollback(); flash(f"Error: {e}", "danger")
    finally: conn.close()
    return redirect(url_for("asistencia.listar_asistencias"))

# RUTA DE DESCARGA ACTUALIZADA
@asistencia_bp.route("/asistencias/descargar")
def descargar_asistencias():
    conn = get_connection()
    try:
        # 1. DATOS HISTÓRICOS
        cur = conn.cursor(cursor_factory=DictCursor)
        cur.execute("""
            SELECT a.id, TRIM(CONCAT_WS(' ', t.nombre, t.apellido)) AS trabajador,
                   a.fecha, a.hora_entrada, a.hora_salida, a.is_asistencia,
                   a.mensaje, a.categoria, a.duracion_dias, a.is_atrasado, a.justificado, a.procesado_ia
            FROM asistencia a LEFT JOIN trabajador t ON t.id = a.trabajador_id
            ORDER BY a.fecha DESC
        """)
        registros = cur.fetchall()
        
        if not registros:
            flash("No hay datos.", "warning")
            return redirect(url_for("asistencia.listar_asistencias"))

        datos_hist = []
        for reg in registros:
            h_str = "0:00:00"
            if reg['hora_entrada'] and reg['hora_salida']:
                di = datetime.combine(reg['fecha'], reg['hora_entrada'])
                do = datetime.combine(reg['fecha'], reg['hora_salida'])
                if do < di: do += timedelta(days=1)
                ts = int((do - di).total_seconds())
                h, r = divmod(ts, 3600); m, s = divmod(r, 60)
                h_str = f"{h}:{m:02d}:{s:02d}"

            datos_hist.append({
                "ID": reg['id'], "Trabajador": reg['trabajador'], "Fecha": reg['fecha'],
                "Entrada": reg['hora_entrada'], "Salida": reg['hora_salida'], "Horas": h_str,
                "Asistió": "Sí" if reg['is_asistencia'] else "No",
                "Justificado": "Sí" if reg['justificado'] else "No",
                "Mensaje IA": reg['mensaje'], "Categoria": reg['categoria'], "Días": reg['duracion_dias']
            })
        
        df_hist = pd.DataFrame(datos_hist)

        # 2. DATOS PREDICCIONES (EJECUTAMOS EL MODELO)
        predicciones_list = entrenar_y_predecir_inasistencias()
        df_pred = pd.DataFrame(predicciones_list)

        # 3. CREAR EXCEL CON DOS HOJAS
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Hoja 1: Historial
            df_hist.to_excel(writer, index=False, sheet_name='Reporte Histórico')
            ws1 = writer.sheets['Reporte Histórico']
            for col in ws1.columns:
                max_len = 0
                col_let = col[0].column_letter
                for cell in col:
                    try:
                        if len(str(cell.value)) > max_len: max_len = len(str(cell.value))
                    except: pass
                ws1.column_dimensions[col_let].width = max_len + 2

            # Hoja 2: Predicciones 
            if not df_pred.empty:
                # Reordenamos columnas para que lo más importante salga primero
                cols_orden = ["Trabajador", "Fechas Exactas Estimadas", "Estado Riesgo", "Días Totales", "Frecuencia Histórica"]
                # Filtramos solo si las columnas existen en el dataframe
                cols_final = [c for c in cols_orden if c in df_pred.columns]
                df_pred = df_pred[cols_final]
                
                df_pred.to_excel(writer, index=False, sheet_name='Predicciones IA')
                
                ws2 = writer.sheets['Predicciones IA']
                for col in ws2.columns:
                    max_len = 0
                    col_let = col[0].column_letter
                    for cell in col:
                        try:
                            if len(str(cell.value)) > max_len: max_len = len(str(cell.value))
                        except: pass
                    ws2.column_dimensions[col_let].width = max_len + 4 

        output.seek(0)
        return send_file(output, as_attachment=True, download_name=f'reporte_ia_detallado_{date.today()}.xlsx',
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    finally:
        conn.close()