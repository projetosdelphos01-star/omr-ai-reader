import os
import tempfile
import json
import re
from typing import Optional, Tuple, Dict, Any
from datetime import datetime
from dotenv import load_dotenv
from google import genai

# Carregar variáveis de ambiente do arquivo .env
load_dotenv()

ALLOWED_AUDIO_EXTENSIONS = {"mp3", "wav", "m4a", "ogg"}


def _log_debug(message: str, data: Optional[Dict[str, Any]] = None):
    """Função auxiliar para logs de depuração"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    log_msg = f"[{timestamp}] [AUDIO_DEBUG] {message}"
    if data:
        log_msg += f" | Dados: {json.dumps(data, ensure_ascii=False, default=str)}"
    print(log_msg)


def _allowed_audio(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_AUDIO_EXTENSIONS


def _extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text or "", re.IGNORECASE)
    candidate = fenced.group(1) if fenced else (text or "")
    candidate = candidate.replace("```", "").strip()
    try:
        return json.loads(candidate)
    except Exception:
        pass
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end != -1 and end > start:
        inner = candidate[start : end + 1]
        try:
            return json.loads(inner)
        except Exception:
            return None
    return None


def analyze_audio_request(file_storage, reference_text: Optional[str]) -> Tuple[Dict[str, Any], int]:
    _log_debug("Iniciando análise de áudio", {
        "has_file_storage": bool(file_storage),
        "filename": file_storage.filename if file_storage else None,
        "has_reference_text": bool(reference_text),
        "reference_text_length": len(reference_text) if reference_text else 0
    })
    
    if not file_storage:
        _log_debug("Arquivo não fornecido")
        return {"status": "no_file", "message": "Nenhum arquivo de áudio enviado"}, 200

    if file_storage.filename == "":
        _log_debug("Nome do arquivo vazio")
        return {"status": "no_file", "message": "Nenhum arquivo de áudio selecionado"}, 200

    if not _allowed_audio(file_storage.filename):
        _log_debug("Tipo de arquivo não permitido", {"filename": file_storage.filename})
        return {
            "status": "invalid_file_type",
            "message": f"Tipo de arquivo não permitido. Use: {', '.join(sorted(ALLOWED_AUDIO_EXTENSIONS))}"
        }, 200

    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") 
    if not api_key:
        _log_debug("GOOGLE_API_KEY não configurada")
        return {
            "status": "config_error",
            "message": "GOOGLE_API_KEY não configurada no ambiente."
        }, 500
    
    _log_debug("API Key encontrada", {"key_length": len(api_key) if api_key else 0})

    try:
        _log_debug("Criando cliente Google Gemini")
        client = genai.Client(api_key=api_key)

        suffix = os.path.splitext(file_storage.filename)[1] or ".m4a"
        _log_debug("Salvando arquivo temporário", {
            "filename": file_storage.filename,
            "suffix": suffix
        })
        
        # Ler o arquivo para obter o tamanho
        file_storage.seek(0)  # Resetar posição do arquivo
        file_data = file_storage.read()
        file_size = len(file_data)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(file_data)
            temp_audio_path = tmp.name

        _log_debug("Arquivo temporário criado", {
            "temp_path": temp_audio_path,
            "file_size": file_size,
            "file_size_mb": round(file_size / (1024 * 1024), 2)
        })

        try:
            _log_debug("Iniciando upload para Google Gemini")
            uploaded = client.files.upload(file=temp_audio_path)
            _log_debug("Upload concluído", {
                "uploaded_file_name": getattr(uploaded, 'name', None),
                "uploaded_file_uri": getattr(uploaded, 'uri', None)
            })

            base_instructions = (
                "Você é um avaliador de leitura em voz alta. Analise a fluência, pronúncia, entonação, ritmo, pausas, "
                "clareza e erros. Se um texto de referência for fornecido, realize o alinhamento e compare o que foi "
                "lido com o texto (palavras faltantes, inseridas, trocadas), tempo total e velocidade (palavras por minuto). "
                "Responda ESTRITAMENTE em JSON no formato especificado a seguir; cada avaliação vai de 0 a 10."
            )

            schema_example = {
                "overall_score": 0.0,
                "fluency": {"score": 0.0, "feedback": ""},
                "pronunciation": {"score": 0.0, "feedback": ""},
                "intonation": {"score": 0.0, "feedback": ""},
                "rhythm": {"score": 0.0, "feedback": ""},
                "pauses": {"score": 0.0, "feedback": ""},
                "clarity": {"score": 0.0, "feedback": ""},
                "duration_seconds": 0.0,
                "words_per_minute": 0.0,
                "reference_used": bool(bool(reference_text)),
                "alignment": {
                    "words_total": 0,
                    "words_read": 0,
                    "words_missing": [],
                    "words_inserted": [],
                    "words_substituted": [],
                    "accuracy_percent": 0.0
                },
                "suggestions": []
            }

            contents = [base_instructions, f"Formato JSON obrigatório: {json.dumps(schema_example)}"]
            if reference_text:
                contents.append(f"Texto de referência (PT-BR):\n{reference_text}")
            contents.append(uploaded)

            _log_debug("Enviando requisição para Gemini", {
                "model": "gemini-2.5-flash",
                "has_reference_text": bool(reference_text),
                "contents_count": len(contents),
                "reference_text_preview": reference_text[:100] + "..." if reference_text and len(reference_text) > 100 else reference_text
            })

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=contents
            )

            _log_debug("Resposta recebida do Gemini", {
                "response_length": len(response.text) if response.text else 0,
                "response_preview": (response.text[:200] + "...") if response.text and len(response.text) > 200 else response.text
            })

            parsed = _extract_json_from_text(response.text or "")
            _log_debug("JSON extraído", {
                "parsed_successfully": parsed is not None,
                "parsed_keys": list(parsed.keys()) if parsed else None
            })
            
            evaluation = parsed if parsed is not None else {"raw": (response.text or "").replace("```", "").strip()}
            
            if parsed is None:
                _log_debug("Falha ao fazer parse do JSON, retornando resposta raw", {
                    "raw_length": len(evaluation.get("raw", ""))
                })

            _log_debug("Análise concluída com sucesso", {
                "evaluation_keys": list(evaluation.keys()) if isinstance(evaluation, dict) else None
            })

            return {"status": "success", "evaluation": evaluation}, 200
        finally:
            try:
                _log_debug("Removendo arquivo temporário", {"temp_path": temp_audio_path})
                os.unlink(temp_audio_path)
            except Exception as cleanup_error:
                _log_debug("Erro ao remover arquivo temporário", {"error": str(cleanup_error)})
    except Exception as e:
        _log_debug("Erro durante análise de áudio", {
            "error_type": type(e).__name__,
            "error_message": str(e),
            "error_details": repr(e)
        })
        return {"status": "processing_error", "message": f"Erro ao analisar áudio: {str(e)}"}, 500
