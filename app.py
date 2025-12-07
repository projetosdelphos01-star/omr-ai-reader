from flask import Flask, request, jsonify
from flask_cors import CORS
from flasgger import Swagger, swag_from
from omr.service import process_request
from audio_converter.audio_service import analyze_audio_request
import re

app = Flask(__name__)

# Função para validar origens permitidas
def is_origin_allowed(origin):
    """Verifica se a origem é permitida"""
    if not origin:
        return True  # Permite requisições sem origin (mobile apps, curl, etc)
    
    # Origens de produção permitidas
    allowed_production = [
        'https://florescer.tec.br',
        'https://www.florescer.tec.br',
        'https://api.florescer.tec.br',
        'https://ia.florescer.tec.br',
    ]
    
    if origin in allowed_production:
        return True
    
    # Permite localhost em qualquer porta (desenvolvimento)
    if re.match(r'^http://localhost:\d+$', origin) or re.match(r'^http://127\.0\.0\.1:\d+$', origin):
        return True
    
    # Permite IPs de rede local
    if re.match(r'^http://192\.168\.\d+\.\d+:\d+$', origin) or \
       re.match(r'^http://10\.\d+\.\d+\.\d+:\d+$', origin) or \
       re.match(r'^http://172\.(1[6-9]|2[0-9]|3[0-1])\.\d+\.\d+:\d+$', origin):
        return True
    
    return False

# Configurar CORS para permitir requisições do frontend
CORS(app, 
     origins=is_origin_allowed,
     methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'],
     allow_headers=['Content-Type', 'Authorization', 'X-Requested-With', 'Origin', 'Accept'],
     supports_credentials=True)

swagger = Swagger(app)

   

@app.route('/api/processar-omr', methods=['POST'])
@swag_from('omr/docs/omr_process.yml')
def upload_file():
    """Processar imagem OMR"""
    result, status = process_request(
        file_storage=request.files.get('file'),
        gabarito_json_str=request.form.get('gabarito')
    )
    return jsonify(result), status

@app.route('/api/analisar-audio', methods=['POST'])
@swag_from('omr/docs/audio_analyze.yml')
def analyze_audio():
    """Analisar leitura do aluno via áudio"""

    # em app.py, dentro de analyze_audio()
    print("Content-Type:", request.content_type)
    print("FILES keys:", list(request.files.keys()))
    print("FORM keys:", list(request.form.keys()))
    result, status = analyze_audio_request(
        file_storage=request.files.get('audio'),
        reference_text=request.form.get('texto')
    )
    print(result)
    return jsonify(result), status

@app.route('/')
@swag_from('omr/docs/health.yml')
def index():
    return "API de Processamento OMR - Envie uma imagem para /api/processar-omr (docs em /apidocs)"

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
