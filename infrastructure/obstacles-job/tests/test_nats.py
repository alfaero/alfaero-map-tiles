"""Obstáculos oficiais do Reino Unido (NATS), spec 003 do alfaero-navdata-pipeline, onda C.

Rodar (dentro de infrastructure/obstacles-job): python -m unittest discover -s tests
"""
import datetime as dt
import hashlib
import io
import unittest
import zipfile

from obstacles import aob, nats
from obstacles.model import NATS_ID_BASE, Base, Line, Obstacle, merge_nats

NATS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<message:AIXMBasicMessage xmlns:aixm="http://www.aixm.aero/schema/5.1" xmlns:gml="http://www.opengis.net/gml/3.2"
  xmlns:message="http://www.aixm.aero/schema/5.1/message">
 <message:hasMember><aixm:VerticalStructure gml:id="a"><aixm:timeSlice><aixm:VerticalStructureTimeSlice gml:id="b">
  <aixm:name>UK0229G149F</aixm:name><aixm:type>TRANSMISSION_LINE</aixm:type><aixm:lighted>NO</aixm:lighted>
  <aixm:part><aixm:VerticalStructurePart gml:id="c"><aixm:verticalExtent uom="FT">351</aixm:verticalExtent>
   <aixm:horizontalProjection_location><aixm:ElevatedPoint gml:id="d"><gml:pos srsName="urn:ogc:def:crs:EPSG::4326">51.0665889 -3.6193167</gml:pos>
   <aixm:elevation uom="FT">977</aixm:elevation></aixm:ElevatedPoint></aixm:horizontalProjection_location></aixm:VerticalStructurePart></aixm:part>
 </aixm:VerticalStructureTimeSlice></aixm:timeSlice></aixm:VerticalStructure></message:hasMember>
 <message:hasMember><aixm:VerticalStructure gml:id="e"><aixm:timeSlice><aixm:VerticalStructureTimeSlice gml:id="f">
  <aixm:name>UK0001W001A</aixm:name><aixm:type>WINDMILL</aixm:type><aixm:lighted>YES</aixm:lighted>
  <aixm:part><aixm:VerticalStructurePart gml:id="g"><aixm:verticalExtent uom="FT">492</aixm:verticalExtent>
   <aixm:horizontalProjection_location><aixm:ElevatedPoint gml:id="h"><gml:pos>55.5 -3.0</gml:pos></aixm:ElevatedPoint></aixm:horizontalProjection_location></aixm:VerticalStructurePart></aixm:part>
 </aixm:VerticalStructureTimeSlice></aixm:timeSlice></aixm:VerticalStructure></message:hasMember>
 <message:hasMember><aixm:VerticalStructure gml:id="i"><aixm:timeSlice><aixm:VerticalStructureTimeSlice gml:id="j">
  <aixm:name>UK0002C002B</aixm:name><aixm:type>CRANE</aixm:type>
  <aixm:part><aixm:VerticalStructurePart gml:id="k"><aixm:verticalExtent uom="M">120</aixm:verticalExtent>
   <aixm:horizontalProjection_location><aixm:ElevatedPoint gml:id="l"><gml:pos>51.5 -0.1</gml:pos></aixm:ElevatedPoint></aixm:horizontalProjection_location></aixm:VerticalStructurePart></aixm:part>
 </aixm:VerticalStructureTimeSlice></aixm:timeSlice></aixm:VerticalStructure></message:hasMember>
 <message:hasMember><aixm:VerticalStructure gml:id="m"><aixm:timeSlice><aixm:VerticalStructureTimeSlice gml:id="n">
  <aixm:name>AREA1</aixm:name><aixm:type>AREA1</aixm:type>
 </aixm:VerticalStructureTimeSlice></aixm:timeSlice></aixm:VerticalStructure></message:hasMember>
 <message:hasMember><aixm:VerticalStructure gml:id="o"><aixm:timeSlice><aixm:VerticalStructureTimeSlice gml:id="p">
  <aixm:name>UK0003S003C</aixm:name><aixm:type>STACK</aixm:type>
  <aixm:part><aixm:VerticalStructurePart gml:id="q"><aixm:verticalExtent uom="FT">400</aixm:verticalExtent>
   <aixm:horizontalProjection_location><aixm:ElevatedPoint gml:id="r"><gml:pos>53.0 -1.0</gml:pos></aixm:ElevatedPoint></aixm:horizontalProjection_location></aixm:VerticalStructurePart></aixm:part>
 </aixm:VerticalStructureTimeSlice></aixm:timeSlice></aixm:VerticalStructure></message:hasMember>
