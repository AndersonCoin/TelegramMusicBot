import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Telegram API credentials
    API_ID = 28737273
    API_HASH = "b2f71f8c2cb0c911a85dee75220bb348"
    BOT_TOKEN = "7951060445:AAGi4k4xdKEKCjxTBggAuBKiNJp_lxHfkxc"
    SESSIN_STRING = "BAG2fvkAB6xeQkFhRwOX3xu6Ol3iOaWJAkiHkAV26txYOTq-HMELAHlj4nVfhvGScyWigCxDP2Q2M_pQfLoi1lW63Tib_rGgTs1VRki9hhnPAODM5QjmL2VgDBRrdooW1Nfl73Ahz4oD5QaMRWjBFy_9RDxaZ45DQzgMrl24e7H8n2k1D9uAbsxX4nlPrQnT0n0esPiSDb9g_Rbg3akx5kYBn1wnbc2VL-Iqd7HQ3S0c_wKDaRhOSjEgdg82Zk34WbXXQOl2pb2oeDLCokepvJIVNsUpdMgGBR9_UILbfmv-NNSvQGe9xmrh1nAXNDEm6PPyO7F8OzfuLfuOKowrq3UArvCgNQAAAAHOEwb_AA"
    # Bot settings
    OWNER_ID = "178432304"
    SUPPORT_GROUP = os.getenv("SUPPORT_GROUP", "")
    
    # Music settings
    DURATION_LIMIT = int(os.getenv("DURATION_LIMIT", 300))  # 5 minutes
    QUEUE_LIMIT = int(os.getenv("QUEUE_LIMIT", 10))
    
    # Admin list
    SUDO_USERS = list(map(int, os.getenv("SUDO_USERS", "").split()))
