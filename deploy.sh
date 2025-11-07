#!/bin/bash

# تحديث النظام
sudo apt update && sudo apt upgrade -y

# تثبيت المتطلبات الأساسية
sudo apt install -y git python3 python3-pip ffmpeg

# متغيرات المشروع
GITHUB_REPO="https://github.com/USERNAME/REPO.git"
PROJECT_DIR="/home/$USER/mybot"

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

# تشغيل البوت باستخدام screen
echo "🚀 تشغيل البوت داخل جلسة screen..."
screen -dmS mybot python3 bot.py

echo "✅ تم رفع وتشغيل البوت بنجاح!"
echo "للدخول إلى الجلسة: screen -r mybot"
