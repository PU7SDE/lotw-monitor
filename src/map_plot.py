import logging
import io
import requests
from PIL import Image, ImageDraw, ImageFont
from typing import Set, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

class MapGenerator:
    # Mapa Equiretangular (Plate Carrée) simples
    # X vai de -180 a 180, Y vai de 90 a -90
    MAP_URL = "https://upload.wikimedia.org/wikipedia/commons/thumb/8/83/Equirectangular_projection_SW.jpg/2048px-Equirectangular_projection_SW.jpg"
    
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.map_path = cache_dir / "world_map.jpg"
        self._ensure_map()

    def _ensure_map(self):
        if not self.map_path.exists():
            try:
                logger.info("Baixando mapa base...")
                headers = {"User-Agent": "Mozilla/5.0 (compatible; LoTWMonitor/1.0)"}
                r = requests.get(self.MAP_URL, stream=True, timeout=60, headers=headers)
                r.raise_for_status()
                with open(self.map_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                logger.info("Mapa base salvo.")
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
        # 18 fields longe (360/20), 18 fields lat (180/10)
        # Lon: -180 + 20*idx
        f1 = ord(grid[0]) - ord('A')
        f2 = ord(grid[1]) - ord('A')

        # Square (0-9)
        # 10 squares lon (20/10 = 2 deg), 10 squares lat (10/10 = 1 deg)
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
        X = (lon + 180) * (w / 360)
        Y = (90 - lat) * (h / 180)  (Y inverte pois imagem cresce para baixo)
        """
        x = (lon + 180.0) * (w / 360.0)
        y = (90.0 - lat) * (h / 180.0)
        return x, y

    def generate(self, confirmed_grids: Set[str], worked_grids: Set[str]) -> bytes:
        """
        Gera imagem PNG com os grids pintados.
        Green = Confirmed
        Red = Worked (but not confirmed)
        """
        if not self.map_path.exists():
            return b""
            
        try:
            with Image.open(self.map_path) as im:
                im = im.convert("RGBA")
                
                # Criar layer transparente para desenhar
                overlay = Image.new("RGBA", im.size, (255, 255, 255, 0))
                draw = ImageDraw.Draw(overlay)
                
                w, h = im.size
                
                # Primeiro Worked (Red), pois Confirmed sobrescreve
                # (Se for confirmado, já foi trabalhado, então a interseção seria pintada 2x)
                # Vamos filtrar: worked only = worked - confirmed
                only_worked = worked_grids - confirmed_grids
                
                for grid in only_worked:
                    lat_min, lon_min, lat_max, lon_max = self._grid_to_latlon(grid)
                    x1, y1 = self._project(lat_min, lon_min, w, h) # Bottom Left (lat min is bottom) -> wait, Y inverts
                    # lat_min -> Y maior (embaixo). lat_max -> Y menor (em cima)
                    # _project já inverte Y.
                    
                    x1, y_bottom = self._project(lat_min, lon_min, w, h)
                    x2, y_top = self._project(lat_max, lon_max, w, h)
                    
                    # Rectangle needs (x0, y0, x1, y1) where 0 is top-left
                    draw.rectangle([x1, y_top, x2, y_bottom], fill=(255, 0, 0, 128), outline=(200, 0, 0, 200))

                for grid in confirmed_grids:
                    lat_min, lon_min, lat_max, lon_max = self._grid_to_latlon(grid)
                    x1, y_bottom = self._project(lat_min, lon_min, w, h)
                    x2, y_top = self._project(lat_max, lon_max, w, h)
                    
                    draw.rectangle([x1, y_top, x2, y_bottom], fill=(0, 255, 0, 128), outline=(0, 200, 0, 200))

                # Compor
                out = Image.alpha_composite(im, overlay)
                
                # --- AUTO CROP ---
                all_grids = confirmed_grids.union(worked_grids)
                if all_grids:
                    min_lat, max_lat = 90.0, -90.0
                    min_lon, max_lon = 180.0, -180.0
                    
                    found_any = False
                    for g in all_grids:
                        lat_min, lon_min, lat_max, lon_max = self._grid_to_latlon(g)
                        if (lat_min == 0 and lat_max == 0 and lon_min == 0 and lon_max == 0):
                            continue
                        
                        if lat_min < min_lat: min_lat = lat_min
                        if lat_max > max_lat: max_lat = lat_max
                        if lon_min < min_lon: min_lon = lon_min
                        if lon_max > max_lon: max_lon = lon_max
                        found_any = True
                    
                    if found_any:
                        # Margem de segurança (graus)
                        padding = 15.0  
                        
                        # Aplica padding e clamp
                        min_lat = max(-90.0, min_lat - padding)
                        max_lat = min(90.0, max_lat + padding)
                        min_lon = max(-180.0, min_lon - padding)
                        max_lon = min(180.0, max_lon + padding)
                        
                        # Converte geo coords para pixel coords
                        # Note que _project retorna X, Y. Y cresce para baixo.
                        # min_lat (mais sul) -> Y maior (bottom)
                        # max_lat (mais norte) -> Y menor (top)
                        # min_lon (mais oeste) -> X menor (left)
                        # max_lon (mais leste) -> X maior (right)
                        
                        left, bottom = self._project(min_lat, min_lon, w, h)
                        right, top = self._project(max_lat, max_lon, w, h)
                        
                        # Ordena coordenadas para Crop (left, top, right, bottom)
                        crop_box = (int(left), int(top), int(right), int(bottom))
                        
                        # Garante que box tenha tamanho mínimo 100x100 para não ficar pixelado demais
                        if (crop_box[2] - crop_box[0] > 50) and (crop_box[3] - crop_box[1] > 50):
                             out = out.crop(crop_box)

                
                # Converter para RGB (remover alpha) e salvar em buffer
                out = out.convert("RGB")
                buf = io.BytesIO()
                out.save(buf, format="PNG")
                return buf.getvalue()
                
        except Exception as e:
            logger.error(f"Erro ao gerar mapa: {e}")
            return b""
