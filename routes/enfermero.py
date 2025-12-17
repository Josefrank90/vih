from flask import Blueprint, render_template, session, redirect, url_for, flash, request, current_app
from database.connection import execute_query 
from datetime import datetime, timedelta 
from functools import wraps 
import qrcode
import base64
from io import BytesIO
import json
from decimal import Decimal

IP_DEL_SERVIDOR = '192.168.8.31' 
PUERTO = '5000'
BASE_URL = f"http://{IP_DEL_SERVIDOR}:{PUERTO}"
# ---------------------


def enfermero_login_required(f):
    """Verifica si el usuario está logueado y es un Enfermero (rol_id=2)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Verifica la sesión y el rol
        if 'user_id' not in session or session.get('role') != 2:
            flash("Acceso denegado. Debe iniciar sesión como Enfermero.", "danger")
            session.clear() 
            return redirect(url_for('auth_bp.login'))
        return f(*args, **kwargs)
    return decorated_function 


enfermero_bp = Blueprint('enfermero_bp', __name__, url_prefix='/enfermero')


def generar_qr_base64(data_qr):
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=4,
            border=2,
        )
        qr.add_data(data_qr)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Guardar en un buffer de memoria
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        
        # Codificar a Base y agregar el prefijo de datos
        return f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode('utf-8')}"
    except Exception as e:
        current_app.logger.error(f"Error al generar QR Base64 para data '{data_qr}': {e}")
        return None 


# --- FUNCIÓN AUXILIAR PARA CARGAR DATOS DE UBICACIÓN (NUEVA) ---

def cargar_datos_ubicacion_enfermero():
    """Consulta y retorna todos los estados, municipios y colonias para el formulario."""
    try:
        query_estados = "SELECT id, nombre FROM estados ORDER BY nombre;"
        estados_data = execute_query(query_estados) or []
        
        # Para el filtrado en el frontend, cargamos los datos necesarios:
        query_municipios = "SELECT id, nombre, estado FROM municipios ORDER BY nombre;"
        municipios_data = execute_query(query_municipios) or []
        
        query_colonias = "SELECT id, nombre, codigo_postal, municipio FROM colonias ORDER BY nombre;"
        colonias_data = execute_query(query_colonias) or []

    except Exception as e:
        current_app.logger.error(f"Error al cargar la lista de ubicaciones estáticas (Enfermero): {e}")
        estados_data = []
        municipios_data = []
        colonias_data = []
    
    return estados_data, municipios_data, colonias_data


# --- 1. DASHBOARD (Mantiene protección de sesión) ---

@enfermero_bp.route('/dashboard')
@enfermero_login_required 
def dashboard():
    qrs_pendientes = 0
    pacientes_registrados = 0
    nuevos_registros = 0
    qrs_pendientes_tabla = []

    try:
        # a) QRs Pendientes
        query_qrs_pendientes = "SELECT COUNT(id) AS total FROM qr WHERE estado = 'Generado' AND paciente_id IS NULL"
        pendientes_data = execute_query(query_qrs_pendientes, fetch_one=True)
        if pendientes_data: qrs_pendientes = pendientes_data.get('total', 0)
            
        # b) Pacientes Registrados (QRs Vinculados)
        query_pacientes_registrados = "SELECT COUNT(id) AS total FROM qr WHERE estado = 'Vinculado'"
        registrados_data = execute_query(query_pacientes_registrados, fetch_one=True)
        if registrados_data: pacientes_registrados = registrados_data.get('total', 0)
        
        # c) Nuevos Registros (Últimas 24 horas)
        try:
            fecha_limite = (datetime.now() - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
            query_nuevos_registros = "SELECT COUNT(id) AS total FROM paciente WHERE fecha_registro >= %s"
            nuevos_data = execute_query(query_nuevos_registros, (fecha_limite,), fetch_one=True)
            if nuevos_data: nuevos_registros = nuevos_data.get('total', 0)
        except Exception as e_specific:
            nuevos_registros = 0
            current_app.logger.warning(f"Error al contar 'Nuevos Registros': {e_specific}. Se mostrará 0.")

        # CONSULTA PARA LA TABLA INFERIOR
        query_tabla_pendientes = """
        SELECT id, codigo AS codigo_qr, fecha_entrega AS fecha_creacion
        FROM qr
        WHERE estado = 'Generado' AND paciente_id IS NULL 
        ORDER BY fecha_entrega DESC
        LIMIT 10
        """
        qrs_pendientes_tabla = execute_query(query_tabla_pendientes) or [] 
            
    except Exception as e_general:
        flash(f"Error CRÍTICO al cargar el dashboard. Detalles: {e_general}", "danger")
        current_app.logger.error(f"Error fatal en enfermero/dashboard: {e_general}")
        return redirect(url_for('auth_bp.login'))

    return render_template('enfermero/dashboard.html',
                           qrs_pendientes=qrs_pendientes,
                           pacientes_registrados=pacientes_registrados,
                           nuevos_registros=nuevos_registros,
                           qrs_pendientes_tabla=qrs_pendientes_tabla)


# --- 2. INICIO DE VINCULACIÓN (Mantiene protección de sesión) ---

@enfermero_bp.route('/vincular_inicio')
@enfermero_login_required 
def vincular_inicio():
    # 1. Consulta la Base de Datos para QRs pendientes
    query_qrs_pendientes = """
    SELECT codigo 
    FROM qr 
    WHERE estado = 'Generado' AND paciente_id IS NULL 
    ORDER BY fecha_entrega DESC
    """
    try:
        qrs_desde_db = execute_query(query_qrs_pendientes) or []
    except Exception as e:
        current_app.logger.error(f"Error al consultar QRs pendientes para vinculación: {e}")
        flash("Error al cargar la lista de códigos QR. Intente más tarde.", "danger")
        qrs_desde_db = []
    
    qrs_listos = []
    
    # 2. Procesamiento: Generar la imagen QR en Base64 para el template
    for qr in qrs_desde_db:
        codigo = qr.get('codigo')
        
        url_para_qr = url_for('paciente_bp.acceso_qr', qr_codigo=codigo, _external=True) 
        
        imagen_base64 = generar_qr_base64(url_para_qr)
        
        if imagen_base64:
            qrs_listos.append({
                'codigo': codigo,
                'imagen_base64': imagen_base64
            })

    # 3. Renderizar la Plantilla
    return render_template('enfermero/vincular_inicio.html', qrs_pendientes=qrs_listos)



# --- 3. VINCULAR QR A PACIENTE (Flujo directo sin Dashboard) ---

@enfermero_bp.route('/vincular_con_codigo', defaults={'codigo': None}, methods=['GET', 'POST'])
@enfermero_bp.route('/vincular_con_codigo/<string:codigo>', methods=['GET', 'POST'])
# NO requiere @enfermero_login_required para acceso directo desde QR
def vincular_con_codigo(codigo):
    
    if not codigo:
        codigo = request.args.get('codigo')
        
    if not codigo:
        flash("Se requiere un código QR para continuar la vinculación.", "warning")
        return redirect(url_for('enfermero_bp.vincular_inicio'))
        
    # Variables de control para el template
    advertencia_vinculado = False
    error = False

    # 1. Verificar el QR (Validaciones)
    query_qr = "SELECT id, estado, paciente_id FROM qr WHERE codigo = %s"
    qr_data = execute_query(query_qr, (codigo,), fetch_one=True)

    if not qr_data:
        flash(f"Error: El código QR '{codigo}' no existe. No es posible continuar con el registro.", "danger")
        error = True
    
    elif qr_data.get('estado') == 'Vinculado' or qr_data.get('paciente_id') is not None:
        flash(f"Advertencia: El código QR '{codigo}' ya está **vinculado** a un paciente.", "warning")
        advertencia_vinculado = True
    
    elif qr_data.get('estado') != 'Generado':
        flash(f"Error: El código QR '{codigo}' no está disponible. Estado: {qr_data.get('estado')}.", "warning")
        error = True

    # 2. Manejar la Solicitud POST (Registro del Paciente y Vinculación)
    if request.method == 'POST':
        
        if advertencia_vinculado or error:
            flash("Error: El código QR no puede ser utilizado para un nuevo registro.", "danger")
            # Recargar datos de ubicación al fallar la validación inicial
            estados_data, municipios_data, colonias_data = cargar_datos_ubicacion_enfermero()
            return render_template('enfermero/registrar_paciente.html', codigo_qr=codigo, 
                                   advertencia_vinculado=advertencia_vinculado, error=error, 
                                   form_data=request.form, 
                                   estados=estados_data, municipios=municipios_data, colonias=colonias_data)

        # --- INICIO LÓGICA DE CAPTURA DEL PACIENTE ---
        nombre = request.form.get('nombre')
        apellido_paterno = request.form.get('apellido_paterno')
        apellido_materno = request.form.get('apellido_materno') or None
        sexo = request.form.get('sexo')
        
        try:
            edad = int(request.form.get('edad'))
        except (ValueError, TypeError):
            flash("La edad debe ser un número entero válido.", "danger")
            estados_data, municipios_data, colonias_data = cargar_datos_ubicacion_enfermero()
            return render_template('enfermero/registrar_paciente.html', codigo_qr=codigo, form_data=request.form,
                                   estados=estados_data, municipios=municipios_data, colonias=colonias_data)
            
        telefono = request.form.get('telefono') or None
        ocupacion = request.form.get('ocupacion') or None
        
        # --- CAPTURA DE NUEVOS CAMPOS DE UBICACIÓN ---
        id_estado = request.form.get('estado')
        id_municipio = request.form.get('municipio')
        id_colonia = request.form.get('colonia')
        codigo_postal = request.form.get('codigo_postal') or None # Permitimos NULL si viene vacío
        
        resultado = None 
        fecha_registro = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # --- VALIDACIÓN DE CAMPOS OBLIGATORIOS (AJUSTADA) ---
        if not all([nombre, apellido_paterno, sexo, edad, id_estado, id_municipio, id_colonia]):
            flash("Faltan campos obligatorios (Nombre, Apellido Paterno, Sexo, Edad, Estado, Municipio, Colonia).", "danger")
            estados_data, municipios_data, colonias_data = cargar_datos_ubicacion_enfermero()
            return render_template('enfermero/registrar_paciente.html', codigo_qr=codigo, form_data=request.form,
                                   estados=estados_data, municipios=municipios_data, colonias=colonias_data)

        paciente_id = None
        
        # 1. INSERTAR EL PACIENTE (Consulta actualizada con los 4 campos de ubicación)
        # NOTA: Debes asegurar que tu tabla 'paciente' tenga las columnas id_estado, id_municipio, id_colonia, codigo_postal
        query_insert_paciente = """
        INSERT INTO paciente (nombre, apellido_paterno, apellido_materno, sexo, edad, telefono, ocupacion, 
                              id_estado, id_municipio, id_colonia, codigo_postal, 
                              resultado, fecha_registro)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        paciente_data = (nombre, apellido_paterno, apellido_materno, sexo, edad, telefono, ocupacion, 
                         id_estado, id_municipio, id_colonia, codigo_postal, 
                         resultado, fecha_registro)
        
        try:
            paciente_id = execute_query(query_insert_paciente, paciente_data, commit=True)
            if paciente_id: paciente_id = int(paciente_id)
        except Exception as e_insert:
            current_app.logger.error(f"Error al insertar paciente: {e_insert}")
            flash(f"Error CRÍTICO: Falló el registro del paciente. Verifique la estructura de su tabla 'paciente'. Detalle: {e_insert}", "danger")
            estados_data, municipios_data, colonias_data = cargar_datos_ubicacion_enfermero()
            return render_template('enfermero/registrar_paciente.html', codigo_qr=codigo, form_data=request.form,
                                   estados=estados_data, municipios=municipios_data, colonias=colonias_data)
            
        # 2. ACTUALIZAR QR
        query_update_qr = "UPDATE qr SET estado = 'Vinculado', paciente_id = %s WHERE codigo = %s" 
        try:
            execute_query(query_update_qr, (paciente_id, codigo), commit=True)
            flash(f"Paciente {nombre} {apellido_paterno} registrado y vinculado exitosamente.", "success")
        
        except Exception as e_update:
            current_app.logger.error(f"Error de DB al actualizar QR. Error: {e_update}")
            flash(f"Paciente registrado. **ADVERTENCIA CRÍTICA**: Falló la vinculación del QR. Contacte a soporte.", "danger")
            
        
        # 3. Redirigir a la página de confirmación.
        return redirect(url_for('enfermero_bp.confirmacion_qr', qr_codigo=codigo, paciente_id=paciente_id))
            
    # 5. GET: Mostrar el formulario de registro de paciente
    
    # Cargar datos de ubicación solo para el método GET
    estados_data, municipios_data, colonias_data = cargar_datos_ubicacion_enfermero()
    
    return render_template('enfermero/registrar_paciente.html', 
                            codigo_qr=codigo, 
                            advertencia_vinculado=advertencia_vinculado,
                            error=error,
                            estados=estados_data,
                            municipios=municipios_data,
                            colonias=colonias_data)


