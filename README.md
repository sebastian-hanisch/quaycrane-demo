# Containerbrücken-Einsatzplanung – Streamlit-Demo

**[→ Demo live ausprobieren](https://sebastianhanisch-quaycrane-demo.streamlit.app/)**

Interaktive Demo zum **Quay Crane Scheduling Problem (QCSP)** aus dem Containerterminal-Betrieb:
ein Schiff liegt am Kai, unterteilt in **Bays** (Ladeluken) mit je einer Anzahl Container-Moves.
Mehrere **Containerbrücken** teilen sich dieselbe Kaischiene und können sich dabei **nie
überholen** (Non-Crossing) – welche Brücke übernimmt welche Bay, in welcher Reihenfolge, damit
das Schiff so schnell wie möglich fertig wird? Teil des Portfolios für die Website
"Sebastian Hanisch – Operations Research und Machine Learning", entstanden als spekulative Demo
zu einer Ausschreibung für "Product Owner / Operations Research & Python Developer" im Bereich
Terminal Operations (Hamburg).

## Warum dieses Problem

Container-Terminal-Betrieb ist der thematische Kern der Ausschreibung ("Scheduler Services zur
Optimierung von Terminalprozessen"). Das Quay Crane Scheduling Problem ist das klassische,
literaturbekannte Scheduling-Problem dieser Domäne (Kim & Park, *European Journal of Operational
Research*, 2004; Bierwirth & Meisel, Übersichtsartikel 2010/2015) und deckt im Portfolio eine
bislang fehlende Nische ab: **Scheduling mit sequenzabhängigen Rüstzeiten UND einer physischen
Non-Crossing-Randbedingung zwischen mehreren Ressourcen** – anders als die bisherigen
Scheduling-nahen Demos (Tor-Zuordnung, Truck-Appointment-Scheduling), die keine Interferenz
zwischen den zugewiesenen Ressourcen kennen.

## Modellierung

Bay-Index == Position entlang der Schiffsseite (Bay 0 ist die am weitesten links liegende). Jede
Bay hat eine feste Bearbeitungsdauer (Moves × Zeit/Move), unabhängig davon, welche Brücke sie
übernimmt. Jede Brücke hat eine physisch fixe Position in der Kranreihenfolge (Kran 0 ist immer
der linkeste) und eine Startposition auf der Schiene.

Für je zwei Bays gilt, abhängig von der Kranzuordnung:

- **Gleiche Brücke**: die beiden Aufgaben dürfen sich zeitlich nicht überlappen und brauchen
  zusätzlich die Fahrzeit zwischen den Bays als Rüstzeit dazwischen (Reihenfolge frei wählbar –
  klassisches Sequencing mit sequenzabhängigen Rüstzeiten).
- **Unterschiedliche Brücken, "konsistente" Zuordnung** (die physisch linkere Brücke bearbeitet
  die linkere Bay): bei zeitlicher Überlappung muss der Sicherheitsabstand in Bays eingehalten
  werden.
- **Unterschiedliche Brücken, "gekreuzte" Zuordnung**: bei zeitlicher Überlappung wäre das eine
  physische Unmöglichkeit (Brücken können sich nicht überholen) – unabhängig vom
  Sicherheitsabstand komplett verboten.

Formale Herleitung im Expander "📐 Mathematische Formulierung" der App.

## Methodik – vier Verfahren im Vergleich

- **Naive (gleichmäßige Aufteilung)**: jede Brücke bekommt gleich viele Bays, ohne Rücksicht auf
  die tatsächliche Arbeitslast – Baseline.
- **Greedy (Zonenbalance)**: das Schiff wird per dynamischer Programmierung (klassisches
  "zerlege ein Array in *k* zusammenhängende Teile, minimiere die größte Teilsumme"-Problem,
  `O(n²k)`) in zusammenhängende, lastbalancierte Zonen geschnitten – zusammenhängende Zonen
  vermeiden Interferenz fast vollständig.
- **Greedy + lokale Suche**: startet bei der besseren von drei Konstruktionen (Zonenbalance, LPT-
  Listenscheduling, Positions-Listenscheduling) und verbessert iterativ per Kran-Tausch und
  Kran-Verlagerung einzelner Bays – nachweislich nie schlechter als der Startpunkt.
- **Exakt** (Google OR-Tools CP-SAT): löst das vollständige Scheduling-Modell exakt – Referenz
  und Cross-Check für die drei Heuristiken. Läuft bewusst nur auf Klick (Button in der
  Seitenleiste), nicht automatisch bei jeder Regler-Änderung mit – bei größeren Szenarien kann
  das mehrere Sekunden dauern, während naive Aufteilung und Zonenbalance samt Zeitplan-Aufbau
  bei 24 Bays / 5 Kränen im Mittel unter einer Millisekunde brauchen und Greedy + lokale Suche
  etwa 0,1 s (siehe Messung im Abschnitt zum Zeitplan-Aufbau weiter unten).

Die Primäransicht zeigt **dynamisch** die bei den aktuellen Reglereinstellungen tatsächlich
schnellste Methode (unter den drei Heuristiken) – keine wird pauschal bevorzugt.

## Fund: naives Listenscheduling nach Arbeitslast (LPT) verliert gegen die naive Baseline

Erste Fassung des Greedy-Verfahrens war klassisches **LPT-Listenscheduling** (Longest Processing
Time first): Bays absteigend nach Dauer sortiert, jede an die Brücke mit frühestmöglicher
Fertigstellung. Für "normale" parallele Maschinen ohne Interferenz ist das eine bewährte,
~4/3-approximative Heuristik. Hier schneidet sie **schlechter** ab als die naive gleichmäßige
Aufteilung. Die ersten Fundzahlen der Erstfassung (z. B. LPT 138,8 min gegen naive 94,3 min) ließen
sich mit der heutigen Konstruktion nicht mehr nachstellen und sind durch Neumessungen ersetzt.

**Messung (heutiger Code, feste Zufalls-Seeds; Standardwerte außer den genannten: 14 Moves
± 40 %, 2,0 min je Move, 0,5 min Fahrzeit je Bay):**

- **Preset "Kleines Feederschiff"** (8 Bays, 2 Kräne, Sicherheitsabstand 1, Zufalls-Seed 3): naive
  102,5 min ohne Wartezeit, LPT-Greedy **105,5 min** mit 2,0 min Wartezeit durch Interferenz,
  die positionsbasierte Variante `"spatial"` 111,5 min mit 17,5 min Wartezeit.
- **240 Instanzen** (8/10/12/16 Bays × 2/3/4 Kräne × Zufalls-Seeds 0-19), Sicherheitsabstand 1:
  `build_schedule` weist die LPT-Zuordnung in **220 von 240 Instanzen (92 %)** ab (mit dieser
  Zuordnung und Reihenfolge je Kran findet die Konstruktion keine zulässige Zeitplanung), die naive
  Aufteilung nie. In den 20 Instanzen, in denen beide zulässig sind, ist LPT in 12 länger und in 8
  kürzer als naive, im Mittel **4,3 % länger**, mit im Mittel 12,5 min Wartezeit gegen 0,0 min.
  Bei Sicherheitsabstand 2 ist LPT in 234 von 240 Instanzen abgelehnt (naive in 7).
- **Wie strukturell ist die Ablehnung?** Für 30 abgelehnte LPT-Zuordnungen (Abstand 1, Zufalls-Seeds
  0-7, Größen 8/2, 10/3, 12/3, 12/4) prüfte CP-SAT mit fest vorgegebener Kranzuordnung: bei 13 ist
  sie für **jede** Zeitplanung unzulässig (bewiesen), bei 17 gibt es eine zulässige Zeitplanung –
  dort scheitert nur die Konstruktion mit ihrer festen Reihenfolge je Kran.

**Ursache:** LPT wählt die Kranzuordnung rein nach Arbeitslast, ohne auf die räumliche Lage der
Bays zu achten. Weil Bay-Index gleichzeitig die Position auf der Schiene ist, führt das zu einer
über das Schiff verstreuten Zuordnung – jede neu hinzukommende Aufgabe kollidiert mit bereits
verteilten Aufgaben benachbarter Kräne und muss warten, bis diese fertig sind. Ein Wechsel der
Sortierreihenfolge (Positions- statt Arbeitslast-Reihenfolge, `greedy_construction(..., "spatial")`)
milderte das nicht zuverlässig – auch räumlich sortierte Listenscheduling-Zuweisung kann je nach
Instanz zwischen Kränen hin- und herspringen.

**Fix:** die Zonenbalance-Konstruktion (`balanced_zone_construction`) ersetzt das Listenscheduling
als primäre Greedy-Methode. Da sie das Schiff strukturell in nicht überlappende, zusammenhängende
Zonen zerlegt, bleibt Kran-Interferenz meist bei 0. Gemessen über dieselben 240 Instanzen
(Sicherheitsabstand 1, Zeitplan jeweils zulässig): Zonenbalance im Mittel **3,6 %** kürzer als die
naive Aufteilung, Greedy + lokale Suche **7,1 %** kürzer. Liegezeiten der vier Presets in min
(naive / Zonenbalance / Greedy + lokale Suche / exakt):

| Preset | naive | Zonenbalance | Greedy + lokale Suche | exakt |
|---|---|---|---|---|
| Kleines Feederschiff | 102,5 | 102,5 | 101,5 | 101,0 |
| Mittleres Schiff, Normalbetrieb | 112,5 | 112,5 | 107,0 | 106,0 |
| Großes Schiff, viele Kräne | 150,5 | 150,5 | 145,0 | kein Ergebnis in 12 s (siehe Laufzeit) |
| Enge Sicherheitsabstände | 116,85 (6,3 min Wartezeit) | 112,85 | 110,05 | 109,2 |

Das exakte Modell rechnet in 0,1-min-Schritten und rundet Zeiten auf; sein Ergebnis kann daher bis
zu 0,1 min über dem stetigen Optimum liegen (Beispiel: 10 Bays / 3 Kräne / Abstand 1 / Zufalls-Seed 3,
Standardwerte sonst: Greedy + lokale Suche 104,8 min, exakt 104,9 min; naive und Zonenbalance je
110,3 min). Die LPT- und positions-sortierten Listenscheduling-Varianten bleiben als zusätzliche
Startpunkte für die lokale Suche erhalten (`greedy_and_polish` probiert alle drei und startet von
der besten), tragen aber in der Praxis selten bei. Die Zahlen sind in `tests/test_claims.py`
belegt.

## Fund: CP-SAT ließ Kräne grundlos warten, obwohl der Makespan optimal war

Nutzerhinweis: im Preset "Mittleres Schiff, Normalbetrieb" zeigte die Exakt-Lösung manchmal
sichtbare Wartezeit ganz am Anfang der Kran-Trajektorien, obwohl die Kräne dort räumlich weit
auseinander lagen - visuell sollte dort keine Interferenz auftreten. Nachgestellt: dieselbe
Instanz mehrfach hintereinander mit `solve_exact` gelöst: der Makespan blieb jedes Mal gleich,
die ausgewiesene Wartezeit schwankte aber von Lauf zu Lauf (die damaligen Zahlen stammen aus der
Fassung vor dem Fix und sind nicht mehr nachstellbar).

**Ursache:** Das Modell minimierte ausschließlich den Makespan. Unter mehreren Lösungen mit
demselben optimalen Makespan ist dem Solver jede davon gleich lieb - eine mit unnötigem
Leerlauf auf einem unkritischen Kran erfüllt die Zielfunktion genauso gut wie eine
wartezeitfreie. `num_search_workers=8` lässt mehrere Suchpfade parallel laufen; je nachdem,
welcher zuerst eine beweisbar optimale Lösung liefert, landet man auf einer mit oder ohne
solche kosmetische Wartezeit - nicht deterministisch, von Lauf zu Lauf unterschiedlich.

**Fix:** lexikografisches Tie-Breaking-Ziel in [quaycrane_cp_solver.py](quaycrane_cp_solver.py)
hinzugefügt - primär weiterhin Makespan minimieren, als zweites (mit einem Gewicht multipliziert,
das garantiert nie über den Makespan gewinnen kann) die Summe aller Endzeiten. Das drückt jede
Aufgabe so früh wie möglich, ohne den Makespan zu verschlechtern, und eliminiert dadurch jede
Lösung mit grundlosem Leerlauf. Neu gemessen (heutiger Code, fünf Läufe desselben Presets
"Mittleres Schiff, Normalbetrieb", Zeitlimit 30 s): Makespan immer 106,0 min (jedes Mal als optimal
bewiesen), Wartezeit immer 0,0 min (`test_exact_solution_has_no_spurious_wait`,
`tests/test_claims.py`). Nebeneffekt: das
zweite Ziel macht den Beweis der Optimalität in Grenzfällen etwas schwerer (siehe Laufzeittabelle
unten, die Standard-Presets sind davon nicht spürbar betroffen).

## Fund: Non-Crossing wurde nur zwischen Aufgaben geprüft, nie während der Fahrt dazwischen

Nutzerhinweis: die Kran-Trajektorien im Chart dürfen sich laut eigener Beschreibung nie
kreuzen - trotzdem beobachtete ein Nutzer genau das, zusammen mit einer Wartezeit beim
kreuzenden Kran. Beobachtet am Preset "Mittleres Schiff, Normalbetrieb" (die damaligen Zeitpunkte stammen aus
der Fassung vor dem Fix und sind nicht mehr nachstellbar): ein Kran fuhr von Bay 4 zu Bay 2 und
durchquerte dabei zwangsläufig Position 3, exakt während ein anderer Kran dort noch stand und
arbeitete. Die ursprünglichen Non-Crossing-Constraints verglichen ausschließlich
Aufgaben-Bearbeitungsintervalle miteinander, nie die Fahrt eines Krans zwischen zwei seiner
eigenen Aufgaben gegen die Aufgaben anderer Kräne.

**Fix, in drei Nachbesserungsrunden** (`_add_travel_non_crossing_constraints` in
[quaycrane_cp_solver.py](quaycrane_cp_solver.py)):

1. Für jedes Paar unmittelbar aufeinanderfolgender Aufgaben *(a, b)* desselben Krans (per
   abgeleitetem `next_ab`-Bool: *b* folgt auf *a*, kein drittes Bay desselben Krans dazwischen)
   wird die Fahrt gegen alle zeitlich übrschneidenden Aufgaben anderer Kräne abgesichert.
2. Fund direkt danach beim Preset "Großes Schiff, viele Kräne" (20 Bays, 5 Kräne): die
   ALLERERSTE Fahrt eines Krans (von seiner festen Startposition zur ersten Aufgabe) hat kein
   vorangehendes *a* und wurde vom ersten Fix übersehen - eigener Constraint-Block dafür ergänzt.
3. Dritter Fund: die neuen Constraints gingen von "sofort losfahren, am Ziel warten" aus,
   während `check_feasible`/das Chart zwischenzeitlich auf "am Ursprung warten, zuletzt
   losfahren" umgestellt wurden (siehe nächster Abschnitt) - zwei unterschiedliche Zeitfenster
   für dieselbe Lücke. Behoben, indem der Solver jetzt genau dasselbe Fenster absichert, das
   auch geprüft/gezeichnet wird: Warten fest bei Position *a* im Fenster `[end_a, start_b -
   Fahrzeit]`, danach die eigentliche Fahrt im Fenster `[start_b - Fahrzeit, start_b]`.

Alle drei Fixe zusammen per Regressionstests abgesichert
(`test_exact_solution_never_crosses_during_travel`,
`test_exact_solution_covers_first_travel_from_start_position`) und per Stichprobe bestätigt
(neu gemessen, heutiger Code, mit Greedy-Hint wie in der App): "Kleines Feederschiff", "Mittleres
Schiff, Normalbetrieb" und "Enge Sicherheitsabstände" je 3× frisch gelöst, `check_feasible` (siehe
nächster Fund) jedes Mal ohne Verletzung; "Großes Schiff, viele Kräne" lieferte in 3 von 3 Läufen
innerhalb von 12 s keine Lösung (siehe Laufzeit).

## Fund: die "sofort losfahren"-Konvention konnte selbst wieder Verletzungen erzeugen

Nebenbefund beim Härtetest von `check_feasible` gegen echte Fahrsegmente (siehe oben): bei
sehr langer erzwungener Wartezeit UND hohem Sicherheitsabstand konnte ein Kran, der laut
Konvention sofort zur Zielposition fährt und dort wartet, während der gesamten Wartezeit zu
nah an einem arbeitenden Nachbarkran stehen - beobachtet bei 18 Bays / 5 Kränen / Sicherheitsabstand 3
(Regler-Maximum), Seed 5 (die damalige Wartezeit von 72,7 min stammt aus der Fassung vor dem
Fix und ist nicht mehr nachstellbar). Heute, mit 12 Moves je Bay wie im Regressionstest: naive
Aufteilung 114,4 min (4,3 min Wartezeit), Zonenbalance und Greedy + lokale Suche je 99,0 min
(10,3 min Wartezeit), alle drei laut `check_feasible` ohne Verletzung (`tests/test_claims.py`).

**Fix (Anzeige/Prüfung):** Konvention in `crane_position_segments`
([quaycrane_evaluation.py](quaycrane_evaluation.py)) umgestellt auf "am Ursprung warten, erst
im letztmöglichen Moment losfahren" - physikalisch naheliegender und löst die meisten Fälle.
Vom exakten Löser wird dieselbe Konvention jetzt aktiv erzwungen (siehe Fund oben), bleibt dort
also immer korrekt.

**Ursprünglich bewusst nicht behobene Einschränkung (Heuristiken), seither vollständig
geschlossen (siehe nächster Fund):** `earliest_feasible_start` (die Kernroutine aller drei
Heuristiken) prüfte nur die Aufgabe selbst, nicht die Wartephase davor - ein Versuch, das per
erweitertem Push-Fenster nachzuziehen, erwies sich als nicht konvergent (das Wartefenster
wächst mit jedem Push selbst, ein einmal erkannter Konflikt lässt sich dadurch nicht auflösen,
anders als bei der Aufgabe selbst). Bei sehr extremen Reglereinstellungen (Sicherheitsabstand
nahe Maximum kombiniert mit vielen Kränen auf kurzem Schiff) konnten die Heuristiken deshalb
selbst noch eine solche Verletzung erzeugen.

## Fund: die Heuristik-Restlücke war tiefer als gedacht - vollständig geschlossen

Der Nutzer wollte diese Einschränkung nicht als akzeptiert stehen lassen ("Ich möchte keine
unzulässigen Lösungen"). Die tatsächliche Behebung brauchte mehrere Anläufe, weil sich
nacheinander mehrere unabhängige, ineinander verschachtelte Ursachen zeigten:

1. **Der explizite Sicherheitsnetz-Fallback (`_fully_sequential_schedule`) war selbst
   unsicher.** Er nahm an, "warten bis zum Ende der spätesten bislang eingeplanten Aktivität,
   dann losfahren" sei immer sicher - falsch: das Warten selbst (an der aktuellen Position, VOR
   der Abfahrt) kann die ganze Zeit über zu nah an einer bereits eingeplanten fremden Aktivität
   liegen; eine spätere Abfahrt hilft dann nicht, der Kran war ja die ganze Zeit über dort.
2. **Blockweise Konstruktions-Reihenfolge kaskadierte in Phantom-Verzögerungen.** Ein Kran ohne
   eigene Aufgabe gilt für die Sicherheitsprüfung als "für immer an seiner Startposition
   gefangen" (siehe `_segments_with_unassigned_cranes`) - baute man Kran für Kran komplett
   nacheinander, wurde ein früh eingeplanter Kran unnötig auf einen extrem späten Zeitpunkt
   verschoben, um einem noch gar nicht bearbeiteten Nachbarn auszuweichen; das erzeugte GENAU
   DORT eine neue, echte Verletzung. **Fix:** rundenweise verschränkte Einfügereihenfolge
   (`_round_robin_interleave`) - jeder Kran bekommt seine erste Aufgabe früh.
3. **`earliest_feasible_start`s Retry-Eskalation war für die REST-Absicherung nicht
   verwendbar** - sie verschiebt den angenommenen "frei ab"-Zeitpunkt nach vorn und übersieht
   dabei, ob die Wartezeit VOR dieser Verschiebung schon verletzt war.
4. Die letztlich robuste Lösung: das Sicherheitsnetz baut jede Aufgabe einzeln, in
   rundenweiser Reihenfolge, und probiert bei einer nicht sofort sicheren Platzierung
   erschöpfend JEDEN Zeitpunkt durch, an dem sich der Sicherheitsstatus eines bereits
   eingeplanten Segments ändern könnte (`_safe_breakpoint_departure`) - verifiziert nach jedem
   Einfügeschritt tatsächlich gegen die komplette Instanz, statt einer Formel zu vertrauen.

**Ein tieferer, eigenständiger Fund dabei: manche Kranzuordnungen sind für den Zeitplaner nicht
bildbar.** Ein rein lastbasiertes Greedy-Verfahren (LPT) kann bei engem
Sicherheitsabstand zwei benachbarten Kränen Bays zuweisen, für die die Konstruktion mit fester Reihenfolge je Kran
keine zulässige Zeitplanung findet (`quaycrane_evaluation.ScheduleInfeasibleError`). Laut der
Messung oben (30 abgelehnte Zuordnungen) ist das bei 13 für jede Zeitplanung beweisbar unzulässig, bei 17 gibt es
eine zulässige. Dort hilft kein Konstruktionstrick bei derselben Reihenfolge, nur eine andere Kranzuordnung. Fix: `build_schedule_robust`
([quaycrane_heuristic.py](quaycrane_heuristic.py)) weicht dann auf die (strukturell robustere)
Zonenbalance-Konstruktion aus, als allerletzter Ausweg auf den exakten Löser.

**Und ein Fund über die Grenze der Heuristiken hinaus: manche Szenarien sind SELBST unlösbar.**
Die Regler erlauben Kombinationen (wenige Bays, viele Kräne, maximaler Sicherheitsabstand), bei
denen schon die gleichmäßig verteilten Kran-Startpositionen enger beieinanderliegen als der
Sicherheitsabstand - dann verletzen zwei Kräne die Regel bereits im Stillstand, bevor überhaupt
einer fährt, und selbst der exakte Löser fände nie eine Lösung. `Instance.is_trivially_infeasible`
([quaycrane_scenario.py](quaycrane_scenario.py)) erkennt das vorab; die App zeigt dann eine
klare Erklärung statt einen Absturz oder eine stillschweigend unzulässige Lösung.

**Nebenbefund beim Testen des CP-SAT-Fallbacks:** der exakte Löser rundete Zeiten in seinem
skalierten Modell mit `round()`, was bei exakten `.5`-Werten (Bankers Rounding) und generell
gelegentlich AB rundete - bei sehr engem Sicherheitsabstand reichte diese Winzigkeit, damit eine
von CP-SAT als "optimal und zulässig" gemeldete Lösung nach dem Zurückskalieren die (strengere,
stetige) `check_feasible`-Prüfung knapp verfehlte. Fix: in
[quaycrane_cp_solver.py](quaycrane_cp_solver.py) wird jetzt konsequent aufgerundet (`scaled()`)
- das Modell nimmt nie eine kürzere Zeit an, als real gebraucht wird.

Alles zusammen per Regressionstests abgesichert: `test_heuristics_stay_feasible_at_extreme_settings`
(vormals `test_exact_stays_feasible_where_heuristics_can_fail` - Name und Zweck gedreht, jetzt
eine Bestätigung statt einer dokumentierten Einschränkung), außerdem
`test_instance_detects_trivial_infeasibility_from_slider_ranges` und
`test_build_schedule_robust_recovers_from_a_structurally_unschedulable_construction`
(`tests/test_heuristic.py`). Zusätzlich per Sweep gemessen (heutiger Code): 6-24 Bays × 1-5 Kräne × Zufalls-Seeds 0-4 bei
Sicherheitsabstand 3, Standardwerte sonst - 475 Kombinationen, davon 90 schon als Szenario
unlösbar (siehe unten) und 385 lösbar. Für alle 385 gilt: **0 Verletzungen** in `check_feasible`
bei jedem Zeitplan, den `build_schedule` überhaupt liefert. Daneben lehnt `build_schedule`
die Kranzuordnung der naiven Aufteilung in 19, der Zonenbalance in 17 und von Greedy + lokale
Suche in 7 der 385 Fälle ab - dann weicht die App auf eine andere Konstruktion bzw. auf den
exakten Löser aus (`build_schedule_robust`, `_schedule_or_exact_fallback`).

## Aufräumen: der "schnelle, aber nicht durchgängig korrekte" Pfad war überflüssig

Nachdem der obige Fund gezeigt hatte, dass nur die verifizierte Breakpoint-Suche
(`_safe_breakpoint_departure`) tatsächlich beweisbar sicher ist, blieb die Frage: wozu dann noch
der ursprüngliche "optimistische" Konstruktionspfad (`_build_schedule_incremental` mit seiner
Intervall-Vermeidungs-Logik `earliest_feasible_start`/`_safe_departure`/`_safe_start`) als
Normalfall, wenn er nur als Fallback abgesichert war? `quaycrane_evaluation.py` baut jetzt in
EINEM einzigen Durchgang: jede Aufgabe wird sofort per Breakpoint-Suche platziert und dabei
gegen die echten, bereits eingeplanten Segmente verifiziert - kein zweiter, separater
Sicherheitsnetz-Pfad mehr nötig. Das entfernt rund 260 Zeilen (`earliest_feasible_start`,
`_safe_departure`, `_safe_start`, `_dangerous_segments`, `_segments_with_unassigned_cranes`,
`_advance_past_forbidden`, `_range_safe_against_segment`, `_build_schedule_incremental`,
`_fully_sequential_schedule` als eigene Funktion) - genau die Stellen, an denen die
Bugfix-Runden oben stattfanden.

Nebeneffekt: die neue Konstruktion ist schnell, weil jede Platzierung nur noch gegen die
tatsächlich betroffenen Segmente geprüft wird. Neu gemessen (heutiger Code, ein Windows-Rechner,
Standardwerte, Sicherheitsabstand 1, je 10 Zufalls-Seeds, Mittel / Maximum in ms, jeweils
Konstruktion der Zuordnung plus `build_schedule`):

| Größe | naive | Zonenbalance | Greedy + lokale Suche (400 Züge) |
|---|---|---|---|
| 12 Bays / 3 Kräne | 0,13 / 0,2 | 0,15 / 0,2 | 15 / 24 |
| 24 Bays / 5 Kräne (größte von der App erlaubte Größe) | 0,46 / 0,7 | 0,64 / 1,1 | 114 / 130 |

Die Vorher-Werte der früheren Fassung (1,45 ms auf 0,28 ms, "knapp 7x schneller") sind nicht mehr
nachstellbar und entfallen.

## Fund: CI schlug fehl - und deckte dabei einen echten Modellierungsfehler im exakten Löser auf

Die GitHub-Actions-Pipeline (`.github/workflows/tests.yml`) lief lokal nie, meldete beim ersten
echten Durchlauf aber drei Fehlschläge in den CP-SAT-Tests - alle mit Zeitüberschreitung. Ursache:
`num_search_workers` war seit dem allerersten Commit fest auf 8 verdrahtet, GitHub-gehostete
Runner haben aber nur 2 vCPUs - 8 parallele Suchpfade auf 2 echten Kernen konkurrieren nur noch um
Kontextwechsel, statt zu parallelisieren, und lassen selbst kleine Instanzen nicht mehr innerhalb
der (für eine gute Dev-Maschine bemessenen) Zeitlimits fertig werden. Fix: `NUM_SEARCH_WORKERS =
min(8, os.cpu_count() or 1)` passt sich automatisch der tatsächlichen Hardware an; zusätzlich
bekamen die drei betroffenen Tests großzügigere Zeitlimits (10-15s -> 25s), weil selbst mit
korrekt dimensionierten Workern 2 echte Kerne schlicht weniger Rechenleistung pro Sekunde liefern
als eine Dev-Maschine - kein Oversubscription-Problem mehr, aber trotzdem weniger Leistung.

**Bei der Fehlersuche dafür (Nutzerfrage: "ist der CP-SAT-Pfad noch korrekt, oder kann man da noch
was verbessern?") fiel ein tieferer, unabhängiger Modellierungsfehler auf**, der seit der
allerersten Version bestand: die Sonderbehandlung für die ALLERERSTE Fahrt eines Krans (von seiner
Startposition zur ersten Aufgabe, siehe Fund weiter oben zur Fahrt-Überschneidung) bot für die
Fahrkorridor-Prüfung nur EINE Ausweichmöglichkeit ("die störende Aufgabe beginnt komplett nach
unserer Ankunft") und begründete das Fehlen der zweiten ("die störende Aufgabe kann nicht VORHER
enden, ohne mit dem Wartefenster am Ursprung zu kollidieren") - diese Begründung stimmt aber nur,
wenn die URSPRUNGSPOSITION selbst ebenfalls zu nah an der störenden Aufgabe liegt. Liegt nur der
FAHRKORRIDOR zu nah dran, die Startposition selbst aber sicher, ist "die störende Aufgabe endet,
BEVOR unsere Fahrt überhaupt beginnt" eine völlig gültige, aber im Modell fehlende Alternative.

Bewiesen per Gegenbeispiel statt bloßer Vermutung: ein von Hand gebauter Zeitplan, den
`check_feasible` (die unabhängige, stetige Referenzprüfung) als vollständig sicher bestätigt,
wurde vom CP-SAT-Modell (Variablen exakt auf diesen Zeitplan fixiert, siehe
`test_first_travel_constraint_accepts_a_safe_schedule`) als **INFEASIBLE** zurückgewiesen. Die
praktische Folgewirkung: der exakte Löser konnte in genau dieser Konstellation ein tatsächlich
erreichbares (und ggf. besseres) Optimum übersehen und stattdessen unnötig lange Wartezeit
erzwingen oder länger für den Optimalitätsbeweis brauchen. Fix in
[quaycrane_cp_solver.py](quaycrane_cp_solver.py): die Fahrkorridor-Prüfung bietet jetzt - wie der
allgemeine Aufgabe-gegen-Aufgabe-Fall es schon immer tat - echte "davor ODER danach"-Alternativen
(`AddBoolOr` statt einer harten Gleichung). Der Wartefenster-Fall selbst bleibt bewusst einseitig:
dessen Fenster beginnt bei t=0, ein "davor" existiert dort tatsächlich nicht.

Modell-Aufbau dafür in `build_model()` aus `solve_exact()` herausgelöst - eigenständig aufrufbar,
u.a. um in genau diesem Test gezielt Variablen zu fixieren und die Machbarkeit isoliert zu prüfen,
ohne den ganzen Lösungsprozess anzustoßen.

## Fund: der exakte Löser lief automatisch mit und bremste jede Regler-Änderung aus

Ursprünglich lief `solve_exact` bei JEDER Änderung an den Reglern automatisch mit (Checkbox
"Exakte Lösung berechnen", standardmäßig aktiviert) - bei größeren Szenarien (viele Bays/Kräne)
kostete das mehrere Sekunden pro Interaktion, obwohl die drei eigenen Heuristiken zusammen unter
einer Millisekunde brauchen (siehe Performance-Fund oben). Da CP-SAT nur als Cross-Check dient,
nicht für das primäre Ergebnis gebraucht wird, ist automatisches Mitlaufen unnötig teuer.

Fix in [app.py](app.py): `_compute_all` in `_compute_heuristics` (läuft immer, schnell) und
`_compute_exact` (eigenständig `@st.cache_data`, läuft nur auf Klick) aufgeteilt. Ein Button
"🎯 Exakte Lösung berechnen" in der Seitenleiste ersetzt die Checkbox; das Ergebnis wird über
`st.session_state` an ein konkretes Szenario (Regler-Kombination) gebunden - ändert sich die
Konfiguration danach, wird die alte exakte Lösung NICHT mehr angezeigt (sie gehörte zu einem
anderen Schiff), sondern ein Hinweis, erneut zu klicken. Mehrfaches Klicken für dasselbe
Szenario trifft dank `@st.cache_data` sofort den Cache, kein wiederholtes Lösen.

## Laufzeit des exakten Lösers

Neu gemessen (heutiger Code; 3 Zufalls-Seeds 0-2 je Zelle, Standardwerte, Sicherheitsabstand 1,
12 s Zeitlimit, CP-SAT mit 8 Suchpfaden auf einem Windows-Rechner mit 16 Kernen, ohne Hint, inkl.
Tie-Breaking-Ziel und Fahrt-Non-Crossing-Constraints; Median der Laufzeit; Zeiten hängen von der
Hardware ab):

| Bays | 2 Kräne | 3 Kräne | 4 Kräne |
|---|---|---|---|
| 8  | 0,5 s (3/3 optimal) | 0,7 s (3/3 optimal) | 0,5 s (3/3 optimal) |
| 12 | Zeitlimit (0/3 optimal, Lösung vorhanden) | 8,9 s (3/3 optimal) | 4,9 s (3/3 optimal) |
| 16 | Zeitlimit (0/3 optimal, Lösung vorhanden) | Zeitlimit (0/3 optimal, Lösung vorhanden) | Zeitlimit (0/3 optimal, Lösung vorhanden) |
| 20 | Zeitlimit, 0/3 mit Lösung | Zeitlimit, 0/3 mit Lösung | Zeitlimit, 0/3 mit Lösung |

Auffällig: bei gleicher Bayzahl wird das Modell mit **mehr Kränen leichter** (12 Bays: Zeitlimit,
8,9 s, 4,9 s für 2, 3, 4 Kräne). Das ist keine Garantie für andere Größen und Seeds (drei Instanzen
je Zelle); denkbare Erklärung, nicht geprüft: wenige Kräne lassen dem Solver weniger Ausweichmöglichkeiten
bei den paarweisen Non-Crossing-Constraints. Deshalb wie im übrigen Portfolio üblich: eine feste
Zeitschranke statt eines größenbasierten Cutoffs - die App kennzeichnet ein Zeitlimit-Ergebnis
mit Lösung als "beste gefundene, nicht bewiesen optimale Lösung", nie fälschlich als Optimum, und
meldet ein Zeitlimit ohne Lösung als solches.

Die Fahrt-Non-Crossing-Constraints (siehe oben) haben den Solver spürbar mehr gefordert als
zuvor - bei 20 Bays / 5 Kränen (Preset "Großes Schiff, viele Kräne") fand er ohne weitere
Hilfe manchmal innerhalb des Zeitlimits gar keine gültige Lösung mehr (Status UNKNOWN statt
FEASIBLE). Gegenmittel: `solve_exact` bekommt jetzt optional ein bereits bekanntes,
zulässiges Schedule als **CP-SAT-Hint** (`hint_tasks` - die App übergibt dafür immer das
Ergebnis von "Greedy + lokale Suche", siehe [app.py](app.py)) - gibt dem Solver sofort einen
gültigen Startpunkt statt bei null zu suchen. `EXACT_SOLVE_TIME_LIMIT_SECONDS` zusätzlich von
8 auf 12s angehoben, weil selbst mit Hint die reine *Bestätigung* der Zulässigkeit bei 20
Bays/5 Kränen noch über 8s brauchte. **Neu gemessen (heutiger Code):** das Preset "Großes Schiff,
viele Kräne" mit dem Hint "Greedy + lokale Suche" (145,0 min) lieferte in 3 von 3 Läufen innerhalb von
12 s keine Lösung (Zeitlimit ohne Ergebnis, 11,5-13,0 s); die App zeigt dann die Meldung "OR-Tools
hat innerhalb des Zeitlimits keine gültige Lösung gefunden". Die frühere Aussage, 12 s reichten bei
diesem Preset zuverlässig, ist damit nicht bestätigt.

## Fund: dieselbe Minuten-Metrik zeigte an verschiedenen Stellen unterschiedlich viele Nachkommastellen

Nutzer-Feedback: die Zahlen wirkten an unterschiedlichen Stellen der App inkonsistent. Ursache
waren zwei separate Probleme mit derselben Symptomatik:

1. **Formatierung.** Die Kopf-Kacheln ("Ihr kürzester Kranplan", "Lohnt sich ein zusätzlicher
   Kran?") und die Pro-Methode-Tabs rundeten Liegezeit/Wartezeit/Fahrzeit/Lastungleichgewicht
   mit `.0f` (ganze Minuten), während die Vergleichstabelle (`comparison_table()`) und der
   PDF-Export dieselben Werte mit `.1f` zeigten - je nachdem, wo man hinschaute, stand für
   dasselbe Ergebnis "107 min" oder "106,8 min". Fix: alle vier Stellen einheitlich auf `.1f`
   gebracht (`app.py`, [quaycrane_ui_panel.py](quaycrane_ui_panel.py)) - eine Nachkommastelle,
   weil Bearbeitungsdauern und Fahrzeiten im Modell selbst genuin gebrochene Werte annehmen
   (Moves × Zeit/Move, Bay-Abstand × Kranfahrzeit), keine künstliche Scheingenauigkeit.
2. **Tieferliegend, erst danach entdeckt:** selbst NACH dem Fix auf `.1f` zeigte die
   Vergleichstabelle weiterhin uneinheitlich viele Nachkommastellen - "112,5" neben "107" in
   derselben Spalte. Grund: `comparison_table()` gab die Werte als Python-Floats (`round(x, 1)`)
   zurück und überließ Streamlits Dataframe-Renderer die Formatierung - bei einem GLATTEN Wert
   (107.0) fällt die ".0" beim Rendern weg, bei einem echten Bruchwert (112.5) nicht. Ein
   Zwischenversuch, die Werte selbst als String zu formatieren (`f"{x:.1f}"`), half NICHT:
   Streamlit erkennt zahlenartige Strings und formatiert sie nochmal selbst, mit demselben
   Effekt. Erst `st.column_config.NumberColumn(format="%.1f")` (in `app.py`, als
   `COMPARISON_TABLE_COLUMN_CONFIG` an den `st.dataframe()`-Aufruf übergeben) erzwingt
   zuverlässig dieselbe Nachkommastellenzahl in jeder Zelle.

## Dateistruktur

| Datei | Inhalt |
|---|---|
| `app.py` | Streamlit-Hauptablauf: Presets im Hauptbereich, Sidebar-Einstellungen, Primäransicht, Kipppunkt-Sektion ("Lohnt sich ein zusätzlicher Kran?"), Methodenvergleich, Formulierungs-Expander |
| `quaycrane_constants.py` | Defaults, Regler-Grenzen, `PRESETS` |
| `quaycrane_presets.py` | `SettingSpec`/`SETTING_SPECS`, Permalink-Logik, Presets, Zufalls-Seed-Button |
| `quaycrane_scenario.py` | Zufällige Bay-Arbeitslasten und Kran-Startpositionen |
| `quaycrane_evaluation.py` | Schedule-Konstruktion (`build_schedule`, konstruktiv immer machbar), Machbarkeitsprüfung, Kennzahlen |
| `quaycrane_heuristic.py` | Naive Aufteilung, Zonenbalance (DP), Listenscheduling-Varianten, lokale Suche |
| `quaycrane_cp_solver.py` | Exakter CP-SAT-Löser (Google OR-Tools) |
| `quaycrane_visualization.py` | Kran-Trajektorien-Chart (Kernvisual), Methodenvergleich, Kran-Auslastung (Plotly) |
| `quaycrane_pdf_export.py` | PDF-Kranplan (`fpdf2`) |
| `quaycrane_ui_panel.py` | Wiederverwendbares Panel je Methode im Methodenvergleich-Expander |
| `tests/` | Machbarkeitsprüfung (inkl. handgebauter Verletzungsfälle), Heuristik-Eigenschaften über mehrere Szenarien, CP-SAT-Cross-Check |

## Verwandte Demos mit demselben mathematischen Modell

Verschiedene Themen im Portfolio teilen (fast) dasselbe Modell. Vor einer neuen Demo-Idee deshalb das
Modell vergleichen, nicht die Kulisse (Stand 2026-09-23):

- **Nichtüberholen/Blockieren auf gemeinsamer Bahn:** diese Demo ist der Referenzfall (Kräne auf einer Schiene,
  1-D). Dasselbe Modell steckt in jeder Idee, bei der sich Ressourcen gegenseitig behindern, etwa mehrere
  Kommissionierer in schmalen Gängen (offene Erweiterung der `order_batch-demo`, dort ein 2-D-Gangnetz).
- Die `doppelspiel-demo` gehört nicht dazu: sie ist ein Zwei-Stufen-Flow-Shop (Johnson), ein anderes Modell.

## Lokal ausführen

```bash
pip install -r requirements-dev.txt
streamlit run app.py
```

Tests: `pytest tests/ -v`

---

Diese Demo ist Teil des Portfolios von [Sebastian Hanisch](https://sebastianhanisch.net) – Operations Research und Machine Learning ([Über mich](https://sebastianhanisch.net/ueber-mich.html)). Mehr zum Thema: [Hafenlogistik optimieren](https://sebastianhanisch.net/hafenlogistik-optimierung.html).
