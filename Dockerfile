FROM python:3.11-slim

WORKDIR /app2

COPY funpay_cortex/ /app2/

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "main.py"]
