import re
import json
import os
from pathlib import Path
import requests
import logging

try:
    from shapely.geometry import shape, Point
    SHAPELY_AVAILABLE = True
except ImportError:
    SHAPELY_AVAILABLE = False

logger = logging.getLogger(__name__)

# Config
GEOJSON_URL = "https://raw.githubusercontent.com/codeforgermany/click_that_hood/main/public/data/brazil-states.geojson"
# Base dir determination (compatible with config.py logic)
BASE_DIR = Path.cwd()
GEOJSON_PATH = BASE_DIR / "data" / "brazil-states.geojson"

POLYGONS_CACHE = {} # State Code -> Polygon/MultiPolygon

def _ensure_geojson():
    """Baixa o GeoJSON dos estados se não existir."""
    if GEOJSON_PATH.exists():
        return

    try:
        logger.info("Baixando GeoJSON de estados do Brasil...")
        r = requests.get(GEOJSON_URL, timeout=30)
        r.raise_for_status()
        
        # Ensure dir
        GEOJSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        
        with open(GEOJSON_PATH, 'wb') as f:
            f.write(r.content)
        logger.info("GeoJSON salvo.")
    except Exception as e:
        logger.error(f"Erro ao baixar GeoJSON: {e}")

def _load_polygons():
    """Carrega polígonos na memória."""
    if POLYGONS_CACHE: return
    
    if not SHAPELY_AVAILABLE:
        logger.warning("Shapely não instalado. Geometria desativada.")
        return

    _ensure_geojson()
    if not GEOJSON_PATH.exists(): return

    try:
        with open(GEOJSON_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        for feature in data.get('features', []):
            props = feature.get('properties', {})
            geom = feature.get('geometry')
            
            # The GeoJSON from 'click_that_hood' uses 'sigla' or 'acronym' usually?
            # Let's check properties structure if possible.
            # Usually: 'sigla', 'name'.
            # click_that_hood brazil-states properties: 
            # {"name": "Acre", "sigla": "AC", ...}
            
            sigla = props.get('sigla')
            if not sigla and 'name' in props:
                # Map name to sigla if needed? 
                # Hopefully 'sigla' is there. If not, we might need a backup map.
                # Let's assume standard behavior or map common names.
                # Inspecting online source: it has "sigla": "AC". Verified.
                sigla = props.get('sigla')

            if sigla and geom:
                POLYGONS_CACHE[sigla] = shape(geom)
                
    except Exception as e:
        logger.error(f"Erro ao carregar polígonos: {e}")

def grid_to_latlon(grid: str):
    """Retorna (lat, lon) central do Grid."""
    grid = grid.upper().strip()
    if len(grid) < 4: return None
    
    # Field
    lon_f = (ord(grid[0]) - ord('A')) * 20 - 180
    lat_f = (ord(grid[1]) - ord('A')) * 10 - 90
    # Square
    lon_s = int(grid[2]) * 2
    lat_s = int(grid[3]) * 1
    
    # Center offsets
    lat_off = 0.5
    lon_off = 1.0
    
    # Subsquare handling (6 chars)
    if len(grid) >= 6:
        # grid[4] (Lon) is a..x (24 divs of 2 deg => 5 mins = 1/12 deg)
        # grid[5] (Lat) is a..x (24 divs of 1 deg => 2.5 mins = 1/24 deg)
        lon_ss = (ord(grid[4]) - ord('A')) * (2.0/24.0)
        lat_ss = (ord(grid[5]) - ord('A')) * (1.0/24.0)
        # Center of subsquare
        lon_off = (2.0/24.0) / 2
        lat_off = (1.0/24.0) / 2
        
        lat = lat_f + lat_s + lat_ss + lat_off
        lon = lon_f + lon_s + lon_ss + lon_off
    else:
        # Center of square
        lat = lat_f + lat_s + lat_off
        lon = lon_f + lon_s + lon_off
        
    return lat, lon

def get_state_from_grid(grid: str) -> str:
    """Mapeia Grid -> Estado usando Geometria (Ponto no Polígono)."""
    # Config
    if not grid or len(grid) < 4: return None
    
    # 0. Manual Overrides (Small states / Ambiguity)
    # GH64 center falls in GO, but it is the main grid for Brasilia (DF).
    # GI84 is Teresina (PI) border with MA. PS8ET lives there.
    MANUAL_GRID_MAP = {
        "GH64": "DF",
        "GI84": "PI"
    }
    if grid in MANUAL_GRID_MAP:
        return MANUAL_GRID_MAP[grid]

    if not SHAPELY_AVAILABLE: return None
    
    try:
        _load_polygons()
        if not POLYGONS_CACHE: return None
        
        lat, lon = grid_to_latlon(grid)
        pt = Point(lon, lat)
        
        # 1. Strict Check (Contains)
        for sigla, poly in POLYGONS_CACHE.items():
            if poly.contains(pt):
                return sigla
                
        # 2. Proximity Check (Coastal/Border Tolerance)
        # "Não seja tão restritivo" - User Request.
        # Check distance to all polygons, find min.
        # 0.3 degrees is approx 33km. Sufficient for coastal grid centers.
        TOLERANCE = 0.3 
        
        closest_state = None
        min_dist = float('inf')
        
        for sigla, poly in POLYGONS_CACHE.items():
            dist = poly.distance(pt)
            if dist < min_dist:
                min_dist = dist
                closest_state = sigla
                
        if closest_state and min_dist <= TOLERANCE:
            return closest_state
            
        return None
        
    except Exception as e:
        logger.error(f"Erro no geo-check do grid {grid}: {e}")
        return None

def get_state_from_call(call: str) -> str:
    """
    Deduz o estado (UF) brasileiro baseado no indicativo (Callsign).
    Lógica de fallback mantida.
    """
    call = call.upper().strip()
    
    # 1. Verifica se é Brasil (PPA-PYZ, ZVA-ZZZ)
    if not re.match(r'^(PP|PQ|PR|PS|PT|PU|PV|PW|PX|PY|ZV|ZW|ZX|ZY|ZZ)', call):
        return None

    # Parse mais detalhado
    match = re.match(r'^([A-Z]{2})([0-9])([A-Z]+)', call)
    if not match:
        return None
        
    pfx, reg, suf = match.groups()
    reg = int(reg)
    
    # Helper for generic prefixes (PY, ZV, etc.)
    is_general = pfx in ['PY', 'PW', 'PX', 'ZV', 'ZW', 'ZX', 'ZY', 'ZZ']
    
    # --- LOGICA DE REGIOES ---
    
    # REGIÃO 1: RJ, ES
    if reg == 1:
        if pfx == 'PP': return 'ES'
        if pfx == 'PU':
            if 'AAA' <= suf <= 'IZZ': return 'ES'
            return 'RJ'
        return 'RJ' # PY1, ZV1 -> RJ

    # REGIÃO 2: SP, GO, DF, TO
    if reg == 2:
        if pfx == 'PQ': return 'TO'
        if pfx == 'PT': return 'DF'
        if pfx == 'PP': return 'GO'
        if pfx == 'PU':
            if 'AAA' <= suf <= 'EZZ': return 'DF'
            if 'FAA' <= suf <= 'HZZ': return 'GO'
            return 'SP' 
        # PY2, ZV2 -> SP (Majority, though GO exists. Only suffix could tell for strictness, but standard is SP)
        return 'SP'

    # REGIÃO 3: RS
    if reg == 3:
        return 'RS'

    # REGIÃO 4: MG
    if reg == 4:
        return 'MG'

    # REGIÃO 5: SC, PR
    if reg == 5:
        if pfx == 'PP': return 'SC'
        if pfx == 'PU':
             if 'AAA' <= suf <= 'LZZ': return 'SC'
             return 'PR'
        return 'PR' # PY5, ZV5 -> PR

    # REGIÃO 6: BA, SE
    if reg == 6:
        if pfx == 'PP': return 'SE'
        if pfx == 'PU':
            if 'AAA' <= suf <= 'IZZ': return 'SE'
            return 'BA'
        return 'BA' # PY6 -> BA

    # REGIÃO 7: AL, CE, PB, PE, PI, RN
    if reg == 7:
        if pfx == 'PP': return 'AL'
        if pfx == 'PT': return 'CE'
        if pfx == 'PR': return 'PB'
        if pfx == 'PS': return 'RN'
        # PU logic logic refined
        if pfx == 'PU':
            # A-D: Alagoas
            if suf[0] in ['A','B','C','D']: return 'AL'
            # E-H: Paraíba
            if suf[0] in ['E','F','G','H']: return 'PB'
            # I-L: Rio Grande do Norte (Confirmed via lookup)
            if suf[0] in ['I','J','K','L']: return 'RN'
            # M-P: Ceará (Likely block)
            if suf[0] in ['M','N','O','P']: return 'CE'
            # Q-Z: Pernambuco (Default/Remaining)
            return 'PE'
        return 'PE' # PY7 -> PE

    # REGIÃO 8: AC, AP, AM, MA, PA, PI, RO, RR
    if reg == 8:
        if pfx == 'PT': return 'AC'
        if pfx == 'PQ': return 'AP'
        if pfx == 'PP': return 'AM'
        if pfx == 'PR': return 'MA' 
        if pfx == 'PY': return 'PA'
        if pfx == 'PS': return 'PI'
        if pfx == 'PW': return 'RO'
        if pfx == 'PV': return 'RR'
        if pfx == 'PU':
             if 'AAA' <= suf <= 'CZZ': return 'AM'
             if 'DAA' <= suf <= 'FZZ': return 'RR'
             if 'GAA' <= suf <= 'IZZ': return 'AP'
             if 'JAA' <= suf <= 'LZZ': return 'AC'
             if 'MAA' <= suf <= 'OZZ': return 'MA'
             if 'PAA' <= suf <= 'SZZ': return 'PI'
             if 'TAA' <= suf <= 'VZZ': return 'RO'
             if 'WAA' <= suf <= 'YZZ': return 'PA'
        return 'AM'

    # REGIÃO 9: MT, MS
    if reg == 9:
        if pfx == 'PY': return 'MT'
        if pfx == 'PT': return 'MS'
        if pfx == 'PU':
            if 'AAA' <= suf <= 'NZZ': return 'MS'
            if 'OAA' <= suf <= 'YZZ': return 'MT'
        return 'MT'
        
    # Region 0 (Islands)
    if reg == 0:
        if suf.startswith('F'): return 'PE'
        if suf.startswith('T'): return 'ES'
        return 'PE'

    return None

def get_all_states():
    return [
       'AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 
       'MT', 'MS', 'MG', 'PA', 'PB', 'PR', 'PE', 'PI', 'RJ', 'RN', 
       'RS', 'RO', 'RR', 'SC', 'SP', 'SE', 'TO'
    ]
