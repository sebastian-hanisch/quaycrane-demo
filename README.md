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
  das mehrere Sekunden dauern, während die drei Heuristiken durchweg unter einer Millisekunde
  brauchen (siehe Performance-Fund weiter unten).

Die Primäransicht zeigt **dynamisch** die bei den aktuellen Reglereinstellungen tatsächlich
schnellste Methode (unter den drei Heuristiken) – keine wird pauschal bevorzugt.

## Fund: naives Listenscheduling nach Arbeitslast (LPT) verliert gegen die naive Baseline

Erste Fassung des Greedy-Verfahrens war klassisches **LPT-Listenscheduling** (Longest Processing
Time first): Bays absteigend nach Dauer sortiert, jede an die Brücke mit frühestmöglicher
Fertigstellung. Für "normale" parallele Maschinen ohne Interferenz ist das eine bewährte,
~4/3-approximative Heuristik. Hier schnitt sie in mehreren Testszenarien **schlechter** ab als
die naive gleichmäßige Aufteilung – z. B. bei 10 Bays / 3 Kränen / Sicherheitsabstand 1 (Seed 3):
Naive 94,3 min, LPT-Greedy **138,8 min** (110 min reine Interferenz-Wartezeit), bei 12 Bays /
4 Kränen / Sicherheitsabstand 2 (Seed 5): Naive 95,8 min, LPT-Greedy **142,2 min** (164,5 min
Wartezeit).

**Ursache:** LPT wählt die Kranzuordnung rein nach Arbeitslast, ohne auf die räumliche Lage der
Bays zu achten. Weil Bay-Index gleichzeitig die Position auf der Schiene ist, führt das zu einer
über das Schiff verstreuten Zuordnung – jede neu hinzukommende Aufgabe kollidiert mit bereits
verteilten Aufgaben benachbarter Kräne und muss warten, bis diese fertig sind. Ein Wechsel der
Sortierreihenfolge (Positions- statt Arbeitslast-Reihenfolge, `greedy_construction(..., "spatial")`)
milderte das nicht zuverlässig – auch räumlich sortierte Listenscheduling-Zuweisung kann je nach
Instanz zwischen Kränen hin- und herspringen.

**Fix:** die Zonenbalance-Konstruktion (`balanced_zone_construction`) ersetzt das Listenscheduling
als primäre Greedy-Methode. Da sie das Schiff strukturell in nicht überlappende, zusammenhängende
Zonen zerlegt, bleibt Kran-Interferenz praktisch immer bei 0 – bei denselben zwei Beispielen
liefert sie 94,3 min bzw. 95,8 min (identisch mit der naiven Aufteilung in diesen Fällen, da die
Arbeitslast dort schon recht gleichmäßig verteilt war) und die anschließende lokale Suche
verbessert von dort auf 88,8 min bzw. 93,8 min – nahe am exakten Optimum (88,8 min bzw. 93,2 min).
Die LPT- und positions-sortierten Listenscheduling-Varianten bleiben als zusätzliche Startpunkte
für die lokale Suche erhalten (`greedy_and_polish` probiert alle drei und startet von der
besten), tragen aber in der Praxis selten bei.

## Fund: CP-SAT ließ Kräne grundlos warten, obwohl der Makespan optimal war

Nutzerhinweis: im Preset "Mittleres Schiff, Normalbetrieb" zeigte die Exakt-Lösung manchmal
sichtbare Wartezeit ganz am Anfang der Kran-Trajektorien, obwohl die Kräne dort räumlich weit
auseinander lagen - visuell sollte dort keine Interferenz auftreten. Nachgestellt: dieselbe
Instanz fünfmal hintereinander mit `solve_exact` gelöst, der Makespan blieb jedes Mal exakt
106 min, die ausgewiesene Wartezeit schwankte aber zwischen 0,0 und 1,1 min.

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
Lösung mit grundlosem Leerlauf. Fünf Wiederholungen derselben Instanz danach: Makespan immer
106 min, Wartezeit immer 0,0 min (`test_exact_solution_has_no_spurious_wait`). Nebeneffekt: das
zweite Ziel macht den Beweis der Optimalität in Grenzfällen etwas schwerer (siehe Laufzeittabelle
unten, die Standard-Presets sind davon nicht spürbar betroffen).

## Fund: Non-Crossing wurde nur zwischen Aufgaben geprüft, nie während der Fahrt dazwischen

Nutzerhinweis: die Kran-Trajektorien im Chart dürfen sich laut eigener Beschreibung nie
kreuzen - trotzdem beobachtete ein Nutzer genau das, zusammen mit einer Wartezeit beim
kreuzenden Kran. Nachgestellt anhand des Presets "Mittleres Schiff, Normalbetrieb": Kran 1
bearbeitete Bay 3 bis t=77,5 min; Kran 2 fuhr im selben Zeitfenster (77,0-78,0 min) von Bay 4
zu Bay 2 - und durchquerte dabei zwangsläufig Position 3, exakt während Kran 1 dort noch
stand. Die ursprünglichen Non-Crossing-Constraints verglichen ausschließlich
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
`test_exact_solution_covers_first_travel_from_start_position`) und per Stichprobe bestätigt:
alle vier Presets je 3× frisch gelöst, `check_feasible` (siehe nächster Fund) jedes Mal ohne
Verletzung.

## Fund: die "sofort losfahren"-Konvention konnte selbst wieder Verletzungen erzeugen

