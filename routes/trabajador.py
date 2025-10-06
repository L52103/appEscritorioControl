from flask import Blueprint, request, render_template, redirect, url_for, flash
from db import get_connection
from psycopg2.extras import DictCursor

trabajador_bp = Blueprint("trabajador", __name__, template_folder="../templates")

@trabajador_bp.route("/trabajadores")
def listar_trabajadores():
    conn = get_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    cur.execute("SELECT * FROM trabajador ORDER BY id ASC")
    trabajadores = cur.fetchall()
    cur.close()
    conn.close()
    
    return render_template("trabajador/lista.html", trabajadores=trabajadores)

@trabajador_bp.route("/trabajadores/crear", methods=["GET", "POST"])
def crear_trabajador():
    if request.method == "POST":
        data = request.form
        
        conn = get_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        

        cur.execute(
            """INSERT INTO trabajador 
            (nombre, apellido, rut, biometria_huella, auth_user_id, sucursal_id, email, contrasena, es_admin)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (data["nombre"], data["apellido"], data["rut"], data.get("biometria_huella"), data.get("auth_user_id"), 
             data["sucursal_id"], data["email"], data["contrasena"], 'es_admin' in data) # 'es_admin' in data devuelve True si el checkbox fue marcado.
        )
        conn.commit()
        cur.close()
        conn.close()
        flash("Trabajador creado exitosamente", "success")
        return redirect(url_for("trabajador.listar_trabajadores"))
    
    return render_template("trabajador/crear.html")

# Define la ruta para editar un trabajador específico por su ID.
@trabajador_bp.route("/trabajadores/editar/<int:id>", methods=["GET", "POST"])
def editar_trabajador(id):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=DictCursor)

    # Si el usuario envió el formulario de edición.
    if request.method == "POST":
        data = request.form
        # Ejecuta la consulta SQL para actualizar el registro que coincida con el ID.
        cur.execute(
            """UPDATE trabajador SET 
            nombre=%s, apellido=%s, rut=%s, biometria_huella=%s, auth_user_id=%s, sucursal_id=%s, 
            email=%s, contrasena=%s, es_admin=%s
            WHERE id=%s""",
            (data["nombre"], data["apellido"], data["rut"], data.get("biometria_huella"), data.get("auth_user_id"),
             data["sucursal_id"], data["email"], data["contrasena"], 'es_admin' in data, id)
        )
        conn.commit()
        cur.close()
        conn.close()
        flash("Trabajador actualizado correctamente", "success")
        return redirect(url_for("trabajador.listar_trabajadores"))

    # Si es una petición GET, primero busca el trabajador en la BBDD.
    cur.execute("SELECT * FROM trabajador WHERE id=%s", (id,))
    trabajador = cur.fetchone()
    cur.close()
    conn.close()
    
    if not trabajador:
        flash("Trabajador no encontrado", "danger")
        return redirect(url_for("trabajador.listar_trabajadores"))
        
    return render_template("trabajador/editar.html", trabajador=trabajador)

# Define la ruta para eliminar un trabajador. Solo responde a POST por seguridad.
@trabajador_bp.route("/trabajadores/eliminar/<int:id>", methods=["POST"])
def eliminar_trabajador(id):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    
    cur.execute("DELETE FROM trabajador WHERE id=%s", (id,))
    
    conn.commit()
    cur.close()
    conn.close()
    
    flash("Trabajador eliminado", "success")
    return redirect(url_for("trabajador.listar_trabajadores"))