# --- 4. CONFIRMACIÓN DE QR Y URL DEL PACIENTE (NO requiere sesión) ---

@enfermero_bp.route('/confirmacion_qr')
# NO requiere @enfermero_login_required
def confirmacion_qr():
    qr_codigo = request.args.get('qr_codigo')
    paciente_id = request.args.get('paciente_id')

    if not qr_codigo or not paciente_id:
        flash("Datos de confirmación incompletos. Vuelva a escanear el QR.", "warning")
        return redirect(url_for('enfermero_bp.vincular_inicio')) 

    url_completa = None
    try:
        # Esta URL se le da al paciente para su flujo
        url_acceso = url_for('paciente_bp.acceso_qr', qr_codigo=qr_codigo, _external=False)
        url_completa = f"{BASE_URL}{url_acceso}" 
        
    except Exception as e_url:
        current_app.logger.error(f"Error BuildError al generar URL para paciente: {e_url}")
        flash(f"Error CRÍTICO: No se pudo generar la URL. Revise el nombre del endpoint 'paciente_bp.acceso_qr'.", "danger")
        url_completa = "ERROR: Revisar logs o contactar soporte"
        return redirect(url_for('enfermero_bp.vincular_inicio')) 

    return render_template('enfermero/confirmacion_qr.html', 
                             qr_codigo=qr_codigo,
                             paciente_id=paciente_id,
                             url_completa=url_completa)

# --- 5. LISTA DE PACIENTES REGISTRADOS (Mantiene protección de sesión) ---

@enfermero_bp.route('/pacientes')
@enfermero_login_required 
def pacientes():
    query = """
    SELECT 
        p.id AS paciente_id,
        p.nombre,
        p.apellido_paterno,
        p.edad,
        p.sexo,
        p.resultado,
        q.codigo AS qr_codigo
    FROM paciente p
    JOIN qr q ON p.id = q.paciente_id
    WHERE q.estado = 'Vinculado'
    ORDER BY p.id DESC
    """

    try:
        pacientes_registrados = execute_query(query) 
        pacientes_registrados = pacientes_registrados or []
            
    except Exception as e:
        current_app.logger.error(f"Error al cargar la lista de pacientes: {e}")
        flash(f"Error al cargar la lista de pacientes: {e}", "danger") 
        pacientes_registrados = []

    return render_template('enfermero/pacientes.html', 
                            pacientes=pacientes_registrados)