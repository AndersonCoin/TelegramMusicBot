#!/bin/bash

# تحديث النظام
sudo apt update && sudo apt upgrade -y

# تثبيت المتطلبات الأساسية
sudo apt install -y git python3 python3-pip ffmpeg

# متغيرات المشروع
GITHUB_REPO="https://github.com/USERNAME/REPO.git"
PROJECT_DIR="/home/$USER/mybot"
SERVICE_NAME="mybot"

# استنساخ المشروع من GitHub
if [ -d "$PROJECT_DIR" ]; then
    echo "📂 المجلد موجود مسبقًا، سيتم تحديثه..."
    cd $PROJECT_DIR
    git pull
else
    echo "⬇️ جاري استنساخ المشروع..."
    git clone $GITHUB_REPO $PROJECT_DIR
    cd $PROJECT_DIR
fi

# تثبيت المكتبات من requirements.txt
if [ -f "requirements.txt" ]; then
    echo "📦 تثبيت المكتبات..."
    pip3 install -r requirements.txt
else
    echo "⚠️ لا يوجد ملف requirements.txt"
fi

# إنشاء ملف خدمة systemd
SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME.service"

sudo bash -c "cat > $SERVICE_FILE" <<EOL
[Unit]
Description=Telegram Bot Service
After=network.target

[Service]
ExecStart=/usr/bin/python3 $PROJECT_DIR/bot.py
WorkingDirectory=$PROJECT_DIR
Restart=always
User=$USER
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOL

# إعادة تحميل systemd وتفعيل الخدمة
sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME
sudo systemctl restart $SERVICE_NAME

echo "✅ تم تثبيت الخدمة وتشغيل البوت بنجاح!"
echo "🔍 لمتابعة اللوجات: sudo journalctl -u $SERVICE_NAME -f"
