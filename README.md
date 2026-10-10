# Portfel

Prywatna aplikacja do śledzenia inwestycji i ich wartości. Pozwala prowadzić kilka portfeli, zapisywać transakcje kupna i sprzedaży oraz przeglądać łączną wartość, wynik inwestycji, zmianę dzienną i historię portfela w PLN.

## Co potrafi

- Pokazuje podsumowanie portfela, wykres zmian wartości, alokację i listę pozycji.
- Obsługuje m.in. akcje polskie i amerykańskie, ETF-y oraz złoto.
- Umożliwia ręczne dodawanie transakcji, import zakupów i sprzedaży z plików xStation5 (`.xlsx`) i Bossa (`.csv`), a także usuwanie pozycji.
- Pobiera notowania i kursy walut na żądanie, po imporcie transakcji oraz przy zapisie zakupu złota; nie uruchamia cyklicznego automatycznego odświeżania.
- Przechowuje dane lokalnie w bazie SQLite `data/portfel.db`.

## Obliczenia i import xStation

Koszt otwartej pozycji jest rozliczany średnią ruchomą osobno w każdym portfelu.
Sprzedaż zmniejsza koszt pozostałych jednostek; po całkowitym zamknięciu pozycji
nowy zakup rozpoczyna nową pulę kosztu. Dla eksportu rachunku PLN z xStation
importer zapisuje rzeczywiste kwoty zakupów i sprzedaży z `Cash Operations.Amount`,
uwzględniające przewalutowanie brokera, zamiast przybliżać je kursem NBP.

Importer odczytuje również wpłaty, wypłaty, dywidendy, podatki i odsetki od gotówki.
Operacje przychodów i kosztów rachunku są przechowywane w tabeli `cash_movements`
(migracja `005_cash_movements`). Wypłaty są ujemnymi wpisami `cash_deposits`.

XIRR jest rocznym zwrotem ważonym kapitałem. W portfelach ze wpłatami przepływami
zewnętrznymi są wpłaty i wypłaty, a wartość końcowa obejmuje aktywa oraz saldo
gotówki, również ujemne. Dywidendy i podatki wpływają na gotówkę i nie są liczone
ponownie jako przepływy zewnętrzne. W portfelach bez wpłat pozostaje metoda
przepływów zakupu i sprzedaży. Przepływy nieruchomości pozostają zewnętrzne zgodnie
z założeniami fazy 1 w `docs/real_estates.md`.

Wartość końcowa XIRR jest datowana na dzień obliczenia, z ostatnimi dostępnymi
cenami oraz kursem walutowym z tego dnia; przyszłe operacje są pomijane.
API zachowuje `value_pln` jako wartość aktywów oraz dodaje `cash_pln` i
`total_value_pln` jako saldo gotówki i sumę aktywów z gotówką. Dla przepływów
wyłącznie z jednego dnia XIRR jest nieokreślony.

Wcześniejszy import nie zawiera pominiętych sprzedaży ani operacji przychodów
i podatków. Sama migracja tych danych nie odtworzy: stary import należy zastąpić
pełną historią z poprawionego importera. Ponowne dodanie pliku do istniejącej
historii utworzy duplikaty. Skrypt `scripts/verify_xstation_export.py` pozwala
sprawdzić zgodność pliku z importerem na bazie w pamięci, bez zmiany danych aplikacji.

## Uruchomienie lokalne

Notowania polskich akcji i ETF-ów w PLN skonfigurowanych w Stooq są pobierane
najpierw z Yahoo Finance (symbole `.WA`). Stooq jest źródłem zapasowym dla
symboli, dla których Yahoo nie zwróciło danych. Po błędzie sieciowym, HTTP 429
lub błędzie serwera Stooq aplikacja pomija to źródło przez 5 minut, a następnie
sprawdza dostępność jednym żądaniem. Timeout połączenia wynosi 2 sekundy,
pozostałych operacji sieciowych 3 sekundy.

Waluty Yahoo są zapamiętywane na 24 godziny w pamięci procesu backendu,
łącznie z jednostkami takimi jak pensy. Restart backendu czyści cache oraz
stan dostępności Stooq; każda instancja backendu ma własny cache.

Zalecane są Python 3.13 oraz Node.js. Obecne przypięte zależności backendu nie obsługują poprawnie Pythona 3.14.

