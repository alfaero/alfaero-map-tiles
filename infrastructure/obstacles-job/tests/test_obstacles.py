"""Testes do pipeline de obstáculos (spec 006; ACs da spec 389 do alfaero-mobile).

Rodar (dentro de infrastructure/obstacles-job): python -m unittest discover -s tests
"""
import unittest

from obstacles import aneel, aob, osm, tiling
from obstacles.model import (ANEEL_ID_BASE, Base, Line, Obstacle, aneel_status, drop_low_measured,
                             estimated_height_m, merge_aneel, parse_height_m, parse_voltage_kv)


class FormatTest(unittest.TestCase):
    def test_ida_e_volta(self):
        t = aob.Tile(20261018, 10, 408, 520, [
            aob.Point(ANEEL_ID_BASE + 7, -5.1234567, -35.7654321, 167.5, aob.WIND_TURBINE, True, False, 45.0),
            aob.Point(11, -5.2, -35.8, 50, aob.TRANSMISSION_TOWER, False, True, None),
            aob.Point(12, -5.21, -35.81, 50, aob.TRANSMISSION_TOWER, False, False, None),
        ], [aob.Span(1, 2, 500, 0)])
        b = aob.encode(t)
        self.assertEqual(len(b), 32 + 3 * 24 + 12)
        self.assertEqual(aob.decode(b), t)

    def test_vao_invalido(self):
        t = aob.Tile(1, 10, 0, 0, [aob.Point(1, 0, 0, 30, 0, False)], [aob.Span(0, 0)])
        with self.assertRaises(ValueError):
            aob.decode(aob.encode(t))


class HeightTest(unittest.TestCase):
    def test_espelho_do_app(self):
        # Mesmos limiares de obstacle_tile_test.dart (AC2).
        for kv, h in [(750, 50), (500, 50), (499, 40), (345, 40), (344, 35), (230, 35),
                      (229, 28), (138, 28), (137, 22), (0, 22)]:
            self.assertEqual(estimated_height_m(aob.TRANSMISSION_TOWER, kv), h, kv)
        self.assertEqual(estimated_height_m(aob.WIND_TURBINE), 150)
        self.assertEqual(estimated_height_m(aob.TELECOM_TOWER), 45)
        self.assertEqual(estimated_height_m(aob.MAST), 30)
        self.assertEqual(estimated_height_m(aob.CHIMNEY), 40)
        self.assertEqual(estimated_height_m(aob.GENERIC), 30)

    def test_tags(self):
        self.assertEqual(parse_height_m("45"), 45)
        self.assertEqual(parse_height_m("45 m"), 45)
        self.assertEqual(parse_height_m("45,5"), 45.5)
        self.assertAlmostEqual(parse_height_m("100 ft"), 30.48)
        self.assertIsNone(parse_height_m("alta"))
        self.assertIsNone(parse_height_m(None))
        self.assertEqual(parse_voltage_kv("500000;230000"), 500)
        self.assertEqual(parse_voltage_kv("138000"), 138)
        self.assertEqual(parse_voltage_kv("medium"), 0)


