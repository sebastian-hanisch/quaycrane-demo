"""End-to-end Smoke-Test via Streamlits offizielles AppTest-Framework: laedt app.py mit
den Standardeinstellungen und prueft, dass kein Python-Fehler auftritt. Ergaenzt die
funktionalen Unit-Tests der uebrigen Module - ein Fehler wie
`streamlit.errors.StreamlitDuplicateElementId` (zwei st.plotly_chart-Aufrufe ohne
eindeutiges key= rendern zufaellig identischen Inhalt und kollidieren) liegt in app.py's
Widget-Verdrahtung selbst und kann nur durch einen echten End-to-End-Lauf gefunden werden,
nicht durch Unit-Tests der Algorithmus-/Visualisierungs-Module (siehe hdbscan-demo, wo
genau dieser Fehlertyp bei einem echten Nutzer auftrat, 2026-09-05)."""

import os

from streamlit.testing.v1 import AppTest

APP_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")


def test_app_loads_without_exception():
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=120)
    assert not at.exception, [str(e) for e in at.exception]
