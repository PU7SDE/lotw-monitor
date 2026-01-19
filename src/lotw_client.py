import requests
import re
import logging
from typing import List, Dict, Optional
from .config import Config

logger = logging.getLogger(__name__)

class LoTWClient:
    LOTW_URL = "https://lotw.arrl.org/lotwuser/lotwreport.adi"

    def __init__(self):
        self.username = Config.LOTW_USERNAME
        self.password = Config.LOTW_PASSWORD

    def fetch_adif(self, since: Optional[str] = None) -> str:
        """
        Baixa ADIF de confirmações (QSLs).
        :param since: Data YYYY-MM-DD para trazer apenas novos.
        """
        params = {
            "login": self.username,
            "password": self.password,
            "qso_query": "1",
            "qso_qsl": "no", # Traga todos (yes traria só confirmados)
            "qso_qsldetail": "yes",
        }
        
        # Se 'since' for None, traz tudo.
        # Se for incremental, LoTW filtra pela data de upload/QSL.

        
        if since:
            params["qso_qslsince"] = since
        else:
            params["qso_qslsince"] = "1900-01-01"

        # IMPORTANTE: Para pegar "trabalhados" (worked), qso_qsl precisa ser "no"
        # (significa "ignore QSL status", ou seja, traga todos). 
        # Mas queremos QSL details se houver.
        
        # O LoTWReport é meio chato. Se qso_qsl='no', ele lista tudo.
        # A gente filtra no client o que é confirmed.
        
        logger.info(f"Baixando ADIF do LoTW (since={params['qso_qslsince']})...")
        try:
            resp = requests.get(self.LOTW_URL, params=params, timeout=120)  # timeout maior pois pode ser grande
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Erro na requisição ao LoTW: {e}")
            raise

        text = resp.text
        if "<eoh>" not in text.lower():
            # Erro de autenticação ou serviço fora do ar muitas vezes retorna HTML
            raise RuntimeError("Resposta do LoTW inválida (não parece ser ADIF). Verifique login/senha.")
            
        return text

    def parse_adif(self, adif_text: str) -> List[Dict[str, str]]:
        """
        Parser de ADIF simples e eficiente.
        """
        lower = adif_text.lower()
        eoh_idx = lower.find("<eoh>")
        if eoh_idx == -1:
            raise RuntimeError("Fim do cabeçalho <EOH> não encontrado no ADIF.")

        records_text = adif_text[eoh_idx + 5:]
        # Remove espaços extras e quebras
        records_text = records_text.strip()
        
        # Regex para capturar campos: <TAG:LEN>VALUE
        # Adicionei suporte a tipo opcional <TAG:LEN:TYPE>
        field_pattern = re.compile(r"<([^:>]+):(\d+)(?::[^>]*)?>")
        
        records = []
        
        # Split por <eor> (case insensitive)
        chunks = re.split(r"<eor>", records_text, flags=re.IGNORECASE)
        
        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk:
                continue
                
            fields = {}
            pos = 0
            while True:
                match = field_pattern.search(chunk, pos)
                if not match:
                    break
                    
                tag_name = match.group(1).upper()
                length = int(match.group(2))
                
                # O valor começa logo após o fechamento da tag >
                start_val = match.end()
                value = chunk[start_val : start_val + length]
                
                fields[tag_name] = value.strip()
                
                # Avança a busca
                pos = start_val + length
            
            if fields:
                records.append(fields)
                
        logger.info(f"Registros parseados: {len(records)}")
        return records

    def get_qsos(self, since: Optional[str] = None) -> List[Dict[str, str]]:
        """
        Retorna todos os QSOs (Trabalhados e Confirmados)
        """
        try:
            raw_adif = self.fetch_adif(since)
            return self.parse_adif(raw_adif)
        except Exception as e:
            logger.error(f"Falha ao obter dados: {e}")
            return []

