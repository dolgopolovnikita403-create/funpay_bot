FROM python:3.11-slim

WORKDIR /app

# Копируем всё содержимое папки funpay_cortex в /app
COPY funpay_cortex/ .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Запускаем бота
CMD ["python", "main.py"]
