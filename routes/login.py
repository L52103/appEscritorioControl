from flask import Blueprint, request, render_template, redirect, url_for, flash
from db import get_connection
from psycopg2.extras import DictCursor

VALID_USERNAME = "admin"
VALID_PASSWORD = "admin1234"

login_bp = Blueprint("login", __name__, template_folder="../templates")

@login_bp.route("/login", methods=['GET', 'POST']) 
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == VALID_USERNAME and password == VALID_PASSWORD:
            return redirect(url_for('index'))
        else:
            error = 'Credenciales incorrectas. Intenta nuevamente.'
    return render_template('login.html', error=error)

