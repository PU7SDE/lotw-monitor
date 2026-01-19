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
    # Font URL (Not used if system font found)
    FONT_URL = None
    
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.map_path = cache_dir / "world_map_v2.tif" 
        # Try specific Mac system font first
        sys_font = Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf")
        if sys_font.exists():
            self.font_path = sys_font
        else:
            self.font_path = cache_dir / "Arial-Bold.ttf"
            
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

        # 2. Font (Download if not system and not cached)
        if not self.font_path.exists() and self.FONT_URL:
             try:
                logger.info("Baixando fonte...")
                r = requests.get(self.FONT_URL, timeout=30)
                r.raise_for_status()
                with open(self.font_path, 'wb') as f:
                    f.write(r.content)
                logger.info("Fonte salva.")
             except Exception as e:
                logger.error(f"Erro ao baixar fonte: {e}")

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
                try:
                    # Tamanho fixo relativo a resolução 8k?
                    # 1 grau = ~22px. Grid height = 10 deg (field) ou 1 deg (square)?
                    # GridSquare (4 chars) é 1 grau latitude x 2 graus longitude.
                    # Altura = ~22px. Largura = ~45px.
                    # Fonte precisa ser PEQUENA ou o mapa expandido.
                    # Se usarmos 10px, cabe mal.
                    # Mas o usuário dá zoom.
                    # Vamos tentar 24px (fica maior que o quadrado 'físico', mas no zoom ok? Não, vai sobrepor)
                    # Ah, espere.
                    # 8192px / 360 = 22.75 px por grau.
                    # O grid 4 chars tem 1 grau de altura.
                    # Então cada quadrado tem ~23px de altura.
                    # Impossível escrever texto legível (GRID + CALL) em 23px de altura.
                    # SOLUÇÃO: Upscale da região recortada ou desenhar no full map com fonte minúscula?
                    # Se desenharmos no full map 8k em 23px, vai ficar ilegível se não der zoom absurdo, mas a imagem final é cropada?
                    # Se cropamos, mantemos a resolução original.
                    # Se fizermos crop de 20x20 graus -> 450x450px.
                    # 20 grids de altura.
                    # O "Gridmaster" map geralmente é alta definição.
                    # Talvez o usuário queira ver APENAS os grids novos ou região?
                    
                    # Vamos TENTAR fazer o texto caber.
                    # Fonte tamanho 8.
                    # Ou desenhar overflow?
                    
                    font = ImageFont.truetype(str(self.font_path), 8)
                except:
                    font = ImageFont.load_default()

                # 2. Desenha todos os grids
                overlay = Image.new("RGBA", im.size, (255, 255, 255, 0))
                draw = ImageDraw.Draw(overlay)
                
                # Cor: Verde claro semitransparente para preenchimento
                # Borda: Preta fina (Gridmaster style)
                fill_color = (0, 255, 0, 80) # Mais transparente para ver relevo? Ou sólido? Gridmaster é "amarelo" geralmente. Vamos de verde monitor padrão.
                outline_color = (0, 0, 0, 255)
                text_color = (0, 0, 0, 255)
                
                for grid in confirmed_grids:
                    lat_min, lon_min, lat_max, lon_max = self._grid_to_latlon(grid)
                    if lat_min == 0 and lat_max == 0: continue
                    
                    x1, y_bottom = self._project(lat_min, lon_min, w, h)
                    x2, y_top = self._project(lat_max, lon_max, w, h)
                    
                    # Gridmaster style: BORDER
                    # Draw rectangle
                    draw.rectangle([x1, y_top, x2, y_bottom], fill=fill_color, outline=outline_color, width=1)
                    
                    # TEXT
                    if grid_labels and grid in grid_labels:
                        label_grid = grid
                        label_call = grid_labels[grid]
                        
                        # Calculate text positions (centered)
                        # We have height = y_bottom - y_top (~22px)
                        # We can put Grid top, Call bottom.
                        
                        # grid text
                        # draw.textbbox is better but lets guess centered
                        cx = (x1 + x2) / 2
                        cy = (y_top + y_bottom) / 2
                        
                        # Draw Grid (Upper half) - Offset -6px
                        draw.text((cx, cy - 6), label_grid, font=font, fill=text_color, anchor="mm")
                        # Draw Call (Lower half) - Offset +6px
                        draw.text((cx, cy + 6), label_call, font=font, fill=text_color, anchor="mm")

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
