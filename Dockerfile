FROM python:3.11-slim

WORKDIR /app

# Метка для принудительной пересборки
LABEL version="2.0"

COPY funpay_cortex/ /app/

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "main.py"]
