import json
import logging
from typing import Dict, List, Set, Any
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

class Storage:
    def __init__(self, filepath: Path):
        self.filepath = filepath
        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        if not self.filepath.exists():
            return {
                "known_grids": [],
                "qso_cache": {},  # call+date+band -> qso_record
                "last_run": None,
                "last_qso_date": "1900-01-01" # Para busca incremental
            }
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Erro ao carregar estado: {e}")
            return {}

    def save(self):
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Erro ao salvar estado: {e}")

    @property
    def last_qso_date(self) -> str:
        return self.data.get("last_qso_date", "1900-01-01")

    @last_qso_date.setter
    def last_qso_date(self, value: str):
        self.data["last_qso_date"] = value
        
    @property
    def last_sync_date(self) -> str:
        """Data da última sincronização bem sucedida no formato YYYY-MM-DD"""
        return self.data.get("last_sync_date", "1900-01-01")

    @last_sync_date.setter
    def last_sync_date(self, value: str):
        self.data["last_sync_date"] = value

    @property
    def known_grids(self) -> Set[str]:
        return set(self.data.get("known_grids", []))

    def merge_qsos(self, new_qsos: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Mescla novos QSOs no cache.
        Retorna lista de grids que passaram a ser CONFIRMADOS (inéditos).
        """
        cache = self.data.setdefault("qso_cache", {})
        
        # Carrega o estado atual de confirmados
        current_confirmed = set(self.data.get("known_grids", []))
        
        newly_confirmed_grids = set()
        
        for qso in new_qsos:
            key = self._qso_key(qso)
            cache[key] = qso
            
            # Checa se é confirmado (LoTW status QSL_RCVD = Y, ou se veio pela query QSL=yes)
            # Como agora baixamos TUDO (trabalhados e confirmados), precisamos validar o campo.
            # LoTW field: QSL_RCVD (Y ou N) ou APP_LOTW_QSLMODE
            is_confirmed = (qso.get("QSL_RCVD", "").upper() == "Y")
            
            if is_confirmed:
                grids = self._extract_grids(qso)
                for g in grids:
                    if g not in current_confirmed:
                        newly_confirmed_grids.add(g)
        
        # Atualiza a lista persistida de confirmados
        if newly_confirmed_grids:
            current_confirmed.update(newly_confirmed_grids)
            self.data["known_grids"] = sorted(list(current_confirmed))
            
        self.data["last_run"] = datetime.now().isoformat()
        
        return sorted(list(newly_confirmed_grids))

    def get_confirmed_grids(self) -> Set[str]:
        return set(self.data.get("known_grids", []))

    def get_worked_grids(self) -> Set[str]:
        """
        Retorna TODOS os grids encontrados no cache de QSOs (trabalhados ou confirmados).
        """
        all_grids = set()
        for qso in self.data.get("qso_cache", {}).values():
            all_grids.update(self._extract_grids(qso))
        return all_grids


    def _qso_key(self, qso: Dict[str, str]) -> str:
        """Gera chave única para o QSO: CALL + DATA + BAND + TIME"""
        return f"{qso.get('CALL')}_{qso.get('QSO_DATE')}_{qso.get('TIME_ON')}_{qso.get('BAND')}"

    def _extract_grids(self, qso: Dict[str, str]) -> Set[str]:
        grids = set()
        # PROP_MODE=SAT ou SAT_NAME presente
        if qso.get("PROP_MODE", "").upper() != "SAT" and not qso.get("SAT_NAME"):
            return grids

        # VUCC_GRIDS tem prioridade
        vucc = qso.get("VUCC_GRIDS", "")
        if vucc:
            for g in vucc.split(","):
                g4 = g.strip().upper()[:4]
                if len(g4) == 4:
                    grids.add(g4)
        else:
            g = qso.get("GRIDSQUARE", "")
            g4 = g.strip().upper()[:4]
            if len(g4) == 4:
                grids.add(g4)
        return grids

    def get_stats(self) -> Dict[str, Any]:
        """
        Gera estatísticas a partir do cache local.
        """
        # Formato: { "HI21": { "count": 10, "last_call": "XX1XX", ... } }
        stats = {}
        for qso in self.data.get("qso_cache", {}).values():
            grids = self._extract_grids(qso)
            for g in grids:
                if g not in stats:
                    stats[g] = {"count": 0, "calls": set()}
                stats[g]["count"] += 1
                stats[g]["calls"].add(qso.get("CALL", "UNKNOWN"))
        return stats

    def get_grid_labels(self) -> Dict[str, str]:
        """
        Retorna um dicionário {GRID: CALL} para os grids confirmados.
        Escolhe arbitrariamente um call caso haja múltiplos (ex: o mais recente processado).
        """
        labels = {}
        # Itera cache para encontrar confirmados
        # Ordenamos por data para tentar pegar o mais recente? O cache não é ordenado garatido.
        # Mas podemos iterar e sobrescrever.
        
        # Ordenar QSOs por data (opcional, mas bom para consistência)
        qsos = list(self.data.get("qso_cache", {}).values())
        # Sort by Date + Time
        qsos.sort(key=lambda x: (x.get("QSO_DATE", ""), x.get("TIME_ON", "")))
        
        for qso in qsos:
            # Check confirmation
            is_confirmed = (qso.get("QSL_RCVD", "").upper() == "Y")
            if is_confirmed:
                call = qso.get("CALL", "?")
                grids = self._extract_grids(qso)
                for g in grids:
                    labels[g] = call
        
        return labels
