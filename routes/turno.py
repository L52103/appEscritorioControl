# Herramientas de Flask, conexión a BBDD y el nuevo DictCursor
from flask import Blueprint, request, render_template, redirect, url_for, flash
from db import get_connection
from psycopg2.extras import DictCursor

# Creamos el Blueprint para el módulo 'turno'
turno_bp = Blueprint("turno", __name__, template_folder="../templates")

# Ruta para mostrar la lista de todos los turnos
@turno_bp.route("/turnos")
def listar_turnos():
    conn = get_connection()
    # Usamos DictCursor para obtener resultados con nombres de columna
    cur = conn.cursor(cursor_factory=DictCursor)
    
    # Consulta mejorada con JOIN para obtener el nombre del área de trabajo
    cur.execute("""
        SELECT t.id, t.horario_inicio, t.horario_fin, t.tipo_turno, t.area_id, a.nombre AS area_nombre
        FROM turno t
        LEFT JOIN areatrabajo a ON t.area_id = a.id
        ORDER BY t.id ASC
    """)
    turnos = cur.fetchall()
    
    cur.close()
    conn.close()
    return render_template("turno/lista.html", turnos=turnos)

# Ruta para crear un nuevo turno
@turno_bp.route("/turnos/crear", methods=["GET", "POST"])
def crear_turno():
    if request.method == "POST":
        data = request.form
        conn = get_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        # Inserta los nuevos datos en la tabla 'turno'
        cur.execute(
            """INSERT INTO turno (horario_inicio, horario_fin, tipo_turno, area_id)
            VALUES (%s, %s, %s, %s)""",
            (data["horario_inicio"], data["horario_fin"], data["tipo_turno"], data["area_id"])
        )
        conn.commit()
        cur.close()
        conn.close()
        flash("Turno creado exitosamente", "success")
        return redirect(url_for("turno.listar_turnos"))
    return render_template("turno/crear.html")

# Ruta para editar un turno existente por su ID
@turno_bp.route("/turnos/editar/<int:id>", methods=["GET", "POST"])
def editar_turno(id):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=DictCursor)

    if request.method == "POST":
        data = request.form
        # Actualiza el registro que coincida con el ID
        cur.execute(
            """UPDATE turno SET horario_inicio=%s, horario_fin=%s, tipo_turno=%s, area_id=%s WHERE id=%s""",
            (data["horario_inicio"], data["horo_fin"], data["tipo_turno"], data["area_id"], id)
        )
        conn.commit()
        cur.close()
        conn.close()
        flash("Turno actualizado correctamente", "success")
        return redirect(url_for("turno.listar_turnos"))

    # Si es GET, busca el turno por su ID para rellenar el formulario
    cur.execute("SELECT * FROM turno WHERE id=%s", (id,))
    turno = cur.fetchone()
    cur.close()
    conn.close()
    
    if not turno:
        flash("Turno no encontrado", "danger")
        return redirect(url_for("turno.listar_turnos"))
        
    return render_template("turno/editar.html", turno=turno)

# Ruta para eliminar un turno (solo por POST)
@turno_bp.route("/turnos/eliminar/<int:id>", methods=["POST"])
def eliminar_turno(id):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    # Borra el registro que coincida con el ID
    cur.execute("DELETE FROM turno WHERE id=%s", (id,))
    conn.commit()
    cur.close()
    conn.close()
    flash("Turno eliminado", "success")
    return redirect(url_for("turno.listar_turnos"))