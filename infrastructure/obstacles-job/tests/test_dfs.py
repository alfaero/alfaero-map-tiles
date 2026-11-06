"""Obstáculos oficiais da Alemanha (DFS), spec 005 do alfaero-navdata-pipeline, onda D.

Rodar (dentro de infrastructure/obstacles-job): python -m unittest discover -s tests
"""
import hashlib
import io
import unittest

from obstacles import aob, dfs
from obstacles.model import DFS_ID_BASE, NATS_ID_BASE, Base, Obstacle, merge_nats

# Formato real da DFS (ED_Obstacles_Area_1, ciclo de 29/10/2026): estrutura com várias partes,
# tipo da parte pode diferir do tipo da estrutura, altura em pés.
DFS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<message:AIXMBasicMessage xmlns:aixm="http://www.aixm.aero/schema/5.1.1" xmlns:gml="http://www.opengis.net/gml/3.2"
  xmlns:message="http://www.aixm.aero/schema/5.1.1/message">
 <message:hasMember><aixm:VerticalStructure gml:id="ID_1"><gml:identifier codeSpace="urn:uuid:">aaaaaaaa-0000-0000-0000-000000000001</gml:identifier>
  <aixm:timeSlice><aixm:VerticalStructureTimeSlice gml:id="ID_VS_1">
  <aixm:name>WINDPARK NORD</aixm:name><aixm:type>WINDMILL</aixm:type><aixm:group>YES</aixm:group>
  <aixm:part><aixm:VerticalStructurePart gml:id="p1"><aixm:verticalExtent uom="FT">656.2</aixm:verticalExtent><aixm:type>WINDMILL</aixm:type><aixm:designator>1</aixm:designator>
   <aixm:horizontalProjection_location><aixm:ElevatedPoint gml:id="e1"><gml:pos>53.5 9.5</gml:pos></aixm:ElevatedPoint></aixm:horizontalProjection_location></aixm:VerticalStructurePart></aixm:part>
  <aixm:part><aixm:VerticalStructurePart gml:id="p2"><aixm:verticalExtent uom="FT">656.2</aixm:verticalExtent><aixm:type>WINDMILL</aixm:type><aixm:designator>2</aixm:designator>
   <aixm:horizontalProjection_location><aixm:ElevatedPoint gml:id="e2"><gml:pos>53.51 9.51</gml:pos></aixm:ElevatedPoint></aixm:horizontalProjection_location></aixm:VerticalStructurePart></aixm:part>
  <aixm:part><aixm:VerticalStructurePart gml:id="p3"><aixm:type>WINDMILL</aixm:type><aixm:designator>3</aixm:designator>
   <aixm:horizontalProjection_location><aixm:ElevatedPoint gml:id="e3"><gml:pos>53.52 9.52</gml:pos></aixm:ElevatedPoint></aixm:horizontalProjection_location></aixm:VerticalStructurePart></aixm:part>
 </aixm:VerticalStructureTimeSlice></aixm:timeSlice></aixm:VerticalStructure></message:hasMember>
 <message:hasMember><aixm:VerticalStructure gml:id="ID_2"><gml:identifier codeSpace="urn:uuid:">aaaaaaaa-0000-0000-0000-000000000002</gml:identifier>
  <aixm:timeSlice><aixm:VerticalStructureTimeSlice gml:id="ID_VS_2">
  <aixm:name>BADEN-WUERTTEMBERG 1</aixm:name><aixm:type>INDUSTRIAL_SYSTEM</aixm:type>
  <aixm:part><aixm:VerticalStructurePart gml:id="p4"><aixm:verticalExtent uom="FT">822.2</aixm:verticalExtent><aixm:type>STACK</aixm:type><aixm:designator>20</aixm:designator>
   <aixm:horizontalProjection_location><aixm:ElevatedPoint gml:id="e4"><gml:pos>48.717069444000003 9.3674666670000004</gml:pos></aixm:ElevatedPoint></aixm:horizontalProjection_location></aixm:VerticalStructurePart></aixm:part>
  <aixm:part><aixm:VerticalStructurePart gml:id="p5"><aixm:verticalExtent uom="FT">400</aixm:verticalExtent><aixm:designator>21</aixm:designator>
   <aixm:horizontalProjection_location><aixm:ElevatedPoint gml:id="e5"><gml:pos>48.72 9.37</gml:pos></aixm:ElevatedPoint></aixm:horizontalProjection_location></aixm:VerticalStructurePart></aixm:part>
 </aixm:VerticalStructureTimeSlice></aixm:timeSlice></aixm:VerticalStructure></message:hasMember>
 <message:hasMember><aixm:VerticalStructure gml:id="ID_3"><gml:identifier codeSpace="urn:uuid:">aaaaaaaa-0000-0000-0000-000000000003</gml:identifier>
  <aixm:timeSlice><aixm:VerticalStructureTimeSlice gml:id="ID_VS_3">
  <aixm:name>FUNKTURM</aixm:name><aixm:type>ANTENNA</aixm:type>
  <aixm:part><aixm:VerticalStructurePart gml:id="p6"><aixm:verticalExtent uom="FT">1200</aixm:verticalExtent><aixm:type>ANTENNA</aixm:type>
   <aixm:horizontalProjection_location><aixm:ElevatedPoint gml:id="e6"><gml:pos>52.5 13.4</gml:pos></aixm:ElevatedPoint></aixm:horizontalProjection_location></aixm:VerticalStructurePart></aixm:part>
 </aixm:VerticalStructureTimeSlice></aixm:timeSlice></aixm:VerticalStructure></message:hasMember>
 <message:hasMember><aixm:VerticalStructure gml:id="ID_4"><gml:identifier codeSpace="urn:uuid:">aaaaaaaa-0000-0000-0000-000000000004</gml:identifier>
  <aixm:timeSlice><aixm:VerticalStructureTimeSlice gml:id="ID_VS_4"><aixm:name>AREA1</aixm:name><aixm:type>AREA1</aixm:type>
 </aixm:VerticalStructureTimeSlice></aixm:timeSlice></aixm:VerticalStructure></message:hasMember>
