# Model AI (nie jest w repozytorium)

Pobierz: `python3 backend/scripts/download_model.py` (dodatkowo `--with-quantized` dla wariantu int8 używanego w eksperymencie).

- Źródło: https://huggingface.co/Xenova/clip-vit-base-patch32 (eksport ONNX modelu `openai/clip-vit-base-patch32`), licencja MIT.
- Rewizja przypięta w skrypcie (`6b7c523703ae26e39be4b03774966f8571c7f523`), pliki weryfikowane SHA‑256.
- Pliki: `onnx/vision_model.onnx` (352 MB, fp32 — domyślny), `onnx/text_model_quantized.onnx` (65 MB — opisy kategorii/kolorów), `tokenizer.json`, `preprocessor_config.json`.
- Katalog jest montowany do kontenera API tylko do odczytu (`./models:/models:ro`). Zmiana pliku modelu ⇒ nowa wersja w `embedding_model` ⇒ automatyczne ponowne indeksowanie zdjęć.
