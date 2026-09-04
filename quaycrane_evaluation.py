"""Schedule-Konstruktion aus einer Einfüge-Reihenfolge, Machbarkeitsprüfung und Kennzahlen.

Eine Lösung wird als `order` repräsentiert: eine Liste von (bay, crane)-Paaren in der
Reihenfolge, in der sie einem Kran zugewiesen werden. Diese Reihenfolge legt sowohl die
Kranzuordnung als auch - je Kran - die Bearbeitungsreihenfolge fest (Teilfolge der `order`,
eingeschränkt auf diesen Kran). `build_schedule` baut daraus einen konkreten Zeitplan, der -
sofern für diese KRANZUORDNUNG überhaupt irgendeine zulässige Zeitplanung existiert - IMMER eine
findet: jede Aufgabe startet frühestens, wenn ihr Kran frei ist (inkl. Fahrzeit von der letzten
Position), und wird zusätzlich so weit nach hinten geschoben, bis kein bereits eingeplanter Kran
verletzt wird (Non-Crossing-Regel). Eigener Fund: die KRANZUORDNUNG selbst kann - unabhängig von
jeder Zeitplanung - strukturell unmöglich sein (z.B. weist ein rein lastbasiertes Greedy-
Verfahren wie LPT zwei benachbarten Kränen Bays zu, die bei engem Sicherheitsabstand keinerlei
gemeinsame sichere Zeitplanung mehr zulassen - siehe `ScheduleInfeasibleError`); das ist keine
Lücke in der Konstruktion, sondern eine Eigenschaft der `order` selbst - `build_schedule` meldet
das dann statt eine unzulässige Lösung zurückzugeben."""

from collections import defaultdict
from dataclasses import dataclass


class ScheduleInfeasibleError(Exception):
    """Für DIESE Kranzuordnung (`order`) existiert keine zulässige Zeitplanung, für keinen
    Einfügezeitpunkt - unabhängig davon, wie clever construiert wird (siehe
    `_safe_breakpoint_departure`s Dokumentation für ein konkretes Beispiel: zwei benachbarte
    Kräne, deren zugewiesene Bays bei engem Sicherheitsabstand keinen gemeinsamen sicheren
    Zeitplan mehr zulassen). Aufrufer, die mehrere Kandidaten-`order`s vergleichen (siehe
    quaycrane_heuristic.py), behandeln dies als "unendlich schlecht" statt abzustürzen."""


@dataclass(frozen=True)
class Task:
    bay: int
    crane: int
    start: float
    end: float
    wait: float  # durch Kran-Interferenz verursachte zusätzliche Wartezeit (>= 0)
    departure: float = None  # wann der Kran fuer DIESE Aufgabe von seiner vorherigen Position
    # losgefahren ist - explizit statt aus `wait` rueckgerechnet, weil ein einzelner
    # `wait`-Skalar nicht unterscheidet, OB gewartet wurde, weil der Kran am Ursprung blieb,
    # am Ziel wartete, oder (moeglich seit der Intervall-Vermeidungs-Konstruktion in
    # `_safe_departure`/`_safe_start`) eine Mischung aus beidem - `crane_position_segments`
    # braucht die tatsaechlich gewaehlte Abfahrt, um dieselbe Trajektorie zu zeichnen/pruefen,
    # die beim Bauen als sicher bestaetigt wurde. None (Default) bedeutet "unbekannt, nimm
    # spaetestmoegliche Abfahrt an" - sicher fuer CP-SAT-Ergebnisse (siehe quaycrane_cp_solver.py,
    # das genau dieses Fenster erzwingt) und fuer Tests, die Task() direkt mit fertigen
    # start/end-Werten bauen.


def _intervals_overlap(a_start, a_end, b_start, b_end):
    return a_start < b_end and b_start < a_end


def _advance_past_forbidden(t0, forbidden):
    """t0 vorschieben, bis es in keinem der `forbidden`-Intervalle [lo, hi) (exklusiv an beiden
    Enden) mehr liegt - durch Sprung auf das jeweilige `hi`, nicht durch schrittweises Wachsen
    (siehe `_safe_departure`-Docstring für den Grund). `hi == inf` bedeutet "ab `lo` für immer
    verboten"; wird t0 dort hineingeschoben, gibt es keine gültige Lösung mehr (None). Endet
    garantiert nach höchstens len(forbidden) Sprüngen (jeder Sprung landet auf einem größeren
    Intervall-Ende als zuvor, endlich viele davon)."""
    t = t0
    for _ in range(len(forbidden) + 1):
        moved = False
        for f_lo, f_hi in forbidden:
            if f_lo < t < f_hi:
                if f_hi == float("inf"):
                    return None
                t = f_hi
                moved = True
                break
        if not moved:
            return t
    return None


