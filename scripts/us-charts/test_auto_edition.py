"""Testes da automação das cartas raster dos EUA (spec 008). Sem rede: `python -I -m unittest`."""
import os
import sqlite3
import sys
import tempfile
import unittest
from collections import namedtuple
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import edition as ed  # noqa: E402
from auto_edition import decide  # noqa: E402
from check import compare  # noqa: E402

PUB = {"published": {"edition": "2026-10-29", "charts": {}}}


def utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


class Datas(unittest.TestCase):
    def test_ciclo_de_56_dias_a_partir_de_29_10(self):  # AC1
        self.assertEqual(ed.edition_after(date(2026, 10, 29)), date(2026, 12, 24))
        self.assertEqual(ed.edition_after(date(2026, 12, 23)), date(2026, 12, 24))
        self.assertEqual(ed.edition_after(date(2026, 12, 24)), date(2027, 2, 18))
        self.assertEqual(ed.edition_after(date(2026, 9, 2)), date(2026, 9, 3))
        self.assertTrue(ed.is_edition(date(2027, 2, 18)))
        self.assertFalse(ed.is_edition(date(2027, 2, 19)))

    def test_vigencia_validade_e_pasta_da_faa(self):  # AC1
        self.assertEqual(ed.effective_utc(date(2026, 12, 24)), utc(2026, 12, 24, 9, 1))
        self.assertEqual(ed.valid_until(date(2026, 12, 24)), date(2027, 2, 18))
        self.assertEqual(ed.faa_folder(date(2026, 12, 24)), "12-24-2026")


class Decisao(unittest.TestCase):
    def test_faa_sem_arquivos_nada(self):  # AC2
        self.assertEqual(decide(PUB, utc(2026, 11, 20), lambda d: False)[0], "none")

    def test_faa_com_arquivos_gera_a_proxima(self):  # AC2
        asked = []
        act = decide(PUB, utc(2026, 12, 4), lambda d: asked.append(d) or True)
        self.assertEqual(act, ("generate", "2026-12-24"))
        self.assertEqual(asked, [date(2026, 12, 24)])

    def test_gerada_espera_a_vigencia_e_publica_as_0901z(self):  # AC4
        st = {**PUB, "generated": {"edition": "2026-12-24"}}
        never = lambda d: self.fail("não devia consultar a FAA")  # noqa: E731
        self.assertEqual(decide(st, utc(2026, 12, 24, 9, 0), never)[0], "none")
        self.assertEqual(decide(st, utc(2026, 12, 24, 9, 1), never), ("publish", "2026-12-24"))
        self.assertEqual(decide(st, utc(2026, 12, 30), never), ("publish", "2026-12-24"))

    def test_gerada_mais_velha_que_a_publicada_e_ignorada(self):  # estado sujo
        st = {**PUB, "generated": {"edition": "2026-09-03"}}
        self.assertEqual(decide(st, utc(2026, 12, 5), lambda d: True), ("generate", "2026-12-24"))

    def test_publicada_nao_publica_de_novo(self):  # AC4
        st = {"published": {"edition": "2026-12-24", "charts": {}}}
        self.assertEqual(decide(st, utc(2026, 12, 25), lambda d: False)[0], "none")


class Conferencia(unittest.TestCase):
    PREV = {"zooms": {"5": 100, "6": 400, "7": 1600}, "size": 1000}

    def new(self, zooms, size=1000, ed="2026-12-24", bad=0):
        return {"meta": {"faa_edition": ed}, "zooms": zooms, "size": size, "bad": bad}

    def test_dentro_das_margens_aprova(self):  # AC3 contra-prova
        self.assertEqual(compare("x", self.new({5: 101, 6: 410, 7: 1650}, 1100), self.PREV, "2026-12-24"), [])

    def test_total_6_por_cento_menor_reprova(self):  # AC3
        self.assertTrue(compare("x", self.new({5: 100, 6: 380, 7: 1485}), self.PREV, "2026-12-24"))

    def test_zoom_com_20_por_cento_a_menos_reprova(self):  # AC3
        p = compare("x", self.new({5: 100, 6: 320, 7: 1680}), self.PREV, "2026-12-24")
        self.assertTrue(any("zoom 6" in m for m in p))

    def test_zoom_faltando_metadado_errado_tamanho_e_amostra_reprovam(self):  # AC3
        self.assertTrue(compare("x", self.new({5: 100, 6: 400}), self.PREV, "2026-12-24"))
        self.assertTrue(compare("x", self.new({5: 100, 6: 400, 7: 1600}, ed="2026-10-29"), self.PREV, "2026-12-24"))
        self.assertTrue(compare("x", self.new({5: 100, 6: 400, 7: 1600}, size=1400), self.PREV, "2026-12-24"))
        self.assertTrue(compare("x", self.new({5: 100, 6: 400, 7: 1600}, bad=1), self.PREV, "2026-12-24"))


class Rodada(unittest.TestCase):
    """run() com a pasta de estado num diretório temporário e as etapas externas trocadas por dublês."""

    def setUp(self):
        import auto_edition as ae
        self.ae = ae
        self.tmp = tempfile.mkdtemp()
        self.saved = {k: getattr(ae, k) for k in ("ROOT", "STATE", "LOCK", "LOG", "faa_has", "notify", "generate", "shutil", "ensure_docker")}
        ae.ROOT = self.tmp
        ae.STATE = os.path.join(self.tmp, "state.json")
        ae.LOCK = os.path.join(self.tmp, "lock")
        ae.LOG = os.path.join(self.tmp, "auto.log")
        ae.save_state({"published": {"edition": "2026-10-29", "charts": {}}})
        self.avisos = []
        ae.notify = lambda subject, body: self.avisos.append((subject, body))
        ae.faa_has = lambda d: True

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(self.ae, k, v)

    def test_falha_na_geracao_avisa_com_a_etapa_e_nao_marca_gerada(self):  # AC6
        def boom(state, edition):
            raise RuntimeError("recortes: 'manter' em (10,20) não acha saliência")
        self.ae.generate = boom
        self.assertEqual(self.ae.run(), 1)
        self.assertEqual(len(self.avisos), 1)
        self.assertIn("falha (generate)", self.avisos[0][0])
        self.assertIn("recortes", self.avisos[0][1])
        self.assertNotIn("generated", self.ae.load_state())
        self.assertFalse(os.path.exists(self.ae.LOCK))  # a falha solta a trava

    def test_trava_recente_sai_sem_fazer_nada_e_velha_e_assumida(self):  # AC7
        chamadas = []
        self.ae.generate = lambda state, edition: chamadas.append(edition)
        open(self.ae.LOCK, "w").close()
        self.assertEqual(self.ae.run(), 0)
        self.assertEqual(chamadas, [])
        velha = os.path.getmtime(self.ae.LOCK) - self.ae.LOCK_MAX_AGE_S - 60
        os.utime(self.ae.LOCK, (velha, velha))
        self.assertEqual(self.ae.run(), 0)  # contra-prova: com a trava vencida, gera
        self.assertEqual(chamadas, ["2026-12-24"])

    def test_menos_de_20_gb_livres_nao_comeca(self):  # AC8
        class Disco:
            @staticmethod
            def disk_usage(path):
                return namedtuple("Uso", "total used free")(0, 0, 19.9e9)
        self.ae.shutil = Disco
        self.ae.ensure_docker = lambda: self.fail("não devia chegar no Docker")
        with self.assertRaisesRegex(RuntimeError, "disco"):
            self.ae.generate(self.ae.load_state(), "2026-12-24")


if __name__ == "__main__":
    unittest.main()
