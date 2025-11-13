# app.py (VERSIÓN FINAL Y LIMPIA)

from flask import Flask, redirect, url_for, session, g, current_app
# Asegúrate de importar la clase Config para usar app.config.from_object
from config import Config
import os
from dotenv import load_dotenv

# 🚨 CRÍTICO: Carga las variables de entorno de .env (si usas un archivo .env)
load_dotenv() 

# Asegúrate de que tus blueprints estén en 'routes/'
from routes.auth import auth_bp
from routes.doctor import doctor_bp
from routes.enfermero import enfermero_bp
from routes.paciente import paciente_bp 

# Asegúrate de que close_db esté en database/connection.py
from database.connection import close_db 

# 1. Configuración de la aplicación
app = Flask(__name__)
# Carga la configuración desde la clase Config
app.config.from_object(Config) 

# 💥 LÍNEA ELIMINADA: La limpieza forzada de sesión (session.clear()) ha sido eliminada. 💥
# La limpieza ahora se realiza correctamente dentro de la función acceso_qr.

# 2. Registro de Blueprints
# Los prefijos definen las URLs base (e.g., /auth/login, /doctor/dashboard)
app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(doctor_bp, url_prefix='/doctor')
app.register_blueprint(enfermero_bp, url_prefix='/enfermero')

# Registra el Blueprint de paciente ESPECIFICANDO el prefijo '/paciente'.
app.register_blueprint(paciente_bp, url_prefix='/paciente') 

# 3. Middleware y Contexto Global

@app.before_request
def load_logged_in_user():
    """Carga el usuario logueado en el contexto global (g) y limpia la sesión de paciente si hay staff logueado."""
    user_id = session.get('user_id')
    
    # 🧹 Limpieza de Sesión de Paciente (Crucial para que personal no vea datos de paciente)
    if user_id is not None:
        session.pop('paciente_id', None)
        session.pop('paciente_qr', None)
        session.pop('paciente_flujo', None)
        
    if user_id is None:
        g.user = None
    else:
        # Carga los datos esenciales del personal logueado
        g.user = {
            'id': user_id,
            'role': session.get('role'),
            'username': session.get('username'),
            'full_name': session.get('full_name', session.get('username'))
        }

@app.teardown_appcontext
def shutdown_session(exception=None):
    """Cierra la conexión a la base de datos al final de la solicitud."""
    # Esto es crucial para liberar conexiones de MySQL
    close_db(exception) 

# 4. Ruta Principal
@app.route('/')
def index():
    """Redirige al dashboard si está logueado, o al login/flujo si no lo está."""
    
    # PRIORIDAD 1: Si hay una sesión de personal, redirige al dashboard de staff
    if 'user_id' in session:
        # Redirige según el rol (1=Doctor, 2=Enfermero)
        if session.get('role') == 1:
            return redirect(url_for('doctor_bp.dashboard'))
        elif session.get('role') == 2:
            return redirect(url_for('enfermero_bp.dashboard'))
            
    # PRIORIDAD 2: Si hay una sesión de paciente (accedió por QR), lo mandamos al flujo
    if 'paciente_id' in session:
        return redirect(url_for('paciente_bp.control_flujo_paciente'))
        
    # PRIORIDAD 3: Redirige al login si no hay sesión activa
    return redirect(url_for('auth_bp.login'))

# 5. Ejecución de la aplicación
if __name__ == '__main__':
    # Usar host='0.0.0.0' para acceso en red local y debug=True para desarrollo
    app.run(debug=True, host='0.0.0.0', port=5000)