def _range_safe_against_segment(crane, a, b, seg, margin):
    """Prüft, ob MEIN Aufenthalt bei Position(en) [a, b] (a==b für einen festen Punkt, a<b für
    eine Fahrt, die den Bereich überstreicht) mit Sicherheitsabstand von `seg` entfernt bleibt -
    unabhängig davon, ob `seg` selbst ein fester Punkt (Warten/Bearbeitung) oder eine Fahrt
    (Position ändert sich linear von p0 zu p1) ist. Da beide Seiten affine Funktionen der Zeit
    sind, reicht die Prüfung an den beiden Enden von `seg` (dieselbe Begründung wie in
    `_segments_violate_margin`) - deckt damit auch ab, dass eine bereits eingeplante Aufgabe
    WÄHREND ihrer eigenen Fahrt verletzt werden könnte, nicht nur während ihrer Bearbeitung."""
    seg_crane, _, p0, _, p1, _ = seg
    if crane < seg_crane:
        return (b + margin <= p0) and (b + margin <= p1)
    return (p0 + margin <= a) and (p1 + margin <= a)


def _segments_with_unassigned_cranes(instance, tasks_so_far):
    """Wie `crane_position_segments`, ergänzt um einen virtuellen "wartet an der Startposition"-
    Eintrag für jeden Kran, der in `tasks_so_far` noch KEINE einzige Aufgabe hat.

    Eigener Fund, der Wurzelgrund hinter einer ganzen Kette vorheriger Fixversuche: ein Kran mit
    noch keiner zugewiesenen Aufgabe ist für `crane_position_segments` (das nur über bereits
    vorhandene `tasks`-Einträge iteriert) schlicht unsichtbar - obwohl er die ganze Zeit
    physisch an seiner festen Startposition steht. Solange seine erste Aufgabe noch nicht
    eingefügt wurde, konnte JEDE ANDERE, bereits eingefügte Aufgabe ungehindert zu nah an ihm
    vorbeiplanen; die Verletzung wurde erst nachträglich sichtbar (in `check_feasible`, das
    `crane_position_segments` auf das VOLLSTÄNDIGE Schedule anwendet, wo alle Kräne sichtbar
    sind), nie aber während der Konstruktion selbst verhindert. Der virtuelle Eintrag nutzt statt
    "für immer" einen großzügigen, aber endlichen Zeithorizont (siehe `_construction_horizon`) -
    "für immer" würde die Rückkopplungs-Logik in `earliest_feasible_start` (die einen endlichen
    `clear_time` zum Weiterkommen braucht) in eine Endlosschleife treiben."""
    segments = list(crane_position_segments(instance, tasks_so_far))
    present = {seg[0] for seg in segments}
    horizon = _construction_horizon(instance)
    for c in range(instance.n_cranes):
        if c not in present:
            pos = instance.crane_start_positions[c]
            segments.append((c, 0.0, pos, horizon, pos, "wait"))
    return segments


def _construction_horizon(instance):
    """Großzügige, aber endliche obere Schranke für die Gesamtdauer - dieselbe Größenordnung wie
    der Horizont im CP-SAT-Modell (siehe quaycrane_cp_solver.py), hier nur in echten Minuten
    statt skalierten Ganzzahlen, für den virtuellen "noch nicht zugewiesen"-Kran-Eintrag."""
    total_work = sum(b.duration for b in instance.bays)
    max_travel = instance.travel_time_per_bay * instance.n_bays
    return total_work + instance.n_bays * max_travel + 1.0


