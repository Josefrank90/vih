# utils/qr_manager.py

import os
import qrcode
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from flask import current_app, url_for

def generar_qr_y_pdf(qr_token, url_acceso):
    """
    Genera la imagen del Código QR con la URL de acceso y la incrusta en un PDF.
    
    :param qr_token: Token único que identifica el QR.
    :param url_acceso: La URL completa que el paciente escaneará.
    :return: La ruta completa del archivo PDF generado.
    """
    
    # Rutas de archivos: Obtener la ruta de la carpeta de configuración
    qr_filename = f'QR_{qr_token}.png'
    pdf_filename = f'QR_{qr_token}.pdf'
    
    qr_img_path = os.path.join(current_app.config['QR_PDF_FOLDER'], qr_filename)
    pdf_path = os.path.join(current_app.config['QR_PDF_FOLDER'], pdf_filename)

    # --- 1. Generar la Imagen del Código QR ---
    try:
        # Crea el objeto QR
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(url_acceso)
        qr.make(fit=True)

        # Crea la imagen del QR y la guarda temporalmente
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(qr_img_path)

    except Exception as e:
        print(f"Error al generar la imagen QR: {e}")
        # En una aplicación real, aquí podrías manejar el error de forma más elegante
        raise 

    # --- 2. Generar el Documento PDF ---
    try:
        c = canvas.Canvas(pdf_path, pagesize=letter)
        ancho, alto = letter

        # ... [El resto del código de ReportLab para dibujar el PDF] ...
        # (Este código es largo, pero crucial. Asegúrate de que esté incluido)

        # Título
        c.setFont("Helvetica-Bold", 16)
        c.drawCentredString(ancho / 2, alto - inch, "Sistema de Autoprueba VIH")

        # Instrucciones
        c.setFont("Helvetica", 12)
        c.drawString(inch, alto - 1.5 * inch, "Instrucciones para el Paciente:")
        c.drawString(inch, alto - 1.7 * inch, "1. Escanee el código QR a continuación con su teléfono.")
        c.drawString(inch, alto - 1.9 * inch, "2. Siga las instrucciones en pantalla para completar la autoprueba.")
        c.drawString(inch, alto - 2.1 * inch, f"3. Token de Referencia: {qr_token}")

        # Incrustar la imagen del QR
        qr_width = 3 * inch
        qr_height = 3 * inch 
        x_pos = (ancho - qr_width) / 2
        y_pos = alto - 5.5 * inch
        
        c.drawImage(qr_img_path, x_pos, y_pos, width=qr_width, height=qr_height)

        # Pie de página
        c.setFont("Helvetica-Oblique", 10)
        c.drawCentredString(ancho / 2, 0.5 * inch, "Confidencial - Material de uso interno.")

        c.showPage()
        c.save()

    except Exception as e:
        print(f"Error al generar el PDF: {e}")
        raise
    finally:
        # 3. Eliminar la imagen temporal del QR
        if os.path.exists(qr_img_path):
            os.remove(qr_img_path)
            
    return pdf_path # ¡Retorna la ruta del PDF!

# NOTA: Asegúrate de que las dependencias 'qrcode' y 'reportlab' estén instaladas