import os
import tempfile
import json
from typing import Optional, Tuple, Dict, Any
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
from openai import APIError, RateLimitError, APIConnectionError

# Carregar variáveis de ambiente do arquivo .env
load_dotenv()

ALLOWED_AUDIO_EXTENSIONS = {"mp3", "wav", "m4a", "ogg", "webm"}


def _log_debug(message: str, data: Optional[Dict[str, Any]] = None):
    """Função auxiliar para logs de depuração"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    log_msg = f"[{timestamp}] [AUDIO_DEBUG] {message}"
    if data:
        log_msg += f" | Dados: {json.dumps(data, ensure_ascii=False, default=str)}"
    print(log_msg)


def _allowed_audio(filename: str) -> bool:
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_AUDIO_EXTENSIONS
    )


def analyze_audio_request(
    file_storage, reference_text: Optional[str]
) -> Tuple[Dict[str, Any], int]:
    """
    Analisa áudio de leitura usando OpenAI (Whisper + GPT-4o).

    Fluxo:
    1. Transcreve o áudio usando Whisper API
    2. Analisa a transcrição usando GPT-4o com JSON mode
    3. Retorna avaliação estruturada compatível com o frontend
    """
    _log_debug(
        "Iniciando análise de áudio",
        {
            "has_file_storage": bool(file_storage),
            "filename": file_storage.filename if file_storage else None,
            "has_reference_text": bool(reference_text),
            "reference_text_length": len(reference_text) if reference_text else 0,
        },
    )

    if not file_storage:
        _log_debug("Arquivo não fornecido")
        return {"status": "no_file", "message": "Nenhum arquivo de áudio enviado"}, 200

    if file_storage.filename == "":
        _log_debug("Nome do arquivo vazio")
        return {
            "status": "no_file",
            "message": "Nenhum arquivo de áudio selecionado",
        }, 200

    if not _allowed_audio(file_storage.filename):
        _log_debug("Tipo de arquivo não permitido", {"filename": file_storage.filename})
        return {
            "status": "invalid_file_type",
            "message": f"Tipo de arquivo não permitido. Use: {', '.join(sorted(ALLOWED_AUDIO_EXTENSIONS))}",
        }, 200

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        _log_debug("OPENAI_API_KEY não configurada")
        return {
            "status": "config_error",
            "message": "OPENAI_API_KEY não configurada no ambiente.",
        }, 500

    _log_debug("API Key encontrada", {"key_length": len(api_key) if api_key else 0})

    try:
        _log_debug("Criando cliente OpenAI")
        client = OpenAI(api_key=api_key)

        suffix = os.path.splitext(file_storage.filename)[1] or ".m4a"
        _log_debug(
            "Salvando arquivo temporário",
            {"filename": file_storage.filename, "suffix": suffix},
        )

        # Ler o arquivo para obter o tamanho
        file_storage.seek(0)  # Resetar posição do arquivo
        file_data = file_storage.read()
        file_size = len(file_data)

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(file_data)
            temp_audio_path = tmp.name

        _log_debug(
            "Arquivo temporário criado",
            {
                "temp_path": temp_audio_path,
                "file_size": file_size,
                "file_size_mb": round(file_size / (1024 * 1024), 2),
            },
        )

        try:
            # ============================================================
            # PASSO 1: Transcrição com Whisper API
            # ============================================================
            _log_debug("Iniciando transcrição com Whisper")

            with open(temp_audio_path, "rb") as audio_file:
                transcription = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="pt",
                    response_format="verbose_json",
                )

            transcribed_text = transcription.text
            audio_duration = getattr(transcription, "duration", 0.0) or 0.0

            _log_debug(
                "Transcrição concluída",
                {
                    "transcribed_text_length": len(transcribed_text),
                    "transcribed_text_preview": (
                        transcribed_text[:200] + "..."
                        if len(transcribed_text) > 200
                        else transcribed_text
                    ),
                    "audio_duration": audio_duration,
                },
            )

            # Calcular palavras por minuto
            word_count = len(transcribed_text.split()) if transcribed_text else 0
            words_per_minute = (
                (word_count / audio_duration * 60) if audio_duration > 0 else 0.0
            )

            # ============================================================
            # PASSO 2: Análise com GPT-4o
            # ============================================================
            _log_debug("Iniciando análise com GPT-4o")

            system_prompt = """Você é um avaliador especializado em leitura em voz alta para estudantes brasileiros. 
Analise a transcrição da leitura e avalie os seguintes critérios: fluência, pronúncia, entonação, ritmo, pausas e clareza.
Se um texto de referência for fornecido, compare o que foi lido com o texto esperado, identificando palavras faltantes, inseridas ou trocadas.
Responda ESTRITAMENTE em JSON válido no formato especificado. Cada score deve ser de 0 a 10."""

            # Construir o prompt do usuário
            user_content = f"""Transcrição da leitura do aluno:
{transcribed_text}

Duração do áudio: {audio_duration:.1f} segundos
Palavras lidas: {word_count}
Velocidade calculada: {words_per_minute:.1f} palavras por minuto

"""
            if reference_text:
                user_content += f"""Texto de referência (PT-BR):
{reference_text}

Compare a transcrição com o texto de referência para identificar palavras faltantes, inseridas ou substituídas.
"""
            else:
                user_content += "Nenhum texto de referência fornecido. Avalie apenas a qualidade geral da leitura.\n"

            user_content += f"""
