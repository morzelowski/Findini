# AGENTS.md — Findini

## Cel i zakres

Budujemy Findini: dopracowaną aplikację na Androida do zgłaszania znalezionych przedmiotów i odnajdywania zgub. Projekt obejmuje działający backend, trwałą bazę, zdjęcia z aparatu, GPS, wyszukiwanie, prywatny kontakt i proces zwrotu. Szkielet, makieta, dokumentacja lub POC nie stanowią ukończonego produktu.

Zespół: Krzysztof Czaplicki, Aleksandra Łabęda, Mateusz Orzełowski.
Temat projektu: Aplikacja mobilna do zgłaszania znalezionych przedmiotów i odnajdywania zgub.
Nazwa/kryptonim: Findini.

Ten plik opisuje stałe zasady pracy w repozytorium. Szczegółowy brief zadania może być w `PROMPT_FINDINI.md` lub w bieżącym poleceniu użytkownika. Nie zakładaj, że funkcja została wykonana tylko dlatego, że opisano ją w dokumentacji.

## Swoboda i samodzielność

- Dobierz technologie i architekturę do celu. Jeśli repozytorium ma już sensowny stos, rozwijaj go. Nie zmieniaj technologii dla samej zmiany.
- Masz swobodę w projektowaniu wyglądu, nawigacji, modelu danych i algorytmów. Rozwiązuj problem użytkownika; brief nie jest katalogiem narzuconych komponentów UI.
- Proponuj i implementuj własne usprawnienia, jeśli pomagają odzyskać przedmiot, skracają proces lub zwiększają zaufanie. Utrzymaj spójny i wykonalny zakres.
- Zanim zaczniesz, przedstaw krótki kierunek i plan. Potem implementuj bez oczekiwania na akceptację zwykłych, odwracalnych decyzji.
- Przy niejasności przyjmij uzasadnione założenie i zapisz je. Pytaj o decyzje blokujące, sprzeczności lub działania wymagające zgody. Nie podejmuj nieautoryzowanych zakupów, publicznych wdrożeń lub operacji nieodwracalnych.
- Nie kończ na analizie. Doprowadź autoryzowaną pracę do działającej, sprawdzonej całości; zgłaszaj konkretne blokady zamiast udawać ukończenie.

## Nienegocjowalne zachowania produktu

1. Szukanie i przeglądanie zgłoszeń działa bez rejestracji. Techniczna sesja gościa dla operacji prywatnych może działać w tle.
2. Zgłoszenia „Zgubiono” i „Znaleziono” są zapisywane na serwerze. Wymagane funkcje nie mogą być zastąpione lokalną tablicą lub atrapą API.
3. Aparat, galeria i lokalizacja używają rzeczywistych możliwości Androida. Odmowa uprawnienia ma użyteczną alternatywę.
4. Lokalizacja zgłoszenia nie oznacza śledzenia przedmiotu. Nie obiecuj wykrywania laptopa, czapki lub kluczy przez GPS telefonu, tagi lub obce sieci bez prawdziwej integracji.
5. Szukanie po obszarze, czasie, kategorii i cechach musi pomagać przy wielu podobnych rzeczach. AI jest dodatkowym sygnałem, nie dowodem własności.
6. Dostarcz co najmniej jedną działającą funkcję AI/analizy obrazu pomagającą znaleźć przedmiot. Podstawowy produkt ma działać również bez dostępnego AI. Sam komunikat „AI wkrótce” nie realizuje wymagania.
7. Roszczenia, dowody, kontakt i potwierdzenie zwrotu tworzą pełny, spójny przepływ. Znalazca podejmuje decyzję o wydaniu przedmiotu.
8. Interfejs jest po polsku, nowoczesny i spójny. Nie pokazuj sukcesu, jeśli serwer nie potwierdził operacji.

## Architektura i jakość kodu

