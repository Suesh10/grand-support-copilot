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

**Ответ** (источник черновика: `llm`, 2.82 с, $0.00068)
```json
{
  "lang": "ru",
  "category": "complaint.insult",
  "priority": "p2",
  "is_spam_or_duplicate": false,
  "extracted": {
    "nickname": "Arman_Petrov",
    "rule_refs": [
      "2.1"
    ],
    "has_evidence": true,
    "server": null
  },
  "draft_reply": {
    "lang": "ru",
    "text": "Приветствую, уважаемый игрок. Ваша жалоба была рассмотрена и одобрена. Игрок Arman_Petrov будет наказан за нарушение пункта 2.1 ОП.\n\nЖалоба закрыта. \n\nС уважением, Администрация \nGrandMobile",
    "cited": [
      "2.1"
    ]
  },
  "needs_human": true,
  "confidence": 0.95,
  "reasons": [
    "решение о наказании подтверждает администратор",
    "Требуется решение администратора о выдаче наказания по жалобе",
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

**Ответ** (источник черновика: `llm`, 0.96 с, $0.00049)
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
    "text": "Здравствуйте. Ваше обращение будет передано старшей администрации. Ожидайте ответа.",
    "cited": [
      "3.4"
    ]
  },
  "needs_human": true,
  "confidence": 0.87,
  "reasons": [
    "категория complaint.admin всегда идёт человеку",
    "решение о наказании подтверждает администратор",
    "апелляция на наказание администратора требует решения старшей администрации"
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

**Ответ** (источник черновика: `llm`, 0.89 с, $0.00071)
```json
{
  "lang": "uz",
  "category": "complaint.cheat",
  "priority": "p1",
  "is_spam_or_duplicate": false,
  "extracted": {
    "nickname": "Bobur_Karimov",
    "rule_refs": [
      "5.2"
    ],
    "has_evidence": true,
    "server": null
  },
  "draft_reply": {
    "lang": "uz",
    "text": "Hurmatli o'yinchi, shikoyatingiz uchun tashakkur bildiramiz. Afsuski, taqdim etilgan dalillar yetarli emas. Iltimos, qo'shimcha dalil (video yozuv, skrinshot) taqdim eting — shunda shikoyatni qayta ko'rib chiqamiz. Yopildi. Asos: 5.2 ОП bandi.",
    "cited": [
      "1.2.2",
      "5.2"
    ]
  },
  "needs_human": true,
  "confidence": 0.66,
  "reasons": [
    "решение о наказании подтверждает администратор",
    "Требуется проверка доказательств на читы"
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
  "priority": "p3",
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

**Ответ** (источник черновика: `template`)
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
    "text": "Сәлеметсіз бе! Сұрағыңыз аға администраторға жіберілді. Жауапты жақын арада аласыз.",
    "cited": []
  },
  "needs_human": true,
  "confidence": 1.0,
  "reasons": [
    "категория report.payment всегда идёт человеку",
    "вопрос о платеже или возврате"
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

**Ответ** (источник черновика: `llm`, 0.83 с, $0.00039)
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
    "text": "Приветствую, обращение передано старшему администратору.",
    "cited": []
  },
  "needs_human": true,
  "confidence": 1.0,
  "reasons": [
    "категория report.account всегда идёт человеку",
    "подозрение на взлом аккаунта",
    "взлом аккаунта"
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
    "text": "Приветствую, ожидайте.",
    "cited": []
  },
  "needs_human": false,
  "confidence": 0.9,
  "reasons": []
}
```
