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
  dostępna.
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

W **Setup Python App** dodaj zmienne z `backend/.env.example` jako zmienne
środowiskowe aplikacji. Nie wgrywaj produkcyjnego pliku `.env` do archiwum ani
repozytorium. Ustaw co najmniej:

- `PORTFEL_ENV=production`
- `PORTFEL_AUTH_DISABLED=false`
- `PORTFEL_PASSWORD_HASH` — hash hasła wygenerowany lokalnie przez
  `python scripts/hash_password.py`.
- `PORTFEL_SECRET_KEY` — losowy klucz wygenerowany przez ten sam skrypt.
- `PORTFEL_SESSION_HOURS=12`
- `PORTFEL_COOKIE_SECURE=true` — aplikacja musi być dostępna przez HTTPS.
- `PORTFEL_CORS_ORIGINS` — zostaw pustą wartość, gdy frontend i API są pod tą
  samą domeną; w przeciwnym razie podaj dozwolone origins rozdzielone przecinkami.
- `PORTFEL_FRONTEND_DIR` — opcjonalnie; domyślnie aplikacja szuka frontendu w
  `backend/frontend_dist`.

Wartość `PORTFEL_DATABASE_PATH` ustaw na pełną ścieżkę do pliku SQLite w
katalogu zapisywalnym przez użytkownika aplikacji, np.
`/home/NAZWA_UZYTKOWNIKA/portfel-data/portfel.db`. Utwórz wcześniej katalog
`portfel-data` i nadaj użytkownikowi aplikacji uprawnienia do zapisu i
odczytu/zapisu w tym katalogu. Aplikacja utworzy plik bazy przy pierwszym
uruchomieniu.

## 5. Restart i test

Po zapisaniu zmiennych środowiskowych zrestartuj aplikację w cPanel albo utwórz
plik `tmp/restart.txt` w katalogu aplikacji, np.:

```bash
mkdir -p ~/portfel/backend/tmp
touch ~/portfel/backend/tmp/restart.txt
```

Otwórz wybrany adres aplikacji, zaloguj się, a następnie w tej samej
przeglądarce odwiedź `/api/health`, np.
`https://twoja-domena.example/api/health`. Oczekiwana odpowiedź to
`{"ok":true}`. Endpoint wymaga zalogowanej sesji, tak jak pozostałe chronione
trasy API.
