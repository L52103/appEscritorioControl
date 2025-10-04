# Herramientas de Flask, conexión a BBDD y el nuevo DictCursor
from flask import Blueprint, request, render_template, redirect, url_for, flash
from db import get_connection
from psycopg2.extras import DictCursor

# Creamos el Blueprint para el módulo 'sucursal'
sucursal_bp = Blueprint("sucursal", __name__, template_folder="../templates")

# Ruta para mostrar la lista de todas las sucursales
@sucursal_bp.route("/sucursales")
def listar_sucursales():
    conn = get_connection()
    # Usamos DictCursor para obtener resultados con nombres de columna
    cur = conn.cursor(cursor_factory=DictCursor)
    
    # Hemos mejorado la consulta con un JOIN para obtener el nombre de la empresa
    # en lugar de solo su ID. Esto enriquece los datos que podemos mostrar.
    cur.execute("""
        SELECT s.id, s.nombre, s.direccion, s.empresa_id, e.nombre AS empresa_nombre
        FROM sucursal s
        LEFT JOIN empresa e ON s.empresa_id = e.id
        ORDER BY s.id ASC
    """)
    sucursales = cur.fetchall()
    
    cur.close()
    conn.close()
    return render_template("sucursal/lista.html", sucursales=sucursales)

# Ruta para crear una nueva sucursal
@sucursal_bp.route("/sucursales/crear", methods=["GET", "POST"])
def crear_sucursal():
    # Si el usuario envía el formulario (POST)
    if request.method == "POST":
        data = request.form
        conn = get_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        # Inserta los nuevos datos en la tabla 'sucursal'
        cur.execute(
            "INSERT INTO sucursal (nombre, direccion, empresa_id) VALUES (%s, %s, %s)",
            (data["nombre"], data["direccion"], data["empresa_id"])
        )
        conn.commit()
        cur.close()
        conn.close()
        flash("Sucursal creada exitosamente", "success")
        return redirect(url_for("sucursal.listar_sucursales"))
        
    # Si es GET, solo muestra el formulario
    return render_template("sucursal/crear.html")

# Ruta para editar una sucursal existente por su ID
@sucursal_bp.route("/sucursales/editar/<int:id>", methods=["GET", "POST"])
def editar_sucursal(id):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=DictCursor)

    # Si el usuario envía el formulario con los cambios
    if request.method == "POST":
        data = request.form
        # Actualiza el registro que coincida con el ID
        cur.execute(
            "UPDATE sucursal SET nombre=%s, direccion=%s, empresa_id=%s WHERE id=%s",
            (data["nombre"], data["direccion"], data["empresa_id"], id)
        )
        conn.commit()
        cur.close()
        conn.close()
        flash("Sucursal actualizada correctamente", "success")
        return redirect(url_for("sucursal.listar_sucursales"))

    # Si es GET, busca la sucursal por su ID para rellenar el formulario
    cur.execute("SELECT * FROM sucursal WHERE id=%s", (id,))
    sucursal = cur.fetchone()
    cur.close()
    conn.close()
    
    if not sucursal:
        flash("Sucursal no encontrada", "danger")
        return redirect(url_for("sucursal.listar_sucursales"))
        
    return render_template("sucursal/editar.html", sucursal=sucursal)

# Ruta para eliminar una sucursal (solo por POST)
@sucursal_bp.route("/sucursales/eliminar/<int:id>", methods=["POST"])
def eliminar_sucursal(id):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    # Borra el registro que coincida con el ID
    cur.execute("DELETE FROM sucursal WHERE id=%s", (id,))
    conn.commit()
    cur.close()
    conn.close()
    flash("Sucursal eliminada", "success")
    return redirect(url_for("sucursal.listar_sucursales"))