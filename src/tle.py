import requests
import hashlib
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

class TLEMonitor:
    TLE_URL = "https://www.qsl.net/pu4elt/TLE/PU4ELT_tle.txt"
    
    def __init__(self, cache_file: Path):
        self.cache_file = cache_file

    def _get_local_hash(self) -> str:
        if not self.cache_file.exists():
            return ""
        try:
            with open(self.cache_file, "r") as f:
                return f.read().strip()
        except Exception:
            return ""

    def _save_local_hash(self, hash_val: str):
        try:
            with open(self.cache_file, "w") as f:
                f.write(hash_val)
        except Exception as e:
            logger.error(f"Erro ao salvar hash TLE: {e}")

    def check_update(self) -> bool:
        """
        Verifica se o TLE mudou comparando o ETag ou MD5 do conteúdo.
        Retorna True se houve atualização.
        """
        logger.info("Checando atualizações de TLE...")
        try:
            # Primeiro tenta HEAD para ver se mudou (usando headers)
            # Mas sites estáticos simples as vezes não confiáveis.
            # Vamos baixar e calcular hash, arquivo é pequeno (<100KB).
            r = requests.get(self.TLE_URL, timeout=30)
            r.raise_for_status()
            
            content = r.content
            current_hash = hashlib.md5(content).hexdigest()
            old_hash = self._get_local_hash()
            
            if current_hash != old_hash:
                logger.info(f"TLE atualizado! Hash antigo: {old_hash}, Novo: {current_hash}")
                self._save_local_hash(current_hash)
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Erro ao checar TLE: {e}")
            return False
