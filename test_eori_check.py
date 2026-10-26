"""Offline tests (no network). Run: python3 -m unittest"""
import unittest
from unittest import mock
import eori_check as ec

EOS_OK = (200, b'<?xml version="1.0"?><S:Envelope xmlns:S="http://schemas.xmlsoap.org/soap/envelope/"><S:Body><ns0:validateEORIResponse xmlns:ns0="http://eori.ws.eos.dds.s/"><return><requestDate>26/10/2026</requestDate><result><eori>SE5560360793</eori><status>0</status><statusDescr>Valid</statusDescr><name>SAAB Aktiebolag</name><street>.</street><postalCode>58188</postalCode><city>LINK\xc3\x96PING</city><country>Sweden</country></result><result><eori>DE1234567</eori><status>1</status><statusDescr>Not valid</statusDescr></result></return></ns0:validateEORIResponse></S:Body></S:Envelope>', ec.EOS_URL)

class T(unittest.TestCase):
    def test_clean(self):
        self.assertEqual(ec.clean(" se 556036-0793 "), "SE5560360793")
    def test_format_error_needs_no_network(self):
        with mock.patch.object(ec, "_post") as p:
            self.assertEqual(ec.check_eoris(["XX12", "12345"])[0]["status"], "format_error")
            p.assert_not_called()
    def test_eos_parse(self):
        with mock.patch.object(ec, "_post", return_value=EOS_OK):
            r = ec.check_eoris(["SE 556036-0793", "DE1234567"])
        self.assertTrue(r[0]["valid"]); self.assertEqual(r[0]["name"], "SAAB Aktiebolag"); self.assertIsNone(r[0]["street"])
        self.assertEqual(r[0]["checked"], "26/10/2026"); self.assertFalse(r[1]["valid"])
    def test_maintenance_page_is_unavailable_not_invalid(self):
        with mock.patch.object(ec, "_post", return_value=(200, b"<html>sorry</html>", "https://sorry.ec.europa.eu/")):
            r = ec.check_eoris(["SE5560360793"])[0]
        self.assertEqual(r["status"], "unavailable"); self.assertIsNone(r["valid"])
    def test_gb_routes_to_hmrc(self):
        with mock.patch.object(ec, "_post", return_value=(200, b'[{"eori":"GB123456789000","valid":false}]', ec.HMRC_URL)) as p:
            r = ec.check_eoris(["GB123456789000"])[0]
        self.assertEqual(p.call_args[0][0], ec.HMRC_URL); self.assertEqual(r["source"], "HMRC")

if __name__ == "__main__":
    unittest.main()
