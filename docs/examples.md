# Примеры работы Support Copilot

Обращения придуманы командой (не из данных Grand Mobile). Ответы — реальный вывод `POST /triage`.

## Жалоба с доказательствами, русский

**Запрос**
```json
{
  "kind": "complaint",
  "messages": [
    {
      "role": "player",
      "attachments": 2,
      "text": "Arman_Petrov оскорблял меня и мою семью в чате, скрины есть, 2.1 ОП"
    }
  ]
}
```

**Ответ** (источник черновика: `llm`, 2.58 с, $0.00060)
```json
{
  "lang": "ru",
  "category": "complaint.insult",
  "priority": "p2",
  "is_spam_or_duplicate": false,
  "extracted": {
    "nickname": "Arman_Petrov",
    "rule_refs": [
      "2.1 ОП"
    ],
    "has_evidence": true,
    "server": null
  },
  "draft_reply": {
    "lang": "ru",
    "text": "Приветствую, уважаемый игрок. Ваша жалоба была рассмотрена и одобрена. Игрок Arman_Petrov будет наказан за 2.1 ОП.\n\nЖалоба закрыта.\n\nС уважением, Администрация GrandMobile",
    "cited": [
      "2.1 ОП"
    ]
  },
  "needs_human": true,
  "confidence": 0.95,
  "reasons": [
    "решение о наказании подтверждает администратор",
    "требуется решение администратора о выдаче конкретного наказания",
    "черновик содержит решение, которое подтверждает только администратор"
  ]
}
```

## Апелляция на своё наказание

**Запрос**
```json
{
  "kind": "complaint",
  "messages": [
    {
      "role": "player",
      "attachments": 1,
      "text": "не согласен с наказанием, бан выдан ошибочно, я не использовал читы, верните аккаунт"
    }
  ]
}
```

**Ответ** (источник черновика: `llm`, 0.90 с, $0.00035)
```json
{
  "lang": "ru",
  "category": "complaint.admin",
  "priority": "p2",
  "is_spam_or_duplicate": false,
  "extracted": {
    "nickname": null,
    "rule_refs": [],
    "has_evidence": true,
    "server": null
  },
  "draft_reply": {
    "lang": "ru",
    "text": "Приветствую.\nВаше обращение рассмотрит старшая администрация.\nС уважением, Администрация GrandMobile!",
    "cited": [
      "3.4 ОП"
    ]
  },
  "needs_human": true,
  "confidence": 0.98,
  "reasons": [
    "категория complaint.admin всегда идёт человеку",
    "решение о наказании подтверждает администратор",
    "апелляция на наказание администратора"
  ]
}
```

## Жалоба на читы, узбекский

**Запрос**
```json
{
  "kind": "complaint",
  "messages": [
    {
      "role": "player",
      "attachments": 1,
      "text": "Bobur_Karimov cheat ishlatyapti, havoda uchib yuribdi, video bor 5.2"
    }
  ]
}
```

**Ответ** (источник черновика: `llm`, 0.94 с, $0.00078)
```json
{
  "lang": "uz",
  "category": "complaint.cheat",
  "priority": "p1",
  "is_spam_or_duplicate": false,
  "extracted": {
    "nickname": "Bobur_Karimov",
    "rule_refs": [
      "5.2 ОП"
    ],
    "has_evidence": true,
    "server": null
  },
  "draft_reply": {
    "lang": "uz",
    "text": "Hurmatli o‘yinchi,\nSizning shikoyatingiz uchun rahmat. Qoidabuzarliklar yoqimsiz holat bo‘lishi mumkinligini tushunamiz. Biroq, tekshiruv o‘tkazish va tegishli choralar ko‘rish uchun video dalil (videofiksatsiya) zarur. Iltimos, nisbatan zarur choralar ko‘rishimiz uchun ko‘proq ma’lumot va dalillar taqdim eting. Sizning hamkorligingiz va tushunishingiz biz uchun muhim. Ishtirokingiz uchun rahmat!",
    "cited": [
      "5.2 ОП"
    ]
  },
  "needs_human": true,
  "confidence": 0.53,
  "reasons": [
    "решение о наказании подтверждает администратор",
    "trebuetsya proverka dokazatelstv"
  ]
}
```

## Репорт: застрял

**Запрос**
```json
{
  "kind": "report",
  "messages": [
    {
      "role": "player",
      "text": "застрял в текстурах у банка, помогите"
    }
  ]
}
```

**Ответ** (источник черновика: `template`)
```json
{
  "lang": "ru",
  "category": "report.help",
  "priority": "p2",
  "is_spam_or_duplicate": false,
  "extracted": {
    "nickname": null,
    "rule_refs": [],
    "has_evidence": false,
    "server": null
  },
  "draft_reply": {
    "lang": "ru",
    "text": "Приветствую, слежу за вами.",
    "cited": []
  },
  "needs_human": false,
  "confidence": 1.0,
  "reasons": []
}
```

## Репорт: платёж, казахский в cp1251 (ї вместо ү)

**Запрос**
```json
{
  "kind": "report",
  "messages": [
    {
      "role": "player",
      "text": "донат жасадым, ГК тїспеді, кґмектесіѕізші"
    }
  ]
}
```

**Ответ** (источник черновика: `llm`, 0.80 с, $0.00032)
```json
{
  "lang": "kk",
  "category": "report.payment",
  "priority": "p0",
  "is_spam_or_duplicate": false,
  "extracted": {
    "nickname": null,
    "rule_refs": [],
    "has_evidence": false,
    "server": null
  },
  "draft_reply": {
    "lang": "kk",
    "text": "Сәлеметсіз бе! Бұл мәселе бойынша өтініш үлкен әкімшіге берілді.",
    "cited": []
  },
  "needs_human": true,
  "confidence": 1.0,
  "reasons": [
    "категория report.payment всегда идёт человеку",
    "вопрос о платеже или возврате",
    "платеж"
  ]
}
```

## Репорт: взлом аккаунта

**Запрос**
```json
{
  "kind": "report",
  "messages": [
    {
      "role": "player",
      "text": "взломали аккаунт, сменили пароль, пропала машина"
    }
  ]
}
```

**Ответ** (источник черновика: `llm`, 0.91 с, $0.00030)
```json
{
  "lang": "ru",
  "category": "report.account",
  "priority": "p0",
  "is_spam_or_duplicate": false,
  "extracted": {
    "nickname": null,
    "rule_refs": [],
    "has_evidence": false,
    "server": null
  },
  "draft_reply": {
    "lang": "ru",
    "text": "Приветствую. Обращение передано старшему администратору.",
    "cited": []
  },
  "needs_human": true,
  "confidence": 1.0,
  "reasons": [
    "категория report.account всегда идёт человеку",
    "подозрение на взлом аккаунта",
    "вопрос взлома аккаунта требует вмешательства старшей администрации"
  ]
}
```

## Пустой репорт

**Запрос**
```json
{
  "kind": "report",
  "messages": [
    {
      "role": "player",
      "text": "+"
    }
  ]
}
```

**Ответ** (источник черновика: `template`)
```json
{
  "lang": "und",
  "category": "report.offtopic",
  "priority": "p3",
  "is_spam_or_duplicate": true,
  "extracted": {
    "nickname": null,
    "rule_refs": [],
    "has_evidence": false,
    "server": null
  },
  "draft_reply": {
    "lang": "ru",
    "text": "Приветствую, слежу за вами.",
    "cited": []
  },
  "needs_human": false,
  "confidence": 0.9,
  "reasons": []
}
```
