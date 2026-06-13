FROM python:3.11-slim

WORKDIR /app

# Копируем ВСЁ из папки funpay_cortex в /app
COPY funpay_cortex/ /app/

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Проверяем, что файлы скопировались (для отладки)
RUN ls -la /app/

# Запускаем бота
CMD ["python", "main.py"]
