from flask import Blueprint, render_template, session, redirect, url_for, flash, request, send_file, current_app, jsonify
from database.connection import execute_query 
from datetime import datetime
from functools import wraps 
import qrcode
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader 
import uuid 
import json 
from decimal import Decimal 
import zipfile 
import os 


IP_DEL_SERVIDOR = '192.168.1.130' 
PUERTO = '5000'
BASE_URL = f"http://{IP_DEL_SERVIDOR}:{PUERTO}"


LOGO_JURISDICCION_PATH = 'static/assets/img/logo_jurisdiccion.png' 
LOGO_SALUD_PATH = 'static/assets/img/logo_salud.png' 


# ===================================================================
# --- FUNCIONES DE OBTENCIÓN DE DATOS GEOGRÁFICOS DESDE DB (INTEGRADAS) ---
# Se usan las funciones de consulta que asumimos están en database.connection
# ===================================================================

def obtener_estados_db(pais_id=1):
    try:
        query = "SELECT id, nombre FROM estados WHERE pais = %s ORDER BY nombre" 
        return execute_query(query, (pais_id,)) or []
    except Exception as e:
        current_app.logger.error(f"❌ ERROR al obtener estados desde DB: {e}")
        return []

def obtener_municipios_db(estado_id):
    try:
        query = "SELECT id, nombre FROM municipios WHERE estado = %s ORDER BY nombre"
        return execute_query(query, (estado_id,)) or []
    except Exception as e:
        current_app.logger.error(f"❌ ERROR al obtener municipios desde DB: {e}")
        return []

def obtener_colonias_db(municipio_id):
    try:
        query = "SELECT id, asentamiento AS nombre FROM colonias WHERE municipio = %s ORDER BY asentamiento"
        return execute_query(query, (municipio_id,)) or []
    except Exception as e:
        current_app.logger.error(f"❌ ERROR al obtener colonias desde DB: {e}")
        return []

# ===================================================================


class CustomJsonEncoder(json.JSONEncoder):
    """
    Codificador personalizado de JSON para manejar objetos Decimal de la DB.
    """
    def default(self, obj):
        if isinstance(obj, Decimal):
            
            return float(obj)
        return json.JSONEncoder.default(self, obj)