def _safe_departure(instance, tasks_so_far, crane, prev_end, prev_pos, bay):
    """Frühester Abfahrtszeitpunkt d >= prev_end, ab dem `crane` von `prev_pos` in Richtung
    `bay` losfahren darf, ohne dass weder das Warten bei `prev_pos` (Fenster [prev_end, d])
    noch die anschließende Fahrt (Fenster [d, d+Fahrzeit], überstreicht alle Positionen
    zwischen `prev_pos` und `bay`) eine bereits eingeplante Aufgabe eines anderen Krans verletzt
    - AUCH nicht während DEREN Fahrt (siehe `_range_safe_against_segment`; ein früherer Fund:
    das Prüfen nur gegen die Bearbeitungsintervalle anderer Aufgaben übersah, dass eine bereits
    eingeplante Aufgabe selbst noch mitten in ihrer eigenen Anfahrt sein kann, wenn eine neue,
    später eingefügte Aufgabe geprüft wird - Einfügereihenfolge und zeitliche Reihenfolge
    stimmen nicht überein). None, falls keine Abfahrt sicher ist.

    Frühere Fassung schob `d` einfach auf `t.end` vor, wenn ein Konflikt auftrat - das
    konvergiert NICHT: liegt eine störende Aufgabe/Fahrt vollständig im Wartefenster
    [prev_end, d], bleibt sie dort für jedes GRÖSSERE d ebenfalls enthalten (das Fenster wächst
    nur noch) - ein Kran, der die ganze Zeit stehen bleibt, war während der Störung
    zwangsläufig anwesend, egal wie lange er danach noch wartet. Die einzige Möglichkeit, ihr
    zu entgehen, ist eine Abfahrt VOR ihrem Beginn - deshalb hier echte Intervall-Vermeidung
    statt Vorschieben: für jede kritische Störung wird ein verbotener Bereich für `d` gesammelt,
    und `d` wird auf das nächste erlaubte Ende gesprungen.

    Gibt `(d, clear_time)` zurück: bei Erfolg ist `d` die gefundene Abfahrt und `clear_time`
    None; scheitert die Suche (weil `prev_end` bereits in einer "für immer verboten"-Zone
    liegt, siehe oben), ist `d` None und `clear_time` der früheste Zeitpunkt, ab dem KEINE der
    hier gefundenen Für-immer-Zonen mehr aktiv ist (das Maximum ihrer jeweiligen `t1`) - der
    Aufrufer (`earliest_feasible_start`) kann damit `prev_end` genau wie beim `_safe_start`-
    Fehlschlag anheben und erneut versuchen, statt sofort aufzugeben. Eigener Fund: ohne dieses
    Retry blieb ein Kran, dessen fest vorgegebene Startposition zufällig dauerhaft zu nah an
    einem bereits vollständig eingeplanten anderen Kran lag, für IMMER ohne Lösung, obwohl eine
    spätere Abfahrt (nach Ende von dessen Aktivität dort) längst sicher gewesen wäre."""
    margin = instance.safety_margin
    travel = instance.travel_time(prev_pos, bay)
    lo, hi = (prev_pos, bay) if prev_pos <= bay else (bay, prev_pos)

    forbidden = []
    blocking_ends = []
    for seg in _segments_with_unassigned_cranes(instance, tasks_so_far):
        if seg[0] == crane:
            continue
        t0, t1 = seg[1], seg[3]
        # "Für immer verboten ab t0" gilt nur, wenn das Segment relativ zu prev_end überhaupt
        # noch (ganz oder teilweise) in der Zukunft liegt - ist es schon vorbei, bevor unser
        # Wartefenster überhaupt beginnt (t1 <= prev_end), kann es nie überlappen und darf
        # keinen Konflikt erzeugen (eigener Fund: ohne dieses Gate blockierte selbst ein Krans
        # allererste, längst abgeschlossene Anfahrt jede spätere Abfahrt für immer).
        if t1 > prev_end and not _range_safe_against_segment(crane, prev_pos, prev_pos, seg, margin):
            forbidden.append((t0, float("inf")))
            blocking_ends.append(t1)
        if travel > 1e-9 and not _range_safe_against_segment(crane, lo, hi, seg, margin):
            forbidden.append((t0 - travel, t1))

    d = _advance_past_forbidden(prev_end, forbidden)
    if d is not None:
        return d, None
    return None, max(blocking_ends, default=None)


def _dangerous_segments(instance, tasks_so_far, crane, bay, margin):
    """Alle Segmente anderer Kräne, zu denen die feste Position `bay` den Sicherheitsabstand
    verletzt - unabhängig von der Zeit. Der Kran darf sich während der aktiven Zeit eines
    solchen Segments NIE an `bay` aufhalten (auch nicht am Rand, siehe `_safe_start`-Docstring:
    "einmal drin, nie wieder sicher heraus" gilt hier genauso wie beim Warten am Ursprung)."""
    return [
        s
        for s in _segments_with_unassigned_cranes(instance, tasks_so_far)
        if s[0] != crane and not _range_safe_against_segment(crane, bay, bay, s, margin)
    ]


def _safe_start(instance, dangerous, duration, arrival):
    """Frühester Bearbeitungsbeginn start >= arrival (Ankunft bei `bay`), sodass der GESAMTE,
    ununterbrochene Aufenthalt an `bay` - Warten am Ziel [arrival, start] UND Bearbeitung
    [start, start+Dauer] zusammen, denn der Kran kann sich zwischendurch nicht "unsichtbar
    machen" - keines der `dangerous`-Segmente (siehe `_dangerous_segments`) verletzt. Da der
    Aufenthalt an seinem linken Ende (arrival) fest ist und nur nach rechts wächst, gilt
    dieselbe Nicht-Konvergenz-Logik wie bei `_safe_departure`: ein einmal (auch nur teilweise)
    hineinreichender Aufenthalt bleibt es für jedes größere `start` auch - deshalb "verboten ab
    t0 - Dauer, für immer" statt Vorschieben. Findet dieselbe Position gar keinen sicheren
    Zeitpunkt (weil sie über die GESAMTE Zeit zwischen `arrival` und dem Ende der letzten
    gefährlichen Aktivität dort nicht sein darf, aber auch nicht rechtzeitig VOR der ersten
    fertig werden kann), gibt es None zurück - der Aufrufer (`earliest_feasible_start`) probiert
    dann eine komplett spätere Anreise, statt hier weiterzusuchen."""
    forbidden = [(s[1] - duration, float("inf")) for s in dangerous if s[3] > arrival]

    start = _advance_past_forbidden(arrival, forbidden)
    return start


