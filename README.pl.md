# InPost Air Direct — Home Assistant

Polski | [English](README.md)

Integracja Home Assistant pobierająca **temperaturę** i jakość powietrza z czujników zamontowanych na Paczkomatach InPost. Czujniki ma około 4000 Paczkomatów w Polsce.

> **Nieoficjalna.** Niezwiązana z InPost ani przez niego niewspierana. Korzysta z nieudokumentowanych endpointów, które mogą się zmienić lub zniknąć w każdej chwili.

## Funkcje

- **Wyszukiwanie Paczkomatu na mapie** (wbudowana mapa Home Assistant: przesuwasz pinezkę i ustawiasz promień). Najbliższe Paczkomaty są sprawdzane na żywo, a na liście są tylko te, które podają **świeżą temperaturę**. Przy każdym widać aktualną temperaturę, odległość i wiek pomiaru.
- Można też szukać **po miejscowości** (wielkość liter i polskie znaki nie mają znaczenia: `lodz` znajdzie Łódź) albo wpisać **kod Paczkomatu**.
- Paczkomat musi podawać temperaturę, żeby dało się go dodać. Jeśli jego ostatnie dane są stare, trzeba to potwierdzić.
- Sensory: temperatura, wilgotność, ciśnienie, PM1, PM2.5, PM4, PM10, NO2, O3 (tylko te, które Paczkomat podaje), indeks jakości powietrza, procent norm WHO, koniec okna pomiaru.
- **Encja pogody (weather)** dla każdego Paczkomatu (temperatura, wilgotność, ciśnienie) do kart pogodowych.
- **Wykrywanie nieaktualnych danych:** jeśli okno pomiaru skończyło się ponad 2 godziny temu, encje pomiarowe stają się niedostępne. Niektóre Paczkomaty podają dane sprzed wielu dni.
- Paczkomaty można pokazać na karcie Mapa (sensor temperatury ma atrybuty `latitude` i `longitude`).
- Konfiguracja w interfejsie, wiele Paczkomatów, regulowany interwał odpytywania (domyślnie 5 min), pobieranie diagnostyki.

## Wymagania

Home Assistant **2025.10** lub nowszy.

## Instalacja (HACS)

1. HACS → ⋮ → **Niestandardowe repozytoria** → dodaj `https://github.com/crypturgus/ha-inpost-air-direct`, kategoria **Integracja**.
2. Zainstaluj **InPost Air Direct** i zrestartuj Home Assistant.
3. Ustawienia → Urządzenia oraz usługi → **Dodaj integrację** → **InPost Air Direct**.
4. Wybierz **Na mapie**, **Według miejscowości** lub **Według kodu Paczkomatu**, a potem wskaż Paczkomat. Kolejne Paczkomaty dodajesz tak samo.

Instalacja ręczna: skopiuj `custom_components/inpost_air_direct` do `/config/custom_components/` i zrestartuj Home Assistant.

## Encje

Identyfikatory poniżej dotyczą Paczkomatu `DZI11M`. Tworzone są tylko encje dla wartości, które Paczkomat faktycznie podaje.

| Encja | Przykładowe ID | Uwagi |
|---|---|---|
| Pogoda | `weather.inpost_air_dzi11m` | temperatura, wilgotność, ciśnienie; bez prognozy i stanu nieba |
| Temperatura | `sensor.inpost_air_dzi11m_temperature` | °C; atrybuty `latitude`, `longitude`, `address` |
| Wilgotność, ciśnienie | `..._humidity`, `..._atmospheric_pressure` | %, hPa |
| PM1, PM2.5, PM4, PM10, NO2, O3 | `..._pm2_5`, ... | μg/m³; atrybut `level` (np. `GOOD`) |
| Indeks jakości powietrza | `..._air_quality_index` | atrybuty `level`, `index`, `sensor_generation` |
| Procent normy WHO | `..._pm2_5_of_who_limit`, ... | |
| Koniec okna pomiaru | `..._measurement_window_end` | encja diagnostyczna; pozostaje dostępna przy nieaktualnych danych |

## Przykładowa konfiguracja

Integrację konfiguruje się w interfejsie. Przykłady kart i automatyzacji: [`examples/dashboard.yaml`](examples/dashboard.yaml), [`examples/automations.yaml`](examples/automations.yaml).

```yaml
type: history-graph
title: Temperatura
hours_to_show: 48
entities:
  - entity: sensor.inpost_air_dzi11m_temperature
```

## Warto wiedzieć

- Wartości to **średnie z ruchomego okna około 60–75 minut**, a nie odczyty chwilowe.
- Temperatury sąsiednich Paczkomatów mogą się różnić o kilka °C (miejsce montażu, słońce, ściana).
- Istnieją dwie generacje czujników (widać to w modelu urządzenia). Podają różne wartości: generacja 1 nie ma PM4, za to część z nich ma NO2 i O3. Mają też **różne skale indeksu jakości powietrza** i różne limity WHO, więc nie porównuj indeksu między Paczkomatami.
- To, że katalog InPost oznacza Paczkomat jako mający czujniki, nie gwarantuje, że one działają. Dlatego Paczkomaty są sprawdzane na żywo przed dodaniem.

## Komunikacja z API

| Cel | Endpoint | Kiedy |
|---|---|---|
| Pomiary | `GET api-pl-points.easypack24.net/v1/points/{kod}/air-sensors` | co interwał, jedno zapytanie na Paczkomat |
| Katalog Paczkomatów | `GET api-shipx-pl.easypack24.net/v1/points` (stronicowanie, ograniczone pola) | tylko przy dodawaniu Paczkomatu, najwyżej raz w tygodniu (pamięć podręczna w HA) |
| Położenie Paczkomatu | ten sam endpoint, `name={kod}` | raz, przy dodawaniu po kodzie |

Serwer nie pozwala filtrować po czujnikach powietrza, a jego filtr miejscowości wymaga dokładnej pisowni. Dlatego katalog Paczkomatów z czujnikami jest trzymany w pamięci podręcznej i przeszukiwany lokalnie. Zapytania o katalog są ponawiane z rosnącym odstępem i z uwzględnieniem nagłówka `Retry-After`. Błąd pobierania pomiarów oznacza tylko tyle, że encje są niedostępne do następnego udanego odczytu. Integracja nie scrapuje stron, nie emuluje przeglądarki i nie potrzebuje dodatkowych kontenerów.

## Współistnienie z innymi integracjami

Domena `inpost_air_direct` może działać równolegle z integracją `inpost_air` od CyberDeer. Historia encji nie jest przenoszona.

## Rozwój

```sh
python3.14 -m venv .venv && .venv/bin/pip install -r requirements_test.txt
.venv/bin/python -m pytest -q
```

Testy korzystają ze środowiska testowego Home Assistant i zapisanych odpowiedzi API. CI uruchamia `hassfest`, walidację HACS i testy (także raz w tygodniu). Wydanie nowej wersji: podbij `version` w `manifest.json`, dodaj sekcję w `CHANGELOG.md` i wypchnij tag `vX.Y.Z`. Workflow sam utworzy wydanie na GitHubie.
