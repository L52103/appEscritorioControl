from flask import Blueprint, request, render_template, redirect, url_for, flash
from db import get_connection

area_bp = Blueprint("areatrabajo", __name__, template_folder="../templates")

@area_bp.route("/areas")
def listar_areas():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM areatrabajo")
    areas = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("areatrabajo/lista.html", areas=areas)

@area_bp.route("/areas/crear", methods=["GET", "POST"])
def crear_area():
    if request.method == "POST":
        data = request.form
        conn = get_connection()
        cur = conn.cursor()
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

@area_bp.route("/areas/editar/<int:id>", methods=["GET", "POST"])
def editar_area(id):
    conn = get_connection()
    cur = conn.cursor()
    if request.method == "POST":
        data = request.form
        cur.execute(
            "UPDATE areatrabajo SET nombre=%s, sucursal_id=%s WHERE id=%s",
            (data["nombre"], data["sucursal_id"], id)
        )
        conn.commit()
        cur.close()
        conn.close()
        flash("Área actualizada correctamente", "success")
        return redirect(url_for("areatrabajo.listar_areas"))

    cur.execute("SELECT * FROM areatrabajo WHERE id=%s", (id,))
    area = cur.fetchone()
    cur.close()
    conn.close()
    if not area:
        flash("Área no encontrada", "danger")
        return redirect(url_for("areatrabajo.listar_areas"))
    return render_template("areatrabajo/editar.html", area=area)

@area_bp.route("/areas/eliminar/<int:id>", methods=["POST"])
def eliminar_area(id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM areatrabajo WHERE id=%s", (id,))
    conn.commit()
    cur.close()
    conn.close()
    flash("Área eliminada", "success")
    return redirect(url_for("areatrabajo.listar_areas"))
