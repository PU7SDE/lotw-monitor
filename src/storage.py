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
        qsos = list(self.data.get("qso_cache", {}).values())
        qsos.sort(key=lambda x: (x.get("QSO_DATE", ""), x.get("TIME_ON", "")))
        
        for qso in qsos:
            is_confirmed = (qso.get("QSL_RCVD", "").upper() == "Y")
            if is_confirmed:
                call = qso.get("CALL", "?")
                grids = self._extract_grids(qso)
                for g in grids:
                    labels[g] = call
        return labels

    def get_dashboard_stats(self) -> Dict[str, Any]:
        """
        Retorna estatísticas detalhadas do dashboard (similar ao HTML fornecido).
        Calcula: Total QSOs, Grids, Sats, DXCC, CQ, ITU, Max Distance, Hunters.
        """
        import math

        stats = {
            "total_confirmed": 0,
            "total_grids": 0,
            "total_sats": 0,
            "max_distance": 0,
            "dxcc_count": 0,
            "cq_count": 0,
            "itu_count": 0,
            "vucc_status": 0,
            "top_hunters": [], # Lista de (Call, Count, GridsStr)
            "sats_breakdown": {}, # Sat -> Count
            "dxcc_breakdown": {}  # Country -> Count
        }

        unique_grids = set()
        unique_sats = set()
        unique_dxcc = set()
        unique_cq = set()
        unique_itu = set()
        hunter_grids = {} # Call -> Set[Grid]
        
        # Helper de Distância (Haversine)
        def calc_dist(lat1, lon1, lat2, lon2):
            R = 6371
            dLat = (lat2 - lat1) * math.pi / 180
            dLon = (lon2 - lon1) * math.pi / 180
            a = math.sin(dLat/2) * math.sin(dLat/2) + \
                math.cos(lat1 * math.pi / 180) * math.cos(lat2 * math.pi / 180) * \
                math.sin(dLon/2) * math.sin(dLon/2)
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
            return int(R * c)

        # Helper Grid -> LatLon Center
        def grid_to_center(grid):
            if not grid or len(grid) < 4: return None
            g = grid.upper().strip()
            # Maidenhead simplificado (apenas 4 chars)
            # Longitude: (Field - 'A') * 20 - 180 + (Square) * 2
            # Latitude: (Field - 'A') * 10 - 90 + (Square) * 1
            # Center: +1 lon, +0.5 lat
            
            A = ord('A')
            lon_field = (ord(g[0]) - A) * 20 - 180
            lat_field = (ord(g[1]) - A) * 10 - 90
            lon_sq = int(g[2]) * 2
            lat_sq = int(g[3]) * 1
            
            lat_center = lat_field + lat_sq + 0.5
            lon_center = lon_field + lon_sq + 1.0
            return (lat_center, lon_center)

        # Iterar QSOs
        for qso in self.data.get("qso_cache", {}).values():
             is_confirmed = (qso.get("QSL_RCVD", "").upper() == "Y")
             
             # HTML filtra por SAT e Confirmed? 
             # O código HTML processa "prop_mode=SAT".
             prop = qso.get("PROP_MODE", "").upper()
             sat_name = qso.get("SAT_NAME", "").upper()
             
             if prop != "SAT" and not sat_name:
                 continue
                 
             if not is_confirmed:
                 continue

             stats["total_confirmed"] += 1
             
             # Grids do QSO
             qs_grids = self._extract_grids(qso)
             unique_grids.update(qs_grids)
             
             # Sat
             if sat_name:
                 unique_sats.add(sat_name)
                 stats["sats_breakdown"][sat_name] = stats["sats_breakdown"].get(sat_name, 0) + 1
             
             # DXCC/CQ/ITU
             dxcc = qso.get("COUNTRY", "").upper()
             if dxcc: 
                 unique_dxcc.add(dxcc)
                 stats["dxcc_breakdown"][dxcc] = stats["dxcc_breakdown"].get(dxcc, 0) + 1
                 
             if qso.get("CQZ"): unique_cq.add(qso.get("CQZ"))
             if qso.get("ITUZ"): unique_itu.add(qso.get("ITUZ"))
             
             # Top Hunter logic
             call = qso.get("CALL", "?").upper()
             if call not in hunter_grids: hunter_grids[call] = set()
             hunter_grids[call].update(qs_grids)
             
             # Distance Calc
             my_grid = qso.get("MY_GRIDSQUARE") or \
                       (qso.get("MY_VUCC_GRIDS", "").split(",")[0] if qso.get("MY_VUCC_GRIDS") else None)
             
             if my_grid and len(my_grid) >= 4:
                 my_coord = grid_to_center(my_grid[:4])
                 for g in qs_grids:
                     target_coord = grid_to_center(g)
                     if my_coord and target_coord:
                         d = calc_dist(my_coord[0], my_coord[1], target_coord[0], target_coord[1])
                         if d > stats["max_distance"]:
                             stats["max_distance"] = d

        stats["total_grids"] = len(unique_grids)
        stats["total_sats"] = len(unique_sats)
        stats["dxcc_count"] = len(unique_dxcc)
        stats["cq_count"] = len(unique_cq)
        stats["itu_count"] = len(unique_itu)
        
        # Prepare Top Hunters (Sort by Unique Grids desc)
        sorted_hunters = sorted(hunter_grids.items(), key=lambda item: len(item[1]), reverse=True)
        # Pegar top 5
        # Pegar top 5 (Filtrando >= 2 grids conforme pedido)
        for call, grids in sorted_hunters:
            if len(grids) < 2:
                continue
                
            stats["top_hunters"].append({
                "call": call,
                "count": len(grids),
                "grids": ", ".join(sorted(list(grids))[:5]) + ("..." if len(grids)>5 else "")
            })
            
            if len(stats["top_hunters"]) >= 5:
                break
            
        return stats
