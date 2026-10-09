# Plan implementacji modułu nieruchomości

## Cel i kontekst

Moduł pozwoli prowadzić nieruchomości jako osobny portfel, ewidencjonować ich wyceny, przychody i koszty oraz uwzględniać je w zbiorczym widoku „Majątek”. Implementacja jest podzielona na pięć etapów. Etap 1 obejmuje backend MVP, etap 2 interfejs, a kolejne etapy rozbudowują moduł o automatyzację, kredyty i rozszerzenia.

### Założenia wspólne

- Aplikacja jest prywatna, jednoosobowa; walutą bazową jest PLN.
- Nieruchomość to instrument typu `real_estate` w osobnym portfelu, z ręcznym dostawcą notowań. Jej kupno zapisuje się jako zwykła transakcja `BUY` o ilości 1; wyceny jako rekordy `Price`.
- Przychody i koszty nieruchomości są zewnętrznymi przepływami XIRR niezależnie od tego, czy portfel korzysta z `CashDeposit`. W zbiorczym widoku „Majątek” należy uwzględniać wyceny i przepływy wszystkich portfeli.
- Kwoty w backendzie są typu `Decimal`, nigdy `float` poza obliczeniami wewnątrz XIRR. Brak danych reprezentuje `None`, nie zero.
- Teksty interfejsu i błędy API są po polsku. Nowe pola istniejących odpowiedzi API są opcjonalne; dotychczasowe zachowanie typów aktywów innych niż nieruchomości pozostaje bez zmian.
- Aplikacja nie uruchamia zadań w tle. Wpisy cykliczne generuje użytkownik na żądanie.
- Etapy realizować kolejno; kolejny rozpocząć po integracji poprzedniego. Każdy etap powinien mieć własny przegląd zmian i kryteria odbioru.

## Etap 1 z 5 — Backend nieruchomości

### 1.1. Model danych i migracja

- Dodać typ instrumentu `real_estate` oraz migrację `004_real_estate.py`.
- Dodać `property_details` jako relację 1:1 z instrumentem: metraż, adres, stawka ryczałtu domyślnie 8,5% i flaga interpolacji domyślnie wyłączona.
- Dodać generyczną tabelę `asset_cash_flows` powiązaną z portfelem i instrumentem. Przechowywać dodatnią kwotę, walutę, rodzaj, kategorię, podatek, notatkę i datę; znak przepływu wynika z rodzaju. Dodać wymagane indeksy.
- Zachować kompatybilność migracji SQLite przez `op.batch_alter_table` tam, gdzie jest potrzebne.

### 1.2. Kupno, wyceny i notowania ręczne

- Kupno nieruchomości rejestrować jako `Transaction BUY`, ilość 1; koszty transakcyjne сумować w `commission`.
- Wyceny zapisywać w `Price` jako wartość całej nieruchomości, używając istniejącego mechanizmu upsert.
- Zmienić `refresh_quotes`, aby pomijał instrumenty `provider="manual"` zarówno przy pełnym, jak i wybranym odświeżeniu.

### 1.3. Przepływy oraz podsumowania

- Rozszerzyć `build_summary` dla pojedynczego portfela i agregatu. W XIRR zawsze uwzględniać przepływy nieruchomości; przeliczać je kursem z daty przepływu i sygnalizować brak kursu zgodnie z obecną logiką.
- Doliczać CAPEX do kosztu pozycji. Dodać opcjonalne pola pozycji: przychody netto, koszty, CAPEX, zwrot całkowity, XIRR pozycji i datę wyceny. Dodać opcjonalne sumy przychodów, kosztów i zwrotu do podsumowania.
- Zaimplementować `build_property_metrics`: koszt nabycia i CAPEX, bieżącą wycenę i cenę za m², przepływy w zadanym okresie, rentowność brutto/netto, zmianę wartości, zwrot całkowity, XIRR oraz zestawienie według kategorii. Nieznane wartości zwracać jako `None`.

### 1.4. API, walidacja i usuwanie