def doctor_login_required(f):
    """Verifica si el usuario está logueado y es un Doctor (rol_id=1)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 1:
            flash("Acceso denegado. Debe iniciar sesión como Doctor.", "danger")
            session.clear() 
            return redirect(url_for('auth_bp.login'))
        return f(*args, **kwargs)
    return decorated_function


doctor_bp = Blueprint('doctor_bp', __name__, url_prefix='/doctor') 


# -------------------------------------------------------------------
# --- RUTAS API (Para carga dinámica de los SELECTS) ---
# -------------------------------------------------------------------
@doctor_bp.route('/api/municipios/<int:estado_id>', methods=['GET'])
@doctor_login_required
def api_municipios(estado_id):
    """Carga los municipios basado en el ID del estado seleccionado."""
    municipios_data = obtener_municipios_db(estado_id)
    return jsonify(municipios_data)

@doctor_bp.route('/api/colonias/<int:municipio_id>', methods=['GET'])
@doctor_login_required
def api_colonias(municipio_id):
    """Carga las colonias/localidades basado en el ID del municipio seleccionado."""
    colonias_data = obtener_colonias_db(municipio_id)
    return jsonify(colonias_data)


# -------------------------------------------------------------------
# --- FUNCIÓN AUXILIAR PARA CALCULAR MÉTRICAS (BASE DE DATOS) ---
# -------------------------------------------------------------------
def calcular_metricas_reporte():
    """Consulta la DB para obtener todas las métricas necesarias para los reportes."""
    
    default_metricas = {
        'grafica_sexo': {'H': 0, 'M': 0, 'O': 0},
        'distribucion_edad': {}, 
        'codigos_generados': 0,
        'codigos_vinculados': 0,
        'total_evaluaciones': 0,
        'casos_positivos': 0,
        'casos_negativos': 0,
        'tasa_positividad': 0.0,
        'tasa_negativa': 0.0
    }
    
    try:
        # 1. Conteo General 
        query_general = """
        SELECT 
            (SELECT COUNT(id) FROM qr) as codigos_generados,
            (SELECT COUNT(id) FROM qr WHERE paciente_id IS NOT NULL) as codigos_vinculados,
            SUM(CASE WHEN resultado = 'Positivo' THEN 1 ELSE 0 END) as positivos,
            SUM(CASE WHEN resultado = 'Negativo' THEN 1 ELSE 0 END) as negativos,
            COUNT(id) as total_evaluaciones
        FROM paciente 
        WHERE resultado IS NOT NULL;
        """
        general_data = execute_query(query_general, fetch_one=True)
        
        if not general_data:
            return default_metricas

        # Conversión segura de tipos
        total = int(general_data.get('total_evaluaciones', 0) or 0)
        positivos = int(general_data.get('positivos', 0) or 0)
        negativos = int(general_data.get('negativos', 0) or 0)
        
        codigos_generados = int(general_data.get('codigos_generados', 0) or 0)
        codigos_vinculados = int(general_data.get('codigos_vinculados', 0) or 0)

        # Cálculo de tasas de forma segura
        tasa_positividad = round((float(positivos) / total) * 100, 1) if total > 0 else 0.0
        tasa_negativa = round((float(negativos) / total) * 100, 1) if total > 0 else 0.0


        # 2. Distribución por Sexo (Lógica de mapeo para 'MASCULINO'/'FEMENINO')
        query_sexo = """
        SELECT 
            UPPER(p.sexo) as sexo, 
            COUNT(p.id) as total_sexo
        FROM paciente p
        WHERE p.resultado IS NOT NULL
        GROUP BY p.sexo;
        """
        data_sexo = execute_query(query_sexo) or []
        
        distribucion_sexo = {'H': 0, 'M': 0, 'O': 0}
        for item in data_sexo:
            sexo_db_val = str(item.get('sexo', 'O')).upper().strip() 
            total_casos = int(item.get('total_sexo', 0))

            if 'MASCULINO' in sexo_db_val or sexo_db_val == 'M':
                distribucion_sexo['H'] += total_casos
            elif 'FEMENINO' in sexo_db_val or sexo_db_val == 'F':
                distribucion_sexo['M'] += total_casos
            else:
                distribucion_sexo['O'] += total_casos


        # 3. Distribución por Rango de Edad (¡SOLUCIÓN AL ERROR 1055!)
        query_edad = """
        SELECT 
            CASE 
                WHEN p.edad BETWEEN 0 AND 5 THEN '0-5 años'
                WHEN p.edad BETWEEN 6 AND 10 THEN '6-10 años'
                WHEN p.edad BETWEEN 11 AND 17 THEN '11-17 años'
                WHEN p.edad BETWEEN 18 AND 24 THEN '18-24 años'
                WHEN p.edad BETWEEN 25 AND 34 THEN '25-34 años'
                WHEN p.edad BETWEEN 35 AND 44 THEN '35-44 años'
                WHEN p.edad BETWEEN 45 AND 54 THEN '45-54 años'
                WHEN p.edad >= 55 THEN '55+ años'
                ELSE 'No especificado'
            END as rango_edad,
            COUNT(p.id) as total,
            
            -- COLUMNA TEMPORAL DE ORDENAMIENTO (SOLUCIÓN al Error 1055)
            CASE 
                WHEN p.edad BETWEEN 0 AND 5 THEN 1
                WHEN p.edad BETWEEN 6 AND 10 THEN 2
                WHEN p.edad BETWEEN 11 AND 17 THEN 3
                WHEN p.edad BETWEEN 18 AND 24 THEN 4
                WHEN p.edad BETWEEN 25 AND 34 THEN 5
                WHEN p.edad BETWEEN 35 AND 44 THEN 6
                WHEN p.edad BETWEEN 45 AND 54 THEN 7
                WHEN p.edad >= 55 THEN 8
                ELSE 9
            END as rango_orden
            
        FROM paciente p
        WHERE p.resultado IS NOT NULL AND p.edad IS NOT NULL
        GROUP BY rango_edad, rango_orden
        ORDER BY rango_orden; 
        """
        data_edad = execute_query(query_edad) or []

        distribucion_edad = {}
        for item in data_edad:
            distribucion_edad[str(item.get('rango_edad', 'N/D'))] = int(item.get('total', 0))
        
        return {
            'codigos_generados': codigos_generados,
            'codigos_vinculados': codigos_vinculados,
            'total_evaluaciones': total,
            'casos_positivos': positivos,
            'casos_negativos': negativos,
            'tasa_positividad': tasa_positividad, 
            'tasa_negativa': tasa_negativa,      
            'distribucion_sexo': distribucion_sexo,
            'distribucion_edad': distribucion_edad
        }

    except Exception as e:
        current_app.logger.error(f"Error CRÍTICO en calcular_metricas_reporte (DB): {e}")
        return default_metricas


# -------------------------------------------------------------------
# --- 1. RUTA DASHBOARD ---
# -------------------------------------------------------------------
@doctor_bp.route('/dashboard')
@doctor_login_required 
def dashboard():
    
    qrs_generados = 0
    qrs_vinculados = 0
    pacientes_positivos = 0
    ultimos_qrs_tabla = [] 
    
    try:
        # Consultas para los KPI's del dashboard
        query_generados = "SELECT COUNT(id) AS total FROM qr"
        query_vinculados = "SELECT COUNT(id) AS total FROM qr WHERE paciente_id IS NOT NULL"
        query_positivos = "SELECT COUNT(id) AS total FROM paciente WHERE resultado = 'Positivo'"
        
        generados_data = execute_query(query_generados, fetch_one=True)
        vinculados_data = execute_query(query_vinculados, fetch_one=True)
        positivos_data = execute_query(query_positivos, fetch_one=True)

        if generados_data: qrs_generados = generados_data.get('total', 0)
        if vinculados_data: qrs_vinculados = vinculados_data.get('total', 0)
        if positivos_data: pacientes_positivos = positivos_data.get('total', 0)
        
        # Consulta para la tabla de Últimos QRs Generados
        query_ultimos = """
        SELECT 
            q.codigo AS codigo_qr, 
            q.estado,
            COALESCE(CONCAT(p.nombre, ' ', p.apellido_paterno), 'N/A') AS paciente_vinculado
        FROM qr q
        LEFT JOIN paciente p ON q.paciente_id = p.id
        ORDER BY q.id DESC
        LIMIT 10
        """
        ultimos_qrs_tabla = execute_query(query_ultimos) or [] 
        
    except Exception as e:
        flash(f"Error al cargar datos del dashboard del Doctor. Detalles: {e}", "danger")
        current_app.logger.error(f"Error en doctor/dashboard: {e}")
        return redirect(url_for('auth_bp.login')) 

    return render_template('doctor/dashboard.html',
                           qrs_generados=qrs_generados,
                           qrs_vinculados=qrs_vinculados,
                           pacientes_positivos=pacientes_positivos,
                           ultimos_qrs_tabla=ultimos_qrs_tabla)


@doctor_bp.route('/reportes')
@doctor_login_required 
def reportes():
    metricas = calcular_metricas_reporte()
    
    if not isinstance(metricas, dict):
        metricas = {}

    try:
        metricas_json = json.dumps(metricas, cls=CustomJsonEncoder)
    except Exception as e:
        current_app.logger.error(f"Error de serialización JSON en reportes: {e}")
        flash("Error interno al preparar los datos para las gráficas.", "danger")
        metricas_json = json.dumps({}) 
        
    return render_template('doctor/reportes.html', 
                           metricas=metricas, 
                           metricas_json=metricas_json) 


# -------------------------------------------------------------------
# --- 5. RUTA DESCARGA DE REPORTE PDF (CON LOGOS) ---
# -------------------------------------------------------------------
@doctor_bp.route('/descargar_reporte_pdf', methods=['GET'])
@doctor_login_required 
def descargar_reporte_pdf():
    metricas = calcular_metricas_reporte()

    if not metricas or metricas.get('total_evaluaciones', 0) == 0:
        flash("No hay datos de evaluaciones completadas para generar el reporte PDF.", "warning")
        return redirect(url_for('doctor_bp.reportes'))
        
    try:
        pdf_buffer = BytesIO()
        c = canvas.Canvas(pdf_buffer, pagesize=letter)
        width, height = letter
        
        y_position = height - 50

        # === INCLUSIÓN DE LOGOS EN EL ENCABEZADO (MÉTODO ROBUSTO) ===
        
        # 1. Logo Izquierda: JURISDICCIÓN
        logo_jurisdiccion_path = os.path.join(current_app.root_path, LOGO_JURISDICCION_PATH)
        
        if os.path.exists(logo_jurisdiccion_path):
            try:
                logo_izq_reader = ImageReader(logo_jurisdiccion_path)
                c.drawImage(logo_izq_reader, 
                            50, height - 90, 
                            width=60, height=45, 
                            preserveAspectRatio=True, anchor='n')
            except Exception as e:
                current_app.logger.error(f"FALLO CRÍTICO al dibujar logo izquierdo (revisar formato PNG/JPG): {e}")
                flash("Advertencia de PDF: No se pudo cargar el logo de la izquierda. Revise el formato (PNG/JPG).", "warning")
        else:
            flash("Advertencia de PDF: El archivo de logo de la izquierda no fue encontrado. (Ruta: static/assets/img/logo_jurisdiccion.png)", "warning")

        # 2. Logo Derecha: SALUD/GOBIERNO
        logo_salud_path = os.path.join(current_app.root_path, LOGO_SALUD_PATH)
        
        if os.path.exists(logo_salud_path):
            try:
                logo_der_reader = ImageReader(logo_salud_path)
                c.drawImage(logo_der_reader, 
                            width - 110, height - 90, 
                            width=60, height=45, 
                            preserveAspectRatio=True, anchor='n')
            except Exception as e:
                current_app.logger.error(f"FALLO CRÍTICO al dibujar logo derecho (revisar formato PNG/JPG): {e}")
                flash("Advertencia de PDF: No se pudo cargar el logo de la derecha. Revise el formato (PNG/JPG).", "warning")
        else:
            flash("Advertencia de PDF: El archivo de logo de la derecha no fue encontrado. (Ruta: static/assets/img/logo_salud.png)", "warning")

        # Línea divisoria debajo del encabezado de logos
        c.setLineWidth(0.5)
        c.line(50, height - 100, width - 50, height - 100) 
        
        y_position = height - 120 
        
        # Título del Reporte
        c.setFont("Helvetica-Bold", 16)
        c.setFillColorRGB(0.1, 0.1, 0.1)
        c.drawCentredString(width / 2.0, y_position, "REPORTE ANALÍTICO DE AUTOPRUEBA VIH")
        y_position -= 25

        c.setFont("Helvetica", 10)
        c.drawCentredString(width / 2.0, y_position, f"Generado el: {datetime.now().strftime('%d/%m/%Y a las %H:%M:%S')}")
        y_position -= 40
        
        # --- SECCIÓN 1: MÉTRICAS GENERALES ---
        c.setFillColorRGB(0.8, 0.2, 0.2) 
        c.rect(50, y_position - 15, width - 100, 20, fill=1)
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(60, y_position - 10, "1. Métricas de Campaña")
        y_position -= 30
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica", 10)
        
        datos_generales = [
            (f"Códigos Generados:", f"{metricas.get('codigos_generados', 0)}"),
            (f"Códigos Vinculados:", f"{metricas.get('codigos_vinculados', 0)}"),
            (f"Total de Evaluaciones Finalizadas:", f"{metricas.get('total_evaluaciones', 0)}"),
        ]
        
        x_start = 60
        for label, value in datos_generales:
            c.drawString(x_start, y_position, label)
            c.drawString(x_start + 250, y_position, value)
            y_position -= 15
        
        y_position -= 20
        
        # --- SECCIÓN 2: TASAS DE RESULTADOS ---
        c.setFillColorRGB(0.2, 0.2, 0.8) 
        c.rect(50, y_position - 15, width - 100, 20, fill=1)
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(60, y_position - 10, "2. Resultados de las Pruebas")
        y_position -= 30
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica", 10)

        tasa_positividad = metricas.get('tasa_positividad', 0.0)
        tasa_negativa = metricas.get('tasa_negatividad', 0.0)

        datos_tasas = [
            (f"Casos Positivos:", f"{metricas.get('casos_positivos', 0)}"),
            (f"Casos Negativos:", f"{metricas.get('casos_negativos', 0)}"),
            (f"Tasa de Positividad:", f"{tasa_positividad:.1f}%"),
            (f"Tasa de Negatividad:", f"{tasa_negativa:.1f}%"),
        ]
        
        for label, value in datos_tasas:
            c.drawString(x_start, y_position, label)
            c.drawString(x_start + 250, y_position, value)
            y_position -= 15

        if y_position < 100:
            c.showPage()
            y_position = height - 50
        
        y_position -= 20
        
        # --- SECCIÓN 3: DISTRIBUCIÓN POR SEXO ---
        c.setFillColorRGB(0.2, 0.8, 0.2) 
        c.rect(50, y_position - 15, width - 100, 20, fill=1)
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(60, y_position - 10, "3. Distribución por Sexo")
        y_position -= 30
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica", 10)

        distribucion_sexo = metricas.get('distribucion_sexo', {'H': 0, 'M': 0, 'O': 0})
        total_sexo = sum(distribucion_sexo.values())

        datos_sexo = [
            ("Hombres:", distribucion_sexo.get('H', 0)),
            ("Mujeres:", distribucion_sexo.get('M', 0)),
            ("Otro/No especificado:", distribucion_sexo.get('O', 0)),
        ]
        
        for label, count in datos_sexo:
            percent = (count / total_sexo) * 100 if total_sexo > 0 else 0.0
            c.drawString(x_start, y_position, label)
            c.drawString(x_start + 250, y_position, f"{count} ({percent:.1f}%)")
            y_position -= 15
            
        if y_position < 100:
            c.showPage()
            y_position = height - 50
            
        y_position -= 20

        # --- SECCIÓN 4: DISTRIBUCIÓN POR EDAD (RANGOS ACTUALIZADOS) ---
        c.setFillColorRGB(0.8, 0.5, 0.2) 
        c.rect(50, y_position - 15, width - 100, 20, fill=1)
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(60, y_position - 10, "4. Distribución por Rango de Edad")
        y_position -= 30
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica", 10)

        distribucion_edad = metricas.get('distribucion_edad', {})
        total_edad = sum(distribucion_edad.values())
        
        # Usar los rangos definidos en la consulta SQL
        rangos_ordenados = ['0-5 años', '6-10 años', '11-17 años', '18-24 años', '25-34 años', '35-44 años', '45-54 años', '55+ años', 'No especificado']
        
        for rango in rangos_ordenados:
            count = distribucion_edad.get(rango, 0)
            percent = (count / total_edad) * 100 if total_edad > 0 else 0.0
            
            if count > 0 or rango in distribucion_edad:
                c.drawString(x_start, y_position, f"{rango}:")
                c.drawString(x_start + 250, y_position, f"{count} ({percent:.1f}%)")
                y_position -= 15
                
                if y_position < 50:
                    c.showPage()
                    y_position = height - 50
                    c.setFont("Helvetica", 10)
        
        # Finalizar el PDF
        c.showPage()
        c.save()
        pdf_buffer.seek(0)
        
        flash("Reporte Analítico descargado exitosamente.", "success")
        return send_file(pdf_buffer, 
                         as_attachment=True, 
                         download_name=f"Reporte_Analitico_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf", 
                         mimetype='application/pdf')

    except Exception as e:
        flash(f"Error CRÍTICO al generar el reporte PDF: {e}", "danger")
        current_app.logger.error(f"Error en descargar_reporte_pdf con logos: {e}")
        return redirect(url_for('doctor_bp.reportes'))


# -------------------------------------------------------------------
# --- 2. GENERAR QR (ACTUALIZADO: DESCARGA INMEDIATA PDF MULTI-PÁGINA) ---
# -------------------------------------------------------------------
@doctor_bp.route('/generar_qr', methods=['GET', 'POST'])
@doctor_login_required 
def generar_qr():
    # 1. Obtener la lista de estados (para la primera carga del formulario)
    estados_disponibles = obtener_estados_db()
    
    # 2. Inicializar 'data' con valores por defecto o los valores del POST.
    data = {
        'campaign_number': request.form.get('campaign_number', ''), 
        'estado_id': request.form.get('estado_id', ''), 
        'municipio_id': request.form.get('municipio_id', ''), 
        'colonia_id': request.form.get('colonia_id', ''), 
        'delivery_date': request.form.get('delivery_date', datetime.now().strftime('%Y-%m-%d')), 
        'quantity': request.form.get('quantity', '1') 
    }
    
    numero_campana = data['campaign_number'] 
    estado_id = data['estado_id']
    municipio_id = data['municipio_id']
    colonia_id = data['colonia_id']
    fecha_entrega_str = data['delivery_date']
    cantidad_qr_str = data['quantity']
    
    if request.method == 'POST':
        
        try:
            cantidad_qr = int(cantidad_qr_str)
            fecha_entrega = datetime.strptime(fecha_entrega_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            flash("Error en la cantidad o formato de fecha. Usa números enteros y el formato AAAA-MM-DD.", "danger")
            # 🛑 PASAMOS LA LISTA DE ESTADOS EN CASO DE ERROR POST
            return render_template('doctor/generar_qr.html', data=data, estados=estados_disponibles)
        
        if cantidad_qr <= 0 or cantidad_qr > 100: # Limitamos a 100 por lote PDF
            flash("La cantidad de QRs debe ser mayor a cero y menor a 100 por lote.", "warning")
            return render_template('doctor/generar_qr.html', data=data, estados=estados_disponibles)
        
        if not numero_campana or not estado_id or not municipio_id or not colonia_id:
            flash("La Campaña, Estado, Municipio y Localidad son obligatorios.", "warning")
            return render_template('doctor/generar_qr.html', data=data, estados=estados_disponibles)
        
        try:
            estado_id = int(estado_id)
            municipio_id = int(municipio_id)
            colonia_id = int(colonia_id)
        except ValueError:
             flash("Error de validación: Los identificadores de ubicación deben ser números.", "danger")
             return render_template('doctor/generar_qr.html', data=data, estados=estados_disponibles)

        # 3. OBTENER LOS NOMBRES COMPLETOS ANTES DE INSERTAR EN LA DB
        query_colonia = "SELECT asentamiento FROM colonias WHERE id = %s"
        colonia_data = execute_query(query_colonia, (colonia_id,), fetch_one=True)
        colonia_nombre = colonia_data['asentamiento'] if colonia_data else 'No Encontrado'
        
        query_municipio = "SELECT nombre FROM municipios WHERE id = %s"
        municipio_data = execute_query(query_municipio, (municipio_id,), fetch_one=True)
        municipio_nombre = municipio_data['nombre'] if municipio_data else 'No Encontrado'
        
        query_estado = "SELECT nombre FROM estados WHERE id = %s"
        estado_data = execute_query(query_estado, (estado_id,), fetch_one=True)
        estado_nombre_geografico = estado_data['nombre'] if estado_data else 'No Encontrado'

        estado_qr_uso = "Generado"
        qrs_generados_exitosamente = 0
        codigos_generados = []

        try:
            # 🛑 CONSULTA DE INSERCIÓN FINAL:
            query = """
            INSERT INTO qr (codigo, numero_campana, lugar_entrega, localidad_entrega, fecha_entrega, estado, estado_geografico)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            
            for i in range(cantidad_qr):
                codigo_qr_unico = str(uuid.uuid4())
                
                success = execute_query(query, (codigo_qr_unico, 
                                                numero_campana, 
                                                colonia_nombre, 
                                                municipio_nombre,
                                                fecha_entrega, 
                                                estado_qr_uso, 
                                                estado_nombre_geografico),
                                        commit=True)
                
                if success is not None and success > 0:
                    qrs_generados_exitosamente += 1
                    codigos_generados.append(codigo_qr_unico)

            if qrs_generados_exitosamente > 0:
                # --- Generar PDF Multi-página para la descarga ---
                pdf_buffer = BytesIO()
                c = canvas.Canvas(pdf_buffer, pagesize=letter)
                width, height = letter
                
                x_margin = 60
                y_start = height - 50
                qr_size = 180 
                line_spacing = 30
                
                for index, codigo in enumerate(codigos_generados):
                    if index > 0 and index % 3 == 0:
                        c.showPage()
                        y_start = height - 50
                    
                    y_position = y_start - (index % 3) * 220 
                    
                    url_para_qr = f"{BASE_URL}{url_for('paciente_bp.acceso_qr', qr_codigo=codigo)}" 
                    
                    c.setFont("Helvetica-Bold", 14)
                    c.drawString(x_margin, y_position, f"Campaña: {numero_campana}")
                    c.setFont("Helvetica", 10)
                    y_position -= line_spacing
                    c.drawString(x_margin, y_position, f"Lugar: {colonia_nombre} ({municipio_nombre}, {estado_nombre_geografico})") 
                    y_position -= line_spacing
                    c.drawString(x_margin, y_position, f"Código: {codigo}")

                    qr_img = qrcode.make(url_para_qr)
                    img_buffer = BytesIO(); qr_img.save(img_buffer, "PNG"); img_buffer.seek(0)
                    qr_image_reader = ImageReader(img_buffer)
                    
                    c.drawImage(qr_image_reader, x_margin + 300, y_position - qr_size + 30, width=qr_size, height=qr_size)
                    
                c.showPage(); c.save(); pdf_buffer.seek(0)
                
                flash(f"✅ ¡Éxito! Se generaron y registraron {qrs_generados_exitosamente} QRs. El PDF está descargando.", "success")
                
                return send_file(pdf_buffer, 
                                 as_attachment=True, 
                                 download_name=f"QRs_Lote_{numero_campana}_{datetime.now().strftime('%Y%m%d')}.pdf", 
                                 mimetype='application/pdf')
            
            else:
                flash("Error al generar los QRs. No se insertó ninguno en la base de datos.", "danger")
                
        except Exception as e:
            flash(f"Error CRÍTICO al generar QRs y PDF: {e}", "danger")
            current_app.logger.error(f"Error en generar_qr: {e}")
            
        return redirect(url_for('doctor_bp.dashboard')) 

    # GET: Muestra el formulario, pasando los estados
    return render_template('doctor/generar_qr.html', data=data, estados=estados_disponibles)

