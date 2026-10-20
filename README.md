# Parkivo — Parking Reservation Service

Backendowy system zarządzania parkingiem oparty na mikrousługach.
Główny cel: pokazać jeden proces biznesowy realizowany przez współpracujące usługi — od rezerwacji miejsca, przez sesję parkowania, po rozliczenie.

## Spis treści

1. [Docelowy system](#1-docelowy-system)
2. [Granica odpowiedzialności usług](#2-granica-odpowiedzialności-usług)
3. [Model danych](#3-model-danych-parking-service)
4. [API Parking Service](#4-api-parking-service)
5. [Stos technologiczny i struktura repozytorium](#5-stos-technologiczny-i-struktura-repozytorium)

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

## 5. Stos technologiczny i struktura repozytorium

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

Planowana struktura:

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