- Czytaj lokalne instrukcje przed zmianami. Zachowuj niezwiązaną pracę użytkownika. Szukaj przez `rg`, jeśli dostępny.
- Preferuj najprostszą architekturę spełniającą wymagania. Nie wprowadzaj mikroserwisów ani rozbudowanej infrastruktury bez realnej potrzeby.
- Rozdziel odpowiedzialności prezentacji, logiki domenowej i dostępu do danych. Dostosuj strukturę do wybranego stosu zamiast tworzyć puste warstwy.
- Wybierz i przypnij zgodne wersje zależności; sprawdzaj API w oficjalnej dokumentacji. Dodaj lockfile oraz konfigurację formatowania i statycznej analizy właściwą dla stosu.
- Kontrakty API, walidacja i reguły domenowe muszą być egzekwowane na serwerze. Klient nie stanowi granicy zaufania.
- Stosuj migracje i odtwarzalne dane demonstracyjne. Nie wykonuj destrukcyjnego resetu istniejących danych bez zgody.
- Używaj stabilnej paginacji i indeksów dla list, lokalizacji, filtrów i relacji. Ogranicz zakres dat, promienie, wielkość strony i rozmiar danych wejściowych.
- Strefy czasowe obsługuj jawnie: zapis dat w UTC, prezentacja w lokalnej strefie; pilotaż domyślnie w Polsce. Rozróżnij czas zdarzenia od czasu publikacji.
- Zdefiniuj maszynę stanów zgłoszeń i roszczeń. Zmiany w procesie zwrotu muszą być atomowe; obsłuż wyścigi i powtórzone żądania bez podwójnego wydania.
- Nie loguj tokenów, treści prywatnych wiadomości, dowodów, pełnych adresów ani zbędnych danych osobowych.

## Prywatność, bezpieczeństwo i zaufanie

### Tożsamość i dostęp

- Anonimowość publiczna nie oznacza braku autoryzacji. Sesja gościa ma losowe, bezpieczne dane uwierzytelniające, a zasoby prywatne mają kontrolę uprawnień.
- Nie traktuj UUID, identyfikatora urządzenia, lokalnego znacznika roli lub znajomości URL jako uwierzytelnienia.
- Tokeny przechowuj w bezpiecznym magazynie Androida; sekrety dostawców wyłącznie na serwerze. Do repozytorium trafia tylko przykład konfiguracji.
- Wyjaśnij ograniczenia utraty anonimowej sesji. Jeśli oferujesz kod odzyskiwania, zabezpiecz go jak sekret i nie przechowuj jawnie po stronie serwera. Nie obiecuj odzyskania danych bez faktycznego mechanizmu.
- Rozmowy i dowody są dostępne tylko uprawnionym uczestnikom. Każde pobranie, edycja i zmiana stanu sprawdza uprawnienia po stronie serwera, również dla plików.

### Dane publiczne i prywatne

- Publiczne reprezentacje API twórz z jawnej listy dozwolonych pól. Nie zwracaj całego obiektu bazy i nie polegaj na ukrywaniu pól w UI.
- Publiczna mapa, odległości i filtrowanie korzystają z lokalizacji zgrubnej. Nie ujawniaj ukrytego punktu przez odpowiedzi „w promieniu” lub dokładny dystans. Testuj ten scenariusz.
- Jeśli dokładna lokalizacja nie jest potrzebna, nie zbieraj jej. Nie śledź lokalizacji w tle. Miejsce przekazania strony ustalają prywatnie.
- Prywatne pytania, odpowiedzi, numery seryjne, dowody i wiadomości nie mogą trafiać do publicznych opisów, wyszukiwarki, indeksu obrazów ani logów.
- Zdjęcia publiczne mogą same ujawniać informacje. Pozwól je sprawdzić przed publikacją; poinformuj, żeby nie publikować czytelnych dokumentów, adresów i danych kontaktowych. Jeśli wdrażasz maskowanie, weryfikuj jego wynik, zamiast obiecywać automatyczną ochronę.
- Waliduj pliki, format, rozmiar i wymiary, usuń EXIF z udostępnianych wersji. Oryginałów z metadanymi nie wystawiaj publicznie. Ogranicz dostęp do dowodów i usuń osierocone pliki.
- Udokumentuj retencję, usuwanie własnych zgłoszeń i dowodów, przechowywanie kopii oraz ograniczenia anonimowości. Nie deklaruj gwarancji prawnych bez podstaw.

### Nadużycia i zwrot