class AneelMergeTest(unittest.TestCase):
    def test_status(self):
        # AC2a, com os valores reais do SIGEL em 18/10 (inclusive acentos).
        for raw in ["Sim", "Operação", "1", "Construção"]:
            self.assertEqual(aneel_status(raw), "built", raw)
        for raw in ["Não", None, ""]:
            self.assertEqual(aneel_status(raw), "unconfirmed", raw)
        self.assertEqual(aneel_status("Construção não iniciada"), "skip")

    def _base_with_osm_turbine(self):
        b = Base()
        b.obstacles[900] = Obstacle(900, -5.0, -35.0, aob.WIND_TURBINE)
        return b

    def test_construido_entra_e_substitui_o_do_osm(self):
        b = self._base_with_osm_turbine()
        stats = merge_aneel(b, [{"id": 1, "lat": -5.0003, "lon": -35.0, "height_m": 160, "status": "Sim"}])
        self.assertNotIn(900, b.obstacles)  # 33 m: o mesmo aerogerador
        self.assertEqual(b.obstacles[ANEEL_ID_BASE + 1].height_m, 160)
        self.assertEqual(stats["built"], 1)

    def test_nao_confirmado_so_com_par_no_osm(self):
        b = self._base_with_osm_turbine()
        merge_aneel(b, [
            {"id": 2, "lat": -5.0, "lon": -35.0004, "height_m": 150, "status": "Não"},  # 44 m do OSM
            {"id": 3, "lat": -5.1, "lon": -35.1, "height_m": 150, "status": "Não"},  # sozinho
            {"id": 4, "lat": -5.2, "lon": -35.2, "height_m": 150, "status": None},  # sozinho
        ])
        self.assertIn(ANEEL_ID_BASE + 2, b.obstacles)
        self.assertNotIn(ANEEL_ID_BASE + 3, b.obstacles)
        self.assertNotIn(ANEEL_ID_BASE + 4, b.obstacles)

    def test_par_alem_do_raio_nao_confirma(self):
        b = self._base_with_osm_turbine()
        merge_aneel(b, [{"id": 5, "lat": -5.0, "lon": -35.0008, "height_m": 150, "status": "Não"}])  # 89 m
        self.assertNotIn(ANEEL_ID_BASE + 5, b.obstacles)
        self.assertIn(900, b.obstacles)

    def test_nao_iniciado_e_baixo_ficam_fora(self):
        b = Base()
        stats = merge_aneel(b, [
            {"id": 6, "lat": 0, "lon": 0, "height_m": 150, "status": "Construção não iniciada"},
            {"id": 7, "lat": 0, "lon": 0, "height_m": 10, "status": "Sim"},
        ])
        self.assertEqual(b.obstacles, {})
        self.assertEqual((stats["skip"], stats["low"]), (1, 1))


class OsmTest(unittest.TestCase):
    def test_linha_vira_torres_com_tensao_maior(self):
        nodes = {i: osm.OsmNode(i, -22.0 - i * 0.001, -44.0, {}) for i in range(1, 5)}
        nodes[2].tags = {"power": "tower", "height": "61"}
        nodes[9] = osm.OsmNode(9, -22.5, -44.5, {"man_made": "mast"})
        ways = [
            osm.OsmWay(100, [1, 2, 2, 3], {"power": "line", "voltage": "138000"}),
            osm.OsmWay(101, [3, 4], {"power": "line", "voltage": "500000;138000"}),
            osm.OsmWay(102, [50, 51, 52, 50], {"man_made": "chimney", "height": "80"}, (-22.7, -44.7)),
        ]
        b = osm.base_from_elements(nodes, ways)
        self.assertEqual(b.lines[0].nodes, [1, 2, 3])  # nó repetido seguido sai
        self.assertEqual(b.obstacles[3].voltage_kv, 500)
        self.assertEqual(b.obstacles[1].voltage_kv, 138)
        self.assertEqual(b.obstacles[2].height_m, 61)
        self.assertEqual(b.obstacles[1].type, aob.TRANSMISSION_TOWER)
        self.assertEqual(b.obstacles[9].type, aob.MAST)
        chimney = [o for o in b.obstacles.values() if o.type == aob.CHIMNEY][0]
        self.assertEqual((chimney.lat, chimney.height_m), (-22.7, 80))

    def test_tipos(self):
        self.assertEqual(osm.osm_point_type({"man_made": "tower", "tower:type": "communication"}),
                         aob.TELECOM_TOWER)
        self.assertEqual(osm.osm_point_type({"man_made": "tower"}), aob.GENERIC)
        self.assertEqual(osm.osm_point_type({"power": "generator", "generator:source": "wind"}),
                         aob.WIND_TURBINE)
        self.assertIsNone(osm.osm_point_type({"power": "pole"}))


