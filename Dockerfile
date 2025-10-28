# الصورة الأساسية (يفضل استخدام النسخة التي تناسب ملف runtime.txt)
FROM python:3.11-slim 

# تثبيت FFmpeg (وهو ما سيحل مشكلة ffprobe)
RUN apt-get update && apt-get install -y ffmpeg 

# تثبيت متطلبات بايثون
COPY requirements.txt /app/
WORKDIR /app
RUN pip install --no-cache-dir -r requirements.txt

# نسخ باقي ملفات المشروع
COPY . /app

# أمر التشغيل الذي يجب أن يشغل ملف main.py
CMD ["python", "main.py"]
