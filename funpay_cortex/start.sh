#!/bin/bash

echo "📦 Устанавливаю зависимости..."
pip install --upgrade pip
pip install -r requirements.txt

echo "🚀 Запускаю бота..."
python main.py
