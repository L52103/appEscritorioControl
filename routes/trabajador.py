# Importa las herramientas necesarias de Flask para crear la ruta, manejar peticiones, etc.
from flask import Blueprint, request, render_template, redirect, url_for, flash
# Importa nuestra función para conectar a la base de datos.
from db import get_connection
# Importa DictCursor para poder acceder a los datos por nombre de columna (ej: fila['nombre']).
from psycopg2.extras import DictCursor

# Crea un "Blueprint", que es como un mini-módulo de la aplicación.
# Esto nos ayuda a organizar el código relacionado con los trabajadores.
trabajador_bp = Blueprint("trabajador", __name__, template_folder="../templates")

# Define la ruta para ver la lista de trabajadores. Solo responde a peticiones GET.
@trabajador_bp.route("/trabajadores")
def listar_trabajadores():
    # Abre una nueva conexión con la base de datos.
    conn = get_connection()
    # Crea un cursor que devuelve filas como diccionarios.
    cur = conn.cursor(cursor_factory=DictCursor)
    
    # Ejecuta una consulta SQL para seleccionar todos los trabajadores y los ordena por ID.
    cur.execute("SELECT * FROM trabajador ORDER BY id ASC")
    # Recoge todos los resultados de la consulta en una lista.
    trabajadores = cur.fetchall()
    
    # Cierra el cursor y la conexión para liberar recursos.
    cur.close()
    conn.close()
    
    # Renderiza la plantilla HTML y le pasa la lista de trabajadores para que la muestre.
    return render_template("trabajador/lista.html", trabajadores=trabajadores)

# Define la ruta para crear un nuevo trabajador. Responde a GET (mostrar formulario) y POST (guardar datos).
@trabajador_bp.route("/trabajadores/crear", methods=["GET", "POST"])
def crear_trabajador():
    # Si el usuario envió el formulario (método POST).
    if request.method == "POST":
        # Recoge los datos enviados en el formulario.
        data = request.form
        
        conn = get_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        
        # Ejecuta la consulta SQL para insertar un nuevo registro en la tabla.
        # Usa %s para pasar los datos de forma segura y evitar inyección SQL.
        cur.execute(
            """INSERT INTO trabajador 
            (nombre, apellido, rut, biometria_huella, auth_user_id, sucursal_id, email, contrasena, es_admin)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (data["nombre"], data["apellido"], data["rut"], data.get("biometria_huella"), data.get("auth_user_id"), 
             data["sucursal_id"], data["email"], data["contrasena"], 'es_admin' in data) # 'es_admin' in data devuelve True si el checkbox fue marcado.
        )
        
        # Confirma los cambios en la base de datos.
        conn.commit()
        cur.close()
        conn.close()
        
        # Muestra un mensaje de éxito al usuario.
        flash("Trabajador creado exitosamente", "success")
        # Redirige al usuario de vuelta a la lista de trabajadores.
        return redirect(url_for("trabajador.listar_trabajadores"))
    
    # Si es una petición GET, simplemente muestra el formulario de creación.
    return render_template("trabajador/crear.html")

# Define la ruta para editar un trabajador específico por su ID.
@trabajador_bp.route("/trabajadores/editar/<int:id>", methods=["GET", "POST"])
def editar_trabajador(id):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=DictCursor)

    # Si el usuario envió el formulario de edición.
    if request.method == "POST":
        data = request.form
        # Ejecuta la consulta SQL para actualizar el registro que coincida con el ID.
        cur.execute(
            """UPDATE trabajador SET 
            nombre=%s, apellido=%s, rut=%s, biometria_huella=%s, auth_user_id=%s, sucursal_id=%s, 
            email=%s, contrasena=%s, es_admin=%s
            WHERE id=%s""",
            (data["nombre"], data["apellido"], data["rut"], data.get("biometria_huella"), data.get("auth_user_id"),
             data["sucursal_id"], data["email"], data["contrasena"], 'es_admin' in data, id)
        )
        conn.commit()
        cur.close()
        conn.close()
        flash("Trabajador actualizado correctamente", "success")
        return redirect(url_for("trabajador.listar_trabajadores"))

    # Si es una petición GET, primero busca el trabajador en la BBDD.
    cur.execute("SELECT * FROM trabajador WHERE id=%s", (id,))
    # Recoge un único resultado.
    trabajador = cur.fetchone()
    cur.close()
    conn.close()
    
    # Si no se encontró un trabajador con ese ID, avisa al usuario.
    if not trabajador:
        flash("Trabajador no encontrado", "danger")
        return redirect(url_for("trabajador.listar_trabajadores"))
        
    # Muestra el formulario de edición, pasándole los datos del trabajador para rellenar los campos.
    return render_template("trabajador/editar.html", trabajador=trabajador)

# Define la ruta para eliminar un trabajador. Solo responde a POST por seguridad.
@trabajador_bp.route("/trabajadores/eliminar/<int:id>", methods=["POST"])
def eliminar_trabajador(id):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    
    # Ejecuta la consulta SQL para borrar el registro que coincida con el ID.
    cur.execute("DELETE FROM trabajador WHERE id=%s", (id,))
    
    conn.commit()
    cur.close()
    conn.close()
    
    flash("Trabajador eliminado", "success")
    return redirect(url_for("trabajador.listar_trabajadores"))