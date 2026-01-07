# استفاده از پایتون نسخه سبک
FROM python:3.10-slim

# نصب پکیج‌های سیستمی لازم برای کامپایل سرور تلگرام و اجرای yt-dlp
RUN apt-get update && apt-get install -y \
    git \
    cmake \
    g++ \
    make \
    zlib1g-dev \
    libssl-dev \
    gperf \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# دانلود و کامپایل کردن سرور لوکال تلگرام (Telegram Bot API Server)
WORKDIR /tmp
RUN git clone --recursive https://github.com/tdlib/telegram-bot-api.git
WORKDIR /tmp/telegram-bot-api
RUN rm -rf build && mkdir build && cd build && \
    cmake -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX:PATH=/usr/local .. && \
    cmake --build . --target install

# آماده‌سازی پوشه کاری ربات
WORKDIR /app

# کپی کردن فایل نیازمندی‌ها و نصب آن‌ها
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# کپی کردن کل فایل‌های پروژه
COPY . .

# ساخت اسکریپت اجرایی برای ران کردن همزمان سرور تلگرام و ربات پایتون
# پورت 8081 پورت داخلی برای ارتباط ربات با سرور تلگرام است
RUN echo '#!/bin/bash\n\
telegram-bot-api --api-id=${TELEGRAM_API_ID} --api-hash=${TELEGRAM_API_HASH} --local --http-port=8081 --dir=/app/tg_data --temp-dir=/app/tg_temp & \n\
python main.py' > /app/start.sh

RUN chmod +x /app/start.sh

# دستور شروع برنامه
CMD ["/app/start.sh"]