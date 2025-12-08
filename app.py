from flask import Flask, request, jsonify
from flask_cors import CORS, cross_origin
from flasgger import Swagger, swag_from
from omr.service import process_request
from audio_converter.audio_service import analyze_audio_request
import re
import json

app = Flask(__name__)

# Lista de origens permitidas
allowed_origins = [
    'https://florescer.tec.br',
    'https://www.florescer.tec.br',
    'https://api.florescer.tec.br',
    'https://ia.florescer.tec.br',
]

# Função para validar origens permitidas (usada pelo flask-cors)
def origin_check(origin):
    """Verifica se a origem é permitida"""
    if not origin:
        return True  # Permite requisições sem origin (mobile apps, curl, etc)
    
    # Verifica lista fixa de produção
    if origin in allowed_origins:
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
# Usando função para validar origens dinamicamente via after_request
CORS(app, 
     resources={r"/api/*": {"origins": "*"}},  # Permite todas as origens para /api/*
     methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'],
     allow_headers=['Content-Type', 'Authorization', 'X-Requested-With', 'Origin', 'Accept'],
     supports_credentials=True,
     expose_headers=['Authorization'],
     automatic_options=True)  # Responde automaticamente a OPTIONS

# Handler global de erros para garantir que headers CORS sejam sempre enviados
@app.errorhandler(Exception)
def handle_exception(e):
    """Garante que headers CORS sejam enviados mesmo em caso de erro"""
    from werkzeug.exceptions import HTTPException
    
    if isinstance(e, HTTPException):
        response = jsonify({
            "error": e.name,
            "message": e.description,
            "code": e.code
        })
        response.status_code = e.code
    else:
        response = jsonify({
            "error": "Internal Server Error",
            "message": str(e) if app.debug else "An internal error occurred",
            "code": 500
        })
        response.status_code = 500
    
    # Adicionar headers CORS manualmente se necessário
    origin = request.headers.get('Origin')
    if origin and origin_check(origin):
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
    
    return response

swagger = Swagger(app)

# Hook after_request para garantir headers CORS em todas as respostas
@app.after_request
def after_request(response):
    """Adiciona headers CORS em todas as respostas"""
    origin = request.headers.get('Origin')
    
    if origin and origin_check(origin):
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, PATCH, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With, Origin, Accept'
        response.headers['Access-Control-Expose-Headers'] = 'Authorization'
    
    # Para requisições OPTIONS (preflight), retornar 200
    if request.method == 'OPTIONS':
        response.status_code = 200
    
    return response

@app.route('/api/processar-omr', methods=['POST', 'OPTIONS'])
@cross_origin(origins=allowed_origins, supports_credentials=True)
@swag_from('omr/docs/omr_process.yml')
def upload_file():
    """Processar imagem OMR"""
    if request.method == 'OPTIONS':
        return '', 200
    
    result, status = process_request(
        file_storage=request.files.get('file'),
        gabarito_json_str=request.form.get('gabarito')
    )
    return jsonify(result), status

@app.route('/api/analisar-audio', methods=['POST', 'OPTIONS'])
@cross_origin(origins=allowed_origins, supports_credentials=True)
@swag_from('omr/docs/audio_analyze.yml')
def analyze_audio():
    """Analisar leitura do aluno via áudio"""
    if request.method == 'OPTIONS':
        return '', 200

    # Logs de depuração na rota
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] [ROUTE_DEBUG] Recebida requisição POST /api/analisar-audio")
    print(f"[{timestamp}] [ROUTE_DEBUG] Content-Type: {request.content_type}")
    print(f"[{timestamp}] [ROUTE_DEBUG] FILES keys: {list(request.files.keys())}")
    print(f"[{timestamp}] [ROUTE_DEBUG] FORM keys: {list(request.form.keys())}")
    
    audio_file = request.files.get('audio')
    texto = request.form.get('texto')
    
    if audio_file:
        print(f"[{timestamp}] [ROUTE_DEBUG] Arquivo recebido: {audio_file.filename}, tamanho: {audio_file.content_length if hasattr(audio_file, 'content_length') else 'N/A'}")
    else:
        print(f"[{timestamp}] [ROUTE_DEBUG] Nenhum arquivo de áudio encontrado")
    
    if texto:
        print(f"[{timestamp}] [ROUTE_DEBUG] Texto de referência recebido, tamanho: {len(texto)} caracteres")
        print(f"[{timestamp}] [ROUTE_DEBUG] Texto preview: {texto[:100]}..." if len(texto) > 100 else f"[{timestamp}] [ROUTE_DEBUG] Texto: {texto}")
    else:
        print(f"[{timestamp}] [ROUTE_DEBUG] Nenhum texto de referência fornecido")
    
    result, status = analyze_audio_request(
        file_storage=audio_file,
        reference_text=texto
    )
    
    print(f"[{timestamp}] [ROUTE_DEBUG] Resultado retornado, status: {status}")
    print(f"[{timestamp}] [ROUTE_DEBUG] Resultado: {json.dumps(result, ensure_ascii=False, default=str)[:500]}...")
    
    return jsonify(result), status

@app.route('/')
@swag_from('omr/docs/health.yml')
def index():
    return "API de Processamento OMR - Envie uma imagem para /api/processar-omr (docs em /apidocs)"

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
