import os
from dotenv import load_dotenv

load_dotenv()

PORTAL_ACCOUNT = os.getenv("PORTAL_ACCOUNT")
PORTAL_PASSWORD = os.getenv("PORTAL_PASSWORD")
VDI_ACCOUNT = os.getenv("VDI_ACCOUNT")
VDI_PASSWORD = os.getenv("VDI_PASSWORD")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CAMPUS = os.getenv("CAMPUS", "總院區")

VDI_URL = "https://vdi.ntuh.gov.tw/logon/LogonPoint/index.html"
