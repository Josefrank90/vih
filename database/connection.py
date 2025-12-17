import mysql.connector
from flask import current_app, g
from functools import wraps 

db_pool = None 

def get_db():
    """Inicializa y devuelve una conexión directa (NO de Pool), utilizando las claves de Config."""
    if 'db' not in g:
        try:
            
            g.db = mysql.connector.connect(
                host=current_app.config['MYSQL_HOST'],
                user=current_app.config['MYSQL_USER'],
                password=current_app.config['MYSQL_PASSWORD'],
                database=current_app.config['MYSQL_DB'],
                port=current_app.config['MYSQL_PORT'], 
                raise_on_warnings=True # Útil para depuración
            )
        except mysql.connector.Error as e:
            current_app.logger.error(f"Error al conectar a la base de datos: {e}")
            # Lanzamos la excepción para que Flask muestre el rastreo completo
            raise 
    return g.db

def close_db(e=None):
    """Cierra la conexión a la base de datos."""
    db = g.pop('db', None)
    if db is not None and db.is_connected():
        db.close()

def execute_query(query, params=None, fetch_one=False, commit=False):
    """
    Ejecuta una consulta SQL.
    - Si commit=True y es INSERT, devuelve lastrowid (int).
    - Si commit=True y es UPDATE/DELETE, devuelve rowcount (int).
    """
    conn = get_db()
    # Usamos cursor(dictionary=True) para que los resultados sean diccionarios (muy recomendado en Flask)
    cursor = conn.cursor(dictionary=True) 
    
    # Normalizar la consulta a mayúsculas para la verificación
    normalized_query = query.strip().upper()

    try:
        cursor.execute(query, params or ())
        
        if commit:
            conn.commit()
            
            
            if normalized_query.startswith(('UPDATE', 'DELETE')):
                # Devuelve el número de filas afectadas (ej. 1 si fue exitoso)
                return cursor.rowcount 
            
            # Si no es UPDATE/DELETE, se asume INSERT y devuelve el ID
            return cursor.lastrowid 
        
        elif fetch_one:
            return cursor.fetchone()
            
        elif cursor.description is not None:
            # Devuelve una lista de diccionarios para SELECTs
            return cursor.fetchall()
        
        return None # Para queries que no esperan resultado
        
    except mysql.connector.Error as err:
        current_app.logger.error(f"Error SQL: {err} | Query: {query} | Params: {params}")
        if commit:
            conn.rollback() 
        return 0 # Devuelve 0 para indicar que 0 filas fueron afectadas, indicando un fallo
    finally:
        # Es fundamental cerrar el cursor después de cada ejecución
        cursor.close()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask import session, flash, redirect, url_for
        if session.get('user_id') is None:
            flash("Necesitas iniciar sesión para acceder a esta página.", "warning")
            return redirect(url_for('auth_bp.login'))
        return f(*args, **kwargs)
    return decorated_function