"""Crop SunsetBot's regional raster map around a chosen coordinate."""
import io

from PIL import Image, ImageDraw

# Calibrated from the labelled axes of SunsetBot's 1344 x 1400 中东 raster.
# This is only a visual crop. It does not increase the model's spatial resolution.
EAST_CHINA = {'lon_min': 100.0, 'lon_max': 124.0, 'lat_min': 17.0,
              'lat_max': 42.0, 'x0': 156, 'x1': 1188, 'y0': 126, 'y1': 1202,
              'width': 1344, 'height': 1400}


def geographic_pixel(latitude, longitude, width, height):
    bounds = EAST_CHINA
    x = (bounds['x0'] + (longitude - bounds['lon_min']) /
         (bounds['lon_max'] - bounds['lon_min']) * (bounds['x1'] - bounds['x0'])) * width / bounds['width']
    y = (bounds['y1'] - (latitude - bounds['lat_min']) /
         (bounds['lat_max'] - bounds['lat_min']) * (bounds['y1'] - bounds['y0'])) * height / bounds['height']
    return x, y


def crop_map(data, latitude, longitude, span_lon=8.0, span_lat=6.0):
    """Return PNG bytes, or None if the point falls outside the official map."""
    image = Image.open(io.BytesIO(data)).convert('RGB')
    width, height = image.size
    geometry = crop_geometry(latitude, longitude, width, height, span_lon, span_lat)
    if geometry is None:
        return None
    left, top, right, bottom, cx, cy = geometry
    view = image.crop((left, top, right, bottom))
    draw = ImageDraw.Draw(view)
    mx, my = cx - left, cy - top
    r = max(4, round(min(view.size) * .012))
    draw.ellipse((mx-r-3, my-r-3, mx+r+3, my+r+3), fill='#ffffff')
    draw.ellipse((mx-r, my-r, mx+r, my+r), fill='#e95464', outline='#782839', width=2)
    output = io.BytesIO()
    view.save(output, format='PNG')
    return output.getvalue()


def crop_geometry(latitude, longitude, width, height, span_lon=8.0, span_lat=6.0):
    """Pixel rectangle and marker position for the calibrated official raster."""
    b = EAST_CHINA
    if not (b['lat_min'] <= latitude <= b['lat_max'] and b['lon_min'] <= longitude <= b['lon_max']):
        return None
    cx, cy = geographic_pixel(latitude, longitude, width, height)
    px0, py0 = geographic_pixel(latitude + span_lat / 2, longitude - span_lon / 2, width, height)
    px1, py1 = geographic_pixel(latitude - span_lat / 2, longitude + span_lon / 2, width, height)
    crop_width, crop_height = int(px1 - px0), int(py1 - py0)
    left = max(int(b['x0'] * width / b['width']), min(int(cx - crop_width / 2),
               int(b['x1'] * width / b['width']) - crop_width))
    top = max(int(b['y0'] * height / b['height']), min(int(cy - crop_height / 2),
              int(b['y1'] * height / b['height']) - crop_height))
    right = min(width, left + crop_width)
    bottom = min(height, top + crop_height)
    return (left, top, right, bottom, cx, cy) if right > left and bottom > top else None
