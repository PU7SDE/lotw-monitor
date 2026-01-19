import time
import requests
import threading
import logging
from typing import Dict, List, Set
from datetime import datetime

from .config import Config
from .storage import Storage
from .lotw_client import LoTWClient
from .tle import TLEMonitor
from .map_plot import MapGenerator
import io

logger = logging.getLogger(__name__)

class MonitorBot:
    def __init__(self):
        self.token = Config.TELEGRAM_BOT_TOKEN
        self.allowed_chat_id = str(Config.TELEGRAM_CHAT_ID)
        self.storage = Storage(Config.STATE_FILE)
        self.client = LoTWClient()
        self.tle_mon = TLEMonitor(Config.STATE_FILE.parent / "tle_cache.txt")
        self.map_gen = MapGenerator(Config.STATE_FILE.parent)
        self._lock = threading.Lock()  # Para evitar rodar sync concorrentemente

    def send_photo(self, chat_id: str, photo_bytes: bytes, caption: str = ""):
        url = f"https://api.telegram.org/bot{self.token}/sendPhoto"
        data = {"chat_id": chat_id, "caption": caption}
        files = {"photo": ("map.jpg", photo_bytes, "image/jpeg")}
        try:
            r = requests.post(url, data=data, files=files, timeout=60)
            r.raise_for_status()
        except Exception as e:
            logger.error(f"Erro ao enviar foto: {e}")

    def send_message(self, chat_id: str, text: str):
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }
        try:
            r = requests.post(url, json=payload, timeout=15)
            r.raise_for_status()
        except Exception as e:
            logger.error(f"Erro ao enviar mensagem Telegram: {e}")

    def notify_new_grids(self, new_grids: List[str], grid_info: Dict[str, Dict]):
        """Envia alerta formatado sobre novos grids."""
        if not new_grids:
            return

        total_count = len(self.storage.known_grids)
        lines = [
            "🚀 *Novo(s) grid(s) de satélite no LoTW!*",
            "",
            f"Você confirmou *{len(new_grids)}* novo(s) grid(s).",
            f"Total confirmado: *{total_count}* grids.",
            "",
            "*Detalhes:*"
        ]

        for grid in new_grids:
            info = grid_info.get(grid, {})
            call = info.get("call", "?")
            date = info.get("date", "")
            # Formata data YYYYMMDD -> DD/MM/YYYY
            if len(date) == 8:
                date = f"{date[6:8]}/{date[4:6]}/{date[0:4]}"
            
            lines.append(f"• `{grid}` com `{call}` ({date})")

        self.send_message(self.allowed_chat_id, "\n".join(lines))
        
        # Envia o mapa atualizado automaticamente
        try:
             confirmed = self.storage.get_confirmed_grids()
             # Passamos worked vazio pois removemos a visualização
             img_bytes = self.map_gen.generate(confirmed, set())
             if img_bytes:
                 self.send_photo(self.allowed_chat_id, img_bytes, "🗺️ Mapa atualizado com os novos grids!")
        except Exception as e:
            logger.error(f"Erro ao enviar mapa automático: {e}")

    def run_check_job(self, manual=False, chat_id=None):
        """
        Roda o processo de verificação (pode ser demorado).
        Deve ser rodado em thread se chamado pelo bot.
        """
        if not self._lock.acquire(blocking=False):
            if manual and chat_id:
                self.send_message(chat_id, "⚠️ Já existe uma sincronização em andamento.")
            return

        try:
            logger.info("Iniciando check job...")
            # 1. Determina data de corte (incremental)
            # Se for manual, pode querer forçar tudo, mas para eficiência vamos usar incremental seguro
            # Se precisar de FULL SYNC, o usuário pode deletar o state.json
            last_date = self.storage.last_qso_date
            
            # Se a última data for muito antiga (padrão), ele pega tudo.
            # Vamos pegar tudo se last_date for o padrão, senão pega incremental.
            qsos = self.client.get_qsos(since=last_date if last_date != "1900-01-01" else None)
            
            if not qsos:
                if manual and chat_id:
                    self.send_message(chat_id, "✅ Nenhuma nova confirmação encontrada no LoTW.")
                return

            # Atualiza data do último QSO para a próxima vez
            # Encontra a data mais recente nos QSOs baixados
            max_date = last_date
            for q in qsos:
                d = q.get("QSO_DATE", "")
                if d > max_date:
                    max_date = d
            
            # 2. Processa e salva no Storage
            # Precisamos extrair infos para o alerta ANTES de salvar (que já mescla)
            # O storage.merge_qsos retorna a lista de grids que ERAM desconhecidos
            
            # Pequeno hack: precisamos mapear grid -> call/date para o alerta
            # O Storage não guarda "quem" deu o grid novo explicitamente no return
            # Então vamos fazer um pré-processamento rápido
            
            new_grids_found = self.storage.merge_qsos(qsos)
            self.storage.last_qso_date = max_date
            self.storage.save()
            
            # Checa TLE
            if self.tle_mon.check_update():
               self.send_message(self.allowed_chat_id, "🛰️ *TLE Alert*: O arquivo de keplerianos do PU4ELT foi atualizado!")

            if new_grids_found:
                # Monta info para o alerta
                # Varre os qsos baixados para achar quem deu o grid
                grid_info = {}
                for q in qsos:
                    # check grids
                    # (Lógica simplificada do storage._extract_grids)
                    gs = self.storage._extract_grids(q)
                    for g in gs:
                        if g in new_grids_found:
                            # Pega o primeiro ou mais recente
                            grid_info[g] = {
                                "call": q.get("CALL"),
                                "date": q.get("QSO_DATE")
                            }
                
                self.notify_new_grids(new_grids_found, grid_info)
            else:
                if manual and chat_id:
                    self.send_message(chat_id, "✅ Novos QSOs baixados, mas sem grids inéditos.")

        except Exception as e:
            logger.error(f"Erro no job: {e}")
            if manual and chat_id:
                self.send_message(chat_id, f"❌ Erro na sincronização: {e}")
        finally:
            self._lock.release()

    def handle_update(self, update: Dict):
        msg = update.get("message")
        if not msg: 
            return
        
        chat_id = str(msg["chat"]["id"])
        text = msg.get("text", "").strip()
        
        if chat_id != self.allowed_chat_id:
            return

        if text == "/grids":
            stats = self.storage.get_stats()
            if not stats:
                self.send_message(chat_id, "📡 Nenhum grid registrado ainda.")
                return
            
            # Formata msg
            lines = [f"📡 *Resumo Satélite* ({len(stats)} grids)", ""]
            for g in sorted(stats.keys()):
                info = stats[g]
                count = info["count"]
                # Pega até 3 calls de exemplo
                calls = list(info["calls"])[:3] 
                calls_str = ", ".join(calls)
                lines.append(f"*{g}*: {count} QSOs ({calls_str}...)")
            
            full_msg = "\n".join(lines)
            if len(full_msg) > 4000:
                full_msg = full_msg[:3900] + "\n...(truncado)"
            
            self.send_message(chat_id, full_msg)

        elif text == "/sync":
            self.send_message(chat_id, "🔄 Iniciando sincronização em background...")
            t = threading.Thread(target=self.run_check_job, args=(True, chat_id))
            t.start()
            
        elif text == "/map":
             self.send_message(chat_id, "🗺️ Gerando mapa...")
             # Gerar em thread para nao bloquear? Map é rápido com pillow, mas download da base pode demorar na 1a vez.
             # Vamos fazer inline por simplificidade, já que download é cacheado.
             confirmed = self.storage.get_confirmed_grids()
             worked = self.storage.get_worked_grids()
             
             try:
                 img_bytes = self.map_gen.generate(confirmed, worked)
                 if img_bytes:
                     self.send_photo(chat_id, img_bytes, "Mapa de Grids (Verde=Confirmado, Vermelho=Trabalhado)")
                 else:
                     logger.error("Falha ao gerar mapa: map_gen.generate retornou vazio.")
                     self.send_message(chat_id, "❌ Erro ao gerar o mapa: retorno vazio.")
             except Exception as e:
                 logger.exception("Exceção ao gerar mapa")
                 self.send_message(chat_id, f"❌ Erro ao gerar o mapa: {e}")

        elif text == "/tle":
            changed = self.tle_mon.check_update()
            if changed:
                self.send_message(chat_id, "✅ TLEs estavam desatualizados e foram renovados agora.")
            else:
                self.send_message(chat_id, "ℹ️ TLEs já estão na última versão.")

        elif text.startswith("/check "):
            call_to_check = text[7:].strip().upper()
            if not call_to_check:
                self.send_message(chat_id, "Uso: `/check <INDICATIVO>`")
                return
            
            # Pesquisa no cache
            # Precisamos iterar o qso_cache do storage
            found = False
            for qso in self.storage.data.get("qso_cache", {}).values():
                if qso.get("CALL") == call_to_check:
                    grid = qso.get("GRIDSQUARE") or qso.get("VUCC_GRIDS") or "?"
                    date = qso.get("QSO_DATE")
                    status = "Confirmado" if (qso.get("QSL_RCVD") == "Y") else "Trabalhado"
                    
                    self.send_message(chat_id, f"✅ ENCONTRADO:\nCall: {call_to_check}\nGrid: {grid}\nData: {date}\nStatus: {status}")
                    found = True
                    break # para no primeiro? ou lista todos? Vamos parar no primeiro por enqto.
            
            if not found:
                self.send_message(chat_id, f"❌ Nenhum registro encontrado para `{call_to_check}`.")

    def start_polling(self):
        logger.info("Bot iniciado...")
        offset = None
        url = f"https://api.telegram.org/bot{self.token}/getUpdates"
        
        while True:
            try:
                params = {"timeout": 30}
                if offset:
                    params["offset"] = offset
                
                r = requests.get(url, params=params, timeout=60)
                r.raise_for_status()
                data = r.json()
                
                for item in data.get("result", []):
                    offset = item["update_id"] + 1
                    self.handle_update(item)
                    
            except Exception as e:
                logger.error(f"Erro polling: {e}")
                time.sleep(5)

