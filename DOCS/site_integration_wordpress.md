# Сайт zetomkatowice.eu → CRM: настройка WordPress

Форма «Kontakt» на сайте (Divi, `et_pb_contact_form`) после отправки шлёт
поля в CRM. Письмо на biuro@zetom.eu уходит как раньше, так что если CRM
недоступна, заявка не теряется.

```
посетитель → форма Divi → письмо biuro@zetom.eu   (как сейчас)
                       └→ POST /zetom/api/site-request/ → окно валидации CRM (источник «Site»)
```

## 1. CRM (сервер)

1. Сгенерировать токен:
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
2. Вписать в `.env` сервера CRM: `SITE_INTAKE_TOKEN=<токен>` и перезапустить контейнер `web`.
   Пока токен пустой, эндпоинт выключен (отвечает 404).
3. Проверить с любого компьютера (должно вернуть `201` и `{"id": ...}`; потом удалить тестовую заявку в окне валидации):
   ```bash
   curl -i -X POST https://<домен-crm>/zetom/api/site-request/ \
     -H "Authorization: Bearer <токен>" -H "Content-Type: application/json" \
     -d '{"first_name":"Test","last_name":"Integracja","phone":"+48322569257","email":"test@zetom.eu","message":"test"}'
   ```
4. Если CRM за Cloudflare: в правилах WAF / Bot Fight Mode разрешить путь `/zetom/api/site-request/`,
   иначе Cloudflare может отбить запрос с сервера WordPress (ответ 403 с HTML-страницей Cloudflare).

## 2. WordPress

### 2.1. Токен и адрес в `wp-config.php`

Через FTP / файловый менеджер хостинга добавить в `wp-config.php` перед строкой
`/* That's all, stop editing! */`:

```php
define( 'ZETOM_CRM_URL', 'https://<домен-crm>/zetom/api/site-request/' );
define( 'ZETOM_CRM_TOKEN', '<токен>' );
```

Токен не кладём в сам сниппет, чтобы его не было видно в админке WordPress.

### 2.2. Сниппет

Плагины → Добавить → **Code Snippets** → установить и активировать.
Snippets → Add New → название «ZETOM → CRM», тип PHP, «Run snippet everywhere», вставить и активировать:

```php
<?php
// Пересылает форму «Kontakt» (Divi) в ZETOM CRM. Письмо Divi уходит как раньше.
add_action( 'et_pb_contact_form_submit', function ( $fields, $has_error, $form_info ) {
    if ( $has_error || ! defined( 'ZETOM_CRM_URL' ) || ! defined( 'ZETOM_CRM_TOKEN' ) ) {
        return;
    }
    $value = function ( $id ) use ( $fields ) {
        return isset( $fields[ $id ]['value'] ) ? sanitize_text_field( $fields[ $id ]['value'] ) : '';
    };
    $payload = array(
        'first_name'   => $value( 'imie' ),
        'last_name'    => $value( 'nazwisko' ),
        'phone'        => $value( 'telefon' ),
        'email'        => $value( 'email' ),
        'company_name' => $value( 'firma' ),
        'message'      => isset( $fields['wiadomosc']['value'] )
            ? sanitize_textarea_field( $fields['wiadomosc']['value'] ) : '',
    );
    $response = wp_remote_post( ZETOM_CRM_URL, array(
        'timeout' => 8,
        'headers' => array(
            'Authorization' => 'Bearer ' . ZETOM_CRM_TOKEN,
            'Content-Type'  => 'application/json',
        ),
        'body'    => wp_json_encode( $payload ),
    ) );
    $code = is_wp_error( $response ) ? $response->get_error_message() : wp_remote_retrieve_response_code( $response );
    if ( ! in_array( $code, array( 200, 201 ), true ) ) {
        error_log( 'ZETOM CRM intake failed: ' . print_r( $code, true ) . ' ' . wp_remote_retrieve_body( $response ) );
    }
}, 10, 3 );
```

Если на сайте несколько форм Divi, а пересылать нужно только «Kontakt», в начало
функции добавить проверку `$form_info['contact_form_number']` (номер формы на странице).

### 2.3. Проверка

1. Отправить форму на https://zetomkatowice.eu/kontakt/ с тестовыми данными.
2. В CRM → окно валидации: появилась заявка, источник «Site», поля на месте.
3. На biuro@zetom.eu пришло обычное письмо Divi.
4. Если заявки нет — смотреть `wp-content/debug.log` (включить `WP_DEBUG_LOG` в `wp-config.php`)
   на строку `ZETOM CRM intake failed`:
   - `401` — токен в `wp-config.php` не совпадает с `.env` CRM;
   - `404` — в CRM не задан `SITE_INTAKE_TOKEN` или неверный адрес;
   - `400` + список полей — данные не прошли проверку CRM (например, телефон или email);
   - `403` с HTML Cloudflare — см. п. 1.4.

## Ответы эндпоинта

| Код | Когда |
|---|---|
| 201 `{"id": N}` | заявка создана |
| 200 `{"id": N, "duplicate": true}` | тот же email и текст за последние 10 минут — вторая не создаётся |
| 400 `{"errors": {...}}` | не прошла проверка полей (имя, фамилия, телефон, email обязательны) |
| 401 | нет или неверный токен |
| 404 | `SITE_INTAKE_TOKEN` не задан — эндпоинт выключен |
| 405 | не POST |
