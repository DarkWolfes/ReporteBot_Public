# Usa una imagen base de Python oficial
FROM python:3.11-slim

# Establece el directorio de trabajo en /app
WORKDIR /app

# Copia los archivos de requerimientos e instala las dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia el resto de los archivos de tu proyecto al contenedor
COPY . .

# Define el comando para ejecutar tu aplicación con Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