</message:AIXMBasicMessage>"""


def parse():
    return nats.parse_obstacles(io.BytesIO(NATS_XML.encode()))


class NatsParseTest(unittest.TestCase):
    def setUp(self):
        self.items, self.stats = parse()
        self.by_name = {i["name"]: i for i in self.items}

    def test_tipos_e_unidades(self):
        self.assertEqual(self.by_name["UK0001W001A"]["type"], aob.WIND_TURBINE)
        self.assertEqual(self.by_name["UK0229G149F"]["type"], aob.TRANSMISSION_TOWER)
        self.assertEqual(self.by_name["UK0003S003C"]["type"], aob.CHIMNEY)
        self.assertEqual(self.by_name["UK0002C002B"]["type"], aob.GENERIC)
        self.assertAlmostEqual(self.by_name["UK0229G149F"]["height_m"], 351 * 0.3048, places=3)
        self.assertEqual(self.by_name["UK0002C002B"]["height_m"], 120)  # já em metros
        t = self.by_name["UK0229G149F"]
        self.assertEqual((t["lat"], t["lon"]), (51.0665889, -3.6193167))

    def test_area1_fora_e_contado(self):
        self.assertNotIn("AREA1", self.by_name)
        self.assertEqual(self.stats["skipped"], 1)
        self.assertEqual(len(self.items), 4)

    def test_id_estavel_na_faixa_da_nats(self):
        again, _ = parse()
        self.assertEqual([i["id"] for i in again], [i["id"] for i in self.items])
        self.assertTrue(all(NATS_ID_BASE <= i["id"] < NATS_ID_BASE + (1 << 48) for i in self.items))
        self.assertEqual(len({i["id"] for i in self.items}), 4)

    def test_tabela_de_tipos(self):
        self.assertEqual(nats.nats_type("TOWER"), aob.TELECOM_TOWER)
        self.assertEqual(nats.nats_type("COOLING_TOWER"), aob.CHIMNEY)
        for t in ("BUILDING", "BRIDGE", "RIG", "POWER_PLANT", "ARCH", "STADIUM", "OTHER", "INDUSTRIAL_SYSTEM", "QUALQUER"):
            self.assertEqual(nats.nats_type(t), aob.GENERIC, t)
        self.assertIsNone(nats.nats_type("AREA1"))


class NatsAiracTest(unittest.TestCase):
    def test_data_efetiva(self):
        self.assertEqual(nats.airac_effective(dt.date(2026, 11, 5)), "20261029")
        self.assertEqual(nats.airac_effective(dt.date(2026, 11, 25)), "20261029")
        self.assertEqual(nats.airac_effective(dt.date(2026, 11, 26)), "20261126")
        self.assertEqual(nats.airac_effective(dt.date(2020, 1, 2)), "20200102")

    def test_url(self):
        self.assertTrue(nats.obstacles_url("20261029").endswith(
            "/UK_ICAO_Obstacle_Dataset_Area_1/EG_OBS_DS_AREA1_FULL_20261029_XML.zip"))


def _zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n, d in entries.items():
            z.writestr(n, d)
    return buf.getvalue()


class NatsZipTest(unittest.TestCase):
    def test_sha256_confere(self):
        data = NATS_XML.encode()
        h = hashlib.sha256(data).hexdigest()
        z = _zip({"EG_OBS_DS_AREA1_FULL_20261029.xml": data,
                  "EG_OBS_DS_AREA1_FULL_20261029.sha256": f"{h} *EG_OBS_DS_AREA1_FULL_20261029.xml"})
        self.assertEqual(nats.xml_from_zip(z), data)

    def test_sha256_errado_lanca(self):
        z = _zip({"EG_OBS_DS_AREA1_FULL_20261029.xml": b"<x/>",
                  "EG_OBS_DS_AREA1_FULL_20261029.sha256": "f" * 64 + " *x"})
        with self.assertRaises(nats.NatsError):
            nats.xml_from_zip(z)

    def test_sem_sha256_lanca(self):
        with self.assertRaises(nats.NatsError):
            nats.xml_from_zip(_zip({"EG_OBS_DS_AREA1_FULL_20261029.xml": b"<x/>"}))


class NatsMergeTest(unittest.TestCase):
    def _base(self):
        b = Base()
        # aerogerador do OSM a ~40 m do da NATS (55.5, -3.0) e outro a ~200 m
        b.obstacles[11] = Obstacle(11, 55.50036, -3.0, aob.WIND_TURBINE)
        b.obstacles[12] = Obstacle(12, 55.5018, -3.0, aob.WIND_TURBINE)
        # torre do OSM vértice de linha a ~22 m da torre da NATS, com vizinha na linha
        b.obstacles[21] = Obstacle(21, 51.06679, -3.6193167, aob.TRANSMISSION_TOWER, voltage_kv=400)
        b.obstacles[22] = Obstacle(22, 51.07, -3.63, aob.TRANSMISSION_TOWER, voltage_kv=400)
        b.lines = [Line(30, [21, 22], 400)]
        # mastro do OSM a ~30 m da chaminé da NATS (tipo incompatível: fica)
        b.obstacles[31] = Obstacle(31, 53.00027, -1.0, aob.MAST)
        return b

    def test_par_compativel_e_substituido_pelo_oficial(self):
        b = self._base()
        stats = merge_nats(b, parse()[0])
        self.assertNotIn(11, b.obstacles)
        self.assertIn(12, b.obstacles)  # contra-prova: além do raio fica
        turbines = [o for o in b.obstacles.values() if o.id >= NATS_ID_BASE and o.type == aob.WIND_TURBINE]
        self.assertEqual(len(turbines), 1)
        self.assertAlmostEqual(turbines[0].height_m, 492 * 0.3048, places=3)
        self.assertEqual(stats["replaced"], 1)

    def test_vertice_de_linha_fica_e_ganha_altura_medida(self):
        b = self._base()
        stats = merge_nats(b, parse()[0])
        self.assertIn(21, b.obstacles)
        self.assertAlmostEqual(b.obstacles[21].height_m, 351 * 0.3048, places=3)
        self.assertEqual(b.lines[0].nodes, [21, 22])
        self.assertFalse(any(o.type == aob.TRANSMISSION_TOWER and o.id >= NATS_ID_BASE for o in b.obstacles.values()))
        self.assertEqual(stats["line_vertex_updated"], 1)

    def test_tipo_incompativel_nao_apaga_vizinho(self):
        b = self._base()
        merge_nats(b, parse()[0])
        self.assertIn(31, b.obstacles)
        self.assertTrue(any(o.type == aob.CHIMNEY and o.id >= NATS_ID_BASE for o in b.obstacles.values()))

    def test_sem_par_entra_novo(self):
        b = Base()
        stats = merge_nats(b, parse()[0])
        self.assertEqual(len(b.obstacles), 4)
        self.assertEqual(stats["added"], 4)
        self.assertTrue(all(o.measured for o in b.obstacles.values()))

    def test_par_a_57_m_na_longitude_em_60_graus_norte(self):
        # a 60N a célula de 0,001 grau tem só ~56 m de largura; o par a 57 m tem que ser achado
        # (NATS em -1.20001 cai na célula -1201; o OSM a 57 m a leste cai na -1199: duas adiante)
        import math
        lon0 = -1.20001
        lon1 = lon0 + 57 / (111320 * math.cos(math.radians(60.3)))
        self.assertEqual(math.floor(lon1 / 0.001) - math.floor(lon0 / 0.001), 2)
        b = Base()
        b.obstacles[41] = Obstacle(41, 60.3, lon1, aob.WIND_TURBINE)
        merge_nats(b, [{"id": NATS_ID_BASE + 1, "name": "X", "lat": 60.3, "lon": lon0,
                        "type": aob.WIND_TURBINE, "height_m": 150.0}])
        self.assertNotIn(41, b.obstacles)


if __name__ == "__main__":
    unittest.main()
