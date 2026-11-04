# Приём миров 1.7-t1 — сводка (dry-run, 04.11.2026 16:46)

| Модель | Итог | Точка было → стало | Δ | Медиана было → стало | Δ | Печать | Гейты: новые / ушли | CI | Флаги |
|---|---|---|---:|---|---:|---|---|---|---|
| svcb | ok | 15,10 → 14,98 | −0,11 | 14,35 → 14,24 | −0,11 | 14,4 → 14,2 | — / — | — | 4 |
| t | ok | 325,74 → 324,47 | −1,27 | 311,00 → 309,43 | −1,57 | 310 → 310 | — / — | — | 3 |
| sber | ok | 355,40 → 355,45 | +0,06 | 323,85 → 323,90 | +0,05 | 325 → 325 | — / — | — | 2 |
| lenta | ok | 3323,46 → 3329,33 | +5,86 | 3173,11 → 3179,36 | +6,25 | 3150 → 3200 | — / — | — | — |
| x5 | ok | 3467,10 → 3474,49 | +7,39 | 3363,50 → 3370,60 | +7,10 | 3350 → 3350 | — / — | — | — |
| magnit | ok | 1507,45 → 1513,96 | +6,52 | 1328,36 → 1335,26 | +6,90 | 1350 → 1350 | — / — | — | — |

## Красные флаги

**svcb**
- class-checks: класс 3 (продление явных лет на год не меняет оценку в пределах допуска): проверка horizon СРАБОТАЛА — находок 1: низ (слой «рыночные ставки как есть»): 6,87 → 6,81 ₽ (−0,06 ₽, −0,87 %) при продлении явных лет на 1 г.; допуск ±0,05 ₽
- gate-texts: гейт m_crisis_vs_cbr: состав не тот, на котором писались слова шаблона ({'longer': (['mid', 'strict'], ['strict'])}) — текст собран правилом, просмотреть ведущему
- gate-texts: гейт nim_path_joint: состав не тот, на котором писались слова шаблона ({'cells': (['N/downturn/schedule', 'N/norm/mid', 'N/norm/schedule', 'N/norm/strict', 'N/soft/mid', 'N/soft/schedule', 'N/soft/strict'], ['N/downturn/schedule', 'N/norm/mid', 'N/norm/schedule', 'N/norm/strict', 'N/soft/mid', 'N/soft/strict'])}) — текст собран правилом, просмотреть ведущему
- gate-texts: гейт pb_by_world: состав не тот, на котором писались слова шаблона ({'regimes': (['crisis'], ['downturn', 'crisis']), 'count': (3, 5)}) — текст собран правилом, просмотреть ведущему

**t**
- spreads: у 10 изменённых ключей в комментарии шаблона есть числа — сверить текст: nii.books.sme_loans.spread.2026, nii.books.securities.spread.2026, nii.books.auto.spread.2029, nii.books.auto.spread.2030, nii.books.mortgage.spread.2028, nii.books.mortgage.spread.2029 …
- derived: у 28 изменённых ключей в комментарии шаблона есть числа — сверить текст: nii.phi_split, regimes.near_nim_shift.2027Q3, regimes.near_nim_shift.2027, regimes.near_nim_shift.2028Q1, regimes.near_nim_shift.2028Q2, regimes.near_nim_shift.2028Q3 …
- tables: подпись справочного варианта window_level_in_modal_cell (маржа и C/I модальной клетки варианта) — числа прежней книги: правило без прогона сетки варианта не считается; сверить и при правке — таблицы заново

**sber**
- spreads: у 10 изменённых ключей в комментарии шаблона есть числа — сверить текст: nii.books.mortgage.spread.2028, nii.books.mortgage.spread.2029, nii.books.mortgage.spread.2030, nii.books.securities.spread.2028, nii.books.securities.spread.2029, nii.books.securities.spread.2030 …
- changes: тексты объяснений гейтов (gate_explanations.yaml), проза текста книги и решений (DECISIONS) — числа прежней книги; массы гейтов и числа меток — правилом; сверить с таблицами

