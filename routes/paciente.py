from flask import Blueprint, render_template, session, redirect, url_for, flash, request, current_app
from database.connection import execute_query 
from datetime import datetime

paciente_bp = Blueprint('paciente_bp', __name__, url_prefix='/paciente')

# --- DEFINICIÓN DE ETAPAS DEL FLUJO FINAL ---
FLUJO_PACIENTE = [
    'bienvenida',
    'video_educativo',     # Etapa 2
    'cuestionario',        # Etapa 3
    'ingreso_resultado',   # Etapa 4
    'resultados'           # Etapa 5
]


@paciente_bp.route('/acceso_qr/<string:qr_codigo>')
def acceso_qr(qr_codigo):
    """Verifica el código QR y redirige al flujo correcto: Enfermero (vinculación) o Paciente (flujo)."""
    
    query_qr = """
    SELECT q.paciente_id, q.estado, p.resultado 
    FROM qr q
    LEFT JOIN paciente p ON q.paciente_id = p.id
    WHERE q.codigo = %s
    """
    qr_data = execute_query(query_qr, (qr_codigo,), fetch_one=True)

    if not qr_data:
        flash("Código QR no válido. Contacte al personal de enfermería.", "danger")
        return redirect(url_for('auth_bp.login'))

    qr_estado = qr_data.get('estado')
    paciente_id = qr_data.get('paciente_id')
    resultado_paciente = qr_data.get('resultado')
    
    # ------------------------------------------------------------------
    # 🟢 LÓGICA DE REDIRECCIÓN DUAL (SOLUCIÓN)
    # ------------------------------------------------------------------

    # A. ESCENARIO DE VINCULACIÓN (ENFERMERO)
    # Si el QR está 'Generado' (es nuevo), redirigir al formulario del ENFERMERO.
    # El móvil del enfermero estará logueado o tendrá acceso directo a esta ruta.
    if qr_estado == 'Generado' and paciente_id is None:
        # El QR aún no ha sido vinculado; se asume que lo escanea el enfermero.
        flash("Código QR detectado. Continúe con el registro del paciente.", "info")
        return redirect(url_for('enfermero_bp.vincular_con_codigo', codigo=qr_codigo))


    # B. ESCENARIO DE PACIENTE (El QR ya está 'Vinculado' y tiene ID)
    if qr_estado == 'Vinculado' and paciente_id is not None:
        
        # 1. Si el paciente ya completó el autodiagnóstico, muestra el resultado final.
        if resultado_paciente is not None:
            flash("Ya has completado tu autodiagnóstico.", "info")
            return redirect(url_for('paciente_bp.mostrar_resultados', 
                                    resultado=resultado_paciente))
        
        # 2. Si el paciente NO ha completado el autodiagnóstico, inicia su flujo.
        session.clear() 
        session['paciente_id'] = paciente_id
        session['qr_codigo'] = qr_codigo
        session['paciente_flujo'] = FLUJO_PACIENTE[0] # Inicia en 'bienvenida'

        return redirect(url_for('paciente_bp.control_flujo_paciente'))

    # C. FALLBACK (Estado desconocido o error de vinculación)
    flash("El código QR no está listo o es inválido. Contacte al personal de enfermería.", "danger")
    return redirect(url_for('auth_bp.login'))


# -------------------------------------------------------------------
# --- 2. MOTOR DE NAVEGACIÓN (Controla las etapas) ---
# -------------------------------------------------------------------
@paciente_bp.route('/flujo')
def control_flujo_paciente():
    """Controla la navegación del paciente a través de las diferentes etapas."""

    paciente_id = session.get('paciente_id')
    flujo_actual = session.get('paciente_flujo')

    if not paciente_id or not flujo_actual:
        flash("Su sesión ha expirado o no ha iniciado el proceso con el QR.", "danger")
        return redirect(url_for('auth_bp.login'))
        
    template_name = f'paciente/{flujo_actual}.html'
    
    # Lógica específica para la etapa 'ingreso_resultado' 
    if flujo_actual == 'ingreso_resultado':
        query_paciente = "SELECT nombre, apellido_paterno FROM paciente WHERE id = %s"
        paciente_data = execute_query(query_paciente, (paciente_id,), fetch_one=True)
        nombre = f"{paciente_data.get('nombre', '')} {paciente_data.get('apellido_paterno', '')}"
        
        # Renderiza la plantilla que contiene el formulario de Positivo/Negativo
        return render_template('paciente/ingreso_resultado.html', 
                               nombre_paciente=nombre)
        
    # Para todas las demás etapas (bienvenida, video_educativo, cuestionario)
    return render_template(template_name)