- Dodać router `/api/real-estate`: tworzenie nieruchomości w jednej transakcji DB, listowanie, szczegóły i edycja detali, metryki.
- Dodać API wycen oraz przepływów pieniężnych, w tym edycję i usuwanie. Walidować rodzaj, dodatnią kwotę oraz powiązanie instrumentu z portfelem.
- Dla czynszu automatycznie wyliczać podatek według stawki z detali, jeśli pole nie zostało przekazane; jawne zero pozostaje dozwolone. Zaokrąglać do grosza metodą `ROUND_HALF_UP`.
- Nie pozwalać usunąć jedynej wyceny z datą zakupu. Zwracać polskie komunikaty 404/422.
- Rozszerzyć usuwanie portfela o przepływy, detale nieruchomości i ręczne wyceny usuwanych instrumentów.

### 1.5. Testy i odbiór etapu

- Dodać testy tworzenia, ręcznych notowań, pomijania providera `manual`, wpływu CAPEX na koszt i P&L, domyślnego podatku, metryk rentowności, usuwania danych i XIRR.
- Sprawdzić agregat „Majątek” z portfelem akcyjnym korzystającym z wpłat i osobnym portfelem nieruchomości.
- Na kopii istniejącej bazy sprawdzić `alembic upgrade head` oraz `downgrade -1`.
- Kryterium regresji: podsumowanie istniejących portfeli bez nieruchomości zachowuje dotychczasowe wartości. Uruchomić `cd backend && python -m pytest`.

## Etap 2 z 5 — Frontend i widok nieruchomości

### 2.1. Typy, klient API i dodawanie nieruchomości

- Po zapoznaniu się z routerem i schematami backendu dodać zgodne typy TS: `RealEstate`, `PropertyMetrics`, `Valuation`, `AssetCashFlow`, `CashFlowKind` oraz opcjonalne pola do `Position` i `PortfolioSummary`.
- Dodać metody API i obsługę stanu w `portfolioService` oraz `usePortfolio`.
- Rozszerzyć modal transakcji o typ nieruchomości i pola: nazwa, adres, metraż, data i cena zakupu, koszty transakcyjne, stawka ryczałtu oraz opcjonalna wycena początkowa. Podpowiedź PCC ma wyliczać 2% ceny, pozostawiając miejsce na inne koszty. Zapis korzysta z endpointu nieruchomości.

### 2.2. Lista pozycji i szczegóły

- Dodać grupę „Nieruchomości” w widoku pozycji; pokazać wycenę, datę wyceny, koszt z CAPEX, przychody netto, koszty, zwrot całkowity i XIRR.
- Dla wyceny starszej niż 12 miesięcy wyświetlać przy dacie komunikat „Zaktualizuj wycenę”. Wiersz otwiera szczegóły nieruchomości.
- Dodać trasę szczegółów przed catch-all i widok `PropertyView.vue`: dane nieruchomości, edycja detali, zakresy okresu i kafelki metryk.

### 2.3. Przepływy, wykresy i wyceny

- Dodać tabelę przychodów i kosztów z formularzem, kategoriami zależnymi od rodzaju, edytowalnym podatkiem dla czynszu oraz szybką akcją dodania czynszu za bieżący miesiąc na podstawie ostatniego wpisu.
- Dodać wykres miesięcznych przychodów i kosztów oraz skumulowanego cashflow netto, w stylistyce istniejącego dashboardu.
- Dodać listę wycen z różnicą względem poprzedniej wyceny oraz możliwość dodawania i usuwania.

### 2.4. Agregat „Majątek”

- Rozszerzyć backend o opcjonalne zestawienie wartości według portfeli i klas aktywów: akcje PL, akcje US (w tym NYSE), ETF, złoto i nieruchomości.
- W dashboardzie agregatu dodać przełącznik alokacji: klasy aktywów, portfele lub pozycje. W widoku pojedynczego portfela pozostawić obecną alokację pozycji.
- Jeśli przychody lub koszty są dodatnie, pokazać kafelek „Najem netto” i uwzględnić zwrot całkowity. Potwierdzić, że historia agregatu odzwierciedla ręczne wyceny.

### 2.5. Odbiór etapu

