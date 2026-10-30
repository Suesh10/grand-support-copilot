"""Шаблоны ответов на казахском и узбекском.

Казахские написал носитель языка из команды, узбекские подготовлены с LLM
и сверены по стилю с реальными ответами админов. Используются:
  - как готовые ответы на типовые репорты (без LLM, бесплатно);
  - как нейтральная передача старшему администратору;
  - как образцы стиля для LLM-черновиков на kk/uz.
"""

KK = {
    "approved": "Сәлеметсіз бе! Шағымыңыз қаралды және мақұлданды: ойыншы {rule} бойынша {punishment} жазасын алады. Белсенділігіңіз үшін рақмет!",
    "need_evidence": "Сәлеметсіз бе! Шағымыңыз қаралды, бірақ ұсынылған дәлелдер жеткіліксіз. Өтінеміз, бейнежазба немесе қосымша дәлелдер қосып, қайта жіберіңіз.",
    "rejected": "Сәлеметсіз бе! Шағымыңыз мұқият қаралды, алайда ереже бұзушылық анықталмады. Хабарлағаныңыз үшін рақмет.",
    "invalid_format": "Сәлеметсіз бе! Өкінішке қарай, шағым белгіленген талаптарға сай рәсімделмеген. Өтінеміз, шағымды ережелерге сәйкес қайта жіберіңіз.",
    "duplicate": "Сәлеметсіз бе! Бұл шағым бұрын жіберілген өтініштің қайталамасы болып табылады. Қосымша ақпарат болса, сол өтініш аясында көрсетіңіз.",
    "help": "Сәлеметсіз бе! Өтінішіңіз қабылданды, администратор жақын арада көмектеседі. Өтінеміз, күте тұрыңыз.",
    "senior": "Сәлеметсіз бе! Сұрағыңыз аға администраторға жіберілді. Жауапты жақын арада аласыз.",
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
    "senior": _UZ_REPORT + "Savolingiz katta administratorga yuborildi. Javob qisqa vaqt ichida beriladi.",
    "offtopic": _UZ_REPORT + "Murojaatingiz o'yin qoidalariga taalluqli emas. Iltimos, aniq masalani tavsiflab, murojaatni qayta yuboring. Yopildi.",
}

BY_LANG = {"kk": KK, "uz": UZ}

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
    """Образцы стиля для LLM на kk/uz: подходящий шаблон + передача старшему."""
    table = BY_LANG.get(lang)
    if not table:
        return []
    key = VERDICT_SITUATION.get(verdict or "", "help" if kind == "report" else "need_evidence")
    return [table[key], table["senior"]]
