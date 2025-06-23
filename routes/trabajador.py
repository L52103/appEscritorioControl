from flask import Blueprint, request, render_template, redirect, url_for, flash
from db import get_connection

trabajador_bp = Blueprint("trabajador", __name__, template_folder="../templates")

@trabajador_bp.route("/trabajadores")
def listar_trabajadores():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM trabajador")
    trabajadores = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("trabajador/lista.html", trabajadores=trabajadores)

@trabajador_bp.route("/trabajadores/crear", methods=["GET", "POST"])
def crear_trabajador():
    if request.method == "POST":
        data = request.form
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO trabajador 
            (nombre, apellido, rut, biometria_huella, auth_user_id, sucursal_id, email, contrasena, es_admin)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (data["nombre"], data["apellido"], data["rut"], data["biometria_huella"], data["auth_user_id"], 
             data["sucursal_id"], data["email"], data["contrasena"], data["es_admin"] == 'true')
        )
        conn.commit()
        cur.close()
        conn.close()
        flash("Trabajador creado exitosamente", "success")
        return redirect(url_for("trabajador.listar_trabajadores"))
    return render_template("trabajador/crear.html")

@trabajador_bp.route("/trabajadores/editar/<int:id>", methods=["GET", "POST"])
def editar_trabajador(id):
    conn = get_connection()
    cur = conn.cursor()
    if request.method == "POST":
        data = request.form
        cur.execute(
            """UPDATE trabajador SET 
            nombre=%s, apellido=%s, rut=%s, biometria_huella=%s, auth_user_id=%s, sucursal_id=%s, 
            email=%s, contrasena=%s, es_admin=%s
            WHERE id=%s""",
            (data["nombre"], data["apellido"], data["rut"], data["biometria_huella"], data["auth_user_id"],
             data["sucursal_id"], data["email"], data["contrasena"], data["es_admin"] == 'true', id)
        )
        conn.commit()
        cur.close()
        conn.close()
        flash("Trabajador actualizado correctamente", "success")
        return redirect(url_for("trabajador.listar_trabajadores"))

    cur.execute("SELECT * FROM trabajador WHERE id=%s", (id,))
    trabajador = cur.fetchone()
    cur.close()
    conn.close()
    if not trabajador:
        flash("Trabajador no encontrado", "danger")
        return redirect(url_for("trabajador.listar_trabajadores"))
    return render_template("trabajador/editar.html", trabajador=trabajador)

@trabajador_bp.route("/trabajadores/eliminar/<int:id>", methods=["POST"])
def eliminar_trabajador(id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM trabajador WHERE id=%s", (id,))
    conn.commit()
    cur.close()
    conn.close()
    flash("Trabajador eliminado", "success")
    return redirect(url_for("trabajador.listar_trabajadores"))
