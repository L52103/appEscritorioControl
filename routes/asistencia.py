from flask import Blueprint, render_template
from db import get_connection

asistencia_bp = Blueprint("asistencia", __name__, template_folder="../templates")

@asistencia_bp.route("/asistencias", methods=["GET"])
def listar_asistencias():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM asistencia")
    asistencias = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("asistencia/lista.html", asistencias=asistencias)
