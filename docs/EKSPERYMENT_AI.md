# Eksperyment: wyszukiwanie zdjęciem wśród wielu podobnych przedmiotów

Surowe wyniki: [`eksperyment_ai_wyniki.json`](eksperyment_ai_wyniki.json). Skrypt: `backend/scripts/ai_experiment.py` (powtarzalny, ziarno losowania 20261107).

## Pytanie
Czy lokalny model obrazu pomaga znaleźć **konkretny egzemplarz** wśród wielu podobnych rzeczy (czapki, plecaki, portfele…) i czy umie powiedzieć „brak przekonującego dopasowania”? Oraz: jak trafne są podpowiedzi kategorii i koloru?

## Dane
- **Amazon Berkeley Objects (ABO)**, licencja CC BY 4.0, zdjęcia „small” (≤256 px). 14 typów odpowiadających kategoriom Findini (czapki, plecaki, torebki, walizki, portfele, etui telefonów, słuchawki, ładowarki, pierścionki, naszyjniki/bransoletki, zegarki, okulary, parasole, kubki/butelki) + 4 typy rozpraszające (krzesła, lampy, dywany, poduszki).
- **Indeks** („zdjęcia znalazców”): zdjęcie główne 411 produktów + 100 rozpraszaczy = 511 zdjęć.
- **Zapytania** („zdjęcie właściciela”): **inne ujęcie** tego samego produktu (`other_image`) — 411 zapytań. To nie jest test „ta sama kopia zdjęcia”.
- **Negatywy**: 122 produkty, których **nie ma** w indeksie — oczekujemy „brak przekonującego dopasowania”.
- Deduplikacja: ABO zawiera warianty produktu z identycznym zdjęciem — pominięto produkty ze wspólnym zdjęciem.

## Model i sprzęt
CLIP ViT‑B/32 (MIT), eksport ONNX `Xenova/clip-vit-base-patch32@6b7c523`, dwa warianty: fp32 (352 MB) i int8 (89 MB). ONNX Runtime 1.31.1 na CPU (Apple M5, 2 wątki). Podpowiedzi zero‑shot: angielskie prompty dla rodzajów (np. „a photo of a backpack”) i kolorów (średnia z 4 szablonów).

## Wyniki — wyszukiwanie egzemplarza
| Metryka | fp32 | int8 | losowo |
|---|---|---|---|
| Recall@1 | **0,353** | 0,309 | 0,002 |
| Recall@5 | **0,538** | 0,470 | 0,010 |
| Recall@10 | **0,662** | 0,574 | 0,020 |
| MRR | 0,443 | 0,389 | — |
| Mediana pozycji właściwego produktu | 5 | 6 | ~256 |
| Recall@10 z filtrem kategorii (sygnał od użytkownika) | **0,710** | 0,664 | — |
| Czas inferencji / zdjęcie (CPU) | 20–31 ms | 22–26 ms | — |

Recall@1 według typu (fp32): etui telefonów 0,87 · czapki 0,47 · plecaki 0,43 · torebki 0,40 · słuchawki 0,37 · okulary 0,37 · kubki 0,37 · ładowarki 0,33 · parasole 0,33 · portfele 0,30 · walizki 0,27 · zegarki 0,19 · pierścionki 0,17 · naszyjniki 0,03. Biżuteria (małe, błyszczące, podobne obiekty) wypada najsłabiej.

**Wniosek 1.** Zdjęcie jest **użytecznym sygnałem rankingu** (właściwa rzecz zwykle w pierwszej piątce–dziesiątce, 33× lepiej niż losowo), ale **nie identyfikuje egzemplarza** — w 2/3 przypadków na pierwszym miejscu jest inna, podobna rzecz.

## Wyniki — czy umiemy powiedzieć „brak dopasowania”?
Podobieństwo kosinusowe (fp32): mediana dla pary „to samo, inne ujęcie” **0,81**, a dla najbardziej podobnej *innej* rzeczy tego samego typu **0,83**. Właściwa rzecz jest bardziej podobna niż najtrudniejszy negatyw tylko w 39% przypadków. Dla negatywów (produktu nie ma w bazie) mediana najlepszego wyniku to **0,84**.

Bezwzględne progi zawodzą: przy progu 0,80 jako „przekonujące” oznaczylibyśmy 68% zapytań, dla których właściwej rzeczy w ogóle nie ma.

**Kryterium względne** — „najlepszy wynik wyraźnie wyprzedza drugi” (przewaga top‑1 nad top‑2):