def earliest_feasible_start(instance, tasks_so_far, crane, bay, prev_end, prev_pos):
    """Frühester Bearbeitungsbeginn für `crane` an `bay`, ausgehend davon, dass der Kran ab
    `prev_end` bei `prev_pos` frei ist - ohne eine bereits eingeplante Aufgabe eines anderen
    Krans zu verletzen, weder während der Bearbeitung noch während Fahrt/Wartezeit davor
    (Non-Crossing vollständig, siehe `_safe_departure`/`_safe_start`). Gibt `(departure, start)`
    zurück - `departure` muss zusammen mit `start` in die `Task` übernommen werden, sonst kann
    `crane_position_segments` die tatsächlich als sicher bestätigte Trajektorie nicht mehr
    rekonstruieren (eigener Fund: ein einzelner `wait`-Skalar reicht dafür nicht, siehe
    `Task.departure`-Docstring).

    Wenn `_safe_start` für eine gegebene Ankunftszeit keine Lösung findet, liegt das daran, dass
    `bay` für den GESAMTEN ununterbrochenen Aufenthalt (Zielwarten + Bearbeitung zusammen, der
    Kran kann sich dazwischen nicht "unsichtbar machen") dauerhaft zu nah an einem anderen Kran
    liegt - Vorschieben allein hilft dann nicht (siehe `_safe_start`-Docstring). Einzige Rettung:
    komplett später losfahren, sodass die Ankunft erst nach dem Ende JEDER dafür gefährlichen
    Aktivität liegt - hier als Neuversuch mit angehobenem `prev_end` umgesetzt (eigener Fund,
    reproduziert am Preset mit maximalem Sicherheitsabstand + 5 Kränen: ohne diesen Neuversuch
    verharrte die Suche bei einer Ankunftszeit, die zwar für die Abfahrt/Anfahrt sicher war, für
    die Zielposition selbst aber nie eine gültige Lösung hätte finden können). Dieselbe
    Eskalation greift jetzt auch, wenn bereits `_safe_departure` selbst keine Abfahrt findet
    (eigener Fund: eine fest vorgegebene Kran-Startposition kann rein zufällig dauerhaft zu nah
    an einer bereits vollständig eingeplanten fremden Aktivität liegen - ohne Neuversuch blieb
    das für immer unlösbar, obwohl eine Abfahrt NACH deren Ende langst sicher gewesen wäre).

    `(None, None)`, falls selbst nach allen Neuversuchen keine sichere Lösung existiert - das
    bedeutet nicht, dass das Gesamtproblem unlösbar ist, nur dass DIESE Zuordnung es an dieser
    Stelle nicht hergibt; Aufrufer weichen dann auf eine garantiert sichere Rückfallposition aus
    (siehe `build_schedule`)."""
    margin = instance.safety_margin
    duration = instance.bays[bay].duration
    attempt_prev_end = prev_end

    for _ in range(len(tasks_so_far) + 2):
        d, dep_clear_time = _safe_departure(instance, tasks_so_far, crane, attempt_prev_end, prev_pos, bay)
        if d is None:
            if dep_clear_time is None or dep_clear_time <= attempt_prev_end:
                return None, None
            attempt_prev_end = dep_clear_time
            continue
        arrival = d + instance.travel_time(prev_pos, bay)
        dangerous = _dangerous_segments(instance, tasks_so_far, crane, bay, margin)
        start = _safe_start(instance, dangerous, duration, arrival)
        if start is not None:
            return d, start

        clear_time = max((s[3] for s in dangerous), default=None)
        if clear_time is None or clear_time <= attempt_prev_end:
            return None, None
        attempt_prev_end = clear_time
    return None, None


def _fully_sequential_schedule(instance, order):
    """Letztes Sicherheitsnetz (siehe `build_schedule`) - baut jede Aufgabe einzeln in
    rundenweise verschränkter Reihenfolge auf (siehe `_round_robin_interleave` - vermeidet die
    Kaskade aus unnötiger Verzögerung, die reine Blockreihenfolge auslöst) und verifiziert nach
    JEDER Einfügung sofort mit `check_feasible` gegen die ECHTE Instanz, statt sich (wie
    `_build_schedule_incremental`) auf die eigene, an mehreren Randfällen bereits als lückenhaft
    erwiesene Vorab-Sicherheitslogik zu verlassen.

    Verletzt eine Einfügung trotzdem, wird NICHT diskutiert, sondern per Breakpoint-Suche auf
    eine beweisbar sichere Abfahrtszeit ausgewichen (siehe `_safe_breakpoint_departure`) - eigener
    Fund: weder "warten bis zum Ende der spätesten bislang eingeplanten Aktivität" NOCH "sofort
    losfahren" allein reichen als pauschale Formel, siehe dort für die Begründung. Erst das
    tatsächliche AUSPROBIEREN jedes in Frage kommenden Zeitpunkts, JEWEILS gegen die komplette
    Instanz verifiziert, ist wasserdicht.

    Frühere Fassungen scheiterten daran, SICHERHEIT aus der KONSTRUKTIONSREIHENFOLGE ableiten zu
    wollen (rein nacheinander abarbeiten; fiktiv weit auseinandergezogene Startpositionen) -
    beide Male ließ sich ein Randfall finden, in dem die Annahme nicht hielt. Dieser Fund macht
    daraus die Konsequenz: nicht mehr ANNEHMEN, dass eine Konstruktion sicher ist, sondern nach
    jedem Schritt tatsächlich PRÜFEN - mit derselben Prüfung, die auch `build_schedule` am Ende
    verwendet, also nichts, das nicht bereits an anderer Stelle gegen echte Fälle verifiziert
    wäre."""
    tasks = {}
    crane_last_end = {c: 0.0 for c in range(instance.n_cranes)}
    crane_last_pos = {c: instance.crane_start_positions[c] for c in range(instance.n_cranes)}
    for bay, crane in _round_robin_interleave(instance, order):
        prev_end, prev_pos = crane_last_end[crane], crane_last_pos[crane]
        duration = instance.bays[bay].duration

        def _verified(departure, start):
            end = start + duration
            candidate = dict(tasks)
            candidate[bay] = Task(bay=bay, crane=crane, start=start, end=end, wait=0.0, departure=departure)
            return len(_crossing_and_overlap_violations(instance, candidate)) == 0

        departure, start = _safe_breakpoint_departure(instance, tasks, crane, bay, prev_end, prev_pos, _verified)

        end = start + duration
        tasks[bay] = Task(bay=bay, crane=crane, start=start, end=end, wait=0.0, departure=departure)
        crane_last_end[crane] = end
        crane_last_pos[crane] = bay
    return tasks


