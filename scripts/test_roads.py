"""Teste rápido do snap de pontos à malha rodoviária."""
# pylint: disable=import-error  # backend resolvido via sys.path.insert abaixo
import sys
sys.path.insert(0, ".")
from backend.services.geo import nearest_road  # noqa: E402

PATH = "data/malha_rodoviaria.geojson"

TESTES = [
    ("SP-330 Anhanguera perto Campinas", -22.8956, -47.0678),
    ("SP-348 Bandeirantes", -23.10,  -47.00),
    ("Campo aberto interior SP",        -22.50,  -47.80),
    ("Regiao Grande SP sul",            -23.65,  -46.75),
]

for label, lat, lon in TESTES:
    dist, feat = nearest_road(lat, lon, PATH, max_m=5000)
    if feat:
        p = feat.get("properties", {})
        hw = p.get("highway", "-")
        rod = p.get("rodovia", "-")
        print(f"{label:<40s}  dist={dist:6.0f}m  highway={hw:<12s}  rodovia={rod}")
    else:
        print(f"{label:<40s}  NENHUMA VIA (dist={dist})")
