# Wdrożenie w cPanel (Setup Python App)

## 1. Przygotowanie paczki

Na Windows uruchom w katalogu głównym repozytorium:

```powershell
.\build_release.ps1
```

Skrypt buduje frontend, umieszcza go w `backend/frontend_dist` i tworzy
`release.zip`. Archiwum zawiera katalogi `backend/` i `data/`. Z `backend/`
pomijane są środowiska wirtualne, testy, pliki `.env`, bazy danych,
`node_modules` i `.git`; z `data/` dołączane są pliki
`nasdaq_stocks.json` i `nyse_stocks.json`. Wgraj `release.zip` do katalogu
domowego na serwerze i rozpakuj, zachowując oba katalogi na tym samym poziomie.
Przykładowo, po rozpakowaniu do `~/portfel` pliki powinny znajdować się pod
`~/portfel/backend/passenger_wsgi.py` oraz `~/portfel/data/`.

## 2. Utworzenie aplikacji Python

W cPanel otwórz **Setup Python App** i utwórz aplikację:

- **Python version:** Python 3.13, jeśli jest dostępny; odpowiada wersji
  zalecanej dla zależności tego projektu.
- **Application root:** ścieżka do rozpakowanego katalogu `backend`, np.
  `portfel/backend` (w tym katalogu znajdują się `requirements.txt` oraz
  `passenger_wsgi.py`).
- **Application URL:** wybierz domenę i ścieżkę, pod którą aplikacja ma być
  dostępna. Obecne wdrożenie działa pod `https://portfel.preficze.pl`.
- **Startup file:** `passenger_wsgi.py`.
- **Application entry point:** `application`.

Zapisz aplikację. cPanel utworzy dla niej środowisko wirtualne.

## 3. Instalacja zależności

W interfejsie aplikacji użyj polecenia instalacji pakietów, jeśli jest dostępne,
albo uruchom w terminalu polecenie `pip` ze środowiska wirtualnego przypisanego
przez cPanel:

```bash
pip install -r ~/portfel/backend/requirements.txt
```

Upewnij się, że polecenie `pip` pochodzi ze środowiska tej aplikacji, a nie
z systemowego Pythona. Przy innej ścieżce do katalogu zmień ścieżkę do pliku.

## 4. Zmienne środowiskowe i baza danych

W obecnym wdrożeniu dwie zmienne są ustawiane bezpośrednio w
`backend/passenger_wsgi.py`, przed importem aplikacji:

```python
os.environ["PORTFEL_PASSWORD_HASH"] = "<hash wygenerowany przez scripts/hash_password.py>"
os.environ["PORTFEL_DATABASE_PATH"] = "/home/vh14224/portfel_app/data/portfel.db"
```

Hash jest ustawiany w kodzie, ponieważ panel cPanel nie zachowuje wiernie
znaków `$` w jego wartości. Oba przypisania nadpisują wartości zmiennych z panelu.
Zmiana hasła lub ścieżki bazy wymaga edycji serwerowego `passenger_wsgi.py`
i restartu aplikacji. Nie kopiuj rzeczywistego hasha do instrukcji ani logów.

Pozostałe zmienne z `backend/.env.example` dodaj w **Setup Python App** jako
zmienne środowiskowe aplikacji. Nie wgrywaj produkcyjnego pliku `.env` do archiwum
ani repozytorium. Ustaw co najmniej:

- `PORTFEL_ENV=production`
- `PORTFEL_AUTH_DISABLED=false`
- `PORTFEL_SECRET_KEY` — losowy klucz wygenerowany przez ten sam skrypt.
- `PORTFEL_SESSION_HOURS=12`
- `PORTFEL_COOKIE_SECURE=true` — aplikacja musi być dostępna przez HTTPS.
- `PORTFEL_CORS_ORIGINS` — zostaw pustą wartość, gdy frontend i API są pod tą
  samą domeną; w przeciwnym razie podaj dozwolone origins rozdzielone przecinkami.
- `PORTFEL_FRONTEND_DIR` — opcjonalnie; domyślnie aplikacja szuka frontendu w
  `backend/frontend_dist`.