def _safe_breakpoint_departure(instance, tasks_so_far, crane, bay, prev_end, prev_pos, verified):
    """Robuste Brachial-Suche: probiert als Abfahrtszeit JEDEN Zeitpunkt durch, an dem sich der
    Sicherheitsstatus irgendeines bereits eingeplanten (ECHTEN) Segments ändern KÖNNTE (dessen
    Start oder Ende) - dazwischen kann sich nichts ändern, da jede Position eine affine Funktion
    der Zeit ist (siehe `_segments_violate_margin`), die Liste deckt also lückenlos jede mögliche
    sicher/unsicher-Grenze ab. Der letzte Kandidat (nach dem Ende JEDER echten Aktivität) ist per
    Konstruktion sicher - die Suche geht also nie leer aus.

    Nutzt bewusst NUR echte, bereits eingeplante Segmente (`crane_position_segments`), NICHT die
    virtuellen "für immer an der Startposition"-Platzhalter für noch unzugewiesene Kräne (siehe
    `_segments_with_unassigned_cranes`, von `earliest_feasible_start` genutzt). Eigener Fund: in
    der allerersten Runde der rundenweisen Einfügung (siehe `_round_robin_interleave`) hat der
    JEWEILS ZUERST eingefügte Kran quasi immer irgendeinen noch-virtuellen Nachbarn in
    Sicherheitsabstands-Reichweite (bei 5 Kränen auf engem Raum unvermeidlich) - `earliest_
    feasible_start` eskaliert dann auf den fiktiven Konstruktions-Horizont, OBWOHL dieser
    Nachbar in Wirklichkeit im NÄCHSTEN Einfügeschritt (derselbe Runde) längst selbst losfährt.
    Diese fiktive, weit überzogene Verzögerung wird dazu noch als "sicher" akzeptiert (nichts
    Echtes existiert ja noch, das sie widerlegen könnte) und blockiert dann UNRETTBAR jede
    spätere, echte Aufgabe in der Nähe - reproduziert am Extrempreset (5 Kräne, max.
    Sicherheitsabstand, kurzes Schiff, dichte Kran-Startpositionen). Da dieser Fallback ohnehin
    NUR gegen echte Daten verifiziert (`verified`, siehe `_crossing_and_overlap_violations`),
    bringt die virtuelle Vorsicht hier keinen Sicherheitsgewinn, nur unnötige/schädliche
    Verzögerung - deshalb ausschließlich echte Segmente.

    Zwei einfachere Formel-Fallbacks wurden verworfen: weder "sofort losfahren" noch "warten bis
    zum Ende der spätesten bislang eingeplanten Aktivität" ist für sich pauschal sicher - im
    ersten Fall kann die Fahrt selbst noch verletzen, im zweiten Fall verletzt schon das WARTEN
    am Ursprung, wenn diese Position dauerhaft (nicht nur vorübergehend) zu nah an einer bereits
    eingeplanten Aktivität eines anderen Krans liegt (spätere Abfahrt hilft dann nicht - der
    Kran war während der Störung ohnehin die ganze Zeit dort). Erst das tatsächliche AUSPROBIEREN
    jedes in Frage kommenden Zeitpunkts, jeweils gegen die komplette Instanz verifiziert, ist
    wasserdicht."""
    # Eigener Fund: die Margin-Prüfung (`_segments_violate_margin`) wertet beide Fensterenden
    # EINSCHLIESSLICH aus (kein offenes Intervall) - eine Abfahrt GENAU auf das Ende eines
    # gefährlichen Segments gelegt gilt dort noch als "während" dessen Aktivität und bleibt
    # verletzt. Jeder Kandidat, der von einem Segmentende abgeleitet ist, braucht deshalb einen
    # winzigen Sicherheitsabstand danach, um wirklich STRIKT danach zu liegen.
    epsilon = 1e-6
    real_segments = [s for s in crane_position_segments(instance, tasks_so_far) if s[0] != crane]
    real_ends = [s[3] for s in real_segments]
    horizon = max([_construction_horizon(instance), prev_end] + real_ends) + epsilon
    travel = instance.travel_time(prev_pos, bay)
    breakpoints = {prev_end, horizon}
    for seg in real_segments:
        if seg[1] >= prev_end:
            breakpoints.add(seg[1])
        if seg[3] >= prev_end:
            breakpoints.add(seg[3] + epsilon)

    for candidate_departure in sorted(breakpoints):
        candidate_start = candidate_departure + travel
        if verified(candidate_departure, candidate_start):
            return candidate_departure, candidate_start
    # Selbst der "horizon"-Kandidat (nach dem Ende JEDER bislang eingeplanten echten Aktivität)
    # scheitert nur, wenn schon das bloße WARTEN an `prev_pos` (unsere erzwungene, feste
    # Position, solange wir nicht abgefahren sind) dauerhaft zu nah an einer bereits
    # eingeplanten Aktivität liegt - dann hilft KEINE Abfahrtszeit, da wir während der ganzen
    # Störung ohnehin dort waren. Das ist keine lösbare Zeitplanungsfrage mehr, sondern zeigt:
    # DIESE Kranzuordnung selbst (`crane` auf `bay`, im Kontext der bereits committeten
    # Nachbar-Aufgaben) lässt für keinen Zeitpunkt eine sichere Lösung zu.
    raise ScheduleInfeasibleError(
        f"Für Kran {crane} an Bay {bay} existiert keine sichere Zeitplanung, gegeben die bereits "
        "eingeplanten Aufgaben anderer Kräne - die Kranzuordnung selbst ist hier unschedulierbar."
    )