class TilingTest(unittest.TestCase):
    def _two_tile_line(self):
        b = Base()
        # Fronteira de tile z10 em lon -44.6484375 (x = 385/386).
        b.obstacles[1] = Obstacle(1, -22.4, -44.66, aob.TRANSMISSION_TOWER, voltage_kv=500)
        b.obstacles[2] = Obstacle(2, -22.4, -44.64, aob.TRANSMISSION_TOWER, voltage_kv=500)
        b.lines = [Line(10, [1, 2], 500), Line(11, [2, 1], 230)]  # mesmo vão em duas linhas
        return b

    def test_vao_na_fronteira_vai_aos_dois_tiles_com_ponta_de_fora(self):
        tiles = tiling.build_tiles(self._two_tile_line(), 20261018)
        self.assertEqual(len(tiles), 2)
        for t in tiles.values():
            self.assertEqual(len(t.spans), 1)  # AC3: dedupe do vão repetido
            self.assertEqual(t.spans[0].voltage_kv, 500)
            self.assertEqual(len(t.points), 2)
            owners = [p for p in t.points if not p.outside_tile]
            self.assertEqual(len(owners), 1)
            self.assertEqual(tiling.tile_of(owners[0].lat, owners[0].lon), (t.x, t.y))
            aob.decode(aob.encode(t))  # decodifica sem vão quebrado

    def test_altura_estimada_vai_marcada(self):
        t = next(iter(tiling.build_tiles(self._two_tile_line(), 1).values()))
        self.assertTrue(all(p.height_m == 50 and not p.measured for p in t.points))

    def test_baixo_medido_sai_menos_vertice_de_linha(self):
        b = self._two_tile_line()
        b.obstacles[1].height_m = 10
        b.obstacles[3] = Obstacle(3, -22.0, -44.0, aob.MAST, height_m=12)
        self.assertEqual(drop_low_measured(b), 1)
        self.assertIn(1, b.obstacles)
        self.assertNotIn(3, b.obstacles)

    def test_tile_igual_ao_app(self):
        # Mesmos valores de terrain_elevation_sampler_test.dart do app (Agulhas Negras).
        self.assertEqual(tiling.tile_of(-22.3833, -44.6667, 11), (769, 1154))
        self.assertEqual(tiling.tile_of(-22.3833, -44.6667, 10), (384, 577))
        self.assertEqual(tiling.tile_of(-22.3833, -44.6667, 9), (192, 288))


class _Resp:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body


class _FakeSession:
    """Serve a camada com `total` registros em páginas de `page`."""

    def __init__(self, total, page=2, fail_first=0, lie_count=None):
        self.total, self.page, self.fail_first = total, page, fail_first
        self.lie_count = lie_count
        self.calls = 0

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        if self.fail_first:
            self.fail_first -= 1
            return _Resp(503, {})
        if not url.endswith("/query"):
            return _Resp(200, {"maxRecordCount": self.page})
        if params.get("returnCountOnly"):
            return _Resp(200, {"count": self.lie_count if self.lie_count is not None else self.total})
        off = params["resultOffset"]
        n = min(self.page, max(0, self.total - off))
        feats = [{"attributes": {"OBJECTID": off + i + 1, "ALT_TOTAL": 150.0, "OPERACAO": "Sim",
                                 "NOME_EOL": "X", "DIRECAO_PREDO": 90},
                  "geometry": {"x": -35.0, "y": -5.0}} for i in range(n)]
        return _Resp(200, {"features": feats})


class AneelFetchTest(unittest.TestCase):
    def test_pagina_ate_o_fim_e_usa_o_maximo_do_servico(self):
        s = _FakeSession(total=5, page=2)
        out = aneel.fetch_turbines(s, sleep=lambda _: None)
        self.assertEqual([t["id"] for t in out], [1, 2, 3, 4, 5])
        self.assertEqual(out[0]["heading_deg"], 90.0)

    def test_retry_em_5xx_recupera(self):
        s = _FakeSession(total=3, page=2, fail_first=2)
        self.assertEqual(len(aneel.fetch_turbines(s, sleep=lambda _: None)), 3)

    def test_contagem_divergente_falha(self):
        s = _FakeSession(total=3, page=2, lie_count=4)
        with self.assertRaises(aneel.AneelError):
            aneel.fetch_turbines(s, sleep=lambda _: None)

    def test_teto_de_paginas(self):
        s = _FakeSession(total=10, page=2)
        with self.assertRaises(aneel.AneelError):
            aneel.fetch_turbines(s, sleep=lambda _: None, max_pages=2)


if __name__ == "__main__":
    unittest.main()
