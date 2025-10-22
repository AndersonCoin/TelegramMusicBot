#!/usr/bin/env python3
"""Runner script to fix issues before starting the bot."""

import os
import sys
import shutil

# إصلاح الملفات أولاً
print("🔧 Fixing files...")

# حذف __pycache__
for root, dirs, files in os.walk("."):
    if "__pycache__" in dirs:
        shutil.rmtree(os.path.join(root, "__pycache__"))
        print(f"Deleted {root}/__pycache__")

# إصلاح ملفات __init__.py
fixes = {
    "bot/__init__.py": '"""Bot package."""\n\n__version__ = "2.1.0"',
    "bot/core/__init__.py": '"""Core package."""\n\nplayer = None',
    "bot/helpers/__init__.py": '"""Helpers package."""',
    "bot/plugins/__init__.py": '"""Plugins package."""',
    "bot/persistence/__init__.py": '"""Persistence package."""',
}

for filepath, content in fixes.items():
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w') as f:
        f.write(content)
    print(f"✅ Fixed {filepath}")

print("\n🚀 Starting bot...")

# تشغيل البوت
os.system("python app.py")