@doctor_bp.route('/descargar_qr/<string:codigo_qr>', methods=['GET'])
@doctor_login_required 
def descargar_qr(codigo_qr):
    query = "SELECT codigo, numero_campana, lugar_entrega FROM qr WHERE codigo = %s"
    qr_data = execute_query(query, (codigo_qr,), fetch_one=True)
    
    if not qr_data:
        flash("Error: El código QR solicitado no existe.", "danger")
        return redirect(url_for('doctor_bp.dashboard')) 
    
    try:
        url_para_qr = f"{BASE_URL}{url_for('paciente_bp.acceso_qr', qr_codigo=codigo_qr)}"
        
        pdf_buffer = BytesIO()
        c = canvas.Canvas(pdf_buffer, pagesize=letter)
        width, height = letter
        
        c.setFont("Helvetica-Bold", 16); c.drawCentredString(width / 2.0, height - 40, "CÓDIGO QR AUTOPRUEBA")
        c.setFont("Helvetica", 10)
        c.drawString(50, height - 90, f"Código: {qr_data['codigo'][:8]}...")
        c.drawString(50, height - 110, f"Campaña: {qr_data['numero_campana']}")
        c.drawString(50, height - 130, f"Lugar: {qr_data['lugar_entrega']}")

        qr_img = qrcode.make(url_para_qr)
        img_buffer = BytesIO(); qr_img.save(img_buffer, "PNG"); img_buffer.seek(0)
        qr_image_reader = ImageReader(img_buffer)
        c.drawImage(qr_image_reader, (width - 200) / 2.0, height - 400, width=200, height=200)

        c.showPage(); c.save(); pdf_buffer.seek(0)
        
        flash(f"Descargando QR: {codigo_qr[:8]}...", "info")
        return send_file(pdf_buffer, 
                         as_attachment=True, 
                         download_name=f"QR_Autoprueba_{codigo_qr[:8]}.pdf", 
                         mimetype='application/pdf')

    except Exception as e:
        flash(f"Error al generar el PDF: {e}", "danger")
        current_app.logger.error(f"Error en descargar_qr: {e}")
        return redirect(url_for('doctor_bp.dashboard'))