| próg przewagi | trafne top‑1 oznaczone | błędne top‑1 oznaczone | negatywy oznaczone | precyzja |
|---|---|---|---|---|
| 0,03 | 0,48 | 0,17 | 0,16 | 0,52 |
| 0,04 | 0,32 | 0,08 | 0,12 | 0,57 |
| **0,05** (wybrane) | 0,27 | 0,04 | 0,04 | **0,72** |
| 0,06 | 0,24 | 0,02 | 0,01 | 0,88 |

**Wniosek 2.** Findini mówi „wyróżnia się podobieństwem” tylko przy przewadze ≥ 0,05 (≈ 7 na 10 takich wskazań jest trafnych w tym zbiorze), a w pozostałych przypadkach komunikuje: *„Żadne zdjęcie nie wyróżnia się wyraźnie — porównaj cechy, miejsce i czas”*. Nawet „wyróżniające się” zdjęcie jest pokazywane obok ostrzeżeń o niezgodnych cechach (np. inny kolor) i nie wpływa na decyzję o wydaniu. W dopasowaniach zguba↔znalezisko samo podobieństwo zdjęcia daje +1 pkt, a „wyróżnienie” +2,5 pkt i liczy się jako cecha wyróżniająca.

Ciekawostka z aplikacji: zdjęcie białej czapki Starter „wyróżniło” granatową czapkę tego samego modelu — dlatego obok wyniku pokazujemy *„Inny kolor niż na Twoim zdjęciu — ocena modelu”*.

## Wyniki — podpowiedzi kategorii i koloru (533 zdjęcia zapytań)
| | fp32 | int8 |
|---|---|---|
| Trafna kategoria Findini (top‑1) | **0,81** | 0,75 |
| Trafny rodzaj (np. „plecak”) | 0,61 | 0,56 |
| Odsetek oznaczonych jako „wyraźna” | 0,69 | 0,63 |
| Trafność kategorii, gdy „wyraźna” | **0,90** | 0,86 |
| Kolor top‑1 zgodny z etykietą (208 zdjęć z angielską etykietą koloru) | **0,54** | 0,45 |

Uśrednianie 4 szablonów promptu poprawiło trafność koloru z 0,44 do 0,54 (sprawdzone w trakcie strojenia na tym samym zbiorze — możliwa niewielka nadmierna optymizacja). Kategoria jest więc podpowiadana z etykietą „wyraźna/niepewna”, a kolor tylko jako sugestia — wszystko wymaga zatwierdzenia przez użytkownika.

## Decyzje wynikające z eksperymentu
- Domyślnie **fp32** (lepszy recall i podpowiedzi; int8 tylko przy braku pamięci).
- Brak „procentu pewności” w interfejsie; poziomy opisowe + sygnały + ostrzeżenia.
- Zdjęcie nigdy nie jest jedynym kryterium — liczą się kategoria, cechy, miejsce i czas, a o wydaniu decyduje znalazca na podstawie ukrytego szczegółu.

## Ograniczenia (ważne)
- **Zdjęcia katalogowe** (białe tło, studyjne światło) — zdjęcia rzeczy znalezionych na ulicy, w złym świetle i z tłem będą trudniejsze; wyniki to raczej górne oszacowanie.
- Szum etykiet ABO: część „słuchawek” to szpule filamentu, „kubki” to kieliszki (wykryte przy przeglądzie zdjęć) — nie poprawialiśmy etykiet.
- Zbiór 411 produktów — przedziały ufności szerokie (np. Recall@1 0,35 ± ok. 0,05).
- Progi (0,05, 0,80, 0,86) dobrane na tym samym zbiorze — potrzebna walidacja na zdjęciach zebranych w pilotażu (z zachowaniem prywatności).
- Brak testu z prawdziwymi zdjęciami „zguba vs znalezisko” tego samego przedmiotu zrobionymi przez różne osoby — rekomendowany kolejny krok (np. 30 własnych przedmiotów zespołu, po 2 zdjęcia w różnych warunkach).

## Porównanie z B/16 — 10.11.2026

Wariant domyślny zmieniono na B/16 po rzeczywistym porównaniu na tym samym podziale danych. [Wyniki i ograniczenia](ZMIANY_2026_11_10.md), [surowy wynik](porownanie_modeli_cpu.json). Powyższy eksperyment B/32 pozostaje historycznym punktem odniesienia.