Nebenbefund beim Härtetest von `check_feasible` gegen echte Fahrsegmente (siehe oben): bei
sehr langer erzwungener Wartezeit UND hohem Sicherheitsabstand konnte ein Kran, der laut
Konvention sofort zur Zielposition fährt und dort wartet, während der gesamten Wartezeit zu
nah an einem arbeitenden Nachbarkran stehen - z. B. 18 Bays / 5 Kräne / Sicherheitsabstand 3
(Regler-Maximum), Seed 5: ein Kran wartet 72,7 min lang an seiner ersten Zielposition, obwohl
ein Nachbarkran während dieser Zeit näher als der Sicherheitsabstand vorbeikommt.

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

**Ein tieferer, eigenständiger Fund dabei: manche Kranzuordnungen sind für KEINE Zeitplanung
schedulierbar.** Ein rein lastbasiertes Greedy-Verfahren (LPT) kann bei engem
Sicherheitsabstand zwei benachbarten Kränen Bays zuweisen, zwischen denen es strukturell keine
zulässige Zeitplanung mehr gibt - unabhängig davon, wie clever konstruiert wird (`quaycrane_evaluation.ScheduleInfeasibleError`). Kein Konstruktionstrick kann das lösen, nur
eine andere Kranzuordnung. Fix: `build_schedule_robust`
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
(`tests/test_heuristic.py`). Zusätzlich per Sweep über hunderte Bay-/Kran-/Seed-Kombinationen
bei maximalem Sicherheitsabstand verifiziert: 0 verbleibende Verletzungen.

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

Nebeneffekt: die neue Konstruktion ist auch spürbar schneller, weil jede Platzierung nur noch
gegen die tatsächlich betroffenen Segmente (die des NEU eingefügten Krans-Schritts, nicht das
gesamte bisherige Schedule neu aufgebaut) geprüft wird, statt bei jedem Kandidaten das komplette
Zwischenergebnis neu zu rekonstruieren. Nachgemessen bei 24 Bays / 5 Kränen (größte von der App
erlaubte Größe): `build_schedule` im Mittel 1.45ms -> 0.28ms pro Aufruf (Worst Case im Sweep
9.8ms -> 0.5ms), `greedy_and_polish` (inkl. voller lokaler Suche, 400 Züge) 0.70s -> 0.10s -
knapp 7x schneller bei jedem Preset-/Regler-Wechsel in der App.

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

Nachgemessen (3 Zufallsinstanzen je Zelle, 12s Zeitlimit, `CP-SAT`, inkl. Tie-Breaking-Ziel UND
Fahrt-Non-Crossing-Constraints):

| Bays | 2 Kräne | 3 Kräne | 4 Kräne |
|---|---|---|---|
| 8  | 0,07 s (3/3 optimal) | 0,05 s (3/3 optimal) | 0,05 s (3/3 optimal) |
| 12 | ~7 s (uneinheitlich optimal) | ~1 s (3/3 optimal) | 0,2 s (3/3 optimal) |
| 16 | Zeitlimit | Zeitlimit | ~8 s (uneinheitlich optimal) |
| 20 | Zeitlimit | Zeitlimit | Zeitlimit |

Auffällig: **12 Bays / 2 Kräne ist schwerer als 16 Bays / 4 Kräne** – wie schon in anderen Demos
dieses Portfolios beobachtet, korreliert die Schwierigkeit eines NP-schweren Scheduling-Modells
nicht sauber mit der Instanzgröße (hier vermutlich, weil wenige Kräne dem Solver weniger
alternative Zuordnungen zum Ausweichen lassen, wenn die paarweisen Non-Crossing-Constraints
greifen). Deshalb wie im übrigen Portfolio üblich: eine feste Zeitschranke statt eines
größenbasierten Cutoffs – die App kennzeichnet ein Zeitlimit-Ergebnis bereits korrekt als
"beste gefundene, nicht bewiesen optimale Lösung", nie fälschlich als Optimum.

Die Fahrt-Non-Crossing-Constraints (siehe oben) haben den Solver spürbar mehr gefordert als
zuvor - bei 20 Bays / 5 Kränen (Preset "Großes Schiff, viele Kräne") fand er ohne weitere
Hilfe manchmal innerhalb des Zeitlimits gar keine gültige Lösung mehr (Status UNKNOWN statt
FEASIBLE). Gegenmittel: `solve_exact` bekommt jetzt optional ein bereits bekanntes,
zulässiges Schedule als **CP-SAT-Hint** (`hint_tasks` - die App übergibt dafür immer das
Ergebnis von "Greedy + lokale Suche", siehe [app.py](app.py)) - gibt dem Solver sofort einen
gültigen Startpunkt statt bei null zu suchen. `EXACT_SOLVE_TIME_LIMIT_SECONDS` zusätzlich von
8 auf 12s angehoben, weil selbst mit Hint die reine *Bestätigung* der Zulässigkeit bei 20
Bays/5 Kränen noch zuverlässig über 8s brauchte.

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

## Lokal ausführen

```bash
pip install -r requirements-dev.txt
streamlit run app.py
```

Tests: `pytest tests/ -v`

---

Teil des [Operations-Research-Demo-Portfolios](https://sebastianhanisch.net/demos.html) von
[Sebastian Hanisch](https://sebastianhanisch.net) – Operations Research und Machine Learning.
Interesse an einer maßgeschneiderten Lösung? [Kontakt aufnehmen](https://sebastianhanisch.net/kontakt.html).