- Egzekwuj limity roszczeń, wiadomości, tworzenia sesji i zgłoszeń oraz kosztownych operacji. Sam limit na identyfikatorze gościa łatwo obejść; zastosuj rozsądne dodatkowe ograniczenia bez nadmiernego śledzenia.
- Nie zwracaj poprawnej odpowiedzi na prywatne pytanie ani informacji umożliwiającej masowe zgadywanie.
- AI, podobieństwo obrazu, e-mail i udane podziękowanie nie są gwarancją tożsamości ani uczciwości.
- Zapewnij zgłoszenie nadużycia, blokowanie kontaktu i kontrolowaną ścieżkę moderacji. Ukrycie zgłoszenia blokuje również jego dalsze nieuprawnione użycie, nie tylko usuwa kartę z listy.
- Nie wprowadzaj przelewów „weryfikacyjnych”, obowiązkowych nagród ani podawania domowego adresu. Krótko wspieraj bezpieczne przekazanie w miejscu publicznym.
- Podziękowania/serduszka mogą wynikać z zakończonego zwrotu i powinny mieć zabezpieczenie przed wielokrotnym naliczaniem.

## AI i wyszukiwanie

- Wybór modelu i algorytmu należy do implementującego agenta. Oceniaj je na konkretnych przypadkach, w tym wielu podobnych egzemplarzach i braku dopasowania.
- Jeśli używasz embeddingów, zachowuj zgodność modelu, wersji, wymiaru i metryki między indeksowaniem a zapytaniem. Zaplanuj reindeksację przy zmianie modelu.
- Wektory podobieństwa lub wynik rankingu nie są skalibrowanym prawdopodobieństwem. Nie pokazuj „pewności właściciela” wyliczonej z odległości wektorów.
- Przy łączeniu miejsca, czasu, cech i obrazu opisz zastosowane sygnały i ich ograniczenia. Nie ukrywaj poważnej niezgodności cech pod wysokim wynikiem AI.
- Przetwarzanie obrazów nie powinno blokować głównego żądania bez limitu czasu. Pokaż stan indeksowania, obsłuż błąd, retry i brak modelu. Nie dopasowuj usuniętych lub ukrytych zgłoszeń z pozostawionego indeksu.
- Dane użytkowników przesyłaj do zewnętrznego modelu tylko w uzasadnionym zakresie i z czytelną informacją. Nie wysyłaj prywatnych dowodów ani sekretów.
- Jeśli używasz LLM, traktuj jego odpowiedzi jako niezaufane: waliduj strukturę, ogranicz narzędzia, czas i koszt. Opisy ogłoszeń nie mogą sterować agentem, wywoływać dowolnych URL ani zmieniać uprawnień.
- Sugestie filtrów i opisów są edytowalne. Publikacja, udostępnienie danych i rozstrzygnięcie roszczenia wymagają świadomej czynności człowieka.
- Bez wymyślonych wyników eksperymentu. Rozdziel dane zapytań i indeksowane; opisuj licencje i źródło materiałów testowych. Duplikat zdjęcia to test techniczny, nie dowód rozpoznawania egzemplarzy.

## Standard doświadczenia użytkownika

- Zaproponuj własny kierunek wizualny. Spójny system typografii, kolorów, odstępów, ikon i komponentów ma być widoczny w całej aplikacji.
- Priorytetem jest szybkie przejście „szukam” / „znalazłem”. Nie wymuszaj tutorialu ani rejestracji przed sprawdzeniem wyników.
- Dostępność: czytelne kontrasty, większy tekst, TalkBack, etykiety ikon i pól, wygodne cele dotykowe, komunikacja niezależna od samego koloru.
- Obsługuj pusty stan, loading, odmowę uprawnień, timeout, brak internetu, niedostępność map/AI i błąd zapisu. Formularz nie powinien tracić pracy przy typowym błędzie.
- Publiczne i prywatne informacje muszą być zrozumiale oznaczone przed publikacją. Nie ukrywaj istotnego kosztu, utraty dostępu lub ujawnienia danych.
- Animacje mają wspierać orientację. Żadnych dekoracji utrudniających czytanie mapy, zdjęć i najważniejszych przycisków.
- Pokazuj prawdziwe odległości zgrubne i rzeczywiste stany. Nie stosuj fikcyjnych liczników, fałszywej aktywności lub atrap rozmów poza oznaczonym demo.

## Weryfikacja

Dobierz narzędzia do stosu. Testy mają sprawdzać ryzykowne zachowania, a nie powtarzać implementację.

Minimalny zakres:

