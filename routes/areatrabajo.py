
from flask import Blueprint, request, render_template, redirect, url_for, flash
from db import get_connection
from psycopg2.extras import DictCursor


area_bp = Blueprint("areatrabajo", __name__, template_folder="../templates")

@area_bp.route("/areas")
def listar_areas():
    conn = get_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    
    # Consulta mejorada con JOIN para obtener el nombre de la sucursal
    cur.execute("""
        SELECT a.id, a.nombre, a.sucursal_id, s.nombre AS sucursal_nombre
        FROM areatrabajo a
        LEFT JOIN sucursal s ON a.sucursal_id = s.id
        ORDER BY a.id ASC
    """)
    areas = cur.fetchall()
    
    cur.close()
    conn.close()
    return render_template("areatrabajo/lista.html", areas=areas)

# Ruta para crear una nueva área de trabajo
@area_bp.route("/areas/crear", methods=["GET", "POST"])
def crear_area():
    if request.method == "POST":
        data = request.form
        conn = get_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        # Inserta los nuevos datos en la tabla 'areatrabajo'
        cur.execute(
            "INSERT INTO areatrabajo (nombre, sucursal_id) VALUES (%s, %s)",
            (data["nombre"], data["sucursal_id"])
        )
        conn.commit()
        cur.close()
        conn.close()
        flash("Área creada exitosamente", "success")
        return redirect(url_for("areatrabajo.listar_areas"))
    return render_template("areatrabajo/crear.html")

# Ruta para editar un área de trabajo existente por su ID
@area_bp.route("/areas/editar/<int:id>", methods=["GET", "POST"])
def editar_area(id):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=DictCursor)

    if request.method == "POST":
        data = request.form
        # Actualiza el registro que coincida con el ID
        cur.execute(
            "UPDATE areatrabajo SET nombre=%s, sucursal_id=%s WHERE id=%s",
            (data["nombre"], data["sucursal_id"], id)
        )
        conn.commit()
        cur.close()
        conn.close()
        flash("Área actualizada correctamente", "success")
        return redirect(url_for("areatrabajo.listar_areas"))

    # Si es GET, busca el área por su ID para rellenar el formulario
    cur.execute("SELECT * FROM areatrabajo WHERE id=%s", (id,))
    area = cur.fetchone()
    cur.close()
    conn.close()
    
    if not area:
        flash("Área no encontrada", "danger")
        return redirect(url_for("areatrabajo.listar_areas"))
        
    return render_template("areatrabajo/editar.html", area=area)

# Ruta para eliminar un área de trabajo (solo por POST)
@area_bp.route("/areas/eliminar/<int:id>", methods=["POST"])
def eliminar_area(id):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    # Borra el registro que coincida con el ID
    cur.execute("DELETE FROM areatrabajo WHERE id=%s", (id,))
    conn.commit()
    cur.close()
    conn.close()
    flash("Área eliminada", "success")
    return redirect(url_for("areatrabajo.listar_areas"))