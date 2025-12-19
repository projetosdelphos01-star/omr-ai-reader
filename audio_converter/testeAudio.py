"""
Exemplo de teste para análise de áudio usando OpenAI (Whisper + GPT-4o).

Uso:
    python testeAudio.py

Certifique-se de configurar a variável OPENAI_API_KEY antes de executar.
"""
from openai import OpenAI
import os

# Configure sua chave de API via variável de ambiente
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("Erro: OPENAI_API_KEY não configurada")
    print("Execute: export OPENAI_API_KEY='sua-chave-aqui'")
    exit(1)

client = OpenAI(api_key=api_key)

# Caminho para o arquivo de áudio de teste
audio_file_path = "Gravando.m4a"

if not os.path.exists(audio_file_path):
    print(f"Erro: Arquivo de áudio não encontrado: {audio_file_path}")
    exit(1)

print(f"Processando áudio: {audio_file_path}")

# Passo 1: Transcrição com Whisper
print("\n1. Transcrevendo áudio com Whisper...")
with open(audio_file_path, "rb") as audio_file:
    transcription = client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file,
        language="pt",
        response_format="verbose_json"
    )

print(f"   Texto: {transcription.text}")
print(f"   Duração: {getattr(transcription, 'duration', 'N/A')} segundos")

# Passo 2: Análise com GPT-4o
print("\n2. Analisando transcrição com GPT-4o...")
response = client.chat.completions.create(
    model="gpt-4o-mini",
    response_format={"type": "json_object"},
    messages=[
        {
            "role": "system",
            "content": "Você é um avaliador de leitura. Analise a transcrição e retorne um JSON com overall_score (0-10) e feedback."
        },
        {
            "role": "user",
            "content": f"Transcrição: {transcription.text}\n\nRetorne JSON com: overall_score, fluency, pronunciation, clarity, suggestions"
        }
    ]
)

print(f"\n3. Resultado da análise:")
print(response.choices[0].message.content)
