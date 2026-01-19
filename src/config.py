import os
from pathlib import Path
from dotenv import load_dotenv

# Carrega variáveis do arquivo .env se existir
load_dotenv()

def _get_required_env(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise ValueError(f"A variável de ambiente obrigatória '{key}' não está definida.")
    return val

class Config:
    TELEGRAM_BOT_TOKEN = _get_required_env("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = _get_required_env("TELEGRAM_CHAT_ID")
    
    LOTW_USERNAME = _get_required_env("LOTW_USERNAME")
    LOTW_PASSWORD = _get_required_env("LOTW_PASSWORD")
    
    # Caminho base: Diretório atual de execução (CWD)
    # Isso permite rodar múltiplas instâncias em pastas diferentes usando o mesmo código.
    BASE_DIR = Path.cwd()
    
    # Arquivo de estado padrão: <cwd>/data/state.json
    STATE_FILE = Path(os.getenv("STATE_FILE", BASE_DIR / "data" / "state.json"))

    # Garante que o diretório de dados exista
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
