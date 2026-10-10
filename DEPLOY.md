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

## 2. Automatyczny deploy przez GitHub Actions

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
