from flask import Flask, redirect, url_for, session, g, request
from flask_mail import Mail, Message 
from itsdangerous import URLSafeTimedSerializer 
from config import Config
import os
from dotenv import load_dotenv

# Carga de variables de entorno (.env)
load_dotenv() 

# Importación de rutas (Blueprints)
from routes.auth import auth_bp
from routes.doctor import doctor_bp
from routes.enfermero import enfermero_bp
from routes.paciente import paciente_bp 

# Conexión a la base de datos
from database.connection import close_db 

# 1. Configuración de la aplicación
app = Flask(__name__)
app.config.from_object(Config) 

# --- CONFIGURACIÓN DE CORREO (SMTP) ---
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True') == 'True'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME') 
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD') 

# SOLUCIÓN AL ERROR SMTP: Definir remitente por defecto
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER') or app.config['MAIL_USERNAME']

# Inicialización de extensiones
mail = Mail(app)
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

# 2. Registro de Blueprints
app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(doctor_bp, url_prefix='/doctor')
app.register_blueprint(enfermero_bp, url_prefix='/enfermero')
app.register_blueprint(paciente_bp, url_prefix='/paciente') 

# 3. Middleware y Contexto Global
@app.before_request
def load_logged_in_user():
    """Carga el usuario logueado y limpia sesiones de paciente si es staff."""
    user_id = session.get('user_id')
    if user_id is not None:
        session.pop('paciente_id', None)
        session.pop('paciente_qr', None)
        session.pop('paciente_flujo', None)
        
    if user_id is None:
        g.user = None
    else:
        g.user = {
            'id': user_id,
            'role': session.get('role'),
            'username': session.get('username'),
            'full_name': session.get('full_name', session.get('username'))
        }

@app.teardown_appcontext
def shutdown_session(exception=None):
    """Cierra la conexión a la base de datos al finalizar la solicitud."""
    close_db(exception) 

# 4. Función de envío de correos (Ajustada para evitar error de sender)
def send_recovery_email(email_dest):
    try:
        token = serializer.dumps(email_dest, salt='recover-password')
        url = url_for('auth_bp.reset_with_token', token=token, _external=True)
        
        # Se especifica el 'sender' explícitamente en el objeto Message
        msg = Message(
            subject="Recuperación de Contraseña - AUTOTESTS_VIH",
            recipients=[email_dest],
            sender=app.config['MAIL_DEFAULT_SENDER'],
            body=f"Hola, para restablecer tu contraseña en el sistema JSXII, haz clic aquí: {url}"
        )
        
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Error crítico enviando correo: {e}")
        return False

# 5. Ruta Principal (Enrutamiento por Roles)
@app.route('/')
def index():
    if 'user_id' in session:
        if session.get('role') == 1:
            return redirect(url_for('doctor_bp.dashboard'))
        elif session.get('role') == 2:
            return redirect(url_for('enfermero_bp.dashboard'))
            
    if 'paciente_id' in session:
        return redirect(url_for('paciente_bp.control_flujo_paciente'))
        
    return redirect(url_for('auth_bp.login'))

# 6. Ejecución del servidor
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)