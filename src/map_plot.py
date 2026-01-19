import logging
import io
import requests
from PIL import Image, ImageDraw, ImageFont
from typing import Set, Tuple, Dict
from pathlib import Path

logger = logging.getLogger(__name__)

class MapGenerator:
    MAP_URL = "https://eoimages.gsfc.nasa.gov/images/imagerecords/57000/57752/land_shallow_topo_8192.tif"
    # Font URL (Roboto Bold) - Updated to working raw URL
    FONT_URL = "https://raw.githubusercontent.com/googlefonts/roboto/main/src/hinted/Roboto-Bold.ttf"
    
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
        """Gera mapa com grids desenhados (Crop -> Upscale -> Draw)."""
        if not self.map_path.exists():
            return b""
            
        try:
            with Image.open(self.map_path) as im:
                im = im.convert("RGB") # Remove alpha from base to save memory
                w_orig, h_orig = im.size
                
                # 1. Determine Crop Bounds
                if not confirmed_grids:
                    # Fallback to full world if empty
                    min_lat, max_lat = -90.0, 90.0
                    min_lon, max_lon = -180.0, 180.0
                else:
                    min_lat, max_lat = 90.0, -90.0
                    min_lon, max_lon = 180.0, -180.0
                    
                    for grid in confirmed_grids:
                        lat_min, lon_min, lat_max, lon_max = self._grid_to_latlon(grid)
                        if lat_min == 0 and lat_max == 0: continue
                        min_lat = min(min_lat, lat_min)
                        max_lat = max(max_lat, lat_max)
                        min_lon = min(min_lon, lon_min)
                        max_lon = max(max_lon, lon_max)
                    
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

                # 2. Crop Base Map
                # _project: y = (90 - lat) * ... 
                # lat=90 -> y=0. lat=-90 -> y=h.
                # max_lat corresponds to TOP Y (smaller value)
                # min_lat corresponds to BOTTOM Y (larger value)
                
                x1, y2 = self._project(min_lat, min_lon, w_orig, h_orig) # SW corner
                x2, y1 = self._project(max_lat, max_lon, w_orig, h_orig) # NE corner
                
                # Validate
                crop_x1 = max(0, int(min(x1, x2)))
                crop_y1 = max(0, int(min(y1, y2)))
                crop_x2 = min(w_orig, int(max(x1, x2)))
                crop_y2 = min(h_orig, int(max(y1, y2)))
                
                if crop_x2 <= crop_x1 or crop_y2 <= crop_y1:
                     return b"" # Invalid crop
                     
                cropped_im = im.crop((crop_x1, crop_y1, crop_x2, crop_y2))
                
                # 3. Upscale (3x) for clean text
                SCALE = 3
                new_w = cropped_im.width * SCALE
                new_h = cropped_im.height * SCALE
                
                # Limit max resolution to 4K to prevent memory OOM/Telegram fail
                if new_w > 4096 or new_h > 4096:
                    ratio = min(4096/new_w, 4096/new_h)
                    new_w = int(new_w * ratio)
                    new_h = int(new_h * ratio)
                    SCALE = SCALE * ratio # Adjust effective scale
                
                final_im = cropped_im.resize((new_w, new_h), Image.Resampling.LANCZOS)
                
                # Helper for new projections relative to CROP
                def project_crop(lat, lon):
                    # Global project
                    gx, gy = self._project(lat, lon, w_orig, h_orig)
                    # Relative to crop
                    rx = (gx - crop_x1) * SCALE
                    ry = (gy - crop_y1) * SCALE
                    return rx, ry

                # Dynamic Font Sizing
                # Calculate actual pixels per degree of latitude in the final image
                # This tells us the height of a grid square
                if (max_lat - min_lat) > 0:
                    px_per_deg = new_h / (max_lat - min_lat)
                else:
                    px_per_deg = 20 # Fallback
                
                # We need to fit 2 lines (Grid + Call) + margins
                # Ideally font size is around 40% of grid height?
                # User asked to reduce MORE (was 2.1).
                # Trying 2.3 (approx 43% height)
                target_font_size = int(px_per_deg / 2.3)
                
                # Clamp minimum size to ensure readability even if it overlaps borders slightly
                if target_font_size < 10:
                    target_font_size = 10
                
                # Load Font
                try:
                    font = ImageFont.truetype(str(self.font_path), target_font_size)
                except:
                    font = ImageFont.load_default()

                # Stroke Logic: Don't stroke tiny fonts as it ruins legibility
                stroke_w = 0
                if target_font_size >= 12:
                    stroke_w = 2
                elif target_font_size >= 10:
                    stroke_w = 1

                # Colors
                # User requested "Different Orange" tone.
                # Switching to Dark Orange: (255, 140, 0) for a richer/deeper look
                fill_color = (255, 140, 0, 90)
                outline_color = (0, 0, 0)
                text_color = (255, 255, 255)
                
                # 4. Draw Overlays
                final_im = final_im.convert("RGBA")
                overlay_layer = Image.new("RGBA", final_im.size, (255,255,255,0))
                draw_ov = ImageDraw.Draw(overlay_layer)

                for grid in confirmed_grids:
                    lat_min, lon_min, lat_max, lon_max = self._grid_to_latlon(grid)
                    if lat_min == 0 and lat_max == 0: continue
                    
                    # Check if inside view
                    if lat_max < min_lat or lat_min > max_lat or lon_max < min_lon or lon_min > max_lon:
                        continue

                    px1, py_bottom = project_crop(lat_min, lon_min)
                    px2, py_top = project_crop(lat_max, lon_max)
                    
                    # Draw Grid Box
                    # Ensure minimal width/height
                    w_rect = max(1, px2-px1)
                    h_rect = max(1, py_bottom-py_top)
                    draw_ov.rectangle([px1, py_top, px2, py_bottom], fill=fill_color, outline=outline_color, width=max(1, int(2*SCALE)))
                    
                    # Draw Text
                    if grid_labels and grid in grid_labels:
                         cx = (px1 + px2) / 2
                         cy = (py_top + py_bottom) / 2
                         label_call = grid_labels[grid]
                         
                         # Offset based on font size (approx 1/2 line height)
                         off = target_font_size * 0.6
                         
                         if stroke_w > 0:
                             draw_ov.text((cx, cy - off), grid, font=font, fill=text_color, anchor="mm", stroke_width=stroke_w, stroke_fill="black")
                             draw_ov.text((cx, cy + off), label_call, font=font, fill=text_color, anchor="mm", stroke_width=stroke_w, stroke_fill="black")
                         else:
                             # No stroke, maybe shadow? Or just text.
                             # For tiny text, black shadow manually? No, simple is better.
                             # Trying a simple drop shadow for contrast
                             draw_ov.text((cx+1, cy - off + 1), grid, font=font, fill="black", anchor="mm")
                             draw_ov.text((cx, cy - off), grid, font=font, fill=text_color, anchor="mm")
                             
                             draw_ov.text((cx+1, cy + off + 1), label_call, font=font, fill="black", anchor="mm")
                             draw_ov.text((cx, cy + off), label_call, font=font, fill=text_color, anchor="mm")
                
                final_im = Image.alpha_composite(final_im, overlay_layer)
                final_im = final_im.convert("RGB")
                
                buf = io.BytesIO()
                final_im.save(buf, format="PNG")
                return buf.getvalue()

        except Exception as e:
            logger.error(f"Erro ao gerar mapa: {e}")
            return b""
