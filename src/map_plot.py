import logging
import io
import requests
from PIL import Image, ImageDraw, ImageFont
from typing import Set, Tuple, Dict
from pathlib import Path

logger = logging.getLogger(__name__)

class MapGenerator:
    # Mapa Equiretangular (Plate Carrée) - Blue Marble Next Generation (NASA 8K)
    # Mapa Equiretangular (Plate Carrée) - Blue Marble Next Generation (NASA 8K)
    MAP_URL = "https://eoimages.gsfc.nasa.gov/images/imagerecords/57000/57752/land_shallow_topo_8192.tif"
    # Font URL (Roboto Bold)
    FONT_URL = "https://github.com/google/fonts/raw/main/ofl/roboto/Roboto-Bold.ttf"
    
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.map_path = cache_dir / "world_map_v2.tif" 
        self.font_path = cache_dir / "Roboto-Bold.ttf" # Force local cache for consistency
            
        self._ensure_resources()
        
    def _ensure_resources(self):
        # 1. Map
        if not self.map_path.exists():
            try:
                logger.info("Baixando mapa base NASA 8K (v2)...")
                headers = {"User-Agent": "Mozilla/5.0 (compatible; LoTWMonitor/1.0)"}
                r = requests.get(self.MAP_URL, stream=True, timeout=120, headers=headers)
                r.raise_for_status()
                with open(self.map_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=16384):
                        f.write(chunk)
                logger.info("Mapa base salvo.")
            except Exception as e:
                logger.error(f"Erro ao baixar mapa: {e}")

        # 2. Font (Download if not cached)
        if not self.font_path.exists() and self.FONT_URL:
             try:
                logger.info("Baixando fonte da web...")
                r = requests.get(self.FONT_URL, timeout=30)
                r.raise_for_status()
                with open(self.font_path, 'wb') as f:
                    f.write(r.content)
                logger.info("Fonte salva.")
             except Exception as e:
                logger.error(f"Erro ao baixar fonte: {e}")

    # ... methods ...

    def generate(self, confirmed_grids: Set[str], worked_grids: Set[str], grid_labels: Dict[str, str] = None) -> bytes:
        # ... logic ...
                # Fonte
                # Tamanho: Grid height ~23px. Fonte 10px * 2 linhas = 20px. 
                # Margem 3px. Fica apertado mas cabe.
                
                try:
                    font = ImageFont.truetype(str(self.font_path), 10)
                except:
                    font = ImageFont.load_default()

                # 2. Desenha todos os grids
                overlay = Image.new("RGBA", im.size, (255, 255, 255, 0))
                draw = ImageDraw.Draw(overlay)
                
                # Cores
                fill_color = (34, 197, 94, 60) # Verde do HTML, semitransparente
                outline_color = (0, 0, 0, 255) # Borda preta
                text_color = (255, 255, 255, 255) 
                
                for grid in confirmed_grids:
                    lat_min, lon_min, lat_max, lon_max = self._grid_to_latlon(grid)
                    if lat_min == 0 and lat_max == 0: continue
                    
                    x1, y_bottom = self._project(lat_min, lon_min, w, h)
                    x2, y_top = self._project(lat_max, lon_max, w, h)
                    
                    # Draw rectangle
                    draw.rectangle([x1, y_top, x2, y_bottom], fill=fill_color, outline=outline_color, width=2)
                    
                    # TEXT
                    if grid_labels and grid in grid_labels:
                        label_grid = grid
                        label_call = grid_labels[grid]
                        
                        cx = (x1 + x2) / 2
                        cy = (y_top + y_bottom) / 2
                        
                        # Offsets for 10px font (Tight fit)
                        # Grid up 5px, Call down 5px
                        draw.text((cx, cy - 5), label_grid, font=font, fill=text_color, anchor="mm", stroke_width=2, stroke_fill="black")
                        draw.text((cx, cy + 5), label_call, font=font, fill=text_color, anchor="mm", stroke_width=2, stroke_fill="black")

    def _grid_to_latlon(self, grid: str) -> Tuple[float, float, float, float]:
        """Converte Grid 4 chars para Lat/Lon."""
        grid = grid.upper().strip()
        if len(grid) < 4: return (0,0,0,0)
        
        f1, f2 = ord(grid[0]) - ord('A'), ord(grid[1]) - ord('A')
        s1, s2 = int(grid[2]), int(grid[3])

        lon_min = -180.0 + (f1 * 20.0) + (s1 * 2.0)
        lat_min = -90.0 + (f2 * 10.0) + (s2 * 1.0)
        return (lat_min, lon_min, lat_min + 1.0, lon_min + 2.0)

    def _project(self, lat: float, lon: float, w: int, h: int) -> Tuple[float, float]:
        """Projeta Lat/Lon para X/Y na imagem full."""
        x = (lon + 180.0) * (w / 360.0)
        y = (90.0 - lat) * (h / 180.0)
        return x, y

    def generate(self, confirmed_grids: Set[str], worked_grids: Set[str], grid_labels: Dict[str, str] = None) -> bytes:
        """Gera mapa com grids desenhados e auto-crop. 
           grid_labels: dict {GRID: CALL} para exibição.
        """
        if not self.map_path.exists():
            return b""
            
        try:
            # 1. Carrega Full na memória (8K é seguro, ~150MB RAM)
            with Image.open(self.map_path) as im:
                im = im.convert("RGBA")
                w, h = im.size
                
                # Fonte
                # Fonte
                # Tamanho fixo relativo a resolução 8k?
                # 8192px / 180 deg = ~45.5 px por grau de latitude.
                # Grid 4 chars = 1 deg altura.
                # Temos ~45px de altura vertical disponivel.
                # Texto tamanho 10 fica ~10-12px altura real. 2 linhas = 24px.
                # Com margem, 12px é um bom tamanho seguro. 
                # Se usarmos sistema Arial Bold, ele renderiza bem.
                
                try:
                    font = ImageFont.truetype(str(self.font_path), 12)
                except:
                    font = ImageFont.load_default()

                # 2. Desenha todos os grids
                overlay = Image.new("RGBA", im.size, (255, 255, 255, 0))
                draw = ImageDraw.Draw(overlay)
                
                # Cor: Verde "Matrix" para alto contraste no mapa escuro, ou Azul Dash?
                # O HTML usa Azul (#2563eb). No mapa escuro (oceano), azul some.
                # Vamos manter o "Gridmaster" request original: Amarelo? Ou Verde?
                # Vamos de Amarelo Ouro (Gold) para destaque total?
                # Ou Cyan? Cyan (#06b6d4) funciona bem em fundo escuro.
                # Vamos usar CYAN para modernizar (match HTML secondary colors?)
                # HTML usa accent #22c55e (verde).
                # Vamos de Verde Neon para contraste máximo.
                fill_color = (34, 197, 94, 60) # Verde do HTML, semitransparente
                outline_color = (0, 0, 0, 255) # Borda preta
                text_color = (255, 255, 255, 255) # Texto BRANCO com sombra (outline manual) para leitura no mapa
                
                for grid in confirmed_grids:
                    lat_min, lon_min, lat_max, lon_max = self._grid_to_latlon(grid)
                    if lat_min == 0 and lat_max == 0: continue
                    
                    x1, y_bottom = self._project(lat_min, lon_min, w, h)
                    x2, y_top = self._project(lat_max, lon_max, w, h)
                    
                    # Draw rectangle
                    draw.rectangle([x1, y_top, x2, y_bottom], fill=fill_color, outline=outline_color, width=2)
                    
                    # TEXT with Stroke for readability
                    if grid_labels and grid in grid_labels:
                        label_grid = grid
                        label_call = grid_labels[grid]
                        
                        cx = (x1 + x2) / 2
                        cy = (y_top + y_bottom) / 2
                        
                        # Offsets for 12px font
                        # Grid up 8px, Call down 8px
                        draw.text((cx, cy - 8), label_grid, font=font, fill=text_color, anchor="mm", stroke_width=2, stroke_fill="black")
                        draw.text((cx, cy + 8), label_call, font=font, fill=text_color, anchor="mm", stroke_width=2, stroke_fill="black")

                out = Image.alpha_composite(im, overlay)
                out = out.convert("RGB")
                
                # 3. Auto Crop
                if confirmed_grids:
                    min_lat, max_lat = 90.0, -90.0
                    min_lon, max_lon = 180.0, -180.0
                    found_any = False
                    
                    for grid in confirmed_grids:
                        lat_min, lon_min, lat_max, lon_max = self._grid_to_latlon(grid)
                        if lat_min == 0 and lat_max == 0: continue
                        
                        min_lat = min(min_lat, lat_min)
                        max_lat = max(max_lat, lat_max)
                        min_lon = min(min_lon, lon_min)
                        max_lon = max(max_lon, lon_max)
                        found_any = True
                    
                    if found_any:
                        # Padding 3 graus
                        padding = 3.0
                        min_lat = max(-90.0, min_lat - padding)
                        max_lat = min(90.0, max_lat + padding)
                        min_lon = max(-180.0, min_lon - padding)
                        max_lon = min(180.0, max_lon + padding)
                        
                        # Minimum Zoom (20x20 deg)
                        if (max_lat - min_lat) < 20.0:
                            mid = (min_lat + max_lat) / 2
                            min_lat = max(-90.0, mid - 10.0)
                            max_lat = min(90.0, mid + 10.0)
                        if (max_lon - min_lon) < 20.0:
                            mid = (min_lon + max_lon) / 2
                            min_lon = max(-180.0, mid - 10.0)
                            max_lon = min(180.0, mid + 10.0)

                        left, bottom = self._project(min_lat, min_lon, w, h)
                        right, top = self._project(max_lat, max_lon, w, h)
                        
                        # Validate Box
                        left, top = max(0, int(left)), max(0, int(top))
                        right, bottom = min(w, int(right)), min(h, int(bottom))
                        
                        if right > left and bottom > top:
                             # CROP
                             cropped = out.crop((left, top, right, bottom))
                             
                             # UPSCALE PARA LEITURA?
                             # Se a imagem for muito pequena (ex: 20x20 graus = ~450px),
                             # o texto tamanho 8 ficará legivel se o usuario nao der zoom?
                             # O telegram manda como imagem comprimida.
                             # Se fizermos upscale tipo 2x ou 3x usando Nearest ou Bilinear, o texto ja desenhado vai blurar.
                             # Melhor seria desenhar EM ALTA RESOLUCAO.
                             # Mas mudar o pipeline agora é arriscado.
                             # Vamos manter nativo e ver como fica no debug.
                             
                             out = cropped

                # 4. Resize final (Limit to 4K to avoid telegram errors)
                if out.width > 3840 or out.height > 3840:
                    out.thumbnail((3840, 3840), Image.Resampling.LANCZOS)
                
                buf = io.BytesIO()
                out.save(buf, format="PNG")
                return buf.getvalue()

        except Exception as e:
            logger.error(f"Erro ao gerar mapa: {e}")
            return b""
