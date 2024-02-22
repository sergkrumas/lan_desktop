
# [PyQt] [Russian] LAN-DESKTOP v0.1 for Windows by Sergei Krumas

LAN-DESKTOP в пределах локальной сети позволяет как управлять удалённым компьютером, так и позволить удалённому компьютеру управлять вашим компьютером. Эта программа решает проблему, когда рядом стоят 2-3 системных блока и на столе нет места комплектовать каждый из них мышкой, клавиатурой и монитором, а графическим режимом пользоваться приходится.

Готовые альтернативы, на которые можно периодически посматривать и брать идейки для дальнейшей разработки: https://github.com/topics/remote-desktop?l=python


## Changelog

### 1й раунд разработки (август 2023 - 13 февраля 2024)
- добавлен чат из примеров Qt, который я портировал на PyQt. В процессе пришлось отказаться от QCBORStreamWriter и QCBORStreamReader и воспользоваться модулем cbor2, так как питоновская обёртка QCBORStreamWriter не видит некоторых Qt-шных методов объекта, а питоновская обёртка QCBORStreamReader не даёт прочитать записанную строку через PyQt в принципе, выдавая ошибку питоновской обёртки - SystemError: sipBuildResult(): invalid format string "NF". Модуль cbor2 работает так же просто как и модуль json.
	- на основе этого чата будет разрабатываться LAN-DESKTOP
	- помимо отправки сообщений в пределах локальной сети чат умеет искать пиров и сообщает об их подключении как только так сразу

### 2й раунд разработки (13 февраля 2024 - ?????)
- теперь интерфейс задаётся полностью кодом. Между текстом чата и списком пиров добавлен сплиттер, который можно перемещать мышкой.


## Второстепенные хотелки
- пробуждать удалённый компьютер командой из программы (Wake on LAN)
- показывать на удалённом компьютере нажимаемые и зажимаемые клавиши
- передавать видео с видеокамеры и голос с микрофона или видеокамеры
- проверка обновлений в репозитории при загрузке или обновление от соседа, который подключается (решить проблему автоматической установки новых зависимостей, если они появятся)



## [Удобная отладка и разработка](DEBUG_UX.md)

## [Если LAN-DESKTOP не работает](TROUBLESHOOTING.md)
