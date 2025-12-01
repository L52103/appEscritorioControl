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
        WITH horas_mes AS (
            SELECT 
                trabajador_id,
                SUM(EXTRACT(EPOCH FROM horas_trabajadas) / 3600.0) AS horas_mes
            FROM public.asistencia
            WHERE fecha >= date_trunc('month', CURRENT_DATE)
              AND fecha <  date_trunc('month', CURRENT_DATE) + INTERVAL '1 month'
              AND horas_trabajadas IS NOT NULL
            GROUP BY trabajador_id
        ),
        ausencias_mes AS (
            SELECT 
                trabajador_id,
                COUNT(*) AS ausencias_mes
            FROM public.asistencia
            WHERE is_asistencia = FALSE
              AND fecha >= date_trunc('month', CURRENT_DATE)
              AND fecha <  date_trunc('month', CURRENT_DATE) + INTERVAL '1 month'
            GROUP BY trabajador_id
        )
        SELECT
            r.trabajador_id,
            r.trabajador,

            -- horas y ausencias del mes actual calculadas desde asistencia
            COALESCE(h.horas_mes, 0)      AS horas,
            COALESCE(a.ausencias_mes, 0)  AS ausencias,

            -- valor_hora como número (1er elemento del array)
            CASE
              WHEN r.valor_hora IS NOT NULL 
                   AND array_length(r.valor_hora,1) >= 1
                THEN (r.valor_hora)[1]::numeric
              ELSE NULL
            END AS valor_hora,

            -- Sueldo calculado usando horas del mes actual * valor_hora
            CASE
              WHEN r.valor_hora IS NOT NULL 
                   AND array_length(r.valor_hora,1) >= 1
                THEN ROUND(
                        COALESCE(h.horas_mes,0) * (r.valor_hora)[1]::numeric
                     , 2)
              ELSE NULL
            END AS sueldo_calculado,

            -- Sueldo guardado como número (1er elemento del array "Sueldo")
            CASE
              WHEN r."Sueldo" IS NOT NULL 
                   AND array_length(r."Sueldo",1) >= 1
                THEN (r."Sueldo")[1]::numeric
              ELSE NULL
            END AS sueldo_guardado

        FROM public.rendimiento r
        LEFT JOIN horas_mes     h ON h.trabajador_id = r.trabajador_id
        LEFT JOIN ausencias_mes a ON a.trabajador_id = r.trabajador_id
        ORDER BY r.trabajador_id;
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
