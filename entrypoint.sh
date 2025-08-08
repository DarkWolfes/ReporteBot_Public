#!/bin/bash
#
# Este script de entrada asegura que la variable de entorno PORT se
# use correctamente y luego inicia la aplicación con Gunicorn.

# Establece el puerto de forma explícita para el comando Gunicorn
# Esto resuelve el error "port not valid"
export PORT=${PORT:-5000}

# Inicia la aplicación con Gunicorn
exec gunicorn --bind 0.0.0.0:$PORT --worker-class uvicorn.workers.UvicornWorker main:app
