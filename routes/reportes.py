# routes/reportes.py

from flask import Blueprint, render_template, flash, redirect, url_for, send_file
from db import get_connection
from psycopg2.extras import DictCursor
import pandas as pd
import plotly.express as px
import locale
import io
from datetime import date

try:
    locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_TIME, 'Spanish')
    except locale.Error:
        print("ADVERTENCIA: Locale en español no encontrado. Los meses podrían aparecer en inglés.")

reportes_bp = Blueprint("reportes", __name__, template_folder="../templates")

def get_data_for_chart():
    """Función centralizada para obtener y procesar los datos del gráfico."""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    
    # --- CONSULTA SQL MEJORADA ---
    # La consulta ahora empieza desde una subconsulta de todos los trabajadores y todos los meses,
    # asegurando que cada trabajador tenga una fila para cada mes, incluso si sus días asistidos son 0.
    sql_query = """
        WITH meses AS (
            SELECT DISTINCT TO_CHAR(fecha, 'YYYY-MM') AS anio_mes
            FROM asistencia
        ),
        trabajadores_meses AS (
            SELECT
                t.id AS trabajador_id,
                TRIM(CONCAT_WS(' ', t.nombre, t.apellido)) AS nombre_trabajador,
                m.anio_mes
            FROM trabajador t
            CROSS JOIN meses m
        )
        SELECT
            tm.nombre_trabajador,
            EXTRACT(YEAR FROM TO_DATE(tm.anio_mes, 'YYYY-MM')) AS anio,
            EXTRACT(MONTH FROM TO_DATE(tm.anio_mes, 'YYYY-MM')) AS mes_num,
            COUNT(DISTINCT a.fecha) AS dias_asistidos
        FROM trabajadores_meses tm
        LEFT JOIN asistencia a ON tm.trabajador_id = a.trabajador_id
                               AND TO_CHAR(a.fecha, 'YYYY-MM') = tm.anio_mes
                               AND a.is_asistencia = TRUE
        GROUP BY tm.nombre_trabajador, anio, mes_num
        ORDER BY anio, mes_num;
    """
    cur.execute(sql_query)
    
    column_names = [desc[0] for desc in cur.description]
    registros = cur.fetchall()

    cur.close()
    conn.close()

    if not registros:
        return None

    df = pd.DataFrame(registros, columns=column_names)
    df['mes_nombre'] = df['mes_num'].apply(lambda x: date(int(df['anio'].iloc[0]), int(x), 1).strftime('%B').capitalize())
    df_sorted = df.sort_values(by=['anio', 'mes_num'])
    return df_sorted

@reportes_bp.route("/reportes/asistencia")
def grafico_asistencia():
    df = get_data_for_chart()

    if df is None or df.empty:
        return render_template("reportes/grafico_asistencia.html", chart_html=None)

    fig = px.line(
        df, x='mes_nombre', y='dias_asistidos', color='nombre_trabajador', markers=True,
        title="Evolución de la Asistencia por Mes",
        labels={
            "mes_nombre": "Mes",
            "dias_asistidos": "Dias asistidos",
            "nombre_trabajador": "Trabajador"
        }
    )
    fig.update_layout(xaxis_title="Mes del Año", yaxis_title="Dias asistidos", title_font_size=22, xaxis_tickangle=-45)

    chart_html = fig.to_html(full_html=False, include_plotlyjs='cdn')
    return render_template("reportes/grafico_asistencia.html", chart_html=chart_html)

@reportes_bp.route("/reportes/descargar-grafico")
def descargar_grafico_excel():
    df = get_data_for_chart()

    if df is None or df.empty:
        flash("No hay datos suficientes para generar el reporte con gráfico.", "warning")
        return redirect(url_for("asistencia.listar_asistencias"))

    fig = px.line(df, x='mes_nombre', y='dias_asistidos', color='nombre_trabajador', markers=True, 
                  title="Evolución de la Asistencia por Mes")

    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')

    df_reporte = df.rename(columns={
        'nombre_trabajador': 'Trabajador',
        'mes_nombre': 'Mes',
        'dias_asistidos': 'Dias asistidos'
    })
    
    df_reporte = df_reporte[['Trabajador', 'Mes', 'Dias asistidos']]
    
    df_reporte.to_excel(writer, sheet_name='Datos de Asistencia', index=False)
    
    img_bytes = fig.to_image(format="png", width=800, height=500, scale=2)
    worksheet = writer.sheets['Datos de Asistencia']
    worksheet.insert_image('E2', 'grafico.png', {'image_data': io.BytesIO(img_bytes)})
    
    writer.close()
    output.seek(0)

    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'reporte_asistencia_con_grafico_{date.today()}.xlsx'
    )