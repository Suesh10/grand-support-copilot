"""Шаблоны ответов на казахском и узбекском.

Казахские написал носитель языка из команды, узбекские подготовлены с LLM
и сверены по стилю с реальными ответами админов. Используются:
  - как готовые ответы на типовые репорты (без LLM, бесплатно);
  - как нейтральная передача администрации;
  - как образцы стиля для LLM-черновиков на kk/uz.
"""

KK = {
    "approved": "Сәлеметсіз бе! Шағымыңыз қаралды және мақұлданды: ойыншы {rule} бойынша {punishment} жазасын алады. Белсенділігіңіз үшін рақмет!",
    "need_evidence": "Сәлеметсіз бе! Шағымыңыз қаралды, бірақ ұсынылған дәлелдер жеткіліксіз. Өтінеміз, бейнежазба немесе қосымша дәлелдер қосып, қайта жіберіңіз.",
    "rejected": "Сәлеметсіз бе! Шағымыңыз мұқият қаралды, алайда ереже бұзушылық анықталмады. Хабарлағаныңыз үшін рақмет.",
    "invalid_format": "Сәлеметсіз бе! Өкінішке қарай, шағым белгіленген талаптарға сай рәсімделмеген. Өтінеміз, шағымды ережелерге сәйкес қайта жіберіңіз.",
    "duplicate": "Сәлеметсіз бе! Бұл шағым бұрын жіберілген өтініштің қайталамасы болып табылады. Қосымша ақпарат болса, сол өтініш аясында көрсетіңіз.",
    "help": "Сәлеметсіз бе! Өтінішіңіз қабылданды, администратор жақын арада көмектеседі. Өтінеміз, күте тұрыңыз.",
    "senior": "Сәлеметсіз бе! Сұрағыңыз әкімшілікке жіберілді. Жауапты жақын арада аласыз.",
    "offtopic": "Сәлеметсіз бе! Бұл өтініш тақырыпқа сай емес. Өтінеміз, нақты мәселеңізді жеке өтініш ретінде жіберіңіз.",
}

_UZ_COMPLAINT = "Hurmatli o'yinchi, shikoyatingiz uchun tashakkur bildiramiz. "
_UZ_REPORT = "Hurmatli o'yinchi, murojaatingiz uchun tashakkur bildiramiz. "
UZ = {
    "approved": _UZ_COMPLAINT + "Shikoyatingiz ko'rib chiqildi va tasdiqlandi: o'yinchi qoidalarning {rule} bandini buzgani uchun {punishment} jazosi bilan jazolandi. Yopildi.",
    "need_evidence": _UZ_COMPLAINT + "Afsuski, taqdim etilgan dalillar yetarli emas. Iltimos, qo'shimcha dalil (video yozuv, skrinshot) taqdim eting — shunda shikoyatni qayta ko'rib chiqamiz. Yopildi.",
    "rejected": _UZ_COMPLAINT + "Tekshiruv natijasida qoidabuzarlik aniqlanmadi. Xabaringiz uchun rahmat. Yopildi.",
    "invalid_format": _UZ_COMPLAINT + "Afsuski, shikoyat shikoyat topshirish qoidalariga muvofiq rasmiylashtirilmagan. Iltimos, shikoyatni qoidalarga mos ravishda qayta yuboring. Yopildi.",
    "duplicate": _UZ_COMPLAINT + "Bu masala bo'yicha shikoyatingiz avvalroq qayd etilgan. Takroriy murojaatlar ko'rib chiqilmaydi; javob birinchi shikoyat bo'yicha beriladi. Yopildi.",
    "help": _UZ_REPORT + "Administrator yaqin orada yordam beradi, iltimos, kuting.",
    "senior": _UZ_REPORT + "Savolingiz administratsiyaga yuborildi. Javob qisqa vaqt ichida beriladi.",
    "offtopic": _UZ_REPORT + "Murojaatingiz o'yin qoidalariga taalluqli emas. Iltimos, aniq masalani tavsiflab, murojaatni qayta yuboring. Yopildi.",
}

BY_LANG = {"kk": KK, "uz": UZ}

