from flask import Blueprint, request, render_template, redirect, url_for, flash
from db import get_connection
from psycopg2.extras import DictCursor

# Creamos el Blueprint para el módulo 'empresa'
empresa_bp = Blueprint("empresa", __name__, template_folder="../templates")

# Ruta para mostrar la lista de todas las empresas
@empresa_bp.route("/empresas")
def listar_empresas():
    conn = get_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    cur.execute("SELECT * FROM empresa ORDER BY id ASC")
    empresas = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("empresa/lista.html", empresas=empresas)

@empresa_bp.route("/empresas/crear", methods=["GET", "POST"])
def crear_empresa():
    # Si el usuario envía el formulario (POST)
    if request.method == "POST":
        data = request.form
        conn = get_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        # Inserta los nuevos datos en la tabla 'empresa'
        cur.execute(
            "INSERT INTO empresa (nombre, rut, direccion) VALUES (%s, %s, %s)",
            (data["nombre"], data["rut"], data["direccion"])
        )
        conn.commit()
        cur.close()
        conn.close()
        flash("Empresa creada exitosamente", "success")
        return redirect(url_for("empresa.listar_empresas"))
    return render_template("empresa/crear.html")

# Ruta para editar una empresa existente por su ID
@empresa_bp.route("/empresas/editar/<int:id>", methods=["GET", "POST"])
def editar_empresa(id):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=DictCursor)

    if request.method == "POST":
        data = request.form
        cur.execute(
            "UPDATE empresa SET nombre=%s, rut=%s, direccion=%s WHERE id=%s",
            (data["nombre"], data["rut"], data["direccion"], id)
        )
        conn.commit()
        cur.close()
        conn.close()
        flash("Empresa actualizada correctamente", "success")
        return redirect(url_for("empresa.listar_empresas"))
    
    cur.execute("SELECT * FROM empresa WHERE id=%s", (id,))
    empresa = cur.fetchone()
    cur.close()
    conn.close()
    
    if not empresa:
        flash("Empresa no encontrada", "danger")
        return redirect(url_for("empresa.listar_empresas"))
    
    return render_template("empresa/editar.html", empresa=empresa)

@empresa_bp.route("/empresas/eliminar/<int:id>", methods=["POST"])
def eliminar_empresa(id):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    cur.execute("DELETE FROM empresa WHERE id=%s", (id,))
    conn.commit()
    cur.close()
    conn.close()
    flash("Empresa eliminada", "success")
    return redirect(url_for("empresa.listar_empresas"))