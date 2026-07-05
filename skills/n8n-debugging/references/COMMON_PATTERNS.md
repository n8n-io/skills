# COMMON_PATTERNS.md — переиспользуемые паттерны и диагностические процедуры

Источники: собственные workflow (Router TEST, sadovodushka, MAX assistant),
живые проверки MCP-инструментов гейтвея (июль 2026). Не добавлять паттерн
без реального использования.

## Структура execution runData (проверено на живых исполнениях)

```
runData
└── <NodeName>              # dict: имя ноды → список запусков
    └── [run]               # список; последний запуск = runs[-1]
        ├── executionStatus # "success" | "error"
        ├── executionTime   # ms
        ├── source          # [{previousNode: "..."}] — откуда пришли данные
        ├── error           # {message, ...} — только при ошибке
        └── data.main       # список выходных веток (IF/Switch дают >1)
            └── [branch]    # список item
                └── [item]  # {json: {...}, pairedItem: {...}}
```

Путь до payload первого item первой ветки: `0.data.main.0.0.json`
(синтаксис json_path инструмента n8n_get_execution; точки в ключах
экранируются как `\.`, обратный слэш как `\\`).

## Диагностическая процедура: разбор audit/execution JSON

1. Сначала структура, не содержимое: список нод, статусы, где error.
2. Найти ноду, где форма данных расходится с ожидаемой (пропал ключ,
   пустая ветка, items=0).
3. Только потом читать значения — точечно, по пути до конкретного поля.

Через MCP-гейтвей это шаги 1-4 протокола из SKILL.md
(summary → targeted read → diff → grep). При работе с файлом JSON без
гейтвея — та же логика через jq: сначала `keys`, потом точечные пути.

## Восстановление контекста после Redis/Postgres нод

Ссылка на исходную ноду вместо протаскивания через цепочку:

```javascript
// один item в потоке
const ctx = $('Normalize Gate Input').first().json;

// несколько item — сохранять соответствие
const ctx = $('Extract Message').item.json;
```

## Postgres: чтение с приведением типа (queryReplacement)

Реальный рабочий паттерн (resolve user по chat_id, тип колонки bigint):

```
Query:
  SELECT COALESCE((SELECT id FROM users WHERE chat_id = $1::bigint LIMIT 1), NULL) AS user_id;
Options → Query Replacement:
  ={{ [$json.chat_id] }}
continueOnFail: true
```

После ноды — merge-паттерн: приоритет уже известного значения, fallback
на результат запроса, обёрнутый в try/catch:

```javascript
const normalInput = $('Normalize Gate Input').first().json;
let resolvedUserId = normalInput.user_id || null;
if (!resolvedUserId) {
  try {
    const pgItems = $input.all();
    if (pgItems && pgItems.length > 0) {
      const pgUserId = pgItems[0].json.user_id;
      if (pgUserId !== null && pgUserId !== undefined) {
        resolvedUserId = Number(pgUserId);
      }
    }
  } catch (e) {}
}
return [{ json: { resolved_user_id: resolvedUserId, /* ...контекст */ } }];
```

## HTTP-запрос с выражениями в теле: Code-нода вместо HTTP Request

HTTP Request нода не резолвит выражения в JSON body (ERROR_PATTERNS #8).
Паттерн замены:

```javascript
const resp = await this.helpers.httpRequest({
  method: 'POST',
  url: 'http://host:8000/query',
  headers: { 'x-api-key': '...' },
  body: { text: $json.text, chat_id: $json.chat_id },
  json: true,
});
return [{ json: resp }];
```

## Выражения: правило префикса "="

Любое поле с `{{ }}` должно начинаться со знака `=`:
`={{ $json.body.text }}`. Без него содержимое уходит как literal-текст
(ERROR_PATTERNS #3). При отладке "undefined в поле" — первым делом
проверить префикс.

## Универсальный нормализатор нефатальных ошибок

Статус: РЕКОМЕНДОВАНО (из архитектурного разбора Router TEST, июль 2026),
внедрение не подтверждено. Вместо N одинаковых Code-нод
"Prepare Non-Fatal Error - X" перед Notify — одна нода, в которую сходятся
все error-выходы; имя источника и текст ошибки берутся из входного item.
После внедрения обновить статус и вписать фактический код.

## Тестовая обвязка: единый Send Adapter

Статус: РЕКОМЕНДОВАНО (тот же разбор), внедрение не подтверждено.
Вместо пар "Is Sim Source?" + Forward перед каждой отправкой — один
дочерний workflow, решающий, слать в мессенджер или в тестовый receiver.
Боевой и тестовый пути перестают отличаться структурно.
