#!/bin/bash
PROJECT_DIR="/home/jalivur/Documents/proyectopantallas"
APP_NAME="fase1.py"

echo "--- LANZADOR INDEPENDIENTE ---"

# 1. Comprobar si ya existe
if pgrep -f "$APP_NAME" > /dev/null; then
    echo "La aplicacion ya esta corriendo."
else
    echo "Iniciando $APP_NAME..."
    cd "$PROJECT_DIR" || exit 1
    
    # Usamos nohup que es mas compatible que el disown entre parentesis
    # El '&' al final lo manda al fondo
    nohup /usr/bin/python3 "$APP_NAME" > /dev/null 2>&1 &
    
    sleep 1
    echo "Comando enviado con exito."
fi

exit 0
