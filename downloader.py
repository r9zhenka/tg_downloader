import os
import sys
import asyncio
import argparse
from datetime import datetime

from telethon import TelegramClient
from telethon.tl.types import InputMessagesFilterVideo, DocumentAttributeFilename

from config import API_ID, API_HASH, CHAT_ID, DOWNLOAD_DIR

SESSION_NAME = "tg_session"


def format_size(size_bytes):
    """Format bytes into human-readable string."""
    if size_bytes is None:
        return "unknown size"
    for unit in ("B", "KB", "MB", "GB"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def progress_callback(current, total):
    """Display download progress."""
    percent = current / total * 100
    bar_length = 30
    filled = int(bar_length * current // total)
    bar = "=" * filled + "-" * (bar_length - filled)
    print(f"\r  [{bar}] {percent:.1f}% ({format_size(current)}/{format_size(total)})", end="", flush=True)


def get_video_filename(message, index):
    """Build a filename for the video: date_index_originalname.ext"""
    date_str = message.date.strftime("%Y-%m-%d")

    original_name = None
    if message.document:
        for attr in message.document.attributes:
            if isinstance(attr, DocumentAttributeFilename):
                original_name = attr.file_name
                break

    if original_name:
        name, ext = os.path.splitext(original_name)
        # Sanitize the name
        name = "".join(c if c.isalnum() or c in (" ", "-", "_") else "_" for c in name).strip()
        return f"{date_str}_{index:04d}_{name}{ext}"
    else:
        ext = ".mp4"
        if message.document and message.document.mime_type:
            mime_to_ext = {
                "video/mp4": ".mp4",
                "video/quicktime": ".mov",
                "video/x-matroska": ".mkv",
                "video/webm": ".webm",
                "video/x-msvideo": ".avi",
            }
            ext = mime_to_ext.get(message.document.mime_type, ".mp4")
        return f"{date_str}_{index:04d}_video{ext}"


async def list_chats(client):
    """Print all available chats with their IDs."""
    print("\nВаши чаты и каналы:\n")
    print(f"{'ID':<25} {'Тип':<12} {'Название'}")
    print("-" * 70)

    async for dialog in client.iter_dialogs():
        chat_type = "Канал" if dialog.is_channel else "Группа" if dialog.is_group else "Личный"
        print(f"{dialog.id:<25} {chat_type:<12} {dialog.name}")

    print(f"\nСкопируйте нужный ID в config.py -> CHAT_ID")


async def download_videos(client):
    """Download all videos from the specified chat."""
    # Validate config
    if API_ID == 0 or not API_HASH or CHAT_ID == 0:
        print("Ошибка: заполните API_ID, API_HASH и CHAT_ID в config.py")
        print("Инструкция находится в комментариях файла config.py")
        return

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    try:
        chat = await client.get_entity(CHAT_ID)
    except Exception as e:
        print(f"Ошибка: не удалось найти чат с ID {CHAT_ID}: {e}")
        print("Проверьте CHAT_ID в config.py. Используйте --list-chats чтобы увидеть доступные чаты.")
        return

    chat_title = getattr(chat, "title", str(CHAT_ID))
    print(f"\nЧат: {chat_title}")
    print("Получаю список видео...\n")

    # Collect all video messages first to know the total count
    video_messages = []
    async for message in client.iter_messages(chat, filter=InputMessagesFilterVideo):
        video_messages.append(message)

    # Reverse to process oldest first
    video_messages.reverse()

    total = len(video_messages)
    if total == 0:
        print("В этом чате нет видео.")
        return

    print(f"Найдено видео: {total}\n")

    downloaded = 0
    skipped = 0
    errors = 0

    for i, message in enumerate(video_messages, 1):
        filename = get_video_filename(message, i)
        filepath = os.path.join(DOWNLOAD_DIR, filename)

        size_str = ""
        if message.document and message.document.size:
            size_str = f" ({format_size(message.document.size)})"

        caption = ""
        if message.message:
            # Show first 50 chars of caption
            caption = f' -- "{message.message[:50]}{"..." if len(message.message) > 50 else ""}"'

        # Skip if already downloaded
        if os.path.exists(filepath):
            print(f"[{i}/{total}] Пропуск (уже скачано): {filename}")
            skipped += 1
            continue

        print(f"[{i}/{total}] Скачиваю: {filename}{size_str}{caption}")

        try:
            await client.download_media(message, file=filepath, progress_callback=progress_callback)
            print()  # newline after progress bar
            downloaded += 1
        except Exception as e:
            print(f"\n  Ошибка при скачивании: {e}")
            errors += 1
            # Remove partial file if exists
            if os.path.exists(filepath):
                os.remove(filepath)

    # Summary
    print(f"\n{'=' * 40}")
    print(f"Готово!")
    print(f"  Скачано:   {downloaded}")
    print(f"  Пропущено: {skipped}")
    if errors:
        print(f"  Ошибок:    {errors}")
    print(f"  Папка:     {os.path.abspath(DOWNLOAD_DIR)}")


async def main():
    parser = argparse.ArgumentParser(description="Скачивание видео из Telegram чата")
    parser.add_argument("--list-chats", action="store_true", help="Показать список всех чатов и их ID")
    args = parser.parse_args()

    if API_ID == 0 or not API_HASH:
        print("Ошибка: заполните API_ID и API_HASH в config.py")
        print("Инструкция находится в комментариях файла config.py")
        return

    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()
    print("Авторизация успешна.")

    if args.list_chats:
        await list_chats(client)
    else:
        await download_videos(client)

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
