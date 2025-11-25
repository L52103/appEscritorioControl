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
# 1. MÓDULO DE IA GENERATIVA (Llama 3)
# ==========================================
_model = None
_model_lock = threading.Lock()

def get_model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                # CAMBIO: Usamos Llama 3 8B. Es el mejor modelo balanceado hoy en día.
                # Asegúrate de tener este archivo en tu carpeta 'routes'
                modelo_nombre = "Meta-Llama-3-8B-Instruct.Q4_0.gguf"
                model_path = "routes" 

                full_path = os.path.join(model_path, modelo_nombre)

                # Intentamos cargar. Si no existe, GPT4All intentará descargarlo si allow_download=True
                # pero es mejor que tú pongas el archivo ahí manualmente.
                if os.path.exists(full_path):
                    print(f"--> Cargando Llama 3 desde: {full_path} ...")
                    _model = GPT4All(
                        modelo_nombre,
                        model_path=model_path,
                        device="gpu",
                        allow_download=False # Pon True si quieres que intente bajarlo (4GB)
                    )
                else:
                    print(f"ADVERTENCIA: No se encontró {modelo_nombre} en {model_path}")
                    print("Intentando descarga automática (puede tardar)...")
                    try:
                        _model = GPT4All(
                            modelo_nombre,
                            model_path=model_path,
                            device="cpu",
                            allow_download=True
                        )
                    except Exception as e:
                        raise FileNotFoundError(f"Error cargando modelo. Asegurate de descargar {modelo_nombre} y ponerlo en la carpeta routes. Error: {e}")

    return _model

def resumir_mensaje(mensaje: str) -> str:
    """
    Usa Llama 3 para extraer el motivo principal.
    """
    try:
        model = get_model()
        
        # Prompt optimizado para Llama 3
        # Llama 3 es muy inteligente, le damos instrucciones directas.
        prompt = f"""<|start_header_id|>system<|end_header_id|>
Tu tarea es clasificar la justificación de una inasistencia laboral.
Analiza el texto del usuario y extrae SOLO la categoría principal.
Las categorías posibles son: Salud, Accidente, Trámite Personal, Familiar, Otro.
Responde con una sola palabra o frase muy corta.
<|eot_id|><|start_header_id|>user<|end_header_id|>
Texto del trabajador: "{mensaje}"
Categoría:<|eot_id|><|start_header_id|>assistant<|end_header_id|>"""
        
        with _model_lock:
            with model.chat_session():
                # temp=0.1 para máxima precisión
                out = model.generate(prompt, max_tokens=15, temp=0.1)
        
        limpio = (out or "").strip()
        
        # Limpieza básica
        limpio = limpio.replace("Categoría:", "").replace(".", "").strip()
        
        return limpio
        
    except Exception as e:
        print(f"Error en IA: {e}")
        return mensaje # Fallback

def detectar_categoria(texto_ia: str) -> str:
    """
    Mapea la respuesta de la IA a las categorías de tu base de datos.
    """
    m = (texto_ia or "").lower()
    
    # Mapa de palabras clave
    if any(x in m for x in ['accidente', 'choque', 'vehicular', 'siniestro']): return 'accidente'
    if any(x in m for x in ['salud', 'médico', 'medico', 'enfermedad', 'doctor', 'hospital', 'fiebre', 'gripe']): return 'medico'
    if any(x in m for x in ['familiar', 'hijo', 'funeral', 'mamá', 'papá', 'hermano']): return 'asunto familiar'
    if any(x in m for x in ['personal', 'trámite', 'tramite', 'banco', 'notaría', 'viaje', 'mudanza']): return 'asunto personal'
    
    return 'otros'

