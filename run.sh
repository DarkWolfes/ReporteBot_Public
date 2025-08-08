# Instala gunicorn y uvicorn
pip install gunicorn uvicorn

# Inicia la aplicación con gunicorn y uvicorn
gunicorn --bind 0.0.0.0:$PORT --worker-class uvicorn.workers.UvicornWorker main:app