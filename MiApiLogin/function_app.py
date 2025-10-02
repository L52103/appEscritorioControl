import azure.functions as func
from azure.functions import FunctionApp
import psycopg2
import os
import json

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