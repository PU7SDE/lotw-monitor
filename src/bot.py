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
import json

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

    # Teclado Principal Persistente
    MAIN_KEYBOARD = {
        "keyboard": [
            [{"text": "📊 Dashboard"}, {"text": "🗺️ Mapa"}],
            [{"text": "🔄 Sync"}, {"text": "📥 Sync Full"}],
            [{"text": "📋 Grids"}, {"text": "🛰️ TLEs"}]
        ],
        "resize_keyboard": True,
        "persistent": True
    }

    def send_photo(self, chat_id: str, photo_bytes: bytes, caption: str = ""):
        url = f"https://api.telegram.org/bot{self.token}/sendPhoto"
        data = {"chat_id": chat_id, "caption": caption, "reply_markup": json.dumps(self.MAIN_KEYBOARD)}
        # O gerador retorna PNG. É importante o nome/mime baterem.
        files = {"photo": ("map.png", photo_bytes, "image/png")}
        try:
            r = requests.post(url, data=data, files=files, timeout=60)
            r.raise_for_status()
        except Exception as e:
            logger.error(f"Erro ao enviar foto: {e}")

    def send_message(self, chat_id: str, text: str, reply_markup=None):
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        
        # Use default keyboard if not provided
        if reply_markup is None:
            reply_markup = self.MAIN_KEYBOARD
            
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
            "reply_markup": reply_markup
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
             grid_labels = self.storage.get_grid_labels()
             img_bytes = self.map_gen.generate(confirmed, set(), grid_labels)
             if img_bytes:
                 self.send_photo(self.allowed_chat_id, img_bytes, "🗺️ Mapa atualizado com os novos grids!")
        except Exception as e:
            logger.error(f"Erro ao enviar mapa automático: {e}")

    def run_check_job(self, manual=False, chat_id=None, force_full=False):
        """
        Roda o processo de verificação (pode ser demorado).
        Deve ser rodado em thread se chamado pelo bot.
        """
        if not self._lock.acquire(blocking=False):
            if manual and chat_id:
                self.send_message(chat_id, "⚠️ Já existe uma sincronização em andamento.")
            return

        try:
            logger.info(f"Iniciando check job (manual={manual}, force_full={force_full})...")
            
            # --- Lógica Smart Sync ---
            # 1. Determina data de corte.
            # Se force_full = True, usa 1900-01-01.
            # Se force_full = False, usa last_sync_date com margem de segurança (1 dia).
            
            import datetime as dt_module
            from datetime import timedelta
            
            if force_full:
                since_date = "1900-01-01"
                logger.info("Modo FORCE FULL ativado.")
            else:
                last_sync = self.storage.last_sync_date
                if last_sync == "1900-01-01":
                    since_date = "1900-01-01" # Nunca rodou, então FULL
                    logger.info("Primeira execução detectada: Modo FULL.")
                else:
                    # Margem de segurança: volta 1 dia para garantir (overlap)
                    # last_sync é YYYY-MM-DD
                    try:
                        ls_dt = datetime.strptime(last_sync, "%Y-%m-%d")
                        safe_dt = ls_dt - timedelta(days=1)
                        since_date = safe_dt.strftime("%Y-%m-%d")
                        logger.info(f"Modo INCREMENTAL. Since: {since_date} (Last success: {last_sync})")
                    except:
                        since_date = "1900-01-01" # Fallback se parse falhar
            
            qsos = self.client.get_qsos(since=since_date)
            
            if not qsos:
                if manual and chat_id:
                    self.send_message(chat_id, f"✅ Sincronização concluída. 0 novos registros desde {since_date}.")
                
                # Mesmo sem novos QSOs, atualizamos o last_sync_date para hoje,
                # para que amanhã a busca seja rápida.
                self.storage.last_sync_date = datetime.now().strftime("%Y-%m-%d")
                self.storage.save()
                return

            if manual and chat_id:
                 self.send_message(chat_id, f"📥 Analisando {len(qsos)} registros do LoTW...")

            # 2. Processa e salva no Storage
            new_grids_found = self.storage.merge_qsos(qsos)
            
            # Atualiza last_sync_date para HOJE (sucesso)
            # Não usamos max_date do QSO, pois queremos saber quando RODAMOS o check.
            self.storage.last_sync_date = datetime.now().strftime("%Y-%m-%d")
            
            # (Opcional) Mantemos last_qso_date para estatísticas, mas não para controle de sync
            max_qso_date = "1900-01-01"
            for q in qsos:
                d = q.get("QSO_DATE", "")
                if d > max_qso_date: max_qso_date = d
            self.storage.last_qso_date = max_qso_date
            
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

        if text == "/help" or text == "/start" or text == "❓ Ajuda":
            self.send_help(chat_id)
            return

        elif text == "/grids" or text == "📋 Grids":
            # Vamos manter o /grids como resumo simples ou redirecionar?
            # O user pediu "/stats" baseado no HTML.
            stats = self.storage.get_stats()
            if not stats:
                 self.send_message(chat_id, "📡 Nenhum grid registrado ainda.")
                 return
            lines = [f"📡 *Resumo Grids* ({len(stats)})", ""]
            lines.append("Use `/stats` para ver o dashboard completo.")
            self.send_message(chat_id, "\n".join(lines))

        elif text == "/stats" or text == "📊 Dashboard":
            d = self.storage.get_dashboard_stats()
            
            # Formata mensagem estilo Dashboard
            msg = [
                "📊 *Satellite Grid Dashboard* 🛰️",
                "",
                f"✅ *Confirmados:* `{d['total_confirmed']}` QSOs",
                f"🗺️ *Grids:* `{d['total_grids']}` (VUCC: {d['total_grids']}/100)",
                f"🛰️ *Satélites:* `{d['total_sats']}`",
                f"📏 *Max DX:* `{d['max_distance']} km`",
                f"🇧🇷 *WAB:* `{d['wab_count']}/27` UFs",
                "",
                f"🌍 *DXCC:* `{d['dxcc_count']}`  •  *CQ:* `{d['cq_count']}`  •  *ITU:* `{d['itu_count']}`",
            ]
            
            if d.get('top_hunters'):
                msg.append("")
                msg.append("🏆 *Top Grid Activators:*")
                for idx, h in enumerate(d['top_hunters'], 1):
                    msg.append(f"{idx}. *{h['call']}* - {h['count']} grids")
            
            # Breakdowns simplificados (Top 3 Sats)
            msg.append("")
            msg.append("📡 *Top Satélites:*")
            sorted_sats = sorted(d['sats_breakdown'].items(), key=lambda x: x[1], reverse=True)[:3]
            if sorted_sats:
                for s, c in sorted_sats:
                    msg.append(f"- {s}: {c}")

            # WAB List (Brazil States)
            msg.append("")
            msg.append("🇧🇷 *Estados Confirmados (WAB):*")
            if sorted_wab:
                # Format: SP (12), RJ (5), ...
                # Compact format
                wab_str = ", ".join([f"{s} ({c})" for s, c in sorted_wab])
                msg.append(wab_str)
            else:
                msg.append("(Nenhum)")

            # WAB Missing
            missing = d.get('wab_missing', [])
            if missing:
                msg.append("")
                msg.append(f"⏳ *Faltam ({len(missing)}):*")
                msg.append(", ".join(sorted(missing)))

            # DXCC List
            msg.append("")
            msg.append("🌍 *DXCC Confirmados:*")
            # Sort by count desc
            sorted_dxcc = sorted(d['dxcc_breakdown'].items(), key=lambda x: x[1], reverse=True)
            if sorted_dxcc:
                # Format: "BRAZIL (10), ARGENTINA (5)" to save vertical space? 
                # Or list? List is clearer.
                for country, count in sorted_dxcc:
                     msg.append(f"- {country}: {count}")
            else:
                msg.append("(Nenhum)")
            
            self.send_message(chat_id, "\n".join(msg))

        elif text.startswith("/debug_state"):
            # Usage: /debug_state MS
            try:
                uf_target = text.split()[1].upper()
                from .wab_data import get_state_from_grid, get_state_from_call
                
                found_msgs = []
                count = 0
                
                for qso in self.storage.data.get("qso_cache", {}).values():
                    if qso.get("QSL_RCVD", "").upper() != "Y": continue
                    if qso.get("COUNTRY", "").upper() != "BRAZIL": continue
                    
                    # Filter SAT only
                    prop = qso.get("PROP_MODE", "").upper()
                    sat_name = qso.get("SAT_NAME", "")
                    if prop != "SAT" and not sat_name:
                        continue
                    
                    # Logic match
                    grids_list = list(self.storage._extract_grids(qso))
                    best_grid = grids_list[0] if grids_list else ""
                    
                    state = get_state_from_grid(best_grid)
                    source = f"Grid {best_grid}"
                    
                    if not state:
                        call = qso.get("CALL", "")
                        state = get_state_from_call(call)
                        source = f"Call {call}"
                        
                    if not state:
                         st = qso.get("STATE", "").upper().strip()
                         if len(st)==2: 
                             state = st
                             source = "ADIF State"

                    if state == uf_target:
                        count += 1
                        if count <= 10:
                            found_msgs.append(f"• {qso.get('CALL')} ({qso.get('QSO_DATE')}) -> Via {source}")
                            
                if found_msgs:
                    self.send_message(chat_id, f"🔍 Resultados para {uf_target} (Total: {count}):\n" + "\n".join(found_msgs))
                else:
                    self.send_message(chat_id, f"Nenhum QSO encontrado para o estado {uf_target}.")
                    
            except IndexError:
                self.send_message(chat_id, "Use: /debug_state <UF> (Ex: /debug_state MS)")
            except Exception as e:
                logger.error(f"Erro debug_state: {e}")
                self.send_message(chat_id, "Erro ao buscar.")

        elif text == "/sync" or text.startswith("/sync ") or text == "/sync_full" or text == "🔄 Sync" or text == "📥 Sync Full":
            # Parse arguments
            args = text.split()
            force_full = False
            if (len(args) > 1 and args[1].lower() == "full") or (text == "/sync_full") or (text == "📥 Sync Full"):
                force_full = True
            
            mode_str = "COMPLETA (Full Download)" if force_full else "Inteligente (Smart Sync)"
            self.send_message(chat_id, f"🔄 Iniciando sincronização: {mode_str}...")
            
            t = threading.Thread(target=self.run_check_job, args=(True, chat_id, force_full)) 
            t.start()
            
        elif text == "/map" or text == "🗺️ Mapa":
             self.send_message(chat_id, "🗺️ Gerando mapa...")
             # Gerar em thread para nao bloquear? Map é rápido com pillow, mas download da base pode demorar na 1a vez.
             # Vamos fazer inline por simplificidade, já que download é cacheado.
             confirmed = self.storage.get_confirmed_grids()
             worked = self.storage.get_worked_grids()
             
             try:
                 confirmed = self.storage.get_confirmed_grids()
                 worked = self.storage.get_worked_grids()
                 grid_labels = self.storage.get_grid_labels()
                 
                 img_bytes = self.map_gen.generate(confirmed, worked, grid_labels)
                 if img_bytes:
                     self.send_photo(chat_id, img_bytes, "Mapa de Grids Confirmados")
                 else:
                     logger.error("Falha ao gerar mapa: map_gen.generate retornou vazio.")
                     self.send_message(chat_id, "❌ Erro ao gerar o mapa: retorno vazio.")
             except Exception as e:
                 logger.exception("Exceção ao gerar mapa")
                 self.send_message(chat_id, f"❌ Erro ao gerar o mapa: {e}")

        elif text == "/tle" or text == "🛰️ TLEs":
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

        elif text.startswith("/forget "):
            # Remove um grid e força resync total
            grid_for = text[8:].strip().upper()
            known = self.storage.data.get("known_grids", [])
            
            if grid_for in known:
                known.remove(grid_for)
                self.storage.data["known_grids"] = sorted(known)
                self.storage.last_qso_date = "1900-01-01" # Forçar novo download completo
                self.storage.save()
                self.send_message(chat_id, f"🗑️ Esqueci {grid_for}. O próximo /sync fará um download COMPLETO para achá-lo de novo.")
            else:
                self.send_message(chat_id, f"⚠️ Grid {grid_for} não consta na lista.")

        elif text.startswith("/testgrid "):
            # Simula um alerta visual COMPLETO
            grid_test = text[10:].strip().upper()
            
            # 1. Envia msg de texto simulada
            msg_lines = [
                "🚀 *Novo(s) grid(s) de satélite no LoTW!* (TESTE)",
                "",
                f"Você confirmou *1* novo(s) grid(s).",
                f"Total confirmado: *{len(self.storage.known_grids) + 1}* grids (Simulado).",
                "",
                "*Detalhes:*",
                f"• `{grid_test}` com `TEST-CALL` ({datetime.now().strftime('%d/%m/%Y')})"
            ]
            self.send_message(chat_id, "\n".join(msg_lines))
            
            # 2. Gera mapa INCLUINDO o grid de teste (sem salvar no banco)
            try:
                confirmed = self.storage.get_confirmed_grids()
                confirmed.add(grid_test) # Adiciona temporariamente para o mapa
                
                # Mock labels
                grid_labels = self.storage.get_grid_labels()
                grid_labels[grid_test] = "TEST-CALL"
                
                img_bytes = self.map_gen.generate(confirmed, set(), grid_labels)
                if img_bytes:
                    self.send_photo(chat_id, img_bytes, "🗺️ Mapa atualizado com os novos grids! (TESTE)")
                else:
                    self.send_message(chat_id, "❌ Erro ao gerar mapa de teste.")
            except Exception as e:
                logger.error(f"Erro teste: {e}")
                self.send_message(chat_id, f"❌ Erro: {e}")

    def set_bot_commands(self):
        """Configura o menu de comandos no Telegram via API."""
        commands = [
            {"command": "stats", "description": "📊 Dashboard de Estatísticas"},
            {"command": "map", "description": "🗺️ Gerar Mapa Visual"},
            {"command": "sync", "description": "🔄 Sincronizar (Rápido)"},
            {"command": "sync_full", "description": "📥 Sincronizar TUDO (Completo)"},
            {"command": "grids", "description": "📋 Resumo de Grids"},
            {"command": "tle", "description": "🛰️ Checar TLEs"},
            {"command": "check", "description": "🔍 Checar Call (Ex: /check call)"},
            {"command": "help", "description": "❓ Ajuda"}
        ]
        url = f"https://api.telegram.org/bot{self.token}/setMyCommands"
        try:
            r = requests.post(url, json={"commands": commands})
            r.raise_for_status()
            logger.info("Menu de comandos configurado com sucesso.")
        except Exception as e:
            logger.error(f"Erro ao configurar menu de comandos: {e}")

    def send_help(self, chat_id: str):
        """Envia mensagem de ajuda com os comandos disponíveis."""
        lines = [
            "🤖 *LoTW Monitor Bot - Ajuda*",
            "",
            "Comandos disponíveis:",
            "• `/stats` - Dashboard completo.",
            "• `/map` - Mapa visual.",
            "• `/sync` - Sincronização rápida.",
            "• `/sync_full` - Sincronização COMPLETA.",
            "• `/check <CALL>` - Verificar indicativo.",
            "• `/grids` - Listar grids.",
            "• `/tle` - Atualizar TLEs.",
            "• `/help` - Ajuda.",
        ]
        self.send_message(chat_id, "\n".join(lines))

    def start_polling(self):
        logger.info("Bot iniciado...")
        
        # Configurar menu
        self.set_bot_commands()
        
        # Envia mensagem de startup
        try:
            self.send_message(self.allowed_chat_id, "🤖 *Bot Iniciado!* Menu de comandos ativo. ☰")
            # self.send_help(self.allowed_chat_id) # Help não é mais tão necessário na startup se tem menu
        except Exception as e:
            logger.error(f"Erro ao enviar mensagem de startup: {e}")

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

