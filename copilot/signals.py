"""Опасные темы на всех языках игры: взлом, платёж, апелляция, угроза, массовый сбой.

Эти темы ТЗ требует отдавать человеку, поэтому они не могут зависеть от языка игрока.
Слова подобраны так, чтобы не ловить обычную игру: «бұзды» и «buzdi» значат ещё и
«нарушил правило», поэтому нужна связка с аккаунтом; «ақша» и «pul» это ещё и
игровые деньги, поэтому нужен глагол про оплату.
"""

import re

APOSTROPHE = "['ʻ‘’`]?"
FLAGS = re.I

HACK_RE = re.compile(
    r"взлом|украли акк|угнали акк|сменили пароль|"
    r"(акк|аккаунт)\w*.{0,25}(бұз|ұрла)|(бұз|ұрла)\w*.{0,25}акк|құпия сөз|"
    rf"(akk|akkaunt)\w*.{{0,25}}(buz|o{APOSTROPHE}g{APOSTROPHE}irla)|(buz|o{APOSTROPHE}g{APOSTROPHE}irla)\w*.{{0,25}}(akk|parol)|"
    rf"parol\w*.{{0,25}}o{APOSTROPHE}zgart|"
    r"\bhacked\b|account.{0,25}(stolen|hacked|compromised)|(stole|lost access to).{0,25}account|changed my password|"
    r"(cuenta|contrase[nñ]a).{0,25}(robad|hacke)|robaron.{0,15}(cuenta|contrase)|hackearon|"
    r"(conta|senha).{0,25}(roubad|hacke|invadid)|roubaram.{0,15}(conta|senha)|hackearam|invadiram",
    FLAGS)

PAYMENT_RE = re.compile(
    r"донат|оплат|платеж|платёж|списал|верните деньги|refund|возврат|"
    r"т[өо]лем|т[өо]ледім|а[қк]ша\w*.{0,20}(т[үу]спе|[қк]айтар|алынды)|(гк|донат)\w*.{0,20}(т[үу]спе|келме)|"
    rf"to{APOSTROPHE}lov|to{APOSTROPHE}ladim|pul\w*.{{0,20}}(tushma|kelma|yechil|qaytar)|(gk|donat)\w*.{{0,20}}(tushma|kelma)|"
    r"\bdonat|\bpaid\b|payment|charged|did ?n.?t (receive|get).{0,20}(coin|gk|money)|"
    r"pagu[eé]|reembolso|me cobraron|devu[eé]lv\w*.{0,12}dinero|no recib\w*.{0,20}(moneda|gk)|"
    r"paguei|pagamento|cobraram|n[aã]o recebi",
    FLAGS)

# Многоязычная часть маркера апелляции: её используют и защита, и классификатор.
APPEAL_WORLD = (
    r"амнисти|снимите (мут|варн|джейл|jail)|"
    r"банды?\s+(алып|ашыңыз|ашып|шеш)|бантан шығар|жаза(м|ны|мды)\s+алып|бан.{0,15}(қате|неге)|неге бан|"
    r"bandan chiqar|ban\w*\s+(yech|och|olib)|nohaq|jazo\w*\s+(olib|bekor)|"
    r"\bunban|\bappeal|remove.{0,10}\bban|wrongly banned|banned for no reason|"
    r"desban|\bapelar|apelaci[oó]n|quit\w*.{0,10}\b(ban|sanci)|"
    r"apela[cç][aã]o|remov\w*.{0,10}\b(ban|puni)"
)
APPEAL_RE = re.compile(rf"апелляц|разбан|разблок|снимите (бан|наказ)|незаслуж|ошибочно забан|{APPEAL_WORLD}", FLAGS)

# Явная угроза жизни или себе: сразу P0.
THREAT_RE = re.compile(
    r"убью|найду тебя|суицид|покончу с собой|"
    r"[өо]лт[іи]рем|сен[іи] табам|өзімді өлтір|"
    rf"o{APOSTROPHE}ldiraman|seni top(aman|ib)|o{APOSTROPHE}zimni o{APOSTROPHE}ldir|"
    r"(i.?ll|i will|gonna)\s+(kill|find) you|kill myself|\bsuicide|"
    r"te voy a (matar|encontrar)|suicid|matarme|"
    r"vou te (matar|encontrar)|me matar",
    FLAGS)
# Намёк на встречу вне игры: человек посмотрит, но это ещё не P0.
OFFLINE_RE = re.compile(r"\bадрес|в реале", FLAGS)

MASS_BUG_RE = re.compile(
    r"(у всех|массов\w*)\s.{0,20}(баг|лаг|вылет|не работа|не заход|краш|завис)|сервер (упал|лежит)|никто не может зайти|"
    r"сервер құлады|server ishlamay|server (is )?down|servidor (ca[ií]do|caiu)",
    FLAGS)