# ==========================================
# 2. UTILIDADES (Fechas/Regex) - SIN CAMBIOS
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
# 3. MÓDULO DE PREDICCIÓN (ML) 
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

    if df.empty:
        return []

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

        # si no encuentra el nombre 
        nombre_df = df_trabajadores[df_trabajadores['id'] == tid]
        if not nombre_df.empty:
            nombre = nombre_df['nombre_completo'].iloc[0]
        else:
            nombre = f"Trabajador {tid}"
        
        # inicio
        riesgo_texto = "Bajo"
        promedio_dias_entre_faltas = None
        fecha_inicio_estimada = None
        
        if len(w_data) >= 2:
            w_data['fecha'] = pd.to_datetime(w_data['fecha'])
            diferencias = w_data['fecha'].diff().dt.days.dropna()

            if not diferencias.empty:
                promedio = diferencias.mean()
                # si el promedio es válido 
                if not pd.isna(promedio) and np.isfinite(promedio):
                    promedio_dias_entre_faltas = promedio
                    ultima_falta = w_data['fecha'].iloc[-1]
                    fecha_inicio_estimada = ultima_falta + timedelta(days=promedio)

                    dias_restantes = (fecha_inicio_estimada - datetime.now()).days
                    
                    if fecha_inicio_estimada < datetime.now():
                        riesgo_texto = "⚠️ ALTO (Atrasado)"
                    elif dias_restantes < 7:
                        riesgo_texto = "Alto"
                    elif dias_restantes < 15:
                        riesgo_texto = "Medio"
                    else:
                        riesgo_texto = "Bajo"
                else:
                   
                    fecha_inicio_estimada = datetime.now() + timedelta(days=30)
                    riesgo_texto = "Sin historial suficiente"
            else:
                
                fecha_inicio_estimada = datetime.now() + timedelta(days=30)
                riesgo_texto = "Sin historial suficiente"
        else:
            fecha_inicio_estimada = datetime.now() + timedelta(days=30)  # Default si no hay datos
            riesgo_texto = "Sin historial suficiente"

        # Días
        dias_duracion_est = 1.0
        if rf_model:
            try:
                mañana = date.today() + timedelta(days=1)
                cat_moda = w_data['categoria'].mode()[0] if not w_data['categoria'].empty else 'otros'
                cat_code = le_cat.transform([cat_moda])[0] if cat_moda in le_cat.classes_ else 0

                X_pred = pd.DataFrame(
                    [[tid, mañana.weekday(), mañana.month, cat_code]],
                    columns=['trabajador_id', 'dia_semana', 'mes', 'cat_encoded']
                )
                dias_duracion_est = rf_model.predict(X_pred)[0]
            except Exception:
                dias_duracion_est = w_data['duracion_dias'].mean()
        else:
            dias_duracion_est = w_data['duracion_dias'].mean() if not w_data.empty else 1

        # si la media viene NaN forzamos a 1 día
        if pd.isna(dias_duracion_est) or not np.isfinite(dias_duracion_est):
            dias_duracion_est = 1

        # Fechas Exactas
        try:
            duracion_entero = int(round(dias_duracion_est))
        except (TypeError, ValueError):
            duracion_entero = 1

        if duracion_entero < 1:
            duracion_entero = 1
        
        # Calculo Fecha Fin
        fecha_fin_estimada = fecha_inicio_estimada + timedelta(days=duracion_entero - 1)
        
        # String 
        str_inicio = fecha_inicio_estimada.strftime("%d/%m/%Y")
        str_fin = fecha_fin_estimada.strftime("%d/%m/%Y")
        
        if duracion_entero > 1:
            rango_texto = f"{str_inicio} al {str_fin}"
        else:
            rango_texto = f"{str_inicio}"

        # Frecuencia histórica solo si tenemos promedio valido
        if promedio_dias_entre_faltas is not None and np.isfinite(promedio_dias_entre_faltas):
            freq_text = f"Falta cada {int(round(promedio_dias_entre_faltas))} días"
        else:
            freq_text = "N/A"

        resultados.append({
            "Trabajador": nombre,
            "Estado Riesgo": riesgo_texto,
            "Fechas Exactas Estimadas": rango_texto,  
            "Días Totales": duracion_entero,
            "Frecuencia Histórica": freq_text
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
            SELECT 
                a.id, a.fecha, a.hora_entrada, a.hora_salida, 
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
        return render_template("asistencia/lista.html", asistencias=asistencias)
    finally:
        conn.close()


@asistencia_bp.route("/predicciones", methods=["GET"])
def dashboard_predicciones():
    try: 
        return render_template("asistencia/predicciones.html", predicciones=entrenar_y_predecir_inasistencias())
    except Exception as e: 
        return f"Error generando predicciones: {e}"

@asistencia_bp.route("/asistencias/<int:id>/procesar", methods=["POST"])
def procesar_asistencia(id):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    try:
        cur.execute("SELECT * FROM asistencia WHERE id = %s FOR UPDATE", (id,))
        row = cur.fetchone()

        if not row:
            flash("Asistencia no encontrada.", "danger")
            return redirect(url_for("asistencia.listar_asistencias"))

        # 1. Obtener mensaje original
        msg_original = row['mensaje'] or ""
        msg_original = msg_original.strip()
        
        # 2. Verificar contenido
        tiene_contenido = len(msg_original) > 3
        
        # Variables default
        cat = "otros"
        ini, fin, dur = row['fecha'], row['fecha'], 1
        nuevo_estado_justificado = False

        if not tiene_contenido:
            print(f"ID {id}: Sin contenido suficiente.")
            nuevo_estado_justificado = False
        else:
            print(f"ID {id}: Procesando con Llama 3: '{msg_original}'")
            
            # A. Usamos Llama 3 para sacar la "Intención" (Categoría en texto)
            intencion_ia = resumir_mensaje(msg_original)
            print(f"   -> Llama 3 dice: {intencion_ia}")
            
            # B. Convertimos esa intención a nuestras categorías fijas
            cat = detectar_categoria(intencion_ia)
            
            # Fallback si Llama 3 falla (raro, pero posible)
            if cat == "otros":
                cat = detectar_categoria(msg_original)

            # C. Calcular fechas
            ini, fin, dur = calcular_rango(msg_original, row['fecha'])
            
            nuevo_estado_justificado = True
            print(f"   -> Categoría Final: {cat} | Duración: {dur}")

        # 3. ACTUALIZACIÓN (SIN TOCAR EL MENSAJE ORIGINAL)
        cur.execute("""
            UPDATE asistencia 
            SET categoria=%s, 
                fecha_inicio_inasistencia=%s, 
                fecha_fin_inasistencia=%s, 
                duracion_dias=%s, 
                procesado_ia=TRUE,
                justificado=%s
            WHERE id=%s
        """, (cat, ini, fin, dur, nuevo_estado_justificado, id))
        
        conn.commit()
        
        if nuevo_estado_justificado:
            flash(f"Procesado con IA. Categoría: {cat}", "success")
        else:
            flash("Sin mensaje para justificar.", "warning")
            
    except Exception as e:
        conn.rollback()
        print(f"Error critico: {e}")
        flash(f"Error: {e}", "danger")
    finally:
        conn.close()
        
    return redirect(url_for("asistencia.listar_asistencias"))

@asistencia_bp.route("/asistencias/descargar")
def descargar_asistencias():
    conn = get_connection()
    try:
        # 1. HISTORIAL
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
                "Mensaje Original": reg['mensaje'], "Categoria Detectada": reg['categoria'], "Días": reg['duracion_dias']
            })
        
        df_hist = pd.DataFrame(datos_hist)

        # 2. PREDICCIONES
        predicciones_list = entrenar_y_predecir_inasistencias()
        df_pred = pd.DataFrame(predicciones_list)

        # 3. EXCEL
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
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

            if not df_pred.empty:
                cols_orden = ["Trabajador", "Fechas Exactas Estimadas", "Estado Riesgo", "Días Totales", "Frecuencia Histórica"]
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
        return send_file(output, as_attachment=True, download_name=f'reporte_Llama3_{date.today()}.xlsx',
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    finally:
        conn.close()