Baza obecnego wdrożenia znajduje się w
`/home/vh14224/portfel_app/data/portfel.db`. Użytkownik aplikacji musi mieć
uprawnienia do zapisu i odczytu w katalogu `data`; backend tworzy brakujący katalog
i plik bazy podczas startu. Przy ręcznym aktualizowaniu aplikacji zachowaj
serwerowy `passenger_wsgi.py` oraz bazę i jej pliki pomocnicze SQLite.
Archiwum zawiera `passenger_wsgi.py`, więc jego rozpakowanie może nadpisać
konfigurację serwera — przed rozpakowaniem zachowaj kopię tego pliku.

## 5. Restart i test

Po zapisaniu zmiennych środowiskowych zrestartuj aplikację w cPanel albo utwórz
plik `tmp/restart.txt` w katalogu aplikacji, np.:

```bash
mkdir -p ~/portfel/backend/tmp
touch ~/portfel/backend/tmp/restart.txt
```

Otwórz wybrany adres aplikacji, zaloguj się, a następnie w tej samej
przeglądarce odwiedź `/api/health`, np.
`https://portfel.preficze.pl/api/health`. Oczekiwana odpowiedź to
`{"ok":true}`. Endpoint wymaga zalogowanej sesji, tak jak pozostałe chronione
trasy API.

## 6. Automatyczny deploy przez GitHub Actions

Workflow `.github/workflows/deploy.yml` uruchamia się po każdym `push` do `main`,
w tym po merge pull requesta. Można go też uruchomić ręcznie przez **Actions →
Deploy → Run workflow**, wybierając `main`. Jeśli deploy ma następować wyłącznie
po merge, zablokuj bezpośrednie pushe do `main` regułą ochrony gałęzi.

Workflow uruchamia testy backendu na Pythonie 3.13, buduje frontend na Node.js 22,
łączy się przez SSH, przesyła pliki przez `rsync`, instaluje zależności w istniejącym
środowisku cPanel i dotyka `backend/tmp/restart.txt`. Passenger restartuje aplikację
przy kolejnym żądaniu. Na koniec workflow sprawdza stronę oraz oczekiwaną odpowiedź
HTTP 401 z `/api/auth/me` bez sesji. Nie zastępuje to testu logowania i danych;
`/api/health` trzeba sprawdzić ręcznie po zalogowaniu.

### Jednorazowa konfiguracja hostingu

