from flask import Blueprint, request, render_template, redirect, url_for, flash
from db import get_connection

turno_trabajador_bp = Blueprint("turno_trabajador", __name__, template_folder="../templates")

@turno_trabajador_bp.route("/turnos_trabajadores")
def listar_turnos_trabajadores():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM turno_trabajador")
    registros = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("turno_trabajador/lista.html", registros=registros)

@turno_trabajador_bp.route("/turnos_trabajadores/crear", methods=["GET", "POST"])
def crear_turno_trabajador():
    if request.method == "POST":
        data = request.form
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO turno_trabajador (turno_id, trabajador_id) VALUES (%s, %s)",
            (data["turno_id"], data["trabajador_id"])
        )
        conn.commit()
        cur.close()
        conn.close()
        flash("Registro creado exitosamente", "success")
        return redirect(url_for("turno_trabajador.listar_turnos_trabajadores"))
    return render_template("turno_trabajador/crear.html")

@turno_trabajador_bp.route("/turnos_trabajadores/editar/<int:id>", methods=["GET", "POST"])
def editar_turno_trabajador(id):
    conn = get_connection()
    cur = conn.cursor()
    if request.method == "POST":
        data = request.form
        cur.execute(
            "UPDATE turno_trabajador SET turno_id=%s, trabajador_id=%s WHERE id=%s",
            (data["turno_id"], data["trabajador_id"], id)
        )
        conn.commit()
        cur.close()
        conn.close()
        flash("Registro actualizado correctamente", "success")
        return redirect(url_for("turno_trabajador.listar_turnos_trabajadores"))

    cur.execute("SELECT * FROM turno_trabajador WHERE id=%s", (id,))
    registro = cur.fetchone()
    cur.close()
    conn.close()
    if not registro:
        flash("Registro no encontrado", "danger")
        return redirect(url_for("turno_trabajador.listar_turnos_trabajadores"))
    return render_template("turno_trabajador/editar.html", registro=registro)

@turno_trabajador_bp.route("/turnos_trabajadores/eliminar/<int:id>", methods=["POST"])
def eliminar_turno_trabajador(id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM turno_trabajador WHERE id=%s", (id,))
    conn.commit()
    cur.close()
    conn.close()
    flash("Registro eliminado", "success")
    return redirect(url_for("turno_trabajador.listar_turnos_trabajadores"))