# Черновик по существу: решение предлагает модель, подтверждает админ. Ключ review — исход неясен.
# {who} ник нарушителя, {by} пункт правил, {term} наказание из текста пункта, {on} «на кого жалоба».
PROPOSALS = {
    "ru": {
        "approved": "Приветствую, уважаемый игрок. Ваша жалоба рассмотрена и одобрена. {who} будет наказан{by}{term}. Спасибо за обращение!",
        "need_evidence": "Приветствую, уважаемый игрок. Ваша жалоба рассмотрена, но доказательств недостаточно. "
                         "Приложите видеозапись или дополнительные скриншоты и подайте жалобу повторно.",
        "duplicate": "Приветствую, уважаемый игрок. Эта жалоба повторяет уже поданную, она на рассмотрении. Подавать её ещё раз не нужно, дождитесь решения.",
        "review": "Приветствую, уважаемый игрок. Ваша жалоба{on} принята. Администрация проверит приложенные материалы{by} и сообщит решение.",
        "appeal_rejected": "Приветствую, уважаемый игрок. Ваше обращение рассмотрено: наказание выдано верно.",
        "appeal_review": "Приветствую, уважаемый игрок. Ваше обращение принято. Администрация проверит ситуацию{by} и сообщит решение.",
    },
    "kk": {
        "approved": "Сәлеметсіз бе! Шағымыңыз қаралды және мақұлданды: {who}{by} жазасын алады. Белсенділігіңіз үшін рақмет!",
        "need_evidence": KK["need_evidence"],
        "review": "Сәлеметсіз бе! Шағымыңыз қабылданды. Әкімшілік материалдарды{by} тексеріп, шешімін хабарлайды.",
        "appeal_rejected": "Сәлеметсіз бе! Өтінішіңіз қаралды: жаза дұрыс берілген.",
        "appeal_review": "Сәлеметсіз бе! Өтінішіңіз қабылданды. Әкімшілік жағдайды{by} тексеріп, шешімін хабарлайды.",
    },
    "uz": {
        "approved": _UZ_COMPLAINT + "Shikoyatingiz ko'rib chiqildi va tasdiqlandi: {who}{by} jazolanadi.",
        "need_evidence": UZ["need_evidence"],
        "review": "Hurmatli o'yinchi, shikoyatingiz uchun rahmat. Administratsiya materiallarni{by} tekshirib, qaror haqida xabar beradi.",
        "appeal_rejected": _UZ_REPORT + "Murojaatingiz ko'rib chiqildi: jazo to'g'ri berilgan.",
        "appeal_review": "Hurmatli o'yinchi, murojaatingiz uchun rahmat. Administratsiya vaziyatni{by} tekshirib, qaror haqida xabar beradi.",
    },
    "en": {
        "review": "Hello! Your complaint has been received. The administration will check the attached materials{by} and let you know the decision.",
        "appeal_review": "Hello! Your request has been received. The administration will look into the situation{by} and let you know the decision.",
    },
    "es": {
        "review": "¡Hola! Su queja ha sido recibida. La administración revisará los materiales adjuntos{by} y le comunicará la decisión.",
        "appeal_review": "¡Hola! Su solicitud ha sido recibida. La administración revisará la situación{by} y le comunicará la decisión.",
    },
    "pt": {
        "review": "Olá! Sua reclamação foi recebida. A administração verificará os materiais anexados{by} e informará a decisão.",
        "appeal_review": "Olá! Sua solicitação foi recebida. A administração verificará a situação{by} e informará a decisão.",
    },
}
# Как язык называет игрока и пункт: падежи разные, поэтому строки целиком.
WHO = {"ru": ("Игрок {nick}", "Нарушитель"), "kk": ("ойыншы {nick}", "ойыншы"), "uz": ("o'yinchi {nick}", "o'yinchi")}
BY_RULE = {"ru": " по пункту {ref}", "kk": " {ref} бойынша", "uz": " qoidalarning {ref} bandi bo'yicha",
           "en": " under rule {ref}", "es": " según la regla {ref}", "pt": " pela regra {ref}"}
ON_NICK = {"ru": " на {nick}"}

# Категория репорта → шаблон; исход жалобы → шаблон.
REPORT_SITUATION = {"report.help": "help", "report.offtopic": "offtopic", "report.question": "senior",
                    "report.complaint": "senior", "report.account": "senior", "report.payment": "senior"}
VERDICT_SITUATION = {"need_evidence": "need_evidence", "rejected": "rejected", "invalid_format": "invalid_format",
                     "duplicate": "duplicate", "already_punished": "duplicate"}


def get(lang: str, situation: str) -> str | None:
    """Шаблон без незаполненных мест ({rule}, {punishment} есть только в approved)."""
    text = BY_LANG.get(lang, {}).get(situation)
    return None if text is None or "{" in text else text


def style_examples(lang: str, kind: str, verdict: str | None) -> list[str]:
    """Образцы стиля для LLM на kk/uz: подходящий шаблон + передача администрации."""
    table = BY_LANG.get(lang)
    if not table:
        return []
    key = VERDICT_SITUATION.get(verdict or "", "help" if kind == "report" else "need_evidence")
    return [table[key], table["senior"]]
