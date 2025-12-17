from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from database.connection import execute_query

auth_bp = Blueprint('auth_bp', __name__, url_prefix='/auth') 

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user_name = request.form.get('usuario')
        password_input = request.form.get('password') 
        
        # 1. Consulta la tabla 'usuario'
        query_user = "SELECT id, password, rol_id FROM usuario WHERE usuario = %s"
        user_data = execute_query(query_user, (user_name,), fetch_one=True)
        
        if user_data:
            # --- CRÍTICO: VERIFICACIÓN DE CONTRASEÑA CORRECTA ---
            # Se asegura que ambos sean strings limpios para la comparación exitosa.
            db_password = str(user_data['password']).strip()
            
            if db_password == password_input:
                
                # --- OBTENER DATOS DE PERFIL ---
                query_personal = "SELECT nombre, apellido_paterno FROM personal WHERE usuario_id = %s"
                personal_data = execute_query(query_personal, (user_data['id'],), fetch_one=True)
                
                # 2. Establecer Sesión
                session.clear() 
                session['user_id'] = user_data['id']
                session['role'] = user_data['rol_id']
                session['username'] = user_name
                
                if personal_data:
                    full_name = f"{personal_data['nombre']} {personal_data['apellido_paterno']}"
                    session['full_name'] = full_name
                else:
                    session['full_name'] = user_name 
                
                # 3. Redirigir según el rol
                try:
                    if session['role'] == 1: 
                        flash(f"Bienvenido, {session['full_name']} (Doctor).", "success")
                        return redirect(url_for('doctor_bp.dashboard')) 
                    
                    elif session['role'] == 2: 
                        flash(f"Bienvenido, {session['full_name']} (Enfermero).", "success")
                        return redirect(url_for('enfermero_bp.dashboard'))
                        
                    else:
                        flash("Rol de usuario no reconocido. Redirigido al Login.", "warning")
                        return redirect(url_for('auth_bp.login'))

                except Exception as e:
                    current_app.logger.error(f"Error CRÍTICO de redirección (Endpoint Missing): {e}")
                    flash("Error CRÍTICO de configuración. No se encontró la ruta de destino.", "danger")
                    return redirect(url_for('auth_bp.login'))

            else:
                flash("Contraseña incorrecta.", "danger")
        else:
            flash("Usuario no encontrado.", "danger")
            
    return render_template('auth/login.html')

@auth_bp.route('/logout')
def logout():
    session.clear() 
    flash("Has cerrado la sesión exitosamente.", "success")
    return redirect(url_for('auth_bp.login'))