- Jednostkowo: reguły statusów, walidacja, sygnały rankingu i brak wiarygodnego dopasowania.
- Integracyjnie z prawdziwą bazą testową: publikacja, migracje, geowyszukiwanie, paginacja, uprawnienia do zgłoszeń, rozmów i plików, brak prywatnych pól w publicznym API, limity oraz konflikt dwóch finalizacji.
- Prywatność lokalizacji: publiczne zapytania i dystanse nie korzystają z ukrytej dokładnej pozycji; wielokrotne zapytania nie pozwalają jej odzyskać.
- Przepływ na dwóch sesjach: zdjęcie i miejsce → wyszukanie → prywatny dowód → decyzja znalazcy → rozmowa → zwrot. Nie wolno czytać cudzych spraw ani zmieniać cudzych statusów.
- Android: kompilacja oraz, gdy środowisko pozwala, sprawdzenie aparatu, GPS, galerii, odmowy uprawnień i połączenia z API na emulatorze lub telefonie. Sam podgląd webowy nie potwierdza działania Androida.
- Awaria: backend offline, nieudany upload, niedostępny model, ponowienie zapisu, restart usług i utrata sesji. Dane i zdjęcia mają przetrwać restart.
- Eksperyment AI na opisanym zestawie podobnych rzeczy i negatywnych przykładów. Zapisz rzeczywiste wyniki i wnioski.
- Prosty test obciążenia dopasowany do założenia pilota: 10 tys. zgłoszeń i około 50 równoległych sesji. Podaj sprzęt, profil żądań, p95, błędy i ograniczenia pomiaru. Nie utożsamiaj tych liczb ze sprawdzoną produkcyjną skalą.

Uruchom formatowanie, analizę statyczną, testy i build odpowiednie do zmian. Po usunięciu błędów sprawdź dotknięty przepływ. Nie twierdź, że test przeszedł, jeśli go nie uruchomiono. Brak sprzętu lub narzędzia opisz konkretnie, wraz z procedurą ręcznej weryfikacji.

## Uruchamianie i dokumentacja

- Zapewnij odtwarzalne uruchomienie backendu i zależności, najlepiej jednym poleceniem. Przechowuj dane i zdjęcia w trwałych wolumenach lub równoważnym magazynie.
- README po polsku ma zawierać wymagania, wersje, konfigurację bez sekretów, migracje, seed, testy, uruchomienie Androida i build APK.
- Wyjaśnij adres serwera dla emulatora i fizycznego telefonu, konfigurację lokalnego HTTP oraz HTTPS poza środowiskiem deweloperskim.
- Opisz zależności od map, geokodowania i AI: konta/klucze, pobranie modeli, koszt, licencje, atrybucje, ograniczenia i zachowanie po awarii. Nie zakładaj dostępności płatnej usługi.
- Dodaj opis architektury i najważniejszych decyzji, kontrakt API, schemat danych, zwięzły model zagrożeń, retencję, backup/restore i sposób moderacji.
- Przygotuj scenariusz demonstracji około 5 minut oraz materiał do posteru/prezentacji: problem, rozwiązanie, architektura, wyniki i ograniczenia. Dokumentacja ma opisywać to, co rzeczywiście zaimplementowano.
- Dane demonstracyjne muszą być oznaczone, bez prawdziwych danych osobowych. Usługi deweloperskie nie mogą bez uwierzytelnienia udawać usług produkcyjnych.

## Definicja ukończenia i raport końcowy

Gotowość oznacza możliwość przejścia pełnego odzyskania przedmiotu w aplikacji Android, przez prawdziwe API i bazę, między odrębnymi uprawnionymi sesjami. Zdjęcia i dane są trwałe, prywatne dane pozostają prywatne, wymagane funkcje nie mają atrap, a instrukcja pozwala odtworzyć uruchomienie.

W raporcie końcowym podaj:

1. Co zaimplementowano i jakie własne decyzje poprawiają produkt.
2. Jak uruchomić backend i Androida oraz gdzie jest APK, jeśli rzeczywiście powstał.
3. Jakie kontrole wykonano i z jakim wynikiem.
4. Jakie są konkretne blokady, ograniczenia i elementy wymagające ręcznej weryfikacji.

Nie nazywaj projektu produkcyjnie gotowym wyłącznie dlatego, że kompiluje się lub wygląda dobrze. Oceniaj go po działaniu całego scenariusza i dowodach z weryfikacji.