# -------------------------------------------------------------------
# --- 3. FUNCIÓN PARA AVANZAR EN EL FLUJO (Botón 'Siguiente') ---
# -------------------------------------------------------------------
@paciente_bp.route('/siguiente')
def siguiente_paso():
    """Avanza a la siguiente etapa en el flujo del paciente."""
    
    flujo_actual = session.get('paciente_flujo')
    
    if not flujo_actual:
        flash("Sesión no válida para avanzar.", "danger")
        return redirect(url_for('auth_bp.login'))

    try:
        indice_actual = FLUJO_PACIENTE.index(flujo_actual)
        indice_siguiente = indice_actual + 1
        
        if indice_siguiente < len(FLUJO_PACIENTE):
            session['paciente_flujo'] = FLUJO_PACIENTE[indice_siguiente]
            return redirect(url_for('paciente_bp.control_flujo_paciente'))
        else:
            # Si intenta avanzar más allá de la última etapa, redirige a la finalización
            return redirect(url_for('paciente_bp.cerrar_sesion_final'))
            
    except ValueError:
        flash("Error en la secuencia del flujo. Reinicie el proceso.", "danger")
        return redirect(url_for('auth_bp.login'))


# -------------------------------------------------------------------
# --- 4. RUTA PARA GUARDAR EL CUESTIONARIO Y AVANZAR ---
# -------------------------------------------------------------------
@paciente_bp.route('/guardar_cuestionario', methods=['POST'])
def guardar_cuestionario():
    """Guarda las respuestas del cuestionario y avanza a la siguiente etapa (ingreso_resultado)."""

    paciente_id = session.get('paciente_id')
    if not paciente_id:
        flash("Sesión no válida.", "danger")
        return redirect(url_for('auth_bp.login'))

    # 🚨 LÓGICA DE GUARDADO DE RESPUESTAS AQUÍ 🚨
    # En un proyecto real, aquí guardarías las respuestas del cuestionario
    # -----------------------------------------------

    flash("Respuestas del cuestionario guardadas. Continúe con el autodiagnóstico.", "info")
    return redirect(url_for('paciente_bp.siguiente_paso'))


# -------------------------------------------------------------------
# --- 5. RUTA PARA GUARDAR EL RESULTADO DE LA AUTOPRUEBA ---
# -------------------------------------------------------------------
@paciente_bp.route('/guardar_resultado', methods=['POST'])
def guardar_resultado():
    """Guarda el resultado de la autoprueba (Positivo/Negativo) y redirige a la página final."""

    paciente_id = session.get('paciente_id')
    
    if not paciente_id:
        flash("Sesión no válida para guardar el resultado.", "danger")
        return redirect(url_for('auth_bp.login'))

    resultado = request.form.get('resultado') # Espera 'Positivo' o 'Negativo'
    
    if resultado not in ['Positivo', 'Negativo']:
        flash("Selección de resultado no válida.", "danger")
        session['paciente_flujo'] = 'ingreso_resultado' 
        return redirect(url_for('paciente_bp.control_flujo_paciente'))

    try:
        # 1. ACTUALIZACIÓN CORREGIDA: Solo actualiza la columna 'resultado'
        query_update = "UPDATE paciente SET resultado = %s WHERE id = %s"
        execute_query(query_update, (resultado, paciente_id), commit=True)
        
        # 2. Limpiar la sesión inmediatamente
        session.clear() 
        
        # 3. Redirigir a la vista final para mostrar el resultado y las recomendaciones
        return redirect(url_for('paciente_bp.mostrar_resultados', resultado=resultado))

    except Exception as e:
        current_app.logger.error(f"Error al guardar resultado para paciente {paciente_id}: {e}")
        flash("Error CRÍTICO al guardar el resultado. Contacte al personal de salud.", "danger")
        return redirect(url_for('auth_bp.login'))


# -------------------------------------------------------------------
# --- 6. RUTA PARA MOSTRAR LA PANTALLA FINAL DE RESULTADOS/RECOMENDACIONES ---
# -------------------------------------------------------------------
@paciente_bp.route('/resultados_final')
def mostrar_resultados():
    """Muestra la página de resultados y recomendaciones (Positivo/Negativo)."""
    
    resultado = request.args.get('resultado')
    
    if not resultado or resultado not in ['Positivo', 'Negativo']:
        flash("Acceso no autorizado o resultado faltante.", "danger")
        return redirect(url_for('auth_bp.login'))
    
    # Generar recomendaciones basadas en el resultado
    if resultado == 'Positivo':
        recomendacion = "Acciones Inmediatas: Llama a la línea de apoyo XXXXX para una cita de confirmación y tratamiento. Tu salud es lo primero."
        clase = 'positivo'
    else:
        recomendacion = "Prevención Continua: Recuerda el uso correcto del preservativo en todas tus relaciones sexuales."
        clase = 'negativo'

    return render_template('paciente/resultados.html', 
                           resultado=resultado, 
                           recomendacion=recomendacion,
                           clase_resultado=clase)


# -------------------------------------------------------------------
# --- 7. RUTA DE CIERRE DE SESIÓN (PANTALLA FINAL) ---
# -------------------------------------------------------------------
@paciente_bp.route('/cerrar_sesion_final')
def cerrar_sesion_final():
    """Muestra la pantalla de agradecimiento ('finalizado.html') y luego cierra la sesión."""
    return render_template('paciente/finalizado.html')