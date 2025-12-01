from flask import Blueprint, request, render_template, redirect, url_for, flash
from db import get_connection
from psycopg2.extras import DictCursor

sueldos_bp = Blueprint("sueldos", __name__, template_folder="../templates")


def to_float_or_none(s):
    if s is None:
        return None
    s = s.strip()
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


@sueldos_bp.route("/sueldos")
def listar_sueldos():
    conn = get_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    cur.execute("""
        SELECT
            trabajador_id,
            trabajador,
            COALESCE(total_horas_trabajadas, 0) AS horas,
            COALESCE(total_ausencias, 0)       AS ausencias,

            CASE
              WHEN valor_hora IS NOT NULL AND array_length(valor_hora,1) >= 1
                THEN (valor_hora)[1]::numeric
              ELSE NULL
            END AS valor_hora,

            CASE
              WHEN valor_hora IS NOT NULL AND array_length(valor_hora,1) >= 1
                THEN ROUND(COALESCE(total_horas_trabajadas,0) * (valor_hora)[1]::numeric, 2)
              ELSE NULL
            END AS sueldo_calculado,

            CASE
              WHEN "Sueldo" IS NOT NULL AND array_length("Sueldo",1) >= 1
                THEN ("Sueldo")[1]::numeric
              ELSE NULL
            END AS sueldo_guardado

        FROM public.rendimiento
        ORDER BY trabajador_id;
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("sueldos/lista.html", data=rows)


@sueldos_bp.route("/sueldos/actualizar", methods=["POST"])
def actualizar_sueldo():
    trabajador_id = int(request.form["trabajador_id"])

    valor_hora    = to_float_or_none(request.form.get("valor_hora"))
    sueldo_manual = to_float_or_none(request.form.get("sueldo_manual"))

    if valor_hora is None and sueldo_manual is None:
        flash("No hay cambios que guardar.", "warning")
        return redirect(url_for("sueldos.listar_sueldos"))

    conn = get_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    try:
        if valor_hora is not None and sueldo_manual is None:
            cur.execute("""
                UPDATE public.rendimiento
                SET valor_hora = ARRAY[%s]::numeric[],
                    "Sueldo"   = ARRAY[
                                   ROUND(COALESCE(total_horas_trabajadas,0) * %s, 2)
                                 ]::numeric[]
                WHERE trabajador_id = %s;
            """, (valor_hora, valor_hora, trabajador_id))

        elif valor_hora is None and sueldo_manual is not None:
            cur.execute("""
                UPDATE public.rendimiento
                SET "Sueldo" = ARRAY[%s]::numeric[]
                WHERE trabajador_id = %s;
            """, (sueldo_manual, trabajador_id))

        else:
            cur.execute("""
                UPDATE public.rendimiento
                SET valor_hora = ARRAY[%s]::numeric[],
                    "Sueldo"   = ARRAY[%s]::numeric[]
                WHERE trabajador_id = %s;
            """, (valor_hora, sueldo_manual, trabajador_id))

        conn.commit()
        flash("Cambios guardados.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error al actualizar: {e}", "danger")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for("sueldos.listar_sueldos"))


@sueldos_bp.route("/sueldos/recalcular", methods=["POST"])
def recalcular_sueldos():
    conn = get_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    try:
        cur.execute("""
            UPDATE public.rendimiento r
            SET "Sueldo" = ARRAY[
                              ROUND(
                                COALESCE(r.total_horas_trabajadas,0) *
                                CASE
                                  WHEN r.valor_hora IS NOT NULL 
                                       AND array_length(r.valor_hora,1) >= 1
                                    THEN (r.valor_hora)[1]::numeric
                                  ELSE 0
                                END
                              , 2)
                            ]::numeric[]
            WHERE r.valor_hora IS NOT NULL
              AND array_length(r.valor_hora,1) >= 1;
        """)
        conn.commit()
        flash("Sueldos recalculados para todos los trabajadores con valor_hora.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error: {e}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("sueldos.listar_sueldos"))
