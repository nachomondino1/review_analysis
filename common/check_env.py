from dotenv import load_dotenv
import os

load_dotenv()
assert os.getenv("HF_TOKEN"), "HF_TOKEN no cargado: revisá ruta del .env"
print("OK", os.getenv("HF_TOKEN")[:6] + "...")