import os
from dotenv import load_dotenv
from flask import Flask, render_template

load_dotenv()  # carga las variables del .env

from routes.empresa import empresa_bp
from routes.sucursal import sucursal_bp
from routes.areatrabajo import area_bp
from routes.trabajador import trabajador_bp
from routes.asistencia import asistencia_bp
from routes.turno import turno_bp
from routes.turno_trabajador import turno_trabajador_bp

app = Flask(__name__)

app.secret_key = os.getenv("SECRET_KEY", "clave_por_defecto_para_dev")  # si no está, usa esta

# Registrar blueprints
app.register_blueprint(empresa_bp)
app.register_blueprint(sucursal_bp)
app.register_blueprint(area_bp)
app.register_blueprint(trabajador_bp)
app.register_blueprint(asistencia_bp)
app.register_blueprint(turno_bp)
app.register_blueprint(turno_trabajador_bp)

@app.route("/")
def index():
    return render_template("index.html")

if __name__ == "__main__":
    app.run(debug=True)