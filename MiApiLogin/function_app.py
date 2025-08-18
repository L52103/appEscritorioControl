import azure.functions as func
from azure.functions import FunctionApp
import psycopg2
import os
import json

# Instancia principal de Azure Function App
app = FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# Endpoint: POST /api/login
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