def build_schedule(instance, order):
    """Baut per Konstruktion (siehe `_build_schedule_incremental`) einen Zeitplan und prüft ihn
    zum Schluss gegen `check_feasible` - dieselbe Prüfung, die auch die Tests und den
    CP-SAT-Cross-Check absichert, als Quelle der Wahrheit statt sich nur auf die eigene
    Konstruktionslogik zu verlassen. Sollte diese Prüfung dennoch fehlschlagen (mehrere
    Fund-Runden zeigten: die Interaktion aus Einfügereihenfolge, Rückkopplung bei dauerhaft
    unsicheren Zielpositionen und paarweiser Non-Crossing-Prüfung ist trickreich genug, dass
    ein weiterer, bislang unentdeckter Randfall nicht ausgeschlossen werden kann), greift der
    garantiert sichere, aber sehr suboptimale Fallback `_fully_sequential_schedule` - lieber
    spürbar schlechtere Liegezeit in einem seltenen Extremfall als eine unzulässige Lösung."""
    tasks = _build_schedule_incremental(instance, order)
    ok, _ = check_feasible(instance, tasks)
    if ok:
        return tasks
    return _fully_sequential_schedule(instance, order)


def _round_robin_interleave(instance, order):
    """Ordnet `order` (unverändert in Kranzuordnung UND je Kran relativer Reihenfolge) so um,
    dass die erste Aufgabe jedes Krans zuerst kommt, dann die zweite jedes Krans, usw. - reine
    EINFÜGEreihenfolge für die Konstruktion, ändert weder welcher Kran welche Bay bekommt noch
    die Reihenfolge INNERHALB eines Krans.

    Eigener Fund (Wurzelursache einer ganzen Kette von Sicherheitslücken): baut man stattdessen
    blockweise (ein Kran komplett, dann der nächste), ist jeder noch nicht an die Reihe
    gekommene Kran für `_segments_with_unassigned_cranes` scheinbar für immer an seiner
    Startposition "gefangen" - ein bereits eingeplanter Kran, der in Wirklichkeit nur kurz in
    dessen Nähe arbeitet, wird dadurch unnötig auf einen extrem späten Zeitpunkt (nahe dem
    Konstruktions-Zeithorizont) verschoben, was wiederum GENAU DORT eine echte, dauerhafte
    Nähe zu einem später eingefügten, dann tatsächlich früh startenden Kran erzeugt - eine
    Kaskade aus Verzögerung erzeugt echte Verletzung. Rundenweises Verschränken gibt jedem Kran
    seine erste (meist ausschlaggebende) Aufgabe früh, bevor ein anderer Kran lange genug als
    "für immer dort stehend" gelten könnte, um so eine Kaskade auszulösen."""
    by_crane = defaultdict(list)
    for bay, crane in order:
        by_crane[crane].append((bay, crane))

    interleaved = []
    round_idx = 0
    remaining = True
    while remaining:
        remaining = False
        for crane in range(instance.n_cranes):
            bays = by_crane.get(crane, [])
            if round_idx < len(bays):
                interleaved.append(bays[round_idx])
                remaining = True
        round_idx += 1
    return interleaved


