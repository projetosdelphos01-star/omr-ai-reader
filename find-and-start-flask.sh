#!/bin/bash

# Script para iniciar o Flask OMR usando uv
# Projeto em: /var/www/html/florescer-ia

FLASK_DIR="/var/www/html/florescer-ia"

if [ ! -d "$FLASK_DIR" ]; then
    echo "❌ Diretório não encontrado: $FLASK_DIR"
    exit 1
fi

echo "✅ Diretório: $FLASK_DIR"
cd "$FLASK_DIR"

echo ""
echo "=== Verificando uv ==="

if ! command -v uv &> /dev/null; then
    echo "❌ uv não encontrado. Instalando..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
fi

echo "✅ uv encontrado"

echo ""
echo "=== Verificando dependências ==="

# Verificar se requirements.txt existe
if [ -f "requirements.txt" ]; then
    echo "✅ requirements.txt encontrado"
    echo "Instalando/atualizando dependências com uv..."
    uv pip install -r requirements.txt
else
    echo "⚠️  requirements.txt não encontrado"
fi

# Verificar flask-cors
if uv run python -c "import flask_cors" 2>/dev/null; then
    echo "✅ flask-cors instalado"
else
    echo "❌ flask-cors não encontrado. Instalando..."
    uv pip install flask-cors
fi

# Verificar gunicorn
if uv run python -c "import gunicorn" 2>/dev/null || uv run gunicorn --version &>/dev/null; then
    echo "✅ gunicorn instalado"
else
    echo "❌ gunicorn não encontrado. Instalando..."
    uv pip install gunicorn
fi

echo ""
echo "=== Verificando se já está rodando ==="

if netstat -tulpn 2>/dev/null | grep -q ":5000" || ss -tulpn 2>/dev/null | grep -q ":5000"; then
    echo "⚠️  Porta 5000 já está em uso!"
    echo "Processo:"
    netstat -tulpn 2>/dev/null | grep ":5000" || ss -tulpn 2>/dev/null | grep ":5000"
    read -p "Deseja parar e reiniciar? (s/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Ss]$ ]]; then
        pkill -f "gunicorn.*app:app" || pkill -f "python.*app.py"
        sleep 2
    else
        exit 0
    fi
fi

echo ""
echo "=== Iniciando Flask com Gunicorn (usando uv) ==="
echo "Diretório: $FLASK_DIR"
echo "Comando: uv run gunicorn -w 4 -b 127.0.0.1:5000 --timeout 300 app:app"
echo ""
echo "Pressione Ctrl+C para parar"
echo ""

# Iniciar gunicorn usando uv
uv run gunicorn -w 4 -b 127.0.0.1:5000 --timeout 300 app:app

