import azure.functions as func
from azure.functions import FunctionApp
import psycopg2
import os
import json
import pytz  
from datetime import datetime

CHILE_TZ = pytz.timezone("America/Santiago")

# Instancia principal de Azure 
app = FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

#  POST /api/login
@app.function_name(name="login")
@app.route(route="login", methods=["POST"])
def login(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = req.get_json()
        email = data.get("email")
        password = data.get("password")

        if not email or not password:
            return func.HttpResponse(
                json.dumps({"message": "Faltan email o password"}),
                mimetype="application/json",
                status_code=400
            )

        conn = psycopg2.connect(
            host=os.environ["PGHOST"],
            database=os.environ["PGDATABASE"],
            user=os.environ["PGUSER"],
            password=os.environ["PGPASSWORD"],
            port=os.environ["PGPORT"]
        )
        cur = conn.cursor()
        cur.execute(
            "SELECT rut, nombre, email FROM trabajador WHERE email=%s AND contrasena=%s",
            (email, password)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()

        if row:
            rut, nombre, email_db = row
            response_data = {
                "message": "Login exitoso",
                "rut": rut,
                "nombre": nombre,
                "email": email_db
            }
            return func.HttpResponse(
                json.dumps(response_data),
                mimetype="application/json",
                status_code=200
            )
        else:
            return func.HttpResponse(
                json.dumps({"message": "Credenciales inválidas"}),
                mimetype="application/json",
                status_code=401
            )
    except Exception as e:
        return func.HttpResponse(
            json.dumps({"message": f"Error: {str(e)}"}),
            mimetype="application/json",
            status_code=500
        )

@app.function_name(name="asistencia_mensaje_upsert_ultima")
@app.route(route="asistencia/mensaje", methods=["POST"])
def asistencia_mensaje_upsert_ultima(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = req.get_json()
        trabajador_id = data.get("trabajador_id")
        email = data.get("email")
        rut = data.get("rut")
        mensaje = (data.get("mensaje") or "").strip()

        if not mensaje:
            return func.HttpResponse(
                json.dumps({"message": "Falta 'mensaje'"}),
                mimetype="application/json",
                status_code=400
            )

        conn = psycopg2.connect(
            host=os.environ["PGHOST"],
            database=os.environ["PGDATABASE"],
            user=os.environ["PGUSER"],
            password=os.environ["PGPASSWORD"],
            port=os.environ["PGPORT"]
        )
        conn.autocommit = False
        cur = conn.cursor()

        # Resolver trabajador_id
        if not trabajador_id:
            if email:
                cur.execute("SELECT id FROM trabajador WHERE email=%s LIMIT 1", (email,))
            elif rut:
                cur.execute("SELECT id FROM trabajador WHERE rut=%s LIMIT 1", (rut,))
            else:
                cur.close(); conn.close()
                return func.HttpResponse(
                    json.dumps({"message": "Debes enviar 'trabajador_id', 'email' o 'rut'."}),
                    mimetype="application/json",
                    status_code=400
                )
            row = cur.fetchone()
            if not row:
                cur.close(); conn.close()
                return func.HttpResponse(
                    json.dumps({"message": "Trabajador no encontrado."}),
                    mimetype="application/json",
                    status_code=404
                )
            trabajador_id = row[0]

        # Tomar la última asistencia de ese trabajador
        cur.execute("""
            SELECT id
            FROM asistencia
            WHERE trabajador_id = %s
            ORDER BY
                fecha DESC NULLS LAST,
                hora_entrada DESC NULLS LAST,
                id DESC
            LIMIT 1
            FOR UPDATE
        """, (trabajador_id,))
        last = cur.fetchone()

        if last:
            asistencia_id = last[0]

            #  Actualizar la última asistencia con el mensaje entrante
            cur.execute("""
                UPDATE asistencia
                   SET mensaje = %s,
                       procesado_ia = FALSE,
                       -- limpiamos/permitimos que la IA reprocese
                       categoria = NULL,
                       justificado = True,
                       fecha_inicio_inasistencia = NULL,
                       fecha_fin_inasistencia = NULL,
                       duracion_dias = NULL
                 WHERE id = %s
             RETURNING id, fecha, hora_entrada, hora_salida, geolocalizacion,
                       trabajador_id, numero_asistencia, is_asistencia, justificado,
                       procesado_ia, mensaje, categoria, fecha_inicio_inasistencia,
                       fecha_fin_inasistencia, duracion_dias
            """, (mensaje, asistencia_id))
            updated = cur.fetchone()
            conn.commit()

            cur.close(); conn.close()
            return func.HttpResponse(
                json.dumps({
                    "message": "Mensaje actualizado en la última asistencia",
                    "registro": row_to_dict(updated)
                }),
                mimetype="application/json",
                status_code=200
            )
        else:
            # Si no hay asistencias previas se crea una fila mínima para adjuntar el mensaje
            cur.execute("""
                INSERT INTO asistencia (
                    fecha, hora_entrada, hora_salida, geolocalizacion,
                    trabajador_id, numero_asistencia, is_asistencia, justificado,
                    procesado_ia, mensaje, categoria, fecha_inicio_inasistencia,
                    fecha_fin_inasistencia, duracion_dias
                )
                VALUES (
                    CURRENT_DATE, NULL, NULL, NULL,
                    %s, NULL, FALSE, NULL,
                    FALSE, %s, NULL, NULL,
                    NULL, NULL
                )
                RETURNING id, fecha, hora_entrada, hora_salida, geolocalizacion,
                          trabajador_id, numero_asistencia, is_asistencia, justificado,
                          procesado_ia, mensaje, categoria, fecha_inicio_inasistencia,
                          fecha_fin_inasistencia, duracion_dias
            """, (trabajador_id, mensaje))
            created = cur.fetchone()
            conn.commit()

            cur.close(); conn.close()
            return func.HttpResponse(
                json.dumps({
                    "message": "No existía asistencia previa: se creó registro y se guardó el mensaje",
                    "registro": row_to_dict(created)
                }),
                mimetype="application/json",
                status_code=201
            )

    except Exception as e:
        # Si hubo error, intentar rollback
        try:
            conn.rollback()
        except:
            pass
        return func.HttpResponse(
            json.dumps({"message": f"Error: {str(e)}"}),
            mimetype="application/json",
            status_code=500
        )

def row_to_dict(row):
    # Ajusta si tu SELECT cambia el orden de columnas
    keys = [
        "id","fecha","hora_entrada","hora_salida","geolocalizacion",
        "trabajador_id","numero_asistencia","is_asistencia","justificado",
        "procesado_ia","mensaje","categoria","fecha_inicio_inasistencia",
        "fecha_fin_inasistencia","duracion_dias"
    ]
    out = {}
    for k, v in zip(keys, row):
        # serializa datetimes/dates a ISO cuando haga falta
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out



@app.function_name(name="asistencia_marcar_ingreso")
@app.route(route="asistencia/ingreso", methods=["POST"])
def asistencia_marcar_ingreso(req: func.HttpRequest) -> func.HttpResponse:
    conn = None
    try:
        data = req.get_json()
        trabajador_id = data.get("trabajador_id")
        email = data.get("email")
        rut = data.get("rut")

        if not (trabajador_id or email or rut):
            return func.HttpResponse(
                json.dumps({"message": "Debes enviar 'trabajador_id' o 'email' o 'rut'."}),
                mimetype="application/json", status_code=400
            )

        # Fecha/hora en Chile
        now_cl = datetime.now(CHILE_TZ)
        fecha_cl = now_cl.date()
        hora_cl = now_cl.time()

        conn = get_conn()
        conn.autocommit = False
        cur = conn.cursor()

        # Resolver trabajador
        trabajador_id = resolve_trabajador_id(cur, trabajador_id, email, rut)
        if not trabajador_id:
            cur.close(); conn.close()
            return func.HttpResponse(
                json.dumps({"message": "Trabajador no encontrado."}),
                mimetype="application/json", status_code=404
            )

        # Traer la última asistencia con bloqueo
        cur.execute("""
            SELECT id, fecha, hora_entrada, hora_salida
              FROM asistencia
             WHERE trabajador_id = %s
             ORDER BY fecha DESC NULLS LAST, id DESC
             LIMIT 1
             FOR UPDATE
        """, (trabajador_id,))
        last = cur.fetchone()

        # Caso 1: existe registro y NO tiene hora_entrada -> actualizar con hora de Chile
        if last:
            a_id, a_fecha, a_hin, a_hout = last
            if a_hin is None:
                cur.execute("""
                    UPDATE asistencia
                       SET fecha = %s,
                           hora_entrada = %s,
                           is_asistencia = TRUE
                     WHERE id = %s
                 RETURNING id, fecha, hora_entrada, hora_salida, trabajador_id, is_asistencia
                """, (fecha_cl, hora_cl, a_id))
                updated = cur.fetchone()
                conn.commit()
                cur.close(); conn.close()
                return func.HttpResponse(
                    json.dumps({"message": "Ingreso marcado", "registro": serialize_registro(updated)}),
                    mimetype="application/json", status_code=200
                )
            # ya tenía hora_entrada y no tiene salida y es hoy -> 409
            if a_hout is None and a_fecha == fecha_cl:
                conn.rollback(); cur.close(); conn.close()
                return func.HttpResponse(
                    json.dumps({"message": "La asistencia de hoy ya tiene hora de entrada."}),
                    mimetype="application/json", status_code=409
                )

        # Caso 2: crear nuevo registro para HOY
        cur.execute("""
            INSERT INTO asistencia (
                fecha, hora_entrada, hora_salida, geolocalizacion,
                trabajador_id, numero_asistencia, is_asistencia, justificado,
                procesado_ia, mensaje, categoria, fecha_inicio_inasistencia,
                fecha_fin_inasistencia, duracion_dias
            )
            VALUES (
                %s, %s, NULL, NULL,
                %s, NULL, TRUE, FALSE,
                FALSE, NULL, NULL, NULL,
                NULL, NULL
            )
            RETURNING id, fecha, hora_entrada, hora_salida, trabajador_id, is_asistencia
        """, (fecha_cl, hora_cl, trabajador_id))
        created = cur.fetchone()
        conn.commit()
        cur.close(); conn.close()
        return func.HttpResponse(
            json.dumps({"message": "Ingreso marcado (nuevo registro)", "registro": serialize_registro(created)}),
            mimetype="application/json", status_code=201
        )

    except Exception as e:
        try:
            if conn: conn.rollback()
        except:
            pass
        return func.HttpResponse(
            json.dumps({"message": f"Error: {str(e)}"}),
            mimetype="application/json", status_code=500
        )


def get_conn():
    return psycopg2.connect(
        host=os.environ["PGHOST"],
        database=os.environ["PGDATABASE"],
        user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
        port=os.environ["PGPORT"]
    )

def serialize_registro(row):
    # Espera: id, fecha, hora_entrada, hora_salida, trabajador_id, is_asistencia
    keys = ["id", "fecha", "hora_entrada", "hora_salida", "trabajador_id", "is_asistencia"]
    out = {}
    for k, v in zip(keys, row):
        out[k] = v.isoformat() if hasattr(v, "isoformat") else v
    return out

def resolve_trabajador_id(cur, trabajador_id, email, rut):
    if trabajador_id:
        return int(trabajador_id)
    if email:
        cur.execute("SELECT id FROM trabajador WHERE email=%s LIMIT 1", (email,))
    elif rut:
        cur.execute("SELECT id FROM trabajador WHERE rut=%s LIMIT 1", (rut,))
    else:
        return None
    r = cur.fetchone()
    return r[0] if r else None


# ---------- POST /api/asistencia/salida ----------

@app.function_name(name="asistencia_marcar_salida")
@app.route(route="asistencia/salida", methods=["POST"])
def asistencia_marcar_salida(req: func.HttpRequest) -> func.HttpResponse:
    conn = None
    try:
        data = req.get_json()
        trabajador_id = data.get("trabajador_id")
        email = data.get("email")
        rut = data.get("rut")

        if not (trabajador_id or email or rut):
            return func.HttpResponse(
                json.dumps({"message": "Debes enviar 'trabajador_id' o 'email' o 'rut'."}),
                mimetype="application/json", status_code=400
            )

        # Fecha/hora en Chile
        now_cl = datetime.now(CHILE_TZ)
        fecha_cl = now_cl.date()
        hora_cl = now_cl.time()

        conn = get_conn()
        conn.autocommit = False
        cur = conn.cursor()

        # Resolver trabajador
        trabajador_id = resolve_trabajador_id(cur, trabajador_id, email, rut)
        if not trabajador_id:
            cur.close(); conn.close()
            return func.HttpResponse(
                json.dumps({"message": "Trabajador no encontrado."}),
                mimetype="application/json", status_code=404
            )

        # Buscar asistencia de HOY con entrada marcada y salida NULL
        cur.execute("""
            SELECT id, fecha, hora_entrada, hora_salida
              FROM asistencia
             WHERE trabajador_id = %s
               AND fecha = %s
             ORDER BY id DESC
             LIMIT 1
             FOR UPDATE
        """, (trabajador_id, fecha_cl))
        row = cur.fetchone()

        if not row:
            conn.rollback(); cur.close(); conn.close()
            return func.HttpResponse(
                json.dumps({"message": "No existe asistencia de hoy para marcar salida."}),
                mimetype="application/json", status_code=404
            )

        a_id, a_fecha, a_hin, a_hout = row

        if a_hin is None:
            conn.rollback(); cur.close(); conn.close()
            return func.HttpResponse(
                json.dumps({"message": "La asistencia de hoy no tiene hora de entrada."}),
                mimetype="application/json", status_code=409
            )

        if a_hout is not None:
            conn.rollback(); cur.close(); conn.close()
            return func.HttpResponse(
                json.dumps({"message": "La asistencia de hoy ya tiene hora de salida."}),
                mimetype="application/json", status_code=409
            )

        # Marcar salida con hora Chile
        cur.execute("""
            UPDATE asistencia
               SET hora_salida = %s,
                   is_asistencia = TRUE
             WHERE id = %s
         RETURNING id, fecha, hora_entrada, hora_salida, trabajador_id, is_asistencia
        """, (hora_cl, a_id))
        updated = cur.fetchone()
        conn.commit()
        cur.close(); conn.close()
        return func.HttpResponse(
            json.dumps({"message": "Salida marcada", "registro": serialize_registro(updated)}),
            mimetype="application/json", status_code=200
        )

    except Exception as e:
        try:
            if conn: conn.rollback()
        except:
            pass
        return func.HttpResponse(
            json.dumps({"message": f"Error: {str(e)}"}),
            mimetype="application/json", status_code=500
        )