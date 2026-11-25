"""Convert the pinned geoBoundaries BGD ADM2 simplified GeoJSON into an offline district map."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps' / 'api'))
from app.district_prices_catalog import DISTRICT_OPTIONS, canonical_district

ALIASES = {'Brahamanbaria': 'Brahmanbaria', 'Khagrachhari': 'Khagrachari',
           'Maulvibazar': 'Moulvibazar', 'Nawabganj': 'Chapai Nawabganj'}


def main():
    source = json.loads(Path(sys.argv[1]).read_bytes())
    paths = {}
    for feature in source['features']:
        name = feature['properties']['shapeName']
        district = ALIASES.get(name) or canonical_district(name)
        geometry = feature['geometry']
        polygons = [geometry['coordinates']] if geometry['type'] == 'Polygon' else geometry['coordinates']
        rings = []
        for polygon in polygons:
            for ring in polygon:
                points = []
                for lon, lat in ring:
                    point = (round((lon - 87.9) * 69), round((26.75 - lat) * 76))
                    if not points or points[-1] != point:
                        points.append(point)
                if len(set(points)) >= 3:
                    rings.append('M' + ' '.join(f'{x},{y}' for x, y in points) + 'Z')
        paths[district] = ''.join(rings)
    if set(paths) != {row['id'] for row in DISTRICT_OPTIONS} or not all(paths.values()):
        raise ValueError('Expected nonempty geometry for 64 recognized Bangladesh districts')
    target = ROOT / 'apps' / 'web' / 'public' / 'bangladesh-district-paths.json'
    target.write_text(json.dumps(paths, sort_keys=True, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
