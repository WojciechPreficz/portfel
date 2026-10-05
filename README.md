# Portfel

Prywatna aplikacja do śledzenia inwestycji i ich wartości. Pozwala prowadzić kilka portfeli, zapisywać transakcje kupna i sprzedaży oraz przeglądać łączną wartość, wynik inwestycji, zmianę dzienną i historię portfela w PLN.

## Co potrafi

- Pokazuje podsumowanie portfela, wykres zmian wartości, alokację i listę pozycji.
- Obsługuje m.in. akcje polskie i amerykańskie, ETF-y oraz złoto.
- Umożliwia ręczne dodawanie transakcji, import zakupów z plików xStation5 (`.xlsx`) i Bossa (`.csv`), a także usuwanie pozycji.
- Pobiera i odświeża notowania oraz kursy walut; automatyczne odświeżanie jest zaplanowane na godz. 17:10 i 22:10 czasu warszawskiego.
- Przechowuje dane lokalnie w bazie SQLite `data/portfel.db`.

## Uruchomienie lokalne

Wymagane są Python 3.10 lub nowszy oraz Node.js.

1. W pierwszym terminalu zainstaluj zależności backendu i uruchom API:

   ```powershell
   cd backend
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

2. W drugim terminalu uruchom frontend:

   ```powershell
   cd frontend
   npm install
   npm run dev
   ```

3. Otwórz adres wyświetlony przez Vite, domyślnie <http://127.0.0.1:5173>. Dokumentacja API FastAPI jest dostępna pod <http://127.0.0.1:8000/docs>.

Frontend komunikuje się z API przez lokalny serwer proxy Vite. Przy pierwszym uruchomieniu backend tworzy bazę danych i uzupełnia katalog instrumentów.
