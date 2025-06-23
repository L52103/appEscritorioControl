from flask import Blueprint, request, render_template, redirect, url_for, flash
from db import get_connection

turno_bp = Blueprint("turno", __name__, template_folder="../templates")

@turno_bp.route("/turnos")
def listar_turnos():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM turno")
    turnos = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("turno/lista.html", turnos=turnos)

@turno_bp.route("/turnos/crear", methods=["GET", "POST"])
def crear_turno():
    if request.method == "POST":
        data = request.form
        conn = get_connection()
        cur = conn.cursor()
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

@turno_bp.route("/turnos/editar/<int:id>", methods=["GET", "POST"])
def editar_turno(id):
    conn = get_connection()
    cur = conn.cursor()
    if request.method == "POST":
        data = request.form
        cur.execute(
            """UPDATE turno SET horario_inicio=%s, horario_fin=%s, tipo_turno=%s, area_id=%s WHERE id=%s""",
            (data["horario_inicio"], data["horario_fin"], data["tipo_turno"], data["area_id"], id)
        )
        conn.commit()
        cur.close()
        conn.close()
        flash("Turno actualizado correctamente", "success")
        return redirect(url_for("turno.listar_turnos"))

    cur.execute("SELECT * FROM turno WHERE id=%s", (id,))
    turno = cur.fetchone()
    cur.close()
    conn.close()
    if not turno:
        flash("Turno no encontrado", "danger")
        return redirect(url_for("turno.listar_turnos"))
    return render_template("turno/editar.html", turno=turno)

@turno_bp.route("/turnos/eliminar/<int:id>", methods=["POST"])
def eliminar_turno(id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM turno WHERE id=%s", (id,))
    conn.commit()
    cur.close()
    conn.close()
    flash("Turno eliminado", "success")
    return redirect(url_for("turno.listar_turnos"))