</message:AIXMBasicMessage>"""


def parse():
    return dfs.parse_obstacles(io.BytesIO(DFS_XML.encode()))


class DfsParseTest(unittest.TestCase):
    def setUp(self):
        self.items, self.stats = parse()
        self.by_name = {i["name"]: i for i in self.items}

    def test_cada_parte_vira_um_obstaculo(self):
        # Parque eólico com 3 partes: 2 com altura, 1 sem (fora e contada).
        self.assertIn("WINDPARK NORD 1", self.by_name)
        self.assertIn("WINDPARK NORD 2", self.by_name)
        self.assertNotIn("WINDPARK NORD 3", self.by_name)
        self.assertEqual(self.stats["no_height"], 1)
        self.assertEqual(self.stats["structures"], 4)
        self.assertEqual(len(self.items), 5)

    def test_tipo_da_parte_vence_o_da_estrutura(self):
        self.assertEqual(self.by_name["BADEN-WUERTTEMBERG 1 20"]["type"], aob.CHIMNEY)
        # parte sem tipo herda o da estrutura (INDUSTRIAL_SYSTEM -> genérico)
        self.assertEqual(self.by_name["BADEN-WUERTTEMBERG 1 21"]["type"], aob.GENERIC)
        self.assertEqual(self.by_name["WINDPARK NORD 1"]["type"], aob.WIND_TURBINE)
        self.assertEqual(self.by_name["FUNKTURM 0"]["type"], aob.TELECOM_TOWER)

    def test_altura_em_pes_vira_metros_e_posicao(self):
        st = self.by_name["BADEN-WUERTTEMBERG 1 20"]
        self.assertAlmostEqual(st["height_m"], 822.2 * 0.3048, places=3)
        self.assertAlmostEqual(st["lat"], 48.717069444, places=6)
        self.assertAlmostEqual(st["lon"], 9.367466667, places=6)

    def test_area1_fica_fora(self):
        self.assertEqual(self.stats["skipped"], 1)
        self.assertFalse(any("AREA1" in n for n in self.by_name))

    def test_id_estavel_e_na_faixa_da_dfs(self):
        again, _ = parse()
        self.assertEqual([i["id"] for i in self.items], [i["id"] for i in again])
        self.assertEqual(len({i["id"] for i in self.items}), len(self.items))
        for i in self.items:
            self.assertGreaterEqual(i["id"], DFS_ID_BASE)
            self.assertLess(i["id"], DFS_ID_BASE + (1 << 48))
        # a faixa da NATS (48 bits a partir de 2^61) não encosta na da DFS
        self.assertGreater(DFS_ID_BASE, NATS_ID_BASE + (1 << 48))

    def test_juncao_com_osm_pela_mesma_regra_da_nats(self):
        base = Base(obstacles={7: Obstacle(7, 53.5001, 9.5001, aob.WIND_TURBINE, None)}, lines=[])
        stats = merge_nats(base, self.items)
        self.assertEqual(stats["replaced"], 1)
        self.assertNotIn(7, base.obstacles)
        self.assertIn(self.by_name["WINDPARK NORD 1"]["id"], base.obstacles)


META = {
    "Amdts": [
        {"Amdt": 1, "AmdtNumeric": "20261126", "Metadata": {"datasets": []}},
        {"Amdt": 0, "AmdtNumeric": "20261029", "Metadata": {"datasets": [{"type": "group", "name": "obstacle", "items": [
            {"type": "leaf", "name": "ED Obstacles Area 1", "releases": [
                {"type": "Excel", "filename": "x.xlsx", "checksum": {"type": "sha512", "value": "0"}},
                {"type": "AIXM 5.1", "filename": "ED_Obstacles_Area_1_2026-10-01_2026-10-29_revision.xml",
                 "checksum": {"type": "sha512", "value": "ABC"}},
            ]},
        ]}]}},
    ],
}


class DfsDownloadTest(unittest.TestCase):
    def test_release_do_ciclo_vigente(self):
        r = dfs.release_of(META, 0)
        self.assertEqual(r["filename"], "ED_Obstacles_Area_1_2026-10-01_2026-10-29_revision.xml")
        self.assertEqual(r["sha512"], "abc")
        self.assertEqual(r["effective"], "20261029")

    def test_sem_dataset_no_amdt_e_erro(self):
        with self.assertRaises(dfs.DfsError):
            dfs.release_of(META, 1)

    def test_url_documentada(self):
        self.assertEqual(dfs.file_url(0, "ED_Obstacles_Area_1_x.xml"),
                         "https://aip.dfs.de/datasets/rest/0/ED_Obstacles_Area_1_x.xml")

    def test_sha512_confere_ou_falha(self):
        data = b"conteudo"
        dfs.verify(data, hashlib.sha512(data).hexdigest())
        with self.assertRaises(dfs.DfsError):
            dfs.verify(data + b" ", hashlib.sha512(data).hexdigest())
        with self.assertRaises(dfs.DfsError):
            dfs.verify(data, "")


if __name__ == "__main__":
    unittest.main()
