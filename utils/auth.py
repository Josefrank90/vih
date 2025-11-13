# utils/auth.py

from functools import wraps
from flask import session, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash # Importación correcta

# --- Funciones de Seguridad ---

def hash_password(password):
    """Genera un hash seguro para la contraseña."""
    return generate_password_hash(password)

def check_hashed_password(hashed_password, password):
    """Verifica si la contraseña coincide con el hash."""
    # Asegúrate de que werkzeug.security esté importado arriba
    return check_password_hash(hashed_password, password)

# --- Constantes de Roles (Basado en tu tabla 'rol') ---

ROL_DOCTOR = 1
ROL_ENFERMERO = 2

# --- Funciones de Roles y Autenticación ---

def is_authenticated():
    """Verifica si hay un usuario logueado (Doctor o Enfermero)."""
    return 'user_id' in session

def get_user_role():
    """Obtiene el rol del usuario actual."""
    return session.get('role', None)

# --- Decoradores para Proteger Rutas ---

def login_required(f):
    """Decorador que requiere que el usuario esté autenticado."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_authenticated():
            flash("Necesitas iniciar sesión para acceder a esta página.", "danger")
            return redirect(url_for('auth_bp.login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(required_role_id):
    """Decorador que requiere un rol específico."""
    def decorator(f):
        @wraps(f)
        @login_required 
        def decorated_function(*args, **kwargs):
            current_role = get_user_role()
            if current_role != required_role_id:
                flash("No tienes permiso para acceder a esta sección.", "danger")
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Decoradores específicos para cada rol
doctor_required = role_required(ROL_DOCTOR)
enfermero_required = role_required(ROL_ENFERMERO)

# NOTA: Asegúrate de tener un archivo __init__.py vacío dentro de la carpeta 'utils/'