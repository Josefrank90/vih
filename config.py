import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'una_clave_de_respaldo_segura'
    
   
    MYSQL_HOST = 'localhost'        
    MYSQL_USER = 'root'
    MYSQL_PASSWORD = 'jose2003'   
    MYSQL_DB = 'autopruebas_vih'   
    MYSQL_PORT = 3306

    QR_PDF_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'static/qrs_pdf')
    if not os.path.exists(QR_PDF_FOLDER):
        os.makedirs(QR_PDF_FOLDER)