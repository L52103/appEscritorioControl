# Herramientas de Flask, conexión a BBDD y el nuevo DictCursor
from flask import Blueprint, request, render_template, redirect, url_for, flash
from db import get_connection
from psycopg2.extras import DictCursor

# Creamos el Blueprint para el módulo 'turno_trabajador'
turno_trabajador_bp = Blueprint("turno_trabajador", __name__, template_folder="../templates")

# Ruta para mostrar la lista de todas las asignaciones
@turno_trabajador_bp.route("/turnos_trabajadores")
def listar_turnos_trabajadores():
    conn = get_connection()
    # Usamos DictCursor para obtener resultados con nombres de columna
    cur = conn.cursor(cursor_factory=DictCursor)
    
    # Consulta mejorada con múltiples JOINs para obtener los nombres del trabajador y el tipo de turno
    cur.execute("""
        SELECT 
            tt.id, 
            tt.turno_id, 
            tt.trabajador_id,
            t.tipo_turno,
            CONCAT(w.nombre, ' ', w.apellido) AS trabajador_nombre
        FROM turno_trabajador tt
        LEFT JOIN turno t ON tt.turno_id = t.id
        LEFT JOIN trabajador w ON tt.trabajador_id = w.id
        ORDER BY tt.id ASC
    """)
    registros = cur.fetchall()
    
    cur.close()
    conn.close()
    return render_template("turno_trabajador/lista.html", registros=registros)

# Ruta para crear una nueva asignación
@turno_trabajador_bp.route("/turnos_trabajadores/crear", methods=["GET", "POST"])
def crear_turno_trabajador():
    if request.method == "POST":
        data = request.form
        conn = get_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        # Inserta los nuevos datos en la tabla 'turno_trabajador'
        cur.execute(
            "INSERT INTO turno_trabajador (turno_id, trabajador_id) VALUES (%s, %s)",
            (data["turno_id"], data["trabajador_id"])
        )
        conn.commit()
        cur.close()
        conn.close()
        flash("Asignación creada exitosamente", "success")
        return redirect(url_for("turno_trabajador.listar_turnos_trabajadores"))
    return render_template("turno_trabajador/crear.html")

# Ruta para editar una asignación existente por su ID
@turno_trabajador_bp.route("/turnos_trabajadores/editar/<int:id>", methods=["GET", "POST"])
def editar_turno_trabajador(id):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=DictCursor)

    if request.method == "POST":
        data = request.form
        # Actualiza el registro que coincida con el ID
        cur.execute(
            "UPDATE turno_trabajador SET turno_id=%s, trabajador_id=%s WHERE id=%s",
            (data["turno_id"], data["trabajador_id"], id)
        )
        conn.commit()
        cur.close()
        conn.close()
        flash("Asignación actualizada correctamente", "success")
        return redirect(url_for("turno_trabajador.listar_turnos_trabajadores"))

    # Si es GET, busca la asignación por su ID para rellenar el formulario
    cur.execute("SELECT * FROM turno_trabajador WHERE id=%s", (id,))
    registro = cur.fetchone()
    cur.close()
    conn.close()
    
    if not registro:
        flash("Registro no encontrado", "danger")
        return redirect(url_for("turno_trabajador.listar_turnos_trabajadores"))
        
    return render_template("turno_trabajador/editar.html", registro=registro)

# Ruta para eliminar una asignación (solo por POST)
@turno_trabajador_bp.route("/turnos_trabajadores/eliminar/<int:id>", methods=["POST"])
def eliminar_turno_trabajador(id):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    # Borra el registro que coincida con el ID
    cur.execute("DELETE FROM turno_trabajador WHERE id=%s", (id,))
    conn.commit()
    cur.close()
    conn.close()
    flash("Asignación eliminada", "success")
    return redirect(url_for("turno_trabajador.listar_turnos_trabajadores"))