Retorne um JSON no seguinte formato exato:
{{
    "overall_score": <número de 0 a 10>,
    "fluency": {{"score": <0-10>, "feedback": "<feedback sobre fluência>"}},
    "pronunciation": {{"score": <0-10>, "feedback": "<feedback sobre pronúncia>"}},
    "intonation": {{"score": <0-10>, "feedback": "<feedback sobre entonação>"}},
    "rhythm": {{"score": <0-10>, "feedback": "<feedback sobre ritmo>"}},
    "pauses": {{"score": <0-10>, "feedback": "<feedback sobre pausas>"}},
    "clarity": {{"score": <0-10>, "feedback": "<feedback sobre clareza>"}},
    "duration_seconds": {audio_duration:.1f},
    "words_per_minute": {words_per_minute:.1f},
    "reference_used": {str(bool(reference_text)).lower()},
    "alignment": {{
        "words_total": <número total de palavras no texto de referência ou na transcrição>,
        "words_read": <número de palavras lidas corretamente>,
        "words_missing": [<lista de palavras que deveriam ter sido lidas mas não foram>],
        "words_inserted": [<lista de palavras lidas que não estavam no texto de referência>],
        "words_substituted": [<lista de objetos {{"expected": "palavra_esperada", "read": "palavra_lida"}}>],
        "accuracy_percent": <porcentagem de precisão 0-100>
    }},
    "suggestions": [<lista de sugestões de melhoria>]
}}

Importante:
- O overall_score deve ser a média ponderada dos outros scores
- Se não houver texto de referência, calcule o alignment baseado apenas na transcrição
- Forneça feedback construtivo e específico em português brasileiro
- As sugestões devem ser práticas e encorajadoras"""

            _log_debug(
                "Enviando requisição para GPT-4o",
                {
                    "model": "gpt-4o-mini",
                    "has_reference_text": bool(reference_text),
                    "transcription_length": len(transcribed_text),
                },
            )

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.3,
            )

            response_content = response.choices[0].message.content
            _log_debug(
                "Resposta recebida do GPT-4o",
                {
                    "response_length": len(response_content) if response_content else 0,
                    "response_preview": (
                        (response_content[:200] + "...")
                        if response_content and len(response_content) > 200
                        else response_content
                    ),
                },
            )

            # Parse do JSON (garantido pelo response_format)
            evaluation = json.loads(response_content)

            _log_debug(
                "JSON parsed com sucesso",
                {
                    "evaluation_keys": (
                        list(evaluation.keys())
                        if isinstance(evaluation, dict)
                        else None
                    )
                },
            )

            _log_debug(
                "Análise concluída com sucesso",
                {
                    "overall_score": evaluation.get("overall_score"),
                    "words_per_minute": evaluation.get("words_per_minute"),
                },
            )

            return {"status": "success", "evaluation": evaluation}, 200

        finally:
            try:
                _log_debug(
                    "Removendo arquivo temporário", {"temp_path": temp_audio_path}
                )
                os.unlink(temp_audio_path)
            except Exception as cleanup_error:
                _log_debug(
                    "Erro ao remover arquivo temporário", {"error": str(cleanup_error)}
                )

    except RateLimitError as e:
        _log_debug(
            "Erro de rate limit ou quota da OpenAI",
            {
                "error_type": type(e).__name__,
                "error_message": str(e),
                "error_code": getattr(e, "code", None),
            },
        )
        error_msg = str(e)
        if "insufficient_quota" in error_msg.lower() or "quota" in error_msg.lower():
            user_message = (
                "Cota da API OpenAI esgotada ou não configurada. "
                "Verifique: 1) Se sua conta tem créditos disponíveis em https://platform.openai.com/account/billing, "
                "2) Se há um método de pagamento configurado, 3) Se a chave de API está correta."
            )
        else:
            user_message = (
                f"Limite de taxa excedido: {error_msg}. "
                "Aguarde alguns instantes e tente novamente."
            )
        return {
            "status": "quota_error",
            "message": user_message,
            "error_details": error_msg,
        }, 429
    except APIError as e:
        _log_debug(
            "Erro da API OpenAI",
            {
                "error_type": type(e).__name__,
                "error_message": str(e),
                "error_code": getattr(e, "code", None),
            },
        )
        error_code = getattr(e, "code", None)
        if error_code == "insufficient_quota":
            return {
                "status": "quota_error",
                "message": (
                    "Cota da API OpenAI esgotada. "
                    "Acesse https://platform.openai.com/account/billing para verificar seus créditos "
                    "e configurar um método de pagamento se necessário."
                ),
                "error_details": str(e),
            }, 429
        elif error_code == "invalid_api_key":
            return {
                "status": "config_error",
                "message": (
                    "Chave de API OpenAI inválida. "
                    "Verifique se a variável OPENAI_API_KEY está configurada corretamente."
                ),
                "error_details": str(e),
            }, 401
        else:
            return {
                "status": "api_error",
                "message": f"Erro na API OpenAI: {str(e)}",
                "error_details": str(e),
            }, 500
    except APIConnectionError as e:
        _log_debug(
            "Erro de conexão com API OpenAI",
            {
                "error_type": type(e).__name__,
                "error_message": str(e),
            },
        )
        return {
            "status": "connection_error",
            "message": (
                "Erro de conexão com a API OpenAI. "
                "Verifique sua conexão com a internet e tente novamente."
            ),
            "error_details": str(e),
        }, 503
    except Exception as e:
        _log_debug(
            "Erro durante análise de áudio",
            {
                "error_type": type(e).__name__,
                "error_message": str(e),
                "error_details": repr(e),
            },
        )
        return {
            "status": "processing_error",
            "message": f"Erro ao analisar áudio: {str(e)}",
        }, 500
