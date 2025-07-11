import os
import json
import logging
import tempfile
import cv2
import numpy as np
import pytesseract
import pymupdf
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from docx import Document
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

# Настройка логов
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Глобальный словарь для хранения данных пользователей (временный)
user_data = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start."""
    await update.message.reply_text(
        "Привет! Я бот для извлечения текста из изображений, PDF и XML. "
        "Отправь мне файл, и я распознаю текст!"
    )


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка изображений и PDF."""
    user_id = update.effective_user.id
    file = await update.message.effective_attachment.get_file()

    # Скачивание файла во временную папку Lambda (/tmp)
    file_path = f"/tmp/{update.message.effective_attachment.file_name}"
    await file.download_to_drive(file_path)

    # Определение типа файла
    if file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp')):
        await process_image(update, file_path, user_id)
    elif file_path.lower().endswith('.pdf'):
        await process_pdf(update, file_path, user_id)
    else:
        await update.message.reply_text("Формат не поддерживается. Отправьте изображение или PDF.")

    # Удаление временного файла
    os.remove(file_path)


async def process_image(update: Update, file_path: str, user_id: int):
    """Извлечение текста из изображения."""
    try:
        image = cv2.imread(file_path)
        if image is None:
            await update.message.reply_text("Не удалось загрузить изображение.")
            return

        # Преобразование изображения в текст
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        text = pytesseract.image_to_string(gray, lang='rus+eng')

        if text.strip():
            user_data[user_id] = {"text": text}
            await update.message.reply_text(
                f"Текст распознан:\n\n{text[:500]}...\n\n"
                "Сохранить как:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("TXT", callback_data="save_txt")],
                    [InlineKeyboardButton("PDF", callback_data="save_pdf")],
                    [InlineKeyboardButton("DOCX", callback_data="save_docx")],
                ])
            )
        else:
            await update.message.reply_text("Текст не найден.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {str(e)}")


async def process_pdf(update: Update, file_path: str, user_id: int):
    """Извлечение текста из PDF."""
    try:
        doc = pymupdf.open(file_path)
        text = ""
        for page in doc:
            text += page.get_text()

        if text.strip():
            user_data[user_id] = {"text": text}
            await update.message.reply_text(
                f"Текст из PDF:\n\n{text[:500]}...\n\n"
                "Сохранить как:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("TXT", callback_data="save_txt")],
                    [InlineKeyboardButton("PDF", callback_data="save_pdf")],
                    [InlineKeyboardButton("DOCX", callback_data="save_docx")],
                ])
            )
        else:
            await update.message.reply_text("Текст не найден.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {str(e)}")


async def save_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохранение текста в выбранный формат."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if user_id not in user_data:
        await query.message.reply_text("Данные устарели. Отправьте файл снова.")
        return

    text = user_data[user_id]["text"]
    file_type = query.data.split("_")[1]
    file_path = f"/tmp/output.{file_type}"

    try:
        if file_type == "txt":
            with open(file_path, "w") as f:
                f.write(text)
        elif file_type == "pdf":
            doc = SimpleDocTemplate(file_path, pagesize=letter)
            doc.build([Paragraph(text)])
        elif file_type == "docx":
            doc = Document()
            doc.add_paragraph(text)
            doc.save(file_path)

        await query.message.reply_document(document=open(file_path, "rb"))
        os.remove(file_path)
    except Exception as e:
        await query.message.reply_text(f"Ошибка при сохранении: {str(e)}")


async def lambda_handler(event, context):
    """Обработчик для AWS Lambda."""
    try:
        app = Application.builder().token(os.getenv("TELEGRAM_TOKEN")).build()

        # Регистрация обработчиков
        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))
        app.add_handler(CallbackQueryHandler(save_file, pattern="^save_"))

        # Обработка входящего запроса
        if "body" in event:
            update = Update.de_json(json.loads(event["body"]), app.bot)
            await app.process_update(update)

        return {"statusCode": 200}
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return {"statusCode": 500}


if __name__ == "__main__":
    # Для локального тестирования (не используется в Lambda)
    app = Application.builder().token("YOUR_TOKEN").build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))
    app.add_handler(CallbackQueryHandler(save_file, pattern="^save_"))
    app.run_polling()