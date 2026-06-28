# Git — Шпаргалка (music-video-maker)

Репозиторий: https://github.com/mirashic33-alt/music-video-maker
Ветка: **master**

## Обновить код на GitHub (после изменений)

```bash
git add .
git commit -m "Что изменили"
git push
```

---

## Пометить версию для видео (тег)

Делать ПОСЛЕ `git push`:

```bash
git tag v1.0 -m "Первая версия"
git push origin v1.0
```

Зрители смогут зайти в раздел **Releases / Tags** на GitHub и скачать код этой версии.

---

## ВАЖНО — безопасность (что НЕ коммитить)

Уже настроено в `.gitignore`, не убирай оттуда:
- `state.json` — твой API-ключ Grok и личные пути.
- `img/`, `output/` — картинки и рендеры (тяжёлые).

Ключ Grok вставляется в самой программе (вкладка «Генерация видео»), в коде его быть НЕ должно.
Перед `git push` можно быстро проверить, что ключ не утёк:

```bash
git grep -nI --cached "xai-"
```

Если что-то нашлось — НЕ пушить, сначала убрать.

---

## Вернуться к старой версии (только посмотреть)

```bash
git log --oneline       # список версий
git checkout <хэш>      # перейти к версии
git checkout master     # вернуться обратно
```

---

## Клонировать на другом компьютере

```bash
git clone https://github.com/mirashic33-alt/music-video-maker.git
cd music-video-maker
```

---

## Частые ошибки

**`error: src refspec main does not match any`**
→ Ветка называется `master`. Используй `git push origin master`.

**`rejected: fetch first`**
→ Сначала `git pull origin master --allow-unrelated-histories`, потом `git push`.

**`remote origin already exists`**
→ Не страшно, репозиторий уже настроен. Продолжай.
