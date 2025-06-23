from flask import Blueprint, request, render_template, redirect, url_for, flash
from db import get_connection

sucursal_bp = Blueprint("sucursal", __name__, template_folder="../templates")

@sucursal_bp.route("/sucursales")
def listar_sucursales():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sucursal")
    sucursales = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("sucursal/lista.html", sucursales=sucursales)

@sucursal_bp.route("/sucursales/crear", methods=["GET", "POST"])
def crear_sucursal():
    if request.method == "POST":
        data = request.form
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO sucursal (nombre, direccion, empresa_id) VALUES (%s, %s, %s)",
            (data["nombre"], data["direccion"], data["empresa_id"])
        )
        conn.commit()
        cur.close()
        conn.close()
        flash("Sucursal creada exitosamente", "success")
        return redirect(url_for("sucursal.listar_sucursales"))
    return render_template("sucursal/crear.html")

@sucursal_bp.route("/sucursales/editar/<int:id>", methods=["GET", "POST"])
def editar_sucursal(id):
    conn = get_connection()
    cur = conn.cursor()
    if request.method == "POST":
        data = request.form
        cur.execute(
            "UPDATE sucursal SET nombre=%s, direccion=%s, empresa_id=%s WHERE id=%s",
            (data["nombre"], data["direccion"], data["empresa_id"], id)
        )
        conn.commit()
        cur.close()
        conn.close()
        flash("Sucursal actualizada correctamente", "success")
        return redirect(url_for("sucursal.listar_sucursales"))

    cur.execute("SELECT * FROM sucursal WHERE id=%s", (id,))
    sucursal = cur.fetchone()
    cur.close()
    conn.close()
    if not sucursal:
        flash("Sucursal no encontrada", "danger")
        return redirect(url_for("sucursal.listar_sucursales"))
    return render_template("sucursal/editar.html", sucursal=sucursal)

@sucursal_bp.route("/sucursales/eliminar/<int:id>", methods=["POST"])
def eliminar_sucursal(id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM sucursal WHERE id=%s", (id,))
    conn.commit()
    cur.close()
    conn.close()
    flash("Sucursal eliminada", "success")
    return redirect(url_for("sucursal.listar_sucursales"))
