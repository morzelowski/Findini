# Lokalna analiza zdjęć

Domyślny wariant: **CLIP ViT-B/16, ONNX Runtime, CPU**. Pobranie: `python3 backend/scripts/download_model.py`.

- [Źródło B/16](https://huggingface.co/Xenova/clip-vit-base-patch16), rewizja `342fdf2f67aded64d138ff074745fb4a5d2bba5f`, licencja MIT.
- Pliki: model obrazu fp32 ~345 MB, model tekstu int8 ~65 MB, tokenizer i konfiguracja. Wagi są sprawdzane SHA-256, wszystkie pliki rozmiarem i przypiętą rewizją. Katalog: `models/clip-vit-b16`.
- [Źródło B/32](https://huggingface.co/Xenova/clip-vit-base-patch32), rewizja `6b7c523703ae26e39be4b03774966f8571c7f523`, licencja MIT. Lżejsza alternatywa: `python3 backend/scripts/download_model.py --model b32`; ustaw `FINDINI_AI_MODEL_DIR=/models/clip-vit-b32` w `.env`. Opcja `--model b32 --with-quantized` pobiera też obraz int8 do dawnego eksperymentu.
- Montowanie tylko do odczytu: `./models:/models:ro`. Model nie wymaga GPU ani konta usługi. Zdjęcia i prywatne dowody nie są wysyłane do zewnętrznego dostawcy; dowody nie są analizowane.
- Zmiana rodziny/rewizji modelu powoduje ponowne indeksowanie zdjęć. Wersja modelu jest częścią `embedding_model`; zapytania nie porównują wektorów różnych modeli. Podczas reindeksacji lista i filtry działają, wyniki zdjęciem uzupełniają się w tle.
- Porównanie na tych samych danych: `cd backend && .venv/bin/python -m scripts.compare_models`. Wynik: `docs/porownanie_modeli_cpu.json`.
