
import os
from dotenv import load_dotenv
from flask import Flask, redirect, render_template, url_for

load_dotenv()

from routes.empresa import empresa_bp
from routes.sucursal import sucursal_bp
from routes.areatrabajo import area_bp
from routes.trabajador import trabajador_bp
from routes.asistencia import asistencia_bp
from routes.turno import turno_bp
from routes.turno_trabajador import turno_trabajador_bp
from routes.reportes import reportes_bp 
from routes.sueldos import sueldos_bp
from routes.login import login_bp

app = Flask(__name__)

app.secret_key = os.getenv("SECRET_KEY", "clave_por_defecto_para_dev")

#  blueprints
app.register_blueprint(empresa_bp)
app.register_blueprint(sucursal_bp)
app.register_blueprint(area_bp)
app.register_blueprint(trabajador_bp)
app.register_blueprint(asistencia_bp)
app.register_blueprint(turno_bp)
app.register_blueprint(turno_trabajador_bp)
app.register_blueprint(reportes_bp) 
app.register_blueprint(sueldos_bp)
app.register_blueprint(login_bp)

@app.route("/")
def home():
    return redirect(url_for('login.login'))

@app.route("/index")
def index():
    return render_template("index.html")



if __name__ == "__main__":
    app.run(debug=True)