from flask import Blueprint, render_template
from db import get_connection
from psycopg2.extras import DictCursor
from logic.horas_logic import analizar_asistencia # Importamos nuestra nueva lógica

reportes_bp = Blueprint("reportes", __name__, template_folder="../templates")

@reportes_bp.route("/reportes/horas")
def reporte_de_horas():
    conn = get_connection()
    cur = conn.cursor(cursor_factory=DictCursor)

    # 1. Obtener todas las asistencias con su trabajador
    cur.execute("""
        SELECT a.*, CONCAT(t.nombre, ' ', t.apellido) AS trabajador_nombre
        FROM asistencia a
        JOIN trabajador t ON a.trabajador_id = t.id
        WHERE a.is_asistencia = TRUE
    """)
    asistencias = cur.fetchall()

    # 2. Obtener todos los turnos
    # (Una optimización sería traer solo los turnos necesarios)
    cur.execute("SELECT * FROM turno")
    # Convertimos la lista de turnos a un diccionario para fácil acceso
    turnos = {turno['id']: turno for turno in cur.fetchall()}

    cur.close()
    conn.close()

    # 3. Procesar cada asistencia
    resultados_analisis = []
    for asistencia in asistencias:
        # Necesitamos saber qué turno le correspondía a este trabajador en esta fecha.
        # Esto requiere una lógica para buscar en la tabla `turno_trabajador`.
        # Por simplicidad aquí asumiremos que podemos encontrar el turno_id.
        
        # --- Lógica para encontrar el turno_id (puede variar) ---
        # Esta es la parte más compleja que depende de tu negocio.
        # ¿Un trabajador tiene siempre el mismo turno? ¿Cambia por día?
        # Supongamos que lo encontramos y es, por ejemplo, el turno con id 1.
        turno_id_correspondiente = 1 # Esto es un EJEMPLO, necesitas tu propia lógica aquí.
        
        turno_correspondiente = turnos.get(turno_id_correspondiente)

        if turno_correspondiente:
            resultado = analizar_asistencia(asistencia, turno_correspondiente)
            resultados_analisis.append(resultado)

    return render_template("reportes/horas.html", resultados=resultados_analisis)