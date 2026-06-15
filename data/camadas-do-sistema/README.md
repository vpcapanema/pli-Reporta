# Camadas do sistema

Projeção GeoJSON materializada a partir de `reports`.

- `pontos/` — um arquivo por camada; geometria `Point`; **servido nos mapas**.
- `poligonos/` — mesmo `id` e atributos; geometria de área de impacto.

Documentação: [docs/ARQUITETURA_CAMADAS.md](../docs/ARQUITETURA_CAMADAS.md) · [docs/CAMPOS_CAMADAS.md](../docs/CAMPOS_CAMADAS.md)

Regenerar arquivos vazios (não sobrescreve features existentes se já houver dados — use com cuidado):

```bash
python scripts/bootstrap_camadas.py
```
