# مرحله 1: استفاده از ایمیج آماده سرور تلگرام (بدون نیاز به کامپایل)
FROM aiogram/telegram-bot-api:latest as api-server

# مرحله 2: ساخت محیط پایتون
FROM python:3.10-slim

# نصب ffmpeg (برای yt-dlp ضروری است) و ابزارهای پایه
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# کپی کردن فایل باینری سرور تلگرام از مرحله 1 به محیط فعلی
COPY --from=api-server /usr/bin/telegram-bot-api /usr/bin/telegram-bot-api

WORKDIR /app

# نصب پکیج‌های پایتون
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# کپی کدها
COPY . .

# اسکریپت شروع (همان منطق قبلی)
# ما یک اسکریپت می‌سازیم که سرور تلگرام و ربات را با هم اجرا کند
RUN echo '#!/bin/bash\n\
# اجرای سرور تلگرام در پس‌زمینه
telegram-bot-api --api-id=${TELEGRAM_API_ID} --api-hash=${TELEGRAM_API_HASH} --local --http-port=8081 --dir=/tmp/tg_data --temp-dir=/tmp/tg_temp & \n\
# کمی صبر برای بالا آمدن سرور
sleep 5 \n\
# اجرای ربات پایتون
python main.py' > /app/start.sh

RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]