def _build_schedule_incremental(instance, order):
    tasks = {}
    crane_last_end = {c: 0.0 for c in range(instance.n_cranes)}
    crane_last_pos = {c: instance.crane_start_positions[c] for c in range(instance.n_cranes)}
    for bay, crane in _round_robin_interleave(instance, order):
        prev_end, prev_pos = crane_last_end[crane], crane_last_pos[crane]
        unconstrained_start = prev_end + instance.travel_time(prev_pos, bay)
        departure, start = earliest_feasible_start(instance, tasks, crane, bay, prev_end, prev_pos)
        if start is None:
            # Garantiert sichere Rückfallposition (siehe earliest_feasible_start-Docstring): ab
            # dem Ende der zuletzt endenden bereits eingeplanten Aufgabe (bzw. Fahrt/Wartephase
            # davor - alle enden spätestens bei deren `.end`) ist nichts mehr aktiv, das
            # verletzt werden könnte. WICHTIG: sowohl Abfahrt ALS AUCH Ankunft müssen dahinter
            # liegen, nicht nur `start` - sonst könnte die Fahrt selbst noch mit einer
            # bestehenden Aufgabe überlappen (eigener Fund: eine frühere Fassung setzte nur
            # `start` sicher, leitete `departure` aber rückwärts davon ab, was die Fahrt
            # ungeprüft ließ).
            latest_end = max((t.end for t in tasks.values()), default=0.0)
            departure = max(prev_end, latest_end)
            start = departure + instance.travel_time(prev_pos, bay)
        end = start + instance.bays[bay].duration
        tasks[bay] = Task(
            bay=bay, crane=crane, start=start, end=end, wait=start - unconstrained_start, departure=departure
        )
        crane_last_end[crane] = end
        crane_last_pos[crane] = bay
    return tasks


def crane_position_segments(instance, tasks):
    """Liefert je Kran eine Liste von Segmenten (crane, t0, pos0, t1, pos1, kind), kind in
    {"wait", "travel", "work"}: Warten (Position konstant, am Ursprung ODER am Ziel - siehe
    unten), Fahrt (Position ändert sich linear) und Bearbeitung (Position konstant).

    Nutzt `t.departure`, falls gesetzt (von `build_schedule`/den Heuristiken bewusst
    mitgeführt - siehe `Task.departure`-Docstring: ein einzelner `wait`-Skalar reicht nicht,
    um zu rekonstruieren, OB ein Kran am Ursprung wartete, am Ziel, oder - seit der
    Intervall-Vermeidungs-Konstruktion in `_safe_departure`/`_safe_start` möglich - eine
    Mischung aus beidem). Ist `t.departure` None (CP-SAT-Ergebnisse, direkt aus `Task()`
    gebaute Testfälle), fällt es auf "so spät wie möglich losfahren" zurück
    (`t.start - Fahrzeit`) - für CP-SAT ist das sicher, weil genau dieses Fenster dort aktiv
    erzwungen wird (siehe quaycrane_cp_solver.py).

    Wird sowohl von check_feasible als auch vom Trajektorien-Chart genutzt, damit Prüfung und
    Darstellung nie auseinanderlaufen (Fund vom 2026-09-04: die ursprüngliche, rein
    aufgabenbasierte Prüfung kannte Fahrsegmente überhaupt nicht; ein späterer Fix ohne
    explizites `departure`-Feld rekonstruierte bei komplexeren, aus Intervall-Vermeidung
    stammenden Zeitplänen eine andere - teils unsichere - Trajektorie als die beim Bauen
    tatsächlich bestätigte)."""
    by_crane = defaultdict(list)
    for t in tasks.values():
        by_crane[t.crane].append(t)

    segments = []
    for crane, ts in by_crane.items():
        ts = sorted(ts, key=lambda t: t.start)
        prev_t, prev_pos = 0.0, instance.crane_start_positions[crane]
        for t in ts:
            travel_time = instance.travel_time(prev_pos, t.bay)
            departure = t.departure if t.departure is not None else t.start - travel_time
            departure = max(departure, prev_t)  # Sicherheitsnetz gegen Rundungsfehler
            if departure > prev_t + 1e-9:
                segments.append((crane, prev_t, prev_pos, departure, prev_pos, "wait"))
            arrival = departure + travel_time
            if t.bay != prev_pos:
                segments.append((crane, departure, prev_pos, arrival, t.bay, "travel"))
            if t.start > arrival + 1e-9:
                segments.append((crane, arrival, t.bay, t.start, t.bay, "wait"))  # Warten am Ziel
            segments.append((crane, t.start, t.bay, t.end, t.bay, "work"))
            prev_t, prev_pos = t.end, t.bay
    return segments


def _position_on_segment(t0, p0, t1, p1, t):
    if t1 <= t0:
        return p0
    return p0 + (p1 - p0) * (t - t0) / (t1 - t0)


def _segments_violate_margin(seg_left, seg_right, margin):
    """seg_left gehört zum Kran mit dem kleineren Index (muss links bleiben). Da beide Segmente
    linear in der Zeit sind, ist ihre Differenz über dem gemeinsamen Zeitfenster ebenfalls
    linear - es reicht, die beiden Fensterenden zu prüfen (Extrema einer affinen Funktion)."""
    _, t0a, p0a, t1a, p1a, _ = seg_left
    _, t0b, p0b, t1b, p1b, _ = seg_right
    lo, hi = max(t0a, t0b), min(t1a, t1b)
    if lo >= hi:
        return False
    left_lo = _position_on_segment(t0a, p0a, t1a, p1a, lo)
    right_lo = _position_on_segment(t0b, p0b, t1b, p1b, lo)
    left_hi = _position_on_segment(t0a, p0a, t1a, p1a, hi)
    right_hi = _position_on_segment(t0b, p0b, t1b, p1b, hi)
    tol = 1e-6
    return (left_lo + margin > right_lo + tol) or (left_hi + margin > right_hi + tol)


