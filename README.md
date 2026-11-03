# Parkivo — Parking Reservation Service

Backendowy system zarządzania parkingiem oparty na mikrousługach.
Główny cel: pokazać jeden proces biznesowy realizowany przez współpracujące usługi — od rezerwacji miejsca, przez sesję parkowania, po rozliczenie.

## Spis treści

1. [Docelowy system](#1-docelowy-system)
2. [Granica odpowiedzialności usług](#2-granica-odpowiedzialności-usług)
3. [Model danych](#3-model-danych-parking-service)
4. [API Parking Service](#4-api-parking-service)
5. [Implementacja LAB1](#5-implementacja-lab1)
6. [Implementacja LAB2 (baza i cache)](#6-implementacja-lab2-baza-i-cache)
7. [Stos technologiczny i struktura repozytorium](#7-stos-technologiczny-i-struktura-repozytorium)

---

## 1. Docelowy system

| # | Usługa | Odpowiada za | Osoba |
|---|--------|--------------|-------|
| 1 | **Parking Service** | parkingi, miejsca, ich statusy | 1 |
| 2 | **Reservation Service** | rezerwacje miejsc na przedział czasu | 1 |
| 3 | **Parking Session Service** | wjazd/wyjazd pojazdów, sesje postoju | 2 |
| 4 | **Billing Service** | cennik, rachunki, płatności | 2 |

Przepływ biznesowy:

1. Użytkownik rezerwuje miejsce A-12 (Reservation Service).
2. Miejsce dostaje status zarezerwowanego (Parking Service).
3. Wjazd pojazdu rozpoczyna sesję, wyjazd ją kończy (Parking Session Service).
4. System oblicza opłatę i tworzy rachunek (Billing Service).
5. Po potwierdzeniu płatności miejsce zostaje zwolnione.

---

## 2. Granica odpowiedzialności usług

### Parking Service (implementowana na LAB1)

**Usługa odpowiada za:**
- prowadzenie rejestru parkingów i miejsc parkingowych (dodawanie, odczyt, edycja),
- typy miejsc (standardowe, dla osób z niepełnosprawnościami, EV),
- **aktualny status każdego miejsca** i pilnowanie dozwolonych przejść między statusami,
- wyszukiwanie miejsc według parkingu, statusu i typu (np. wolne miejsca EV).

**Usługa nie odpowiada za:**
- rezerwacje, ich przedziały czasu i kolizje terminów (Reservation Service),
- wjazdy, wyjazdy i czas postoju pojazdów (Parking Session Service),
- ceny, rachunki i płatności (Billing Service).

### Podział usług

| Usługa | Odpowiedzialność biznesowa | Własne dane | Operacje | Informacje potrzebne od innej usługi |
|--------|---------------------------|-------------|----------|--------------------------------------|
| **Pierwsza — Parking Service** (LAB1) | Co fizycznie istnieje na parkingu i w jakim stanie jest każde miejsce | `parking_lots`, `parking_spaces` (w tym status miejsca) | tworzenie/odczyt parkingów, dodawanie miejsc, odczyt i filtrowanie miejsc, zmiana statusu miejsca, `/health` | **brak** — usługa działa samodzielnie; to inni pytają ją o miejsca |
| **Druga — Reservation Service** (planowana) | Kto i kiedy zarezerwował miejsce; brak nakładających się rezerwacji tego samego miejsca | `reservations` (id, space_id, user_id, starts_at, ends_at, status) | utworzenie, odczyt, anulowanie rezerwacji, wygasanie niepotwierdzonych | od Parking Service: czy miejsce istnieje i nie jest `OUT_OF_SERVICE`; zmiana statusu miejsca na `RESERVED` / `FREE` |

### Pojęcia domeny

| Pojęcie | Definicja | Kto może zmieniać |
|---------|-----------|-------------------|
| **Parking (ParkingLot)** | Obiekt o nazwie, adresie i pojemności, który grupuje miejsca. | Parking Service (administrator parkingu) |
| **Miejsce (ParkingSpace)** | Pojedyncze, ponumerowane (np. A-12) miejsce na parkingu, o określonym typie. | Parking Service (administrator parkingu) |
| **Status miejsca** | Aktualny stan miejsca: `FREE`, `RESERVED`, `OCCUPIED`, `OUT_OF_SERVICE`. | Parking Service przyjmuje zmianę; inicjują ją: Reservation Service (`RESERVED`/`FREE`), Parking Session Service (`OCCUPIED`/`FREE`), administrator (`OUT_OF_SERVICE`) |
| **Typ miejsca** | Rodzaj miejsca: `STANDARD`, `DISABLED`, `EV`. | tylko Parking Service (przy tworzeniu miejsca) |
| **Rezerwacja** | Prawo użytkownika do miejsca w przedziale czasu — *nie* jest to status miejsca. | tylko Reservation Service |

### Dlaczego taki podział?

Granice wynikają z **odpowiedzialności biznesowej**, a nie z tabel w bazie. Parking Service odpowiada na pytanie *„jakie miejsca są i w jakim są stanie?”*, a Reservation Service na pytanie *„kto może z nich skorzystać i kiedy?”*. Te dwie rzeczy zmieniają się z innych powodów i w innym tempie: cennik czy zasady rezerwacji (np. wygasanie po 15 minutach) nie powinny wymuszać zmian w rejestrze miejsc. Gdyby podział robić po tabelach, powstałaby osobna usługa dla każdej encji (np. „usługa typów miejsc”), co nie ma sensu biznesowego — `ParkingLot` i `ParkingSpace` żyją razem w jednym kontekście (bounded context), bo miejsce nie istnieje bez parkingu, a spójność pojemności i numeracji trzeba pilnować w jednym miejscu.

### Kontrakt przyszłego wywołania HTTP

**Reservation Service → Parking Service**: po utworzeniu rezerwacji oznacz miejsce jako zarezerwowane.

- **Nadawca:** Reservation Service
- **Odbiorca:** Parking Service
- **Metoda i ścieżka:** `PATCH /spaces/{id}/status`

Żądanie:

```http
PATCH /spaces/12/status HTTP/1.1
Content-Type: application/json

{ "status": "RESERVED" }
```

Odpowiedź `200 OK`:

```json
{ "id": 12, "parking_lot_id": 1, "number": "A-12", "type": "STANDARD", "status": "RESERVED" }
```

Odpowiedzi błędów: `404` (miejsce nie istnieje), `409` (miejsce jest już `RESERVED`/`OCCUPIED`/`OUT_OF_SERVICE`), `422` (niepoprawny status).

**Zachowanie przy niedostępności odbiorcy** (timeout, błąd połączenia, `5xx`):

- Reservation Service ustawia timeout 2 s i ponawia żądanie maks. 2 razy (backoff 0,5 s).
- Jeśli nadal brak odpowiedzi — **nie zapisuje rezerwacji** i zwraca klientowi `503 Service Unavailable` z `{"detail": "Parking Service niedostępny"}`. Dzięki temu nie powstaje rezerwacja miejsca, które nie zostało zablokowane.
- `409` od Parking Service oznacza „miejsce zajęte” i jest przekazywane klientowi jako `409`.

### Trzy warianty architektury

**Wariant A — aplikacja monolityczna**

```
Klient
  |
  v
Jedna aplikacja
├── obsługa parkingów i miejsc
├── obsługa rezerwacji
├── sesje parkowania
└── rozliczenia
  |
  v
Jedna baza danych
```

Wszystkie funkcje działają w jednym procesie. Wywołanie odbywa się bezpośrednio w kodzie (np. moduł rezerwacji wywołuje metodę zmiany statusu miejsca).

**Wariant B — modularny monolit**

```
Klient
  |
  v
Jedna aplikacja i jeden proces
├── moduł parkingów
├── moduł rezerwacji
├── moduł sesji
└── moduł rozliczeń
  |
  v
Jedna baza danych
```

Moduły mają wyraźne granice i osobny kod, ale są uruchamiane i wdrażane razem. Komunikacja odbywa się wewnątrz procesu („wywołanie w kodzie”).

**Wariant C — mikrousługi**

```
Klient
  |
  +--> Parking Service     --> Parking DB
  +--> Reservation Service --> Reservation DB
  +--> Session Service     --> Session DB
  +--> Billing Service     --> Billing DB
```

Każda usługa to osobny proces z własną bazą; usługi wołają się nawzajem przez HTTP (np. Reservation Service → Parking Service).

### Checkpoint przed kodowaniem

- **Zakres pierwszej usługi:** rejestr parkingów i miejsc oraz ich statusów.
- **Rola drugiej:** Reservation Service rezerwuje miejsca na czas i prosi Parking Service o zmianę statusu.
- **Reguła pierwszej usługi:** miejsca zajętego (`OCCUPIED`) nie można zarezerwować; dozwolone są tylko określone przejścia statusów (patrz [sekcja 3](#reguła-biznesowa-przejścia-statusów-miejsca)).

---

## 3. Model danych (Parking Service)

### ParkingLot

| Pole | Typ | Wymagane | Opis |
|------|-----|----------|------|
| `id` | int | nadaje **serwer** | klucz główny, autoinkrementacja |
| `name` | string (1–100) | tak | nazwa, unikalna |
| `address` | string (1–200) | tak | adres |

### ParkingSpace

| Pole | Typ | Wymagane | Opis |
|------|-----|----------|------|
| `id` | int | nadaje **serwer** | klucz główny |
| `parking_lot_id` | int | tak (z ścieżki) | parking, do którego należy miejsce |
| `number` | string (1–10) | tak | np. `A-12`, unikalny w obrębie parkingu |
| `type` | enum | nie (domyślnie `STANDARD`) | `STANDARD`, `DISABLED`, `EV` |
| `status` | enum | nie (domyślnie `FREE` przy tworzeniu) | `FREE`, `RESERVED`, `OCCUPIED`, `OUT_OF_SERVICE` |

Decyzje projektowe:

- **Identyfikator nadaje serwer** — klient nie może wybrać cudzego ani kolidującego id.
- **Dwa modele**, bo parking i miejsce mają różny cykl życia: parking zmienia się rzadko, status miejsca często.
- Status przy tworzeniu miejsca zawsze `FREE`; klient nie może utworzyć miejsca od razu jako `OCCUPIED`.

### Reguła biznesowa: przejścia statusów miejsca

Status zmienia się tylko według poniższej tabeli (dotyczy wyłącznie danych Parking Service, więc da się ją sprawdzić bez drugiej usługi):

| Z \ Na | FREE | RESERVED | OCCUPIED | OUT_OF_SERVICE |
|--------|:----:|:--------:|:--------:|:--------------:|
| **FREE** | — | ✅ | ✅ | ✅ |
| **RESERVED** | ✅ | — | ✅ | ✅ |
| **OCCUPIED** | ✅ | ❌ | — | ✅ |
| **OUT_OF_SERVICE** | ✅ | ❌ | ❌ | — |

Dodatkowo: ustawienie tego samego statusu, który miejsce już ma, jest konfliktem.

- **Dozwolone:** miejsce `FREE` → `RESERVED` (`PATCH /spaces/12/status` z `{"status": "RESERVED"}`) → `200`.
- **Niedozwolone:** miejsce `OCCUPIED` → `RESERVED` albo `OUT_OF_SERVICE` → `OCCUPIED` → **`409 Conflict`**
  `{"detail": "Niedozwolona zmiana statusu: OCCUPIED -> RESERVED"}`.
- **Niepoprawna wartość** statusu (np. `"BROKEN"`) → `422`.

---

## 4. API Parking Service

Konwencje:

- Format: JSON, daty (jeśli występują) w ISO 8601 UTC.
- `404` — nieistniejący zasób, `409` — konflikt z aktualnym stanem, `422` — niepoprawne dane.
- Pusta lista to `200` i `[]`; brak pojedynczego elementu to `404`.

### Tabela operacji

| Metoda | Endpoint | Znaczenie | Sukces | Błędy |
|--------|----------|-----------|--------|-------|
| GET | `/health` | status działania usługi | 200 | — |
| GET | `/parking-lots` | lista parkingów | 200 | — |
| POST | `/parking-lots` | utworzenie parkingu | 201 | 409, 422 |
| GET | `/parking-lots/{id}` | jeden parking | 200 | 404, 422 |
| GET | `/parking-lots/{id}/spaces` | lista miejsc parkingu (filtry `status`, `type`) | 200 | 404, 422 |
| POST | `/parking-lots/{id}/spaces` | dodanie miejsca | 201 | 404, 409, 422 |
| GET | `/spaces/{id}` | jedno miejsce | 200 | 404, 422 |
| PATCH | `/spaces/{id}/status` | zmiana statusu miejsca | 200 | 404, 409, 422 |

### Format błędów

Zachowujemy standardowy format FastAPI.

**`HTTPException` (404, 409)** — jeden opis tekstowy:

```json
{ "detail": "Parking lot 99 not found" }
```

**Walidacja (422)** — lista szczegółów w `detail`:

```json
{
  "detail": [
    {
      "type": "string_too_short",
      "loc": ["body", "name"],
      "msg": "String should have at least 1 character",
      "input": ""
    }
  ]
}
```

### GET /health

Bez danych domenowych.

`200`:

```json
{ "status": "ok", "service": "parking-service" }
```

### GET /parking-lots

`200` — lista (może być pusta `[]`):

```json
[
  { "id": 1, "name": "Parking Centrum", "address": "ul. Długa 1, Gdańsk" }
]
```

### POST /parking-lots

Żądanie:

| Pole | Typ | Wymagane | Ograniczenia |
|------|-----|----------|--------------|
| `name` | string | tak | 1–100 znaków, unikalna |
| `address` | string | tak | 1–200 znaków |

```json
{ "name": "Parking Centrum", "address": "ul. Długa 1, Gdańsk" }
```

`201 Created`:

```json
{ "id": 1, "name": "Parking Centrum", "address": "ul. Długa 1, Gdańsk" }
```

Błędy: `409` `{"detail": "Parking lot with name 'Parking Centrum' already exists"}`; `422` (brak lub pusta nazwa/adres).

### GET /parking-lots/{id}

Parametr ścieżki: `id` (int).

`200`:

```json
{ "id": 1, "name": "Parking Centrum", "address": "ul. Długa 1, Gdańsk" }
```

Błędy: `404` `{"detail": "Parking lot 99 not found"}`; `422` (`id` nie jest liczbą).

### GET /parking-lots/{id}/spaces

Parametry zapytania (opcjonalne): `status` (`FREE|RESERVED|OCCUPIED|OUT_OF_SERVICE`), `type` (`STANDARD|DISABLED|EV`).

Przykład: `GET /parking-lots/1/spaces?status=FREE&type=EV`

`200` (parking istnieje, ale nic nie pasuje → `[]`):

```json
[
  { "id": 3, "parking_lot_id": 1, "number": "A-03", "type": "EV", "status": "FREE" }
]
```

Błędy: `404` (parking nie istnieje); `422` (niepoprawna wartość filtra).

### POST /parking-lots/{id}/spaces

Żądanie:

| Pole | Typ | Wymagane | Ograniczenia |
|------|-----|----------|--------------|
| `number` | string | tak | 1–10 znaków, unikalny w parkingu |
| `type` | enum | nie | `STANDARD` (domyślnie), `DISABLED`, `EV` |

```json
{ "number": "A-12", "type": "STANDARD" }
```

`201 Created` (status zawsze `FREE`):

```json
{ "id": 12, "parking_lot_id": 1, "number": "A-12", "type": "STANDARD", "status": "FREE" }
```

Błędy: `404` (parking nie istnieje); `409` `{"detail": "Space A-12 already exists in parking lot 1"}`; `422`.

### GET /spaces/{id}

`200`:

```json
{ "id": 12, "parking_lot_id": 1, "number": "A-12", "type": "STANDARD", "status": "FREE" }
```

Błędy: `404` `{"detail": "Space 99 not found"}`; `422`.

### PATCH /spaces/{id}/status

Żądanie:

| Pole | Typ | Wymagane | Ograniczenia |
|------|-----|----------|--------------|
| `status` | enum | tak | `FREE`, `RESERVED`, `OCCUPIED`, `OUT_OF_SERVICE` |

```json
{ "status": "RESERVED" }
```

`200`:

```json
{ "id": 12, "parking_lot_id": 1, "number": "A-12", "type": "STANDARD", "status": "RESERVED" }
```

Błędy:

- `404` `{"detail": "Space 99 not found"}`
- `409` `{"detail": "Niedozwolona zmiana statusu: OCCUPIED -> RESERVED"}` (reguła z sekcji 3; także ten sam status co aktualny)
- `422` (np. `{"status": "BROKEN"}` lub brak pola `status`)

---

## 5. Implementacja LAB1

Zaimplementowana jest tylko pierwsza usługa — **Parking Service** (FastAPI). Pozostałe usługi są wyłącznie zaprojektowane.

### Uruchomienie

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8101
```

Swagger UI: `http://127.0.0.1:8101/docs`. Testy: `python -m pytest`.

### Struktura kodu

```
app/
  main.py      # create_app(), endpointy, tabela dozwolonych przejść statusów
  models.py    # modele Pydantic i enumy (SpaceStatus, SpaceType)
  store.py     # magazyn w pamięci (Store) i dane początkowe (seed)
tests/
  conftest.py        # fixture client (świeża aplikacja z create_app())
  test_health.py     # test /health
  test_parking.py    # testy domenowe: odczyt, zapis, 404, 422, 409, reguła przejść
requirements.txt
```

### Przechowywanie danych i ograniczenia

- Dane są w **słownikach w pamięci procesu** (`Store.lots`, `Store.spaces`). Na LAB1 nie ma bazy danych, pliku ani cache.
- Magazyn jest tworzony **raz na instancję aplikacji** w `create_app()` i zapisany w `app.state.store`; endpointy dostają go przez `Depends(get_store)`. Zmiana z `POST`/`PATCH` jest więc widoczna w następnym `GET`.
- Każde wywołanie `create_app()` daje **własny, nowy magazyn** — dzięki temu testy zaczynają od znanego stanu.
- **Restart procesu** (także ten wywołany przez `--reload`) usuwa wszystkie zmiany z pamięci i przywraca dane początkowe.
- **Dwie instancje** uruchomione na różnych portach mają **osobne magazyny** i osobne liczniki `id`.
- Identyfikatory nadaje serwer (osobne liczniki dla parkingów i miejsc), więc po restarcie numeracja zaczyna się od nowa.

### Dane początkowe (seed)

Po starcie aplikacja zawiera:

| Zasób | id | Dane |
|-------|----|------|
| Parking | 1 | `Parking Szpital`, `ul. lwowska 60` |
| Miejsce | 1 | `A-01`, `STANDARD`, `FREE` |
| Miejsce | 2 | `A-02`, `EV`, `FREE` |
| Miejsce | 3 | `A-03`, `DISABLED`, `FREE` |

### Kody odpowiedzi — dlaczego takie

| Kod | Kiedy | Uzasadnienie |
|-----|-------|--------------|
| `200 OK` | odczyt lub zmiana statusu istniejącego miejsca | operacja się udała, nie powstał nowy zasób |
| `201 Created` | `POST` parkingu lub miejsca | w wyniku operacji powstał nowy zasób z `id` nadanym przez serwer |
| `404 Not Found` | parking lub miejsce o podanym `id` nie istnieje | adres wskazuje zasób, którego nie ma; pusta lista to jednak `200` i `[]`, bo kolekcja istnieje |
| `409 Conflict` | duplikat nazwy parkingu, duplikat numeru miejsca w parkingu, niedozwolone przejście statusu | dane są poprawne same w sobie, ale **kolidują z aktualnym stanem** — to samo żądanie w innym stanie mogłoby się udać |
| `422 Unprocessable Entity` | pusta nazwa, za długi `number`, status spoza listy, `id` niebędące liczbą | żądanie jest zrozumiałe, ale **dane są niepoprawne niezależnie od stanu**; sprawdza je Pydantic, zanim kod dotknie magazynu |

Reguła przejść statusów daje `409`, a nie `422`, ponieważ `{"status": "RESERVED"}` jest poprawnym żądaniem: jego odrzucenie zależy od aktualnego statusu miejsca (`FREE → RESERVED` przejdzie, `OCCUPIED → RESERVED` nie).

Wszystkie warunki odrzucenia (`404`, `409`) są sprawdzane **przed** zmianą danych, więc odrzucone żądanie nie zostawia częściowo zmienionego stanu.

### Testy automatyczne

Uruchomienie: `python -m pytest` (nie wymaga działającego Uvicorna — używany jest `TestClient`).

Fixture `client` w `tests/conftest.py` tworzy **świeżą aplikację przez `create_app()`**, więc każdy test startuje od danych początkowych z sekcji „Dane początkowe (seed)” i nie zależy od kolejności uruchomienia.

| Scenariusz | Testy (`tests/test_parking.py`) |
|------------|---------------------------------|
| `/health` | `test_health` (`tests/test_health.py`) |
| Lista i szczegóły | `test_list_and_detail_of_seeded_lot`, `test_list_spaces_filters_and_empty_list` (w tym `200` i `[]`) |
| Zapis → odczyt | `test_create_space_then_read_it_back`, `test_create_lot_then_read_it_back` |
| Brak zasobu (`404`) | `test_missing_resources_return_404` |
| Niepoprawne dane (`422`), brak zmiany stanu | `test_invalid_data_returns_422_and_changes_nothing` |
| Konflikt (`409`), brak zmiany stanu | `test_duplicate_lot_name_returns_409_and_changes_nothing`, `test_duplicate_space_number_returns_409_and_changes_nothing` |
| Reguła biznesowa (przejścia statusów) | `test_allowed_status_transition_is_visible_in_next_get`, `test_occupied_space_cannot_be_reserved`, `test_out_of_service_space_must_return_to_free_first`, `test_setting_the_same_status_is_a_conflict` |
| Izolacja testów | `test_each_test_starts_from_seed_state` |

Testy sprawdzają kod HTTP oraz istotne pola JSON. Testy odrzuceń (`422`, `409`) dodatkowo potwierdzają osobnym `GET`, że stan magazynu się nie zmienił.

Restart procesu i prawdziwy port są sprawdzane osobno, ręcznie (`TestClient` nie uruchamia Uvicorna).

### Eksperyment z restartem

**Cel:** pokazać, że dane przetrwają między żądaniami, ale nie między uruchomieniami procesu.

**Przygotowanie:** serwer uruchomiony bez `--reload`, żeby restart był wyłącznie moją decyzją, i bez zmian w kodzie w trakcie eksperymentu:

```bash
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8101
```

Wszystkie żądania wykonane w Swagger UI (`http://127.0.0.1:8101/docs`, „Try it out”).

| Krok | Żądanie | Oczekiwany wynik | Wynik rzeczywisty |
|------|---------|------------------|-------------------|
| 1. Stan początkowy | `GET /parking-lots/1/spaces` | `200`, 3 miejsca (`A-01`, `A-02`, `A-03`), wszystkie `FREE` | zgodny z oczekiwaniem — [zrzut 1](#zrzut-1) |
| 2. Zmiana danych | `POST /parking-lots/1/spaces` z `{"number": "B-01", "type": "EV"}`, potem `PATCH /spaces/1/status` z `{"status": "OCCUPIED"}` | nowe miejsce `B-01` (`id=4`, `FREE`) i `A-01` jako `OCCUPIED` | potwierdzone w kroku 3 |
| 3. Potwierdzenie osobnym `GET` | `GET /parking-lots/1/spaces` | `200`, 4 miejsca, `A-01` = `OCCUPIED`, jest `B-01` | zgodny z oczekiwaniem — [zrzut 2](#zrzut-2) |
| 4. Restart | Ctrl+C w terminalu z serwerem, ponowne uruchomienie tą samą komendą | serwer startuje od nowa | — |
| 5. Powtórzenie `GET` | `GET /parking-lots/1/spaces` | `200`, znów 3 miejsca, `A-01` = `FREE`, brak `B-01` | zgodny z oczekiwaniem — [zrzut 3](#zrzut-3) |

**Przywrócenie stanu:** nie jest potrzebne — restart procesu sam przywraca dane początkowe (seed).

<a id="zrzut-1"></a>**Zrzut 1 — stan początkowy (3 miejsca, wszystkie `FREE`)**

![Stan początkowy](img_1.png)

<a id="zrzut-2"></a>**Zrzut 2 — po zmianie (`A-01` = `OCCUPIED`, dodane `B-01`)**

![Po zmianie danych](img_2.png)

<a id="zrzut-3"></a>**Zrzut 3 — po restarcie (stan jak na początku)**

![Po restarcie](img_3.png)

**Wyjaśnienie:**

- Dane **przetrwały między żądaniami**, ponieważ magazyn `Store` jest tworzony **raz** w `create_app()` i zapisany w `app.state.store`. Każde żądanie czyta i zapisuje te same słowniki w pamięci działającego procesu, więc osobny `GET` widzi zmianę z `POST`/`PATCH`.
- Dane **nie przetrwały restartu**, ponieważ słowniki żyją wyłącznie w pamięci procesu. Ctrl+C kończy proces i system zwalnia jego pamięć. Nowy proces wywołuje `create_app()` od początku, tworzy pusty `Store` i ładuje dane początkowe (`seed`), więc `A-01` wraca do `FREE`, a `B-01` znika. Na LAB1 jest to zamierzone ograniczenie: nie ma bazy danych ani zapisu do pliku.

### Praca z dokumentacją (EK_03)

#### Fragment 1 — model żądania (Request Body)

Dokumentacja: <https://fastapi.tiangolo.com/tutorial/body/>

**Problem:** sprawdzić dane wejściowe (pusta nazwa, za długi numer, nieznany status) i nie pozwolić klientowi podawać `id`.
**Rozwiązanie:** ciało żądania to parametr funkcji typu modelu Pydantic; FastAPI waliduje je przed wejściem do funkcji.

`app/models.py`:

```python
class ParkingLotCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    address: str = Field(min_length=1, max_length=200)

class ParkingLot(ParkingLotCreate):
    id: int
```

`app/main.py`:

```python
@app.post("/parking-lots", response_model=ParkingLot, status_code=201)
def create_lot(data: ParkingLotCreate, store: Store = Depends(get_store)):
    ...
    return store.add_lot(data)
```

`app/store.py` (`model_dump()` z dokumentacji):

```python
lot = ParkingLot(id=self.next_lot_id, **data.model_dump())
```

**Sprawdzenie:** `POST /parking-lots` z pustą nazwą daje `422`, a lista parkingów się nie zmienia (`test_invalid_data_returns_422_and_changes_nothing`); poprawny `POST` daje `201`, a osobny `GET` potwierdza zapis (`test_create_lot_then_read_it_back`).

#### Fragment 2 — obsługa błędów (Handling Errors)

Dokumentacja: <https://fastapi.tiangolo.com/tutorial/handling-errors/>

**Problem:** odróżnić brak zasobu (`404`) od konfliktu ze stanem (`409`) i przerwać operację, zanim zmieni dane.
**Rozwiązanie:** `raise HTTPException(status_code=..., detail=...)` — wyjątek się rzuca, a nie zwraca, więc kończy funkcję natychmiast.

`app/main.py`:

```python
space = store.get_space(space_id)
if space is None:
    raise HTTPException(status_code=404, detail=f"Space {space_id} not found")
if body.status not in ALLOWED_TRANSITIONS[space.status]:
    raise HTTPException(
        status_code=409,
        detail=f"Niedozwolona zmiana statusu: {space.status.value} -> {body.status.value}",
    )
space.status = body.status
```

**Sprawdzenie:** `GET /spaces/99` daje `404` z `{"detail": "Space 99 not found"}` (`test_missing_resources_return_404`); `OCCUPIED → RESERVED` daje `409`, a następny `GET` pokazuje nadal `OCCUPIED` (`test_occupied_space_cannot_be_reserved`).

## 6. Implementacja LAB2 (baza i cache)

LAB2 rozwija **tę samą usługę** (Parking Service): dane z pamięci procesu przechodzą do bazy SQLite (SQLAlchemy), a wybrany odczyt dostaje cache w Redis (cache-aside). **Kontrakt API z sekcji 4 nie zmienia się** — te same metody, ścieżki, identyfikatory, JSON i kody błędów (`404`, `409`, `422`).

Stan prac w tym README: opisane są kroki 1–7 (stan początkowy, model danych, podłączenie bazy, operacje i reguła w bazie, cache-aside, awaria cache, testy). Końcowa dokumentacja zostanie dopisana w kroku 8.

### Zmiany względem LAB1

| | LAB1 | LAB2 |
|---|------|------|
| Dane | słowniki w pamięci (`Store`) | tabele w SQLite (`app.db`) |
| Restart procesu | dane wracają do seeda | dane zostają w pliku bazy |
| Dostęp do danych | `Depends(get_store)` | repozytorium (`app/repository.py`) |
| Konfiguracja | brak | `create_app(database_url, redis_client)` + zmienne środowiskowe |
| Cache | brak | odczyt `GET /spaces/{id}` w Redis (krok 5) |

### Krok 1 — stan początkowy

Przed zmianami uruchomiono testy LAB1 (`python -m pytest -q`) oraz usługę (`python -m uvicorn app.main:app --port 8101`). Zmiany danych przez API były widoczne w kolejnych `GET`, ale **po restarcie procesu znikały** — szczegółowy przebieg i zrzuty ekranu: [Eksperyment z restartem](#eksperyment-z-restartem). To jest problem, który rozwiązuje LAB2. W LAB1 nie było żadnej bazy ani pliku z danymi, więc nie ma istniejącej persystencji do opisania.

### Krok 2 — model danych i decyzje

| Decyzja | Odpowiedź i uzasadnienie |
|---------|--------------------------|
| Jakie dane muszą przetrwać restart? | Parkingi, miejsca i **aktualny status każdego miejsca** — to jedyne dane domenowe Parking Service. |
| Jakie tabele i powiązania są potrzebne? | `parking_lots` (`id`, `name` unikalna, `address`) oraz `parking_spaces` (`id`, `parking_lot_id` → FK do `parking_lots.id`, `number`, `type`, `status`). Relacja 1:N: parking ma wiele miejsc. |
| Która usługa może je zapisywać? | Wyłącznie Parking Service. Inne usługi zmieniają status tylko przez `PATCH /spaces/{id}/status`, nigdy bezpośrednio w tabelach. |
| Których danych drugiej usługi tu nie zapisujemy? | Rezerwacji (kto i kiedy — Reservation Service), sesji postoju i rachunków. Status `RESERVED` to stan miejsca, a nie rezerwacja. |
| Co chroni baza, a co reguła biznesowa? | **Baza:** klucze główne, klucz obcy `parking_lot_id`, unikalność `parking_lots.name` oraz pary `(parking_lot_id, number)`. **Reguła w kodzie:** dozwolone przejścia statusów (sekcja 3); naruszenie → `409`, zanim cokolwiek się zmieni. Tabeli przejść nie da się wyrazić samym ograniczeniem bazy. |
| Jaki odczyt cache'ujemy i jak długo może być nieaktualny? | `GET /spaces/{id}`; kopia może być nieaktualna maksymalnie do końca TTL (60 s), a w praktyce krócej, bo zmiana statusu usuwa wpis. Decyzja o rezerwacji nie powinna zapadać wyłącznie na podstawie kopii. |
| Prefiks, klucz, TTL, unieważnianie? | Prefiks `lab2:<numer_albumu>:parking-service`, klucz `…:space:{id}` (np. `lab2:<album>:parking-service:space:1`), TTL 60 s, unieważnienie przez `DELETE` klucza **po** commicie w bazie przy `PATCH /spaces/{id}/status`. |

Wszystkie operacje na parkingach i miejscach korzystają z jednego magazynu — bazy. `Store` w pamięci przestaje być używany.

### Krok 3 — podłączenie bazy

**Zależności** (`requirements.txt`, zależności LAB1 zachowane):

```
SQLAlchemy>=2.0,<2.1
redis>=5,<7
```

**Docelowa struktura kodu:**

```
app/
  main.py        # create_app(database_url=None, redis_client=None), endpointy LAB1
  models.py      # modele Pydantic (kontrakt API) — bez zmian
  db_models.py   # modele ORM: tabele parking_lots, parking_spaces
  database.py    # silnik, fabryka sesji, PRAGMA foreign_keys=ON
  repository.py  # operacje na bazie, jedna sesja na operację
  cache.py       # JsonCache (Redis) — używany od kroku 5
tests/
requirements.txt
README.md
```

**Konfiguracja:**

| Zmienna | Znaczenie | Przykład |
|---------|-----------|----------|
| `DATABASE_URL` | adres bazy (ścieżka względna do katalogu uruchomienia) | `sqlite:///./app.db` |
| `REDIS_URL` | adres Redis | `redis://localhost:6379/0` |
| `CACHE_PREFIX` | prefiks kluczy (wymagany przy starcie) | `lab2:<numer_albumu>:parking-service` |
| `CACHE_TTL_SECONDS` | czas życia wpisu | `60` |

Konfiguracja jest przekazywana jako argument `create_app(database_url, redis_client)`, więc testy mogą wskazać osobną bazę i atrapę Redis. Zasoby (silnik, klient Redis, repozytorium, cache) powstają w `lifespan` przy starcie aplikacji i są zwalniane przy zamknięciu (zamknięcie klienta Redis, `engine.dispose()`). Schemat tworzy `Base.metadata.create_all(engine)`; baza **nie jest kasowana** przy starcie, a `create_all` nie zmienia istniejących kolumn (migracje Alembic są poza zakresem). Dane początkowe (seed) są dodawane tylko do pustej bazy, żeby nie nadpisywać zmian ani nie dublować rekordów po restarcie.

Plik bazy (`*.db` i pliki pomocnicze SQLite) jest w `.gitignore` i nie trafia do repozytorium. Zawartość bazy można podejrzeć w DataGrip (źródło danych SQLite → plik `app.db`).

**Uruchomienie z konfiguracją:**

```bash
export DATABASE_URL="sqlite:///./app.db"
export REDIS_URL="redis://localhost:6379/0"
export CACHE_PREFIX="lab2:<numer_albumu>:parking-service"
export CACHE_TTL_SECONDS=60
python -m uvicorn app.main:app --port 8101
```

Po zmianie zmiennych serwer trzeba zatrzymać (Ctrl+C) i uruchomić ponownie w tym samym terminalu — samo `--reload` ich nie odświeża.

### Krok 4 — operacje i reguła w bazie

Wszystkie operacje z sekcji 4 (listy, szczegóły, `POST` parkingu i miejsca, `PATCH` statusu) korzystają wyłącznie z bazy przez `ParkingRepository`; `Store` w pamięci został usunięty. Zmianą, która posłuży później do testu unieważnienia cache, jest `PATCH /spaces/{id}/status`.

- **Kolejność w zapisie:** odczyt stanu → sprawdzenie reguły → zmiana → commit. W `update_status` całość dzieje się w jednej transakcji (`sessions.begin()`); wyjątek przed commitem wycofuje ją, więc odrzucone żądanie nie zostawia częściowej zmiany.
- **Reguła przejść statusów** (`ALLOWED_TRANSITIONS`, `app/repository.py`) działa na stanie z bazy; naruszenie → `ValueError` → `409` z komunikatem `Niedozwolona zmiana statusu: X -> Y`. Ten sam status co obecny jest konfliktem.
- **Mapowanie błędów:** brak rekordu → `LookupError` → `404`; duplikat nazwy parkingu lub numeru miejsca → `409`. Konflikt wykrywa sprawdzenie w transakcji, a `IntegrityError` z naruszenia **unikalności** (np. wyścig dwóch żądań) też daje `409`. Inne błędy bazy (np. klucz obcy) **nie** są zamieniane na `409` — kończą się błędem serwera.
- **Dowód trwałości i brak częściowego zapisu** (testy w `tests/test_persistence.py`, osobna aplikacja na tym samym pliku bazy z pustym cache):
  - `test_changes_survive_new_app_instance` — zapis miejsca i zmiana statusu są widoczne po utworzeniu nowej instancji; seed nie nadpisuje zmian,
  - `test_rejected_operations_leave_database_unchanged` — odrzucone `409` nie zmieniają stanu po ponownym odczycie,
  - `test_unique_violation_maps_to_409_and_rolls_back`, `test_foreign_key_is_enforced` — ograniczenia bazy działają, a nieudana transakcja jest wycofana.

Ręcznie: zmiana statusu → `GET /spaces/1` → zatrzymanie i ponowny start Uvicorna → `GET /spaces/1` zwraca zmieniony status; `PATCH` na niedozwolony status daje `409`, a kolejny `GET` pokazuje poprzedni stan.

### Krok 5 — cache-aside dla `GET /spaces/{id}`

Cache obejmuje jeden odczyt: szczegóły miejsca. Klucz: `<CACHE_PREFIX>:space:<id>` (np. `lab2:<album>:parking-service:space:1`), wartość to JSON odpowiedzi (`model_dump(mode="json")`, nie obiekt ORM), TTL z `CACHE_TTL_SECONDS` (60 s).

**Odczyt (`GET /spaces/{id}`)** — odpowiedź zawiera nagłówek `X-Cache`:

| Wartość | Znaczenie |
|---------|-----------|
| `HIT` | wpis był w Redis; baza nie została odpytana |
| `MISS` | brak wpisu; odczyt z bazy i zapis kopii do Redis z TTL |
| `BYPASS` | Redis niedostępny; odpowiedź z bazy bez cache |

Brak miejsca → `404`, bez zapisu do cache (nie cache'ujemy błędów).

**Zmiana (`PATCH /spaces/{id}/status`):** najpierw commit w bazie, **dopiero potem** `cache.delete(id)`. Odrzucona zmiana (`404`/`409`) nie dochodzi do unieważnienia, więc nie kasuje wpisu niepotrzebnie. Awaria Redis przy `delete` nie cofa zatwierdzonej zmiany (szczegóły: krok 6).

**Dowód na prawdziwym Redis** (Docker `lab2-redis`, miejsce 1, stan początkowy `FREE`):

| Krok | Żądanie | Oczekiwany wynik | Rzeczywisty wynik |
|------|---------|------------------|-------------------|
| 1 | `GET /spaces/1` | `200`, `X-Cache: MISS` | zgodny |
| 2 | `GET /spaces/1` | `200`, `X-Cache: HIT` | zgodny |
| 3 | `redis-cli TTL <klucz>` | liczba ≤ 60 | `52` |
| 4 | `PATCH /spaces/1/status` `{"status":"RESERVED"}` | `200`, `RESERVED` | zgodny |
| 5 | `GET /spaces/1` | `MISS`, status `RESERVED` (nie stara wartość) | zgodny |

Reset: `docker exec lab2-redis redis-cli DEL <klucz>` oraz usunięcie pliku `app.db` (nie używać `FLUSHALL`/`FLUSHDB`).

**Testy** (`tests/test_cache.py`, atrapa Redis): `test_miss_then_hit_skips_repository` (HIT nie woła repozytorium, TTL = 60), `test_patch_invalidates_cache`, `test_rejected_patch_keeps_cache`, `test_missing_space_is_404_and_not_cached`.

### Krok 6 — awaria cache

Redis jest opcjonalny: jego awaria nie może zablokować odczytu ani cofnąć zatwierdzonej zmiany w bazie. `JsonCache` (`app/cache.py`) łapie `RedisError` przy `get`, `put` i `delete`, loguje ostrzeżenie i nie przerywa żądania. Klient Redis ma krótkie limity (`socket_connect_timeout` i `socket_timeout` 0,3 s) i brak ponowień.

| Operacja przy niedostępnym Redis | Zachowanie |
|----------------------------------|-----------|
| `GET /spaces/{id}` | `200` z bazy, `X-Cache: BYPASS` |
| `PATCH /spaces/{id}/status` | zmiana zatwierdzona w bazie, `200`; nieudane `delete` jest tylko logowane |
| nieudany zapis kopii po `MISS` | `200` z bazy, `X-Cache: BYPASS` |
| reguła biznesowa / `404` | działają bez zmian (`409`, `404`) |

**Ograniczenie spójności:** commit w bazie i usunięcie klucza w Redis nie są jedną transakcją. Jeśli Redis jest niedostępny podczas `PATCH`, stary wpis zostaje i po powrocie Redis `GET` zwraca **starą wartość aż do wygaśnięcia TTL** (max 60 s). Prosty cache-aside nie daje też ścisłej spójności przy równoległych zapisach i odczytach. Dla danych, które nie tolerują takiego opóźnienia (np. ostateczna decyzja o rezerwacji), nie wolno opierać się na kopii z cache.

**Endpoint `/ready`** (rozszerzenie; `/health` bez zmian): `{"service","status","database","cache"}`. Baza i Redis działają → `ok`, `200`; Redis nie działa → `degraded`, `200`; baza nie działa → `error`, `503`.

**Dowód na prawdziwym Redis** (miejsce 1, stan początkowy `FREE`):

| Krok | Akcja | Oczekiwany wynik | Rzeczywisty wynik |
|------|-------|------------------|-------------------|
| 1 | `GET /spaces/1` dwa razy | `MISS`, potem `HIT` | zgodny |
| 2 | `docker stop lab2-redis` | — | — |
| 3 | `GET /spaces/1` | `200`, `X-Cache: BYPASS`, `FREE` | zgodny |
| 4 | `PATCH /spaces/1/status` `RESERVED` | `200`, `RESERVED` (zapis w bazie) | zgodny |
| 5 | `GET /ready` | `200`, `degraded`, `cache: down` | zgodny |
| 6 | `docker start lab2-redis`, `GET /spaces/1` | stara wartość z cache do końca TTL | `HIT`, status `FREE` (stary), TTL 57 s |
| 7 | `redis-cli DEL <klucz>`, `GET /spaces/1` | `MISS`, `RESERVED` | zgodny |

Krok 6 pokazuje opisane ograniczenie: baza ma `RESERVED`, a cache jeszcze `FREE`. Reset: `DEL` klucza i usunięcie `app.db`.

**Testy** (`tests/test_cache_failure.py`): odczyt i zapis bez Redis (`BYPASS`, zmiana w bazie), reguły i `404` bez Redis, nieudane unieważnienie zostawia starą wartość, nieudany zapis kopii, `/ready` w stanie `degraded`. Atrapa `MemoryRedis` nie symuluje upływu TTL, więc wygasania nie potwierdza — to sprawdzono ręcznie.

### Krok 7 — testy

Uruchomienie: `python -m pytest -q` (nie wymaga Dockera ani Redis). Fixture `client` w `tests/conftest.py` tworzy dla **każdego testu** osobną bazę SQLite w `tmp_path` i nową atrapę `MemoryRedis` z prefiksem `lab2:test:parking-service`, więc testy nie współdzielą danych ani kluczy. Atrapa nie symuluje upływu TTL (potwierdzono go ręcznie, niżej). Testy LAB1 (walidacja, konflikty, reguła przejść) zostały zachowane i przechodzą na bazie.

| Wymaganie | Test |
|-----------|------|
| Trwałość: zapis, nowa instancja z tą samą bazą i pustym cache | `test_changes_survive_new_app_instance` (`tests/test_persistence.py`) |
| HIT/MISS; przy HIT repozytorium nie jest wywołane | `test_miss_then_hit_skips_repository` (`tests/test_cache.py`) — licznik wywołań `get_space` przez `monkeypatch` = 1 |
| Unieważnienie: GET, zmiana przez API, kolejny GET z nową wartością i `MISS` | `test_patch_invalidates_cache` (+ `test_rejected_patch_keeps_cache`) |
| Awaria cache: `fake_redis.down = True`, odczyt `200` + `BYPASS`, zapis zatwierdzony w bazie | `test_read_and_write_work_without_redis` (`tests/test_cache_failure.py`) |
| Brak częściowego zapisu po odrzuceniu | `test_rejected_operations_leave_database_unchanged` |
| Błędy: brak zasobu nie trafia do cache | `test_missing_space_is_404_and_not_cached` |

Dodatkowo: `test_failed_invalidation_leaves_stale_value_until_ttl`, `test_failed_cache_set_still_returns_database_value`, `test_ready_reports_degraded_without_redis`, `test_unique_violation_maps_to_409_and_rolls_back`, `test_foreign_key_is_enforced`. Łącznie 28 testów.

**Ręczna weryfikacja z prawdziwym Redis** (Docker `lab2-redis`, `CACHE_TTL_SECONDS=5`, miejsce 1, stan początkowy `FREE`, baza `app.db` usunięta przed próbą):

| Krok | Żądanie / akcja | Oczekiwany wynik | Rzeczywisty wynik |
|------|-----------------|------------------|-------------------|
| 1 | `GET /spaces/1` ×2 | `MISS`, `HIT` | zgodny |
| 2 | `redis-cli TTL <klucz>` | ≤ 5 | `5` |
| 3 | czekanie 6 s, `GET /spaces/1` | `MISS` (wpis wygasł) | zgodny |
| 4 | `PATCH` na `OCCUPIED`, `GET` ×2 | `MISS` z nowym statusem, potem `HIT` | zgodny |
| 5 | restart Uvicorna, `GET` | `HIT` — wpis przeżył restart aplikacji; status `OCCUPIED` | zgodny |
| 6 | czekanie 6 s, `GET` (nowy proces) | `MISS`, `OCCUPIED` odczytany z bazy | zgodny |
| 7 | odłączenie i przywrócenie Redis | patrz krok 6 (`BYPASS`, stara wartość do końca TTL) | zgodny |

Reset: `docker exec lab2-redis redis-cli DEL <klucz>` i usunięcie `app.db`. Nie używano `FLUSHALL`/`FLUSHDB`; testy mają własny prefiks.

## 7. Stos technologiczny i struktura repozytorium

| Element | Technologia |
|---------|-------------|
| Mikrousługi | Python + FastAPI |
| Walidacja | Pydantic |
| Baza danych | PostgreSQL (osobna baza/schemat dla usługi) |
| ORM | SQLAlchemy |
| Komunikacja | REST API; RabbitMQ dla zdarzeń (`VehicleEntered`, `ParkingSessionEnded`, `PaymentConfirmed`) — w późniejszych etapach |
| Uruchamianie | Docker + Docker Compose |
| Testy | pytest + httpx |
| Dokumentacja | Swagger UI / OpenAPI (`/docs`) |

Planowana struktura docelowa (na LAB1 istnieje tylko kod Parking Service w `app/`):

```
parkivo/
  services/
    parking-service/
    reservation-service/
    parking-session-service/
    billing-service/
  docker-compose.yml
  docs/
  tests/
  README.md
```
