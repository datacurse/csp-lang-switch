# CSP Translation Glossary (English → Russian)

> Built 2026-05-19 from word frequencies in `english_742DEA58_strings.csv`
> (9,368 strings, 63,111 word tokens, 3,440 distinct forms).
> Full frequency table: [`word_frequency.csv`](word_frequency.csv).

This is the **canonical term list**. When a word below appears in a string,
translate it with the **Canonical** form unless a Note says it is
context-dependent. Consistency matters more than elegance — the same English
term must always map to the same Russian term across all 32 resource files.

CSP has no official Russian localization, so canonical forms follow the
de-facto Russian conventions of Photoshop / Krita where one exists.

## How to read this

* **Count** = occurrences of that word form in the source column (plurals
  counted separately; combined lemma totals noted where large).
* ⚠️ = **ambiguous** — the English word has two distinct meanings in CSP;
  pick by context, never blindly.
* 🔒 = **brand / do not translate.**

---

## 1. Core objects (nouns)

| English | Count | Canonical Russian | Notes |
|---|--:|---|---|
| layer / layers | 696 / 129 | слой / слои | The single most important term. Never «пласт». |
| settings | 660 | настройки | Not «параметры», not «опции». |
| color | 567 | цвет | |
| file / files | 538 / 157 | файл / файлы | |
| page / pages | 312 / 174 | страница / страницы | |
| folder | 305 | папка | |
| canvas | 280 | холст | |
| size | 275 | размер | |
| tool | 249 | инструмент | |
| mode | 239 | режим | |
| image | 239 | изображение | |
| palette | 185 | палитра | UI panel. |
| material | 182 | материал | |
| line / lines | 180 / 124 | линия / линии | |
| data | 176 | данные | |
| brush | 175 | кисть | |
| camera | 148 | камера | |
| library | 148 | библиотека | |
| selection | 140 | выделение | The selected region, not the act of choosing. |
| object | 140 | объект | |
| area | 138 | область | |
| number | 124 | ⚠️ число / номер | «число» = quantity; «номер» = ordinal/ID. |
| frame | 121 | ⚠️ кадр / рамка | «кадр» = animation frame; «рамка» = comic/panel frame. |
| width | 118 | ширина | |
| pose | 108 | поза | |
| border | 105 | ⚠️ граница / рамка | «граница» = edge/outline; «рамка» = frame box. |
| format | 102 | формат | |
| ruler | 101 | линейка | |
| value | 101 | значение | |
| information | 100 | сведения | «информация» also acceptable; keep one. |
| group | 98 | группа | |
| list | 97 | список | |
| gradient | 97 | градиент | |
| position | 91 | положение | |
| version | 91 | версия | |
| cover | 89 | обложка | Book/comic cover. |
| mask | 89 | маска | |
| shape | 88 | фигура | |
| vector | 84 | вектор / векторный | adj. «векторный слой» = vector layer. |
| action | 82 | операция | CSP "Auto Action" → «Автооперация». |
| preset | 82 | набор настроек | Or «предустановка». Avoid bare «пресет». |
| animation | 82 | анимация | |
| tone | 79 | тон | Manga screentone → «скринтон». |
| device | 78 | устройство | |
| name | 227 | ⚠️ имя / название | «имя» for layers/files; «название» for titles. |
| work | 180 | произведение | CSP's word for the artwork/document. |
| software | 136 | программа | «программное обеспечение» only in legal text. |
| drawing | 131 | рисунок | |
| license | 126 | лицензия | |
| light | 125 | ⚠️ свет / источник света | 3D context: «источник света». |
| app | 115 | приложение | |

## 2. Actions (verbs / button & menu labels)

| English | Count | Canonical Russian | Notes |
|---|--:|---|---|
| change | 545 | изменить | |
| set | 357 | задать | «установить» when about installing. |
| use / using | 344 / 88 | использовать / использование | |
| show | 267 | показать | imperfective «показывать» for toggles. |
| select | 240 | ⚠️ выбрать / выделить | «выбрать» = choose; «выделить» = make a selection. |
| save | 223 | сохранить | |
| export | 211 | экспортировать | noun «экспорт». |
| open | 178 | открыть | |
| delete | 171 | удалить | |
| switch | 168 | переключить | |
| add | 165 | добавить | |
| create | 158 | создать | |
| adjust | 154 | настроить | «коррекция» for color-correction features. |
| import | 130 | импортировать | noun «импорт». |
| reset | 114 | сбросить | noun «сброс». |
| enter | 112 | ⚠️ ввести / войти | «ввести» a value; «войти» = log in. |
| apply | 107 | применить | |
| edit | 105 | ⚠️ редактировать / Правка | Menu name "Edit" → «Правка»; the verb → «редактировать». |
| specify | 96 | указать | |
| copy | 88 | копировать | noun «копия». |
| check | 99 | ⚠️ проверить / отметить | «проверить» = verify; «отметить» = tick a checkbox. |
| display | 99 | отображать | noun «дисплей» only for the physical screen. |
| view | 78 | ⚠️ вид / просмотр | Menu "View" → «Вид»; "preview" sense → «просмотр». |
| try | 111 | попробовать | "Try again" → «Повторить попытку». |
| paint | 143 | 🔒 / закрасить | In "Clip Studio Paint" do NOT translate; verb → «закрасить». |

## 3. Modifiers & common adjectives

| English | Count | Canonical Russian | Notes |
|---|--:|---|---|
| new | 226 | новый | |
| selected | 142 | выбранный / выделенный | Match whichever sense of `select` applies. |
| failed | 111 | не удалось | "X failed" → «Не удалось выполнить X». |
| following | 107 | следующий | |
| current | 91 | текущий | |
| default | 85 | по умолчанию | |
| same | 80 | тот же | |
| blending | 80 | наложение | "Blending mode" → «Режим наложения» (NOT «смешивание»). |
| copyright | 79 | авторское право | |

## 4. Brand / proper nouns — 🔒 do not translate

| English | Count | Rule |
|---|--:|---|
| Clip / Studio / Paint | 328 / 316 / 143 | "Clip Studio Paint", "CLIP STUDIO" — keep verbatim. The high counts are mostly the product name, not vocabulary. |

## 5. Words to drop or handle grammatically

These rank high but need **no glossary entry** — they are grammar, not terms:

* `please` (356) — Russian UI omits politeness fillers; drop it. Translate
  "Please select a file" → «Выберите файл», not «Пожалуйста, выберите…».
* `the / to / of / and / a / in / for / is / be / or / with / not / on / will`
  etc. — articles, prepositions, auxiliaries; translated by sentence structure.
* `want` (197) — appears in "Do you want to…?" → render the whole idiom as
  «Вы действительно хотите…?» / «Хотите…?».
* `again` (125) — «снова» / «ещё раз»; in "Try again" use «Повторить попытку».
* `d` (627), `s` (367), `x` (103) — tokenizer noise from "3D", possessives,
  and "×"/dimensions. Ignore.

---

## Open decisions for the user

A few canonical choices above are judgement calls — confirm or override:

1. **`work` → «произведение»** vs «работа» vs «документ». CSP uses "work" for
   the open artwork; «произведение» is literal, «документ» is the most
   software-conventional.
2. **`preset` → «набор настроек»** vs «предустановка» vs «пресет».
3. **`information` → «сведения»** vs «информация».
4. **`tone` → «тон»** — but manga screentones may read better as «скринтон».

Resolve these once and the glossary is locked.