- Scenariusz ręczny: utworzyć portfel nieruchomości, dodać nieruchomość, trzy czynsze, dwa koszty, CAPEX i nową wycenę; sprawdzić kafelki i agregat „Majątek”.
- Sprawdzić brak regresji w portfelach akcyjnych. Uruchomić `cd frontend && npm run build`, `npm run format:check` oraz `cd backend && python -m pytest`.

## Etap 3 z 5 — Przepływy cykliczne generowane na żądanie

### 3.1. Model i migracja

- Dodać migrację `005_recurring_cash_flows.py` i tabelę szablonów z portfelem, instrumentem, rodzajem, kategorią, kwotą, stawką podatku, walutą, dniem miesiąca, zakresem dat, notatką i flagą aktywności.
- Rozszerzyć przepływy o `recurring_id`, `skipped` i `edited`; dodać unikalność szablonu i daty.
- Wykluczyć wpisy pominięte z podsumowań, metryk i XIRR.

### 3.2. Serwis generowania

- Zaimplementować wyznaczanie oczekujących wystąpień od daty startu do wcześniejszej z dat: końca szablonu i daty żądanej. Istniejący wpis, również pominięty, blokuje ponowne wygenerowanie.
- Generować idempotentnie brakujące przepływy, z domyślnym podatkiem dla czynszu. Dla dnia 29–31 w krótszym miesiącu używać ostatniego dnia miesiąca.
- Usunięcie wpisu wygenerowanego oznacza je jako pominięty; wpis ręczny usuwać fizycznie. Dodać możliwość przywrócenia wpisu.
- Zmiana szablonu dotyczy nowych wystąpień. `apply_from` może odtworzyć tylko wygenerowane, nieedytowane ręcznie wpisy od wskazanej daty.
- Zapewnić atomową akcję zmiany kwoty od daty: zamknąć stary szablon dzień wcześniej i utworzyć nowy.

### 3.3. API, interfejs i testy

- Dodać endpointy CRUD szablonów, podglądu oczekujących i generowania przepływów; usuwanie szablonu opcjonalnie usuwa jego wygenerowane wpisy.
- W `PropertyView` dodać listę szablonów, edycję oraz zmianę kwoty od daty. Pokazywać baner liczby i sumy oczekujących wpisów z akcją generowania.
- Oznaczać przepływy cykliczne, umożliwić filtr pominiętych wpisów i ich przywracanie.
- Testy: idempotencja, koniec miesiąca, pominięcie i wpływ na wyliczenia, zmiana kwoty, ochrona wpisów edytowanych ręcznie. Uruchomić testy backendu i kontrole frontendu.

## Etap 4 z 5 — Kredyty i majątek netto

### 4.1. Zobowiązania i serwis

- Dodać migrację `006_liabilities.py`, tabele zobowiązań i spłat oraz walidację nieujemnych kwot.
- Obliczać saldo jako kapitał początkowy pomniejszony o spłacony kapitał do wskazanego dnia; salda nie przechowywać.
- Dodać podpowiedź następnej raty annuitetowej lub malejącej. Traktować ją jako wartość pomocniczą, bo użytkownik wpisuje kwoty z banku.

### 4.2. Metryki i API

- W metrykach nieruchomości pokazać odsetki, opłaty, cashflow przed kredytem i po kredycie, saldo, LTV, wkład własny, equity, cash-on-cash oraz XIRR wkładu własnego.
- Liczyć XIRR wkładu własnego z przepływem początkowym po odjęciu kredytu, najmem netto, kosztami, ratami i wartością końcową po odjęciu salda.
- W podsumowaniu dodać zobowiązania i majątek netto; dla agregatu sumować zobowiązania wszystkich portfeli. XIRR portfeli z kredytem ma uwzględniać finansowanie i spłaty, a bez zobowiązań zachować dotychczasowy wynik.
- Rozszerzyć historię o zobowiązania i majątek netto oraz punkty w dniach spłat. Dodać API CRUD zobowiązań i płatności oraz endpoint podpowiedzi raty. Usuwanie portfela usuwa jego zobowiązania i spłaty.

### 4.3. Interfejs i odbiór