1. W pierwszym terminalu zainstaluj zależności backendu i uruchom API:

   ```powershell
   cd backend
   py -3.13 -m venv .venv-py313
   .\.venv-py313\Scripts\Activate.ps1
   pip install -r requirements-dev.txt
   $env:PORTFEL_AUTH_DISABLED = "true"
   uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

   `PORTFEL_AUTH_DISABLED=true` jest wyłącznie obejściem lokalnego developmentu.
   Szczegóły konfiguracji znajdziesz w sekcji [Uwierzytelnianie](#uwierzytelnianie).

2. W drugim terminalu uruchom frontend:

   ```powershell
   cd frontend
   npm install
   npm run dev
   ```

3. Otwórz adres wyświetlony przez Vite, domyślnie <http://127.0.0.1:5173>.
   Dokumentacja API FastAPI jest dostępna pod <http://127.0.0.1:8000/docs>
   tylko przy `PORTFEL_AUTH_DISABLED=true`.

   ## Uwierzytelnianie

   Uwierzytelnianie jest domyślnie włączone. Wymaga hasła przechowywanego jako hash
   oraz losowego klucza do podpisywania sesji.

   Zmienne środowiskowe:

   - `PORTFEL_PASSWORD_HASH` — wymagany hash hasła w formacie Argon2 lub bcrypt.
   - `PORTFEL_SECRET_KEY` — wymagany, losowy klucz o długości co najmniej 32 bajtów,
     używany do podpisywania ciasteczka sesji.
   - `PORTFEL_SESSION_HOURS` — czas ważności sesji w godzinach; domyślnie `12`.
   - `PORTFEL_COOKIE_SECURE` — czy ciasteczko ma być wysyłane wyłącznie przez HTTPS;
     domyślnie `false` w development i `true` w produkcji.
   - `PORTFEL_AUTH_DISABLED` — wyłącza uwierzytelnianie wyłącznie na potrzeby
     lokalnego developmentu; domyślnie `false` i nie może być włączone w produkcji.
   - `PORTFEL_ENV` — środowisko aplikacji; domyślnie `development`. Wartość
     `production` włącza domyślnie `PORTFEL_COOKIE_SECURE`.
   - `PORTFEL_DATABASE_PATH` — ścieżka do bazy SQLite; domyślnie
     `data/portfel.db` w katalogu głównym repozytorium. Akceptuje ścieżki
     względne i bezwzględne. Dla zgodności nadal obsługiwana jest starsza nazwa
     `PORTFEL_DB_PATH` (ustawienie `PORTFEL_DATABASE_PATH` ma pierwszeństwo).
   - `PORTFEL_CORS_ORIGINS` — dozwolone origins rozdzielone przecinkami;
     domyślnie `http://127.0.0.1:5173,http://localhost:5173`. Pusta wartość
     wyłącza dodatkowe origins CORS, co jest właściwe, gdy frontend i API są
     dostępne pod tą samą domeną.
   - `PORTFEL_FRONTEND_DIR` — katalog z zbudowanym frontendem; domyślnie
     `backend/frontend_dist` względem katalogu głównego repozytorium.

   Po aktywowaniu środowiska wirtualnego backendu hash hasła i klucz wygenerujesz
   z katalogu głównego repozytorium:

   ```powershell
   python scripts/hash_password.py
   ```

   Skrypt poprosi o hasło i wypisze wartości `PORTFEL_PASSWORD_HASH` oraz
   `PORTFEL_SECRET_KEY`. Utwórz w katalogu głównym plik `.env` (np. poleceniem
   `notepad .env`) i wklej do niego wygenerowane linie, np.:

   ```dotenv
   PORTFEL_PASSWORD_HASH=<wygenerowany-hash>
   PORTFEL_SECRET_KEY=<wygenerowany-klucz>
   PORTFEL_SESSION_HOURS=12
   PORTFEL_COOKIE_SECURE=false
   PORTFEL_AUTH_DISABLED=false
   ```

   Plik `.env` jest ignorowany przez Git — **nie wolno go commitować** ani
   udostępniać, ponieważ zawiera dane uwierzytelniające. Aby uruchomić backend
   z tym plikiem, z katalogu `backend` użyj:

   ```powershell
   uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --env-file ..\.env
   ```

   Lokalnie, bez konfiguracji hasła i klucza, można zamiast tego ustawić
   `PORTFEL_AUTH_DISABLED=true` przed uruchomieniem backendu:

   ```powershell
   $env:PORTFEL_AUTH_DISABLED = "true"
   uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

   To ustawienie jest przeznaczone wyłącznie do lokalnego developmentu; nie używaj
   go w produkcji. **Na produkcji `PORTFEL_COOKIE_SECURE` musi mieć wartość `true`,
   a aplikacja musi działać za HTTPS.** Ciasteczko sesji ma flagi `HttpOnly` i
   `SameSite=Strict`.

   Frontend lokalny komunikuje się z API przez serwer proxy Vite. Wdrożenie
   serwujące frontend i API pod jedną domeną nie wymaga CORS; listę dodatkowych
   originów można ustawić przez `PORTFEL_CORS_ORIGINS`. Przy pierwszym uruchomieniu
   backend tworzy bazę danych i uzupełnia katalog instrumentów.

Ścieżkę do bazy można ustawić zmienną `PORTFEL_DATABASE_PATH` przed
uruchomieniem backendu. Domyślnie jest to `data/portfel.db` w katalogu głównym
repozytorium; ścieżki względne podane w zmiennej również są liczone względem
tego katalogu. Backend tworzy brakujący katalog docelowy podczas startu.

Przykładowy plik ze zmiennymi dla wdrożenia znajduje się w
[`backend/.env.example`](backend/.env.example). Nie zawiera on prawdziwych
sekretów; uzupełnij hash hasła i klucz przed uruchomieniem z włączonym
uwierzytelnianiem.

Wszystkie trasy API poza `POST /api/auth/login` i `POST /api/auth/logout`
wymagają zalogowania; obejmuje to również `GET /api/auth/me` i `GET /api/health`.
Przy włączonym uwierzytelnianiu ścieżki `/docs`, `/redoc` i `/openapi.json` są
wyłączone. Lokalny frontend korzysta z proxy Vite dla `/api`; konfiguracja CORS
backendu ogranicza originy do lokalnych adresów Vite.
