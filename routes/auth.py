from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from database.connection import execute_query
from flask_mail import Message

auth_bp = Blueprint('auth_bp', __name__, url_prefix='/auth') 

# --- RUTA: REGISTRAR ---
@auth_bp.route('/registrar', methods=['GET', 'POST'])
def registrar():
    if request.method == 'POST':
        nombres = request.form.get('nombres')
        fecha_nacimiento = request.form.get('fecha_nacimiento')
        cedula = request.form.get('cedula')
        email = request.form.get('email').lower().strip()
        telefono = request.form.get('telefono')
        rol_id = request.form.get('rol_id')
        password = request.form.get('password')

        # 1. Validación de Dominios Permitidos
        dominios_validos = ['gmail.com', 'hotmail.com', 'outlook.com', 'yahoo.com', 'icloud.com']
        dominio = email.split('@')[-1] if '@' in email else ''
        
        if dominio not in dominios_validos:
            flash("Por favor use un correo válido (Gmail, Hotmail, Outlook o Yahoo).", "danger")
            return render_template('auth/registrar.html')

        try:
            # 2. Insertar en tabla usuario
            query_usuario = "INSERT INTO usuario (usuario, password, rol_id) VALUES (%s, %s, %s)"
            usuario_id = execute_query(query_usuario, (email, password, rol_id), commit=True)

            if usuario_id:
                # 3. Insertar perfil detallado en tabla personal
                query_personal = """
                    INSERT INTO personal (nombre, fecha_nacimiento, cedula_profesional, 
                                         email, telefono, usuario_id) 
                    VALUES (%s, %s, %s, %s, %s, %s)
                """
                execute_query(query_personal, (nombres, fecha_nacimiento, cedula, 
                                             email, telefono, usuario_id), commit=True)
                
                flash("Cuenta creada exitosamente. Ya puede iniciar sesión.", "success")
                return redirect(url_for('auth_bp.login'))
            
        except Exception as e:
            current_app.logger.error(f"Error en el registro: {e}")
            flash("Error al crear la cuenta. Es posible que el correo ya esté registrado.", "danger")

    return render_template('auth/registrar.html')


# --- RUTA: LOGIN ---
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email_input = request.form.get('email').lower().strip()
        password_input = request.form.get('password') 
        
        query_user = "SELECT id, password, rol_id, usuario FROM usuario WHERE usuario = %s"
        user_data = execute_query(query_user, (email_input,), fetch_one=True)
        
        if user_data:
            db_password = str(user_data['password']).strip()
            
            if db_password == password_input:
                query_personal = "SELECT nombre FROM personal WHERE usuario_id = %s"
                personal_data = execute_query(query_personal, (user_data['id'],), fetch_one=True)
                
                session.clear() 
                session['user_id'] = user_data['id']
                session['role'] = user_data['rol_id']
                
                if personal_data and personal_data['nombre']:
                    session['full_name'] = personal_data['nombre']
                else:
                    session['full_name'] = user_data['usuario']
                
                if session['role'] == 1: 
                    flash(f"Bienvenido, {session['full_name']}.", "success")
                    return redirect(url_for('doctor_bp.dashboard')) 
                elif session['role'] == 2: 
                    flash(f"Bienvenido, {session['full_name']}.", "success")
                    return redirect(url_for('enfermero_bp.dashboard'))
                else:
                    flash("Rol no reconocido.", "warning")
                    return redirect(url_for('auth_bp.login'))
            else:
                flash("Contraseña incorrecta.", "danger")
        else:
            flash("El correo electrónico no está registrado.", "danger")
            
    return render_template('auth/login.html')


# --- FUNCIONALIDAD: RECUPERACIÓN DE CONTRASEÑA ---

@auth_bp.route('/reset_password', methods=['GET', 'POST'])
def reset_password_request():
    if request.method == 'POST':
        email = request.form.get('email').lower().strip()
        
        query = "SELECT id FROM usuario WHERE usuario = %s"
        user = execute_query(query, (email,), fetch_one=True)
        
        if user:
            # Importaciones locales
            from app import mail, serializer
            import os 

            token = serializer.dumps(email, salt='recover-password')
            link = url_for('auth_bp.reset_with_token', token=token, _external=True)
            
            # SOLUCIÓN DEFINITIVA: Forzamos el remitente desde la variable de entorno directamente
            remitente = os.getenv('MAIL_USERNAME') 
            
            msg = Message(
                "Restablecer Contraseña - AUTOTESTS_VIH", 
                recipients=[email],
                sender=remitente # <--- Forzado aquí
            )
            msg.body = f"Para restablecer su acceso al sistema JSXII, haga clic en el siguiente enlace: {link}\nEste enlace expirará en 30 minutos."
            
            try:
                mail.send(msg)
                flash("Se ha enviado un enlace de recuperación a su correo electrónico.", "success")
                return redirect(url_for('auth_bp.login'))
            except Exception as e:
                current_app.logger.error(f"Error SMTP detallado: {e}")
                flash("Error al enviar el correo. Verifique su conexión.", "danger")
        else:
            flash("Ese correo electrónico no está registrado.", "warning")
            
    return render_template('auth/reset_request.html')


@auth_bp.route('/reset/<token>', methods=['GET', 'POST'])
def reset_with_token(token):
    from app import serializer
    try:
        email = serializer.loads(token, salt='recover-password', max_age=1800)
    except:
        flash("El enlace de recuperación ha expirado o es inválido.", "danger")
        return redirect(url_for('auth_bp.login'))
    
    if request.method == 'POST':
        nueva_password = request.form.get('password')
        query = "UPDATE usuario SET password = %s WHERE usuario = %s"
        execute_query(query, (nueva_password, email), commit=True)
        
        flash("Su contraseña ha sido actualizada. Ya puede iniciar sesión.", "success")
        return redirect(url_for('auth_bp.login'))
        
    return render_template('auth/reset_with_token.html', token=token)


# --- RUTA: LOGOUT ---
@auth_bp.route('/logout')
def logout():
    session.clear() 
    flash("Has cerrado sesión exitosamente.", "success")
    return redirect(url_for('auth_bp.login'))