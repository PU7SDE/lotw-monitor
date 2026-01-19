import logging
import io
import requests
from PIL import Image, ImageDraw, ImageFont
from typing import Set, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

class MapGenerator:
    # Mapa Equiretangular (Plate Carrée) - Blue Marble Next Generation (21K - Ultra High Res)
    # X vai de -180 a 180, Y vai de 90 a -90
    MAP_URL = "https://upload.wikimedia.org/wikipedia/commons/b/b2/Blue_Marble_Next_Generation_%2B_topography_%2B_bathymetry.jpg"
    
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.map_path = cache_dir / "world_map_21k.jpg"
        self._ensure_map()

    def _ensure_map(self):
        if not self.map_path.exists():
            try:
                logger.info("Baixando mapa base 21K (isso pode demorar na 1a vez)...")
                headers = {"User-Agent": "Mozilla/5.0 (compatible; LoTWMonitor/1.0)"}
                r = requests.get(self.MAP_URL, stream=True, timeout=120, headers=headers)
                r.raise_for_status()
                with open(self.map_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=16384):
                        f.write(chunk)
                logger.info("Mapa base 21K salvo.")
            except Exception as e:
                logger.error(f"Erro ao baixar mapa: {e}")

    def _grid_to_latlon(self, grid: str) -> Tuple[float, float, float, float]:
        """
        Converte Grid 4 chars (ex: GG66) para (lat_min, lon_min, lat_max, lon_max).
        """
        grid = grid.upper().strip()
        if len(grid) < 4:
            return (0,0,0,0)

        # Field (A-R)
        f1 = ord(grid[0]) - ord('A')
        f2 = ord(grid[1]) - ord('A')

        # Square (0-9)
        s1 = int(grid[2])
        s2 = int(grid[3])

        lon_min = -180.0 + (f1 * 20.0) + (s1 * 2.0)
        lat_min = -90.0 + (f2 * 10.0) + (s2 * 1.0)
        
        lon_max = lon_min + 2.0
        lat_max = lat_min + 1.0
        
        return (lat_min, lon_min, lat_max, lon_max)

    def _project(self, lat: float, lon: float, w: int, h: int) -> Tuple[float, float]:
        """
        Projeta Lat/Lon para X/Y na imagem (Equiretangular).
        """
        x = (lon + 180.0) * (w / 360.0)
        y = (90.0 - lat) * (h / 180.0)
        return x, y

    def generate(self, confirmed_grids: Set[str], worked_grids: Set[str]) -> bytes:
        """
        Gera imagem recortada com zoom inteligente.
        Usa Lazy Loading para suportar mapa 21K sem explodir RAM.
        """
        if not self.map_path.exists():
            return b""
            
        try:
            # Abre o arquivo (Lazy - não carrega pixels ainda)
            with Image.open(self.map_path) as im:
                w_orig, h_orig = im.size
                
                # 1. Determina a área de interesse (Crop Box) ANTES de carregar
                all_grids = confirmed_grids
                min_lat, max_lat = 90.0, -90.0
                min_lon, max_lon = 180.0, -180.0
                found_any = False
                
                if all_grids:
                    for g in all_grids:
                        lat_min_g, lon_min_g, lat_max_g, lon_max_g = self._grid_to_latlon(g)
                        if (lat_min_g == 0 and lat_max_g == 0): continue
                        
                        if lat_min_g < min_lat: min_lat = lat_min_g
                        if lat_max_g > max_lat: max_lat = lat_max_g
                        if lon_min_g < min_lon: min_lon = lon_min_g
                        if lon_max_g > max_lon: max_lon = lon_max_g
                        found_any = True
                
                # Variáveis de offset para o desenho (se fizermos crop)
                off_x, off_y = 0, 0
                
                # Se achamos grids, definimos o crop
                if found_any:
                    padding = 3.0 # Zoom forte
                    min_lat = max(-90.0, min_lat - padding)
                    max_lat = min(90.0, max_lat + padding)
                    min_lon = max(-180.0, min_lon - padding)
                    max_lon = min(180.0, max_lon + padding)
                    
                    # Zoom mínimo 20x20 graus
                    if (max_lat - min_lat) < 20.0:
                        mid = (min_lat + max_lat) / 2
                        min_lat = max(-90.0, mid - 10.0)
                        max_lat = min(90.0, mid + 10.0)
                    if (max_lon - min_lon) < 20.0:
                        mid = (min_lon + max_lon) / 2
                        min_lon = max(-180.0, mid - 10.0)
                        max_lon = min(180.0, mid + 10.0)

                    # Calcula coordenadas no mapa FULL
                    left, bottom = self._project(min_lat, min_lon, w_orig, h_orig)
                    right, top = self._project(max_lat, max_lon, w_orig, h_orig)
                    
                    # Garante inteiros e limites
                    left, top = max(0, int(left)), max(0, int(top))
                    right, bottom = min(w_orig, int(right)), min(h_orig, int(bottom))
                    
                    # Validar tamanho do crop (evitar zero ou negativo)
                    if right <= left or bottom <= top:
                         # Fallback para full map
                         found_any = False
                    else:
                        crop_box = (left, top, right, bottom)
                        
                        # FAZ O CROP (Carrega apenas essa parte na RAM)
                        working_im = im.crop(crop_box)
                        off_x, off_y = left, top
                
                if not found_any:
                    # Se não tem grids, ou falhou, usa o mapa todo (mas resize logo!)
                    # Não podemos carregar 21K full.
                    # Vamos fazer thumbnail DO ARQUIVO usando draft ou resize
                    # Pillow draft é eficiente para JPEGs
                    working_im = im.copy() # Cópia leve
                    working_im.thumbnail((4096, 2048), Image.Resampling.LANCZOS)
                    # Recalcula w/h efetivos para projeção
                    w_orig, h_orig = working_im.size 
                    # off_x, off_y continuam 0
                
                # Agora working_im é pequeno o suficiente. Convertemos para RGBA.
                working_im = working_im.convert("RGBA")
                
                # Camada de desenho
                overlay = Image.new("RGBA", working_im.size, (255, 255, 255, 0))
                draw = ImageDraw.Draw(overlay)
                
                # Desenha os grids
                for grid in confirmed_grids:
                    lat_min, lon_min, lat_max, lon_max = self._grid_to_latlon(grid)
                    
                    # Projeta nas coordenadas do mapa ORIGINAL (escala full)
                    # SE fizemos crop, temos w_orig da imagem original.
                    # SE fizemos resize (found_any=False), w_orig foi atualizado para size reduzido.
                    
                    # Caso Resize (found_any=False): w_orig já é pequeno. off_x=0. OK.
                    # Caso Crop (found_any=True): w_orig é 21K. off_x é o offset.
                    
                    # O self._project usa w, h passados.
                    # Precisamos passar o w, h que correspondem à escala da projeção.
                    # No crop: escala é a original. Passamos 21600, 10800.
                    # No resize: escala é a reduzida. Passamos 4096, 2048.
                    
                    if found_any:
                        # Escala Full
                        x1, y_bottom = self._project(lat_min, lon_min, im.size[0], im.size[1]) # Use im.size for original dimensions
                        x2, y_top = self._project(lat_max, lon_max, im.size[0], im.size[1])
                        
                        # Ajusta offset do crop
                        x1 -= off_x
                        x2 -= off_x
                        y_bottom -= off_y
                        y_top -= off_y
                    else:
                        # Escala Reduzida
                        x1, y_bottom = self._project(lat_min, lon_min, w_orig, h_orig)
                        x2, y_top = self._project(lat_max, lon_max, w_orig, h_orig)

                    # Desenha rect (apenas se estiver visível no crop)
                    # Pillow clipa automaticamente, mas coords podem ser negativas.
                    draw.rectangle([x1, y_top, x2, y_bottom], fill=(0, 255, 0, 128), outline=(0, 200, 0, 200))

                # Composite e Saída
                out = Image.alpha_composite(working_im, overlay)
                out = out.convert("RGB")
                
                # Final safeguard resize (Telegram limitation)
                # Se o crop for enorme (ex: zoom na russia inteira), redimensiona.
                if out.width > 3840 or out.height > 3840:
                    out.thumbnail((3840, 3840), Image.Resampling.LANCZOS)
                
                buf = io.BytesIO()
                out.save(buf, format="PNG")
                return buf.getvalue()

        except Exception as e:
            logger.error(f"Erro ao gerar mapa: {e}")
            return b""
