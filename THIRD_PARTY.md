# Компоненты и происхождение

Исходный код LocalDub предоставляется под GPL-3.0-or-later (LICENSE). Встроенные компоненты сохраняют свои лицензии. Сборка распространяется как экспериментальный MVP с открытым исходным кодом.

| Компонент | Закреплённый вариант | Лицензия / исходники |
|---|---|---|
| libmpv | shinchiro 20261016, обычный x86_64, mpv a2cd83c56 | GPL; [mpv](https://github.com/mpv-player/mpv), [рецепты Windows-сборки](https://github.com/shinchiro/mpv-winbuild-cmake/releases/tag/20261016). x86_64-v3 не используется. |
| FFmpeg/ffprobe | Gyan 9.0.2 essentials | GPLv3 в выбранной сборке; [релиз и исходный commit](https://github.com/GyanD/codexffmpeg/releases/tag/9.0.2), [FFmpeg](https://ffmpeg.org/) |
| Piper | rhasspy Windows 2023.11.14-2 | MIT для старого Piper; [исходники и релиз](https://github.com/rhasspy/piper/releases/tag/2023.11.14-2). Архивный проект выбран из-за проверенного Windows CLI; это не текущий Piper 1.x. |
| espeak-ng / piper-phonemize | внутри старого Piper ZIP | espeak-ng GPLv3; [исходники](https://github.com/espeak-ng/espeak-ng), [piper-phonemize](https://github.com/rhasspy/piper-phonemize). |
| ONNX Runtime | внутри Piper + Python 1.23.2 | MIT; [исходники](https://github.com/microsoft/onnxruntime). |
| CTranslate2 | 4.6.0 CPU, AVX/GENERIC | MIT; [исходники](https://github.com/OpenNMT/CTranslate2/tree/v4.6.0), [CPU dispatch](https://github.com/OpenNMT/CTranslate2/blob/v4.6.0/src/cpu/cpu_isa.cc). |
| Marian en→ru | ordois conversion 9ae164a637a7e380d3e09768899c886af9925afe | Apache-2.0 по карточкам [оригинала Helsinki-NLP](https://huggingface.co/Helsinki-NLP/opus-mt-en-ru) и [конверсии](https://huggingface.co/ordois/opus-mt-en-ru-ctranslate2-int8). Проверены реальные переводы; архивный manifest модели содержит SHA-256 файлов. |
| Whisper tiny | Systran d90ca5fe260221311c53c58e660288d3deb8d356 | MIT; [модель](https://huggingface.co/Systran/faster-whisper-tiny), [whisper](https://github.com/openai/whisper), faster-whisper 1.2.1 MIT. |
| Denis medium | piper-voices c10ece1aade47bb51c153c893d14e5bf8e5b7117 | [MODEL_CARD](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/ru/ru_RU/denis/medium/MODEL_CARD): CC0 для датасета; репозиторий моделей MIT. Карточка включена рядом с моделью. |
| CPython/Tcl/Tk | Python 3.12.14 | PSF и Tcl/Tk license. |
| sentencepiece | 0.2.1 | Apache-2.0. |
| NumPy / PyAV / psutil | см. lock | BSD / BSD / BSD. PyAV включает свои FFmpeg-библиотеки; лицензии сохранены в Python-пакетах. |
| PyInstaller | 6.16.0 | GPL с исключением для создаваемых приложений. |

Все URL загрузки и фактические SHA-256 — в `component-manifest.json`; полные Python-версии — в `requirements-lock.txt`. В `licenses` сохранены основные лицензионные тексты и notices. Публичная перепубликация бинарников требует отдельно обеспечить соответствующие исходники и уведомления всех включённых библиотек; ссылки здесь документируют происхождение, а не заменяют полный комплект corresponding source.

Голос Irina рассматривался и исключён: его карточка указывает неизвестную лицензию датасета. Ruslan не выбран из-за CC-BY-NC-SA датасета. Denis выбран с явно указанной CC0. Клонирование голосов не используется.
