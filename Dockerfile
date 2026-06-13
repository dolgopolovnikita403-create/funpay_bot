FROM python:3.11-slim

WORKDIR /app

# Копируем всё из папки funpay_cortex в /app
COPY funpay_cortex/ .

# Копируем requirements.txt (если он в корне репозитория, не в папке)
COPY funpay_cortex/requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Проверяем, что файлы скопировались
RUN ls -la /app/

# Запускаем бота
CMD ["python", "main.py"]
