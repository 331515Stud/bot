FROM python:3.9-slim
RUN apt-get update && apt-get install -y tesseract-ocr-rus
COPY . /app
WORKDIR /app
RUN pip install -r requirements.txt
CMD ["functions-framework", "--target=telegram_webhook"]
