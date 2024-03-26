
# [PyQt] [Russian] LAN-DESKTOP v0.1 for Windows by Sergei Krumas

LAN-DESKTOP в пределах локальной сети позволяет как управлять удалённым компьютером, так и позволить удалённому компьютеру управлять вашим компьютером. Эта программа решает проблему, когда рядом стоят 2-3 системных блока и на столе нет места комплектовать каждый из них мышкой, клавиатурой и монитором, а графическим режимом пользоваться приходится.

Готовые альтернативы, на которые можно периодически посматривать и брать идейки для дальнейшей разработки: https://github.com/topics/remote-desktop?l=python


## Зависимости
После установки pyautogui из зависимосте, дополнительно потребуется выполнить следующую команду `sudo apt-get install python3-tk python3-dev`


## Changelog

### 1й раунд разработки (август 2023 - 13 февраля 2024)
- добавлен чат из примеров Qt, который я портировал на PyQt. В процессе пришлось отказаться от QCBORStreamWriter и QCBORStreamReader и воспользоваться модулем cbor2, так как питоновская обёртка QCBORStreamWriter не видит некоторых Qt-шных методов объекта, а питоновская обёртка QCBORStreamReader не даёт прочитать записанную строку через PyQt в принципе, выдавая ошибку питоновской обёртки - SystemError: sipBuildResult(): invalid format string "NF". Модуль cbor2 работает так же просто как и модуль json.
    - на основе этого чата будет разрабатываться LAN-DESKTOP
    - помимо отправки сообщений в пределах локальной сети чат умеет искать пиров и сообщает об их подключении как только так сразу

### 2й раунд разработки (13 февраля 2024 - ?????)
- теперь интерфейс задаётся полностью кодом. Между текстом чата и списком пиров добавлен сплиттер, который можно перемещать мышкой
- (21 мар 24) успешно осуществлена передача скриншота с Linux Mint на виртуальной машине в Windows 10 на физической машине. Работает и в случае двух копий на одной машине, тогда в одном из чатов придётся включать флалок `Send Screenshot`. Полученный скриншот сохраняется в папке приложения с именем f'{time.time()}'.jpg и пока ещё не отображается в самой приложухе. Решена проблема долгой передачи картинки: метод чтения читал слишком мало данных
- (21 мар 24) полученный скриншот теперь выводится в окне, окно отображается сразу при получении скриншота
- (25 мар 24) изменил струтуру передачи по TCP (по UDP передача осталась прежней)
    - раньше было так:
        - 4 байта для размера сообщения (big-endian)
        - тело соообщения (cbor2 binary)
    - теперь будет так:
        - 4 байта для совокупного размера serial-сообщения и binary-сообщения (big-endian)
        - 4 байта для размера serial-сообщения (big-endian)
        - 4 байта для размера binary-сообщения (big-endian)
        - тело serial-сообщения (cbor2 binary)
        - тело binary-сообщения (attached binary)
- (25 мар 24) чекбокс «Send Screenshot» переименован в «Allow Remote Control». Его активация даёт возможность извне управлять компьютером, на котором запущено приложение с активированным чекбоксом. При запуске в Linux чекбокс автоматически активируется. Этот чекбокс существует для целей разработки и в дальнейшем весь UX будет пересмотрен.
- (25 мар 24) теперь ведомое приложение может указать область захвата: все мониторы или только какой-то один. Кастомная область захвата будет добавлена поздней. Вдобавок вместе со скриншотом приходят координаты прямоугольника области захвата
- (26 мар 24) добавил мгновенное закрытие приложения при нажатии клавиши `Escape`
- (26 мар 24) передача событий мышки (левая, правая, колесо)
    - пофиксил расхождение в размерах области захвата и размерах изображения
    - ограничение генерации управляющих данных: курсор должен быть на картинке
    - реализована тестовая передача координат курсора (элементы интерфейса должны менять отрисовку при наведении курсора, например, на объекты на рабочем столе и на часы в трее в Linux Mint). Пока нормального маппинга не реализовано и окно вьюпорта должно иметь одинаковые размеры с область захвата
    - реализован маппинг координат (ведь изображение рисуется без соблюдения масштаба и не всегда в левом верхнем углу, для того чтобы втиснутся в текущие размеры окна)
    - реализована передача инфы о зажатии и отпускании
        - левой кнопки мыши (уже работают перетаскивания)
        - правой кнопки мыши
        - средней кнопки мыши (колесо)
    - реализована передача инфы о вращениях колеса мыши
- (26 мар 24) добавил менюбар ко вьюпорту с командой закрытия приложения
- (26 мар 24) в заголовке вьюпорта отображается адрес удалённого компьютера, управление которым производится
- (26 мар 24) во вьюпорте теперь отображаются нажимаемые и отпускаемые клавиши для целей дебага
- (26 мар 24) написан транслятор данных: Qt-атрибуты событий нажатия клавиш транслируются в аргументы для функций pyautogui
- (26 мар 24) реализована передача инфы о зажатых и отпущенных клавишах клавиатуры
- (26 мар 24) переписал отрисовку вьюпорта так, чтобы менюбар не перекрывал изображение
- (26 мар 24) если не удалось транслировать нажимаемую клавишу в понятный аргумент для функций модуля pyautogui, то по периметру вьюпорта временно появится покраснение


## Второстепенные хотелки
- передавать видео с видеокамеры и голос с микрофона или видеокамеры
- проверка обновлений в репозитории при загрузке или обновление от соседа, который подключается (решить проблему автоматической установки новых зависимостей, если они появятся)


## [Удобная отладка и разработка](DEBUG_UX.md)

## [Если LAN-DESKTOP не работает](TROUBLESHOOTING.md)