[Oferta VH.PL](https://vh.pl/hosting-www) wymienia dostęp SSH i SFTP.
Nie potwierdza to jeszcze aktywacji SSH na konkretnym koncie ani dostępności
`rsync`. Możesz wejść do cPanel przez **Panel klienta VH.PL → Hosting → cPanel**
([instrukcja VH.PL](https://vh.pl/pomoc/jak-zalogowac-sie-do-cpanel)).

1. Sprawdź w cPanel **SSH Access / Dostęp SSH** i **Terminal**. Jeśli ich nie ma
   lub logowanie SSH nie działa, poproś wsparcie VH.PL o włączenie SSH z powłoką
   i podanie hosta oraz portu. W Terminalu albo po zalogowaniu SSH sprawdź:

   ```bash
   command -v bash
   command -v rsync
   ```

   Oba polecenia powinny wypisać ścieżki. Potwierdź też możliwość instalacji
   zależności przez `pip` w środowisku aplikacji. Sam FTP/SFTP nie wystarczy
   dla tego workflow.
2. W **Setup Python App** odczytaj pełną ścieżkę **Application root** oraz
   ścieżkę do Pythona w środowisku wirtualnym (z polecenia aktywacji podanego
   w panelu). `DEPLOY_PATH` ma wskazywać katalog nadrzędny dla `backend/` i
   `data/`, np. `/home/vh14224/portfel_app`, **jeśli** Application root to
   `/home/vh14224/portfel_app/backend`. `DEPLOY_PYTHON` ma wskazywać pełną
   ścieżkę do `bin/python` tego środowiska. Nie używaj systemowego Pythona.
3. Wygeneruj lokalnie osobny klucz SSH do wdrożeń:

   ```powershell
   ssh-keygen -t ed25519 -C "github-actions-portfel" -f "$env:USERPROFILE/.ssh/portfel_deploy"
   ```

   Dla tego workflow pozostaw passphrase pustą. Klucz **publiczny**
   (`portfel_deploy.pub`) zaimportuj i autoryzuj w cPanel przez **SSH Access →
   Manage SSH Keys** albo dodaj do `~/.ssh/authorized_keys` konta hostingu.
   Klucz prywatny trafi wyłącznie do GitHub Secrets.
4. Ustal host i port SSH z panelu hostingu; host SSH nie musi być domeną strony.
   Sprawdź połączenie lokalnie:

   ```powershell
   ssh -i "$env:USERPROFILE/.ssh/portfel_deploy" -p PORT UZYTKOWNIK@HOST
   ```

5. Pobierz wpis klucza hosta (na Windows polecenie jest dostępne m.in. w Git Bash):

   ```bash
   ssh-keyscan -p PORT HOST
   ```

   Porównaj fingerprint z informacją od hostingu lub zaufanego panelu, zanim
   zapiszesz wynik jako `DEPLOY_KNOWN_HOSTS`. Dla portu innego niż 22 zachowaj
   format `[HOST]:PORT`. Workflow wymaga weryfikacji klucza hosta.
6. Sprawdź, że na serwerze istnieją `backend/passenger_wsgi.py` z właściwymi
   wartościami obu zmiennych oraz produkcyjne ustawienia w cPanel z punktu 4.
   Wykonaj kopię bazy SQLite przed pierwszym automatycznym wdrożeniem
   (np. przez SQLite backup API albo przy zatrzymanej aplikacji).

### Konfiguracja repozytorium na GitHub

W **Settings → Secrets and variables → Actions** dodaj:

| Typ | Nazwa | Wartość |
| --- | --- | --- |
| Secret | `DEPLOY_SSH_KEY` | Cała zawartość prywatnego klucza `portfel_deploy`, wraz z nagłówkiem i końcem |
| Secret | `DEPLOY_KNOWN_HOSTS` | Zweryfikowane wpisy klucza hosta SSH z `ssh-keyscan` |
| Variable | `DEPLOY_HOST` | Host SSH z panelu hostingu |
| Variable | `DEPLOY_PORT` | Port SSH, np. `22` (domyślny, gdy wartość jest pusta) |
| Variable | `DEPLOY_USER` | Użytkownik SSH, np. `vh14224` |
| Variable | `DEPLOY_PATH` | Pełna ścieżka katalogu zawierającego `backend/` i `data/` |
| Variable | `DEPLOY_PYTHON` | Pełna ścieżka do `bin/python` środowiska aplikacji cPanel |

Ścieżki muszą być bezwzględne, bez spacji i znaków specjalnych powłoki; nie wpisuj
`~` ani polecenia `source`. Nie trzeba dodawać hasha hasła, ścieżki bazy ani
`PORTFEL_SECRET_KEY` do GitHub Actions: zachowujemy istniejącą konfigurację serwera.

Włącz GitHub Actions w repozytorium, zapisz zmiany na GitHub i uruchom pierwszy
deploy ręcznie dla `main`. Sprawdź logi, logowanie oraz `/api/health`. Kolejne
merge do `main` uruchomią workflow automatycznie. Błąd testów lub builda zatrzymuje
wdrożenie przed połączeniem z serwerem.

### Zakres aktualizacji i ograniczenia

Skrypt `scripts/deploy.sh` aktualizuje backend (z pominięciem `passenger_wsgi.py`,
konfiguracji hostingu, środowisk wirtualnych, testów, plików `.env` i baz), zbudowany
frontend oraz dwa katalogi instrumentów JSON. Nie przesyła produkcyjnej bazy
i nie używa `rsync --delete`: pliki istniejące wyłącznie na serwerze pozostają.
Jeśli usuniesz moduł backendu z repozytorium, usuń jego starą kopię na serwerze
ręcznie po sprawdzeniu, że nie jest już potrzebna.

Aktualizacja plików i zależności odbywa się w działającym katalogu aplikacji;
możliwa jest krótka przerwa lub mieszanka wersji podczas kopiowania. Nie ma
automatycznego rollbacku. Błąd instalacji lub kontroli HTTP wymaga sprawdzenia
logów i ewentualnego przywrócenia poprzedniej paczki. Zmiany samego
`passenger_wsgi.py` trzeba wprowadzać na serwerze ręcznie, bo workflow go zachowuje.
Start backendu wykonuje obecną w kodzie inicjalizację schematu; workflow nie
uruchamia dodatkowo `alembic upgrade head`.

Dokumentacja: [zdarzenia GitHub Actions](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows),
[restart Passenger](https://www.phusionpassenger.com/docs/advanced_guides/troubleshooting/apache/restart_app.html).