def _crossing_and_overlap_violations(instance, tasks):
    """Kern von `check_feasible` OHNE die Vollständigkeits-Prüfung (jede Bay genau einmal) -
    eigenständig nutzbar, um auch ein UNVOLLSTÄNDIGES Zwischenergebnis während der Konstruktion
    auf Sicherheit zu prüfen (siehe `_fully_sequential_schedule`s `_verified`-Helfer): dort ist
    "nicht jede Bay abgedeckt" per Definition erwartet und keine echte Verletzung, nur die
    Non-Crossing-/Überlappungs-Regeln zählen."""
    violations = []
    by_crane = defaultdict(list)
    for t in tasks.values():
        by_crane[t.crane].append(t)

    for crane, ts in by_crane.items():
        for a in ts:
            for b in ts:
                if a.bay != b.bay and _intervals_overlap(a.start, a.end, b.start, b.end):
                    violations.append(f"Kran {crane}: Überlappung Bay {a.bay}/{b.bay}.")

    cranes = sorted(by_crane.keys())
    segments_by_crane = defaultdict(list)
    for seg in crane_position_segments(instance, tasks):
        segments_by_crane[seg[0]].append(seg)

    for pi in range(len(cranes)):
        for qi in range(pi + 1, len(cranes)):
            p, q = cranes[pi], cranes[qi]
            for seg_p in segments_by_crane[p]:
                for seg_q in segments_by_crane[q]:
                    if _segments_violate_margin(seg_p, seg_q, instance.safety_margin):
                        violations.append(
                            f"Non-Crossing verletzt (Fahrt/Warten eingeschlossen): Kran {p} "
                            f"(t={seg_p[1]:.1f}-{seg_p[3]:.1f}, Pos {seg_p[2]:.1f}->{seg_p[4]:.1f}) "
                            f"vs. Kran {q} (t={seg_q[1]:.1f}-{seg_q[3]:.1f}, "
                            f"Pos {seg_q[2]:.1f}->{seg_q[4]:.1f})."
                        )
    return violations


def check_feasible(instance, tasks):
    violations = []
    if set(tasks.keys()) != set(range(instance.n_bays)):
        violations.append("Nicht jede Bay genau einmal abgedeckt.")
    violations.extend(_crossing_and_overlap_violations(instance, tasks))
    return len(violations) == 0, violations


def evaluate(instance, tasks, label=""):
    makespan = max((t.end for t in tasks.values()), default=0.0)
    by_crane = defaultdict(list)
    for t in tasks.values():
        by_crane[t.crane].append(t)

    crane_stats = {}
    total_travel = 0.0
    total_wait = 0.0
    for c in range(instance.n_cranes):
        ts = sorted(by_crane.get(c, []), key=lambda t: t.start)
        busy = sum(t.end - t.start for t in ts)
        wait = sum(t.wait for t in ts)
        finish = ts[-1].end if ts else 0.0
        travel = 0.0
        pos = instance.crane_start_positions[c]
        for t in ts:
            travel += instance.travel_time(pos, t.bay)
            pos = t.bay
        idle_after = makespan - finish
        crane_stats[c] = {
            "n_bays": len(ts),
            "busy_time": busy,
            "travel_time": travel,
            "wait_time": wait,
            "finish_time": finish,
            "idle_after": idle_after,
        }
        total_travel += travel
        total_wait += wait

    loads = [crane_stats[c]["busy_time"] for c in range(instance.n_cranes)]
    imbalance = (max(loads) - min(loads)) if loads else 0.0

    return {
        "label": label,
        "tasks": tasks,
        "makespan": makespan,
        "crane_stats": crane_stats,
        "total_travel_time": total_travel,
        "total_wait_time": total_wait,
        "load_imbalance": imbalance,
    }


def finalize_tasks(instance, raw):
    """raw: dict bay -> (crane, start, end), z.B. aus dem CP-SAT-Löser. Ergänzt je Kran anhand
    der chronologischen Reihenfolge die `wait`-Kennzahl (Wartezeit durch Interferenz) - dieselbe
    Definition wie in build_schedule, nur nachträglich statt während der Konstruktion."""
    by_crane = defaultdict(list)
    for bay, (crane, start, end) in raw.items():
        by_crane[crane].append((bay, start, end))

    tasks = {}
    for crane, items in by_crane.items():
        items.sort(key=lambda x: x[1])
        pos = instance.crane_start_positions[crane]
        t = 0.0
        for bay, start, end in items:
            unconstrained = t + instance.travel_time(pos, bay)
            tasks[bay] = Task(bay=bay, crane=crane, start=start, end=end, wait=max(0.0, start - unconstrained))
            pos, t = bay, end
    return tasks


def comparison_table(results):
    import pandas as pd

    rows = []
    for r in results:
        rows.append(
            {
                "Methode": r["label"],
                "Liegezeit (min)": round(r["makespan"], 1),
                "Wartezeit durch Interferenz (min)": round(r["total_wait_time"], 1),
                "Fahrzeit gesamt (min)": round(r["total_travel_time"], 1),
                "Lastungleichgewicht (min)": round(r["load_imbalance"], 1),
            }
        )
    return pd.DataFrame(rows)