- W szczegółach nieruchomości dodać sekcję kredytu, saldo, LTV, raty i oba XIRR; formularz spłaty może pobierać podpowiedź podziału raty.
- Umożliwić dodanie kredytu razem z nieruchomością. W „Majątku” pokazać aktywa, zobowiązania i majątek netto oraz przełącznik historii aktywów/netto.
- Testować saldo, nadpłatę, wzór raty, dźwignię w XIRR, agregat i niezmienność wyników portfela akcyjnego bez zobowiązań. Uruchomić testy backendu i kontrole frontendu.

## Etap 5 z 5 — Rozszerzenia (trzy niezależne części)

### 5A. Interpolacja wycen

- Gdy `interpolate_valuations=True`, liczyć liniową wartość pomiędzy dwiema wycenami proporcjonalnie do liczby dni. Przed pierwszą wyceną zwracać brak wartości, po ostatniej przenosić ostatnią wycenę bez ekstrapolacji.
- Pozostałe instrumenty zachowują dotychczasowy `price_on`; klucz cache musi rozróżniać tryb interpolacji.
- Dodać punkty pośrednie do historii (np. tygodniowe lub w dniach kursów FX), aby wykres był płynny. Dodać przełącznik wygładzania w edycji nieruchomości.
- Testować wartość w połowie okresu (500 000 → 520 000 daje 510 000), przenoszenie ostatniej wartości oraz wyłączoną interpolację.

### 5B. Import CSV wycen i przepływów

- Oprzeć implementację na istniejącym imporcie transakcji i modalu importu.
- Obsłużyć separatory średnik/przecinek, przecinek dziesiętny, spacje tysięcy, daty ISO i `DD.MM.YYYY`, UTF-8 BOM i CP1250.
- Wyceny przyjmują kolumny `data;wartosc`; przepływy: `data;rodzaj;kategoria;kwota;podatek;notatka`. Rodzaje obsługują polskie nazwy i kody API.
- Dodać endpointy podglądu `dry_run` z poprawnymi wierszami, błędami z numerem wiersza i duplikatami. Duplikat przepływu określa ta sama data, rodzaj, kwota i kategoria.
- Dodać import w sekcjach wycen i przepływów z podglądem przed zapisem. Testować formaty, CP1250, duplikaty i błędy.

### 5C. Roczne zestawienie do PIT-28

- Dodać endpoint raportu per nieruchomość i łącznie, z przychodem brutto RENT i OTHER_INCOME w podziale na miesiące, podatkiem naliczonym/zapłaconym oraz kontrolnym wyliczeniem ryczałtu.
- Próg 100 000 zł i stawki 8,5% oraz 12,5% trzymać w jednym miejscu konfiguracji. Wyraźnie zaznaczyć, że próg dotyczy podatnika, a przy wspólnym najmie małżonków użytkownik sam dzieli przychód.
- Zwracać ostrzeżenie o różnicy między podatkiem zapisanym w aplikacji a wyliczeniem kontrolnym; umożliwić eksport CSV.
- Dodać zakładkę „Podatki” z wyborem roku, tabelą miesięcy i eksportem. Umieścić adnotację: „Zestawienie pomocnicze, nie stanowi porady podatkowej”.
- Testować przekroczenie progu w trakcie roku, zgodność sum miesięcznych z rocznymi i rok bez przychodów.

### 5.4. Odbiór etapu

- Trzy części są niezależne i mogą być wdrażane osobno.
- Dla każdej części uruchomić odpowiednie testy oraz kontrole frontendu.
- Żadna część nie może zmieniać wyników portfeli bez nieruchomości.

## Kontrole wspólne przed integracją

- Porównać bazowe odpowiedzi `/api/portfolio/summary` dla istniejących portfeli i agregatu „Majątek”, szczególnie po etapie 1. Istotną ryzyką regresji jest zmiana sposobu liczenia XIRR portfeli z `CashDeposit`.
- W każdym etapie sprawdzić migracje właściwe dla SQLite i usuwanie danych zależnych.
- Odbiór całości: `cd backend && python -m pytest`, `cd frontend && npm run build && npm run format:check`; tam, gdzie dotyczy, ręcznie przejść scenariusz danego etapu.
