"""Revised Romanization of Hangul: a port of the rr rules from Aromanize-js (MIT, Fajar Chandra)."""

CHO = {
    'ᄀ': 'g', 'ᄁ': 'kk', 'ᄂ': 'n', 'ᄃ': 'd', 'ᄄ': 'tt', 'ᄅ': 'r', 'ᄆ': 'm', 'ᄇ': 'b', 'ᄈ': 'pp',
    'ᄉ': 's', 'ᄊ': 'ss', 'ᄋ': '', 'ᄌ': 'j', 'ᄍ': 'jj', 'ᄎ': 'ch', 'ᄏ': 'k', 'ᄐ': 't', 'ᄑ': 'p', 'ᄒ': 'h',
}

JUNG = {
    'ᅡ': 'a', 'ᅢ': 'ae', 'ᅣ': 'ya', 'ᅤ': 'yae', 'ᅥ': 'eo', 'ᅦ': 'e', 'ᅧ': 'yeo', 'ᅨ': 'ye',
    'ᅩ': 'o', 'ᅪ': 'wa', 'ᅫ': 'wae', 'ᅬ': 'oe', 'ᅭ': 'yo', 'ᅮ': 'u', 'ᅯ': 'wo', 'ᅰ': 'we',
    'ᅱ': 'wi', 'ᅲ': 'yu', 'ᅳ': 'eu', 'ᅴ': 'eui', 'ᅵ': 'i',
}

JONG = {
    'ᆨ': 'k', 'ᆨᄋ': 'g', 'ᆨᄂ': 'ngn', 'ᆨᄅ': 'ngn', 'ᆨᄆ': 'ngm', 'ᆨᄒ': 'kh',
    'ᆩ': 'kk', 'ᆩᄋ': 'kg', 'ᆩᄂ': 'ngn', 'ᆩᄅ': 'ngn', 'ᆩᄆ': 'ngm', 'ᆩᄒ': 'kh',
    'ᆪ': 'k', 'ᆪᄋ': 'ks', 'ᆪᄂ': 'ngn', 'ᆪᄅ': 'ngn', 'ᆪᄆ': 'ngm', 'ᆪᄒ': 'kch',
    'ᆫ': 'n', 'ᆫᄅ': 'll',
    'ᆬ': 'n', 'ᆬᄋ': 'nj', 'ᆬᄂ': 'nn', 'ᆬᄅ': 'nn', 'ᆬᄆ': 'nm', 'ᆬㅎ': 'nch',
    'ᆭ': 'n', 'ᆭᄋ': 'nh', 'ᆭᄅ': 'nn',
    'ᆮ': 't', 'ᆮᄋ': 'd', 'ᆮᄂ': 'nn', 'ᆮᄅ': 'nn', 'ᆮᄆ': 'nm', 'ᆮᄒ': 'th',
    'ᆯ': 'l', 'ᆯᄋ': 'r', 'ᆯᄂ': 'll', 'ᆯᄅ': 'll',
    'ᆰ': 'k', 'ᆰᄋ': 'lg', 'ᆰᄂ': 'ngn', 'ᆰᄅ': 'ngn', 'ᆰᄆ': 'ngm', 'ᆰᄒ': 'lkh',
    'ᆱ': 'm', 'ᆱᄋ': 'lm', 'ᆱᄂ': 'mn', 'ᆱᄅ': 'mn', 'ᆱᄆ': 'mm', 'ᆱᄒ': 'lmh',
    'ᆲ': 'p', 'ᆲᄋ': 'lb', 'ᆲᄂ': 'mn', 'ᆲᄅ': 'mn', 'ᆲᄆ': 'mm', 'ᆲᄒ': 'lph',
    'ᆳ': 't', 'ᆳᄋ': 'ls', 'ᆳᄂ': 'nn', 'ᆳᄅ': 'nn', 'ᆳᄆ': 'nm', 'ᆳᄒ': 'lsh',
    'ᆴ': 't', 'ᆴᄋ': 'lt', 'ᆴᄂ': 'nn', 'ᆴᄅ': 'nn', 'ᆴᄆ': 'nm', 'ᆴᄒ': 'lth',
    'ᆵ': 'p', 'ᆵᄋ': 'lp', 'ᆵᄂ': 'mn', 'ᆵᄅ': 'mn', 'ᆵᄆ': 'mm', 'ᆵᄒ': 'lph',
    'ᆶ': 'l', 'ᆶᄋ': 'lh', 'ᆶᄂ': 'll', 'ᆶᄅ': 'll', 'ᆶᄆ': 'lm', 'ᆶᄒ': 'lh',
    'ᆷ': 'm', 'ᆷᄅ': 'mn',
    'ᆸ': 'p', 'ᆸᄋ': 'b', 'ᆸᄂ': 'mn', 'ᆸᄅ': 'mn', 'ᆸᄆ': 'mm', 'ᆸᄒ': 'ph',
    'ᆹ': 'p', 'ᆹᄋ': 'ps', 'ᆹᄂ': 'mn', 'ᆹᄅ': 'mn', 'ᆹᄆ': 'mm', 'ᆹᄒ': 'psh',
    'ᆺ': 't', 'ᆺᄋ': 's', 'ᆺᄂ': 'nn', 'ᆺᄅ': 'nn', 'ᆺᄆ': 'nm', 'ᆺᄒ': 'sh',
    'ᆻ': 't', 'ᆻᄋ': 'ss', 'ᆻᄂ': 'tn', 'ᆻᄅ': 'tn', 'ᆻᄆ': 'nm', 'ᆻᄒ': 'th',
    'ᆼ': 'ng',
    'ᆽ': 't', 'ᆽᄋ': 'j', 'ᆽᄂ': 'nn', 'ᆽᄅ': 'nn', 'ᆽᄆ': 'nm', 'ᆽᄒ': 'ch',
    'ᆾ': 't', 'ᆾᄋ': 'ch', 'ᆾᄂ': 'nn', 'ᆾᄅ': 'nn', 'ᆾᄆ': 'nm', 'ᆾᄒ': 'ch',
    'ᆿ': 'k', 'ᆿᄋ': 'k', 'ᆿᄂ': 'ngn', 'ᆿᄅ': 'ngn', 'ᆿᄆ': 'ngm', 'ᆿᄒ': 'kh',
    'ᇀ': 't', 'ᇀᄋ': 't', 'ᇀᄂ': 'nn', 'ᇀᄅ': 'nn', 'ᇀᄆ': 'nm', 'ᇀᄒ': 'th',
    'ᇁ': 'p', 'ᇁᄋ': 'p', 'ᇁᄂ': 'mn', 'ᇁᄅ': 'mn', 'ᇁᄆ': 'mm', 'ᇁᄒ': 'ph',
    'ᇂ': 't', 'ᇂᄋ': 'h', 'ᇂᄂ': 'nn', 'ᇂᄅ': 'nn', 'ᇂᄆ': 'mm', 'ᇂᄒ': 't', 'ᇂᄀ': 'k',
}


_kakasi = None


def _is_japanese(char):
    code = ord(char)
    return 0x3040 <= code <= 0x30FF or 0x4E00 <= code <= 0x9FFF


def romanize_japanese(text):
    global _kakasi
    if _kakasi is None:
        import pykakasi

        _kakasi = pykakasi.kakasi()
    return " ".join(item["hepburn"] for item in _kakasi.convert(text) if item["hepburn"]).strip()


def romanize_text(text):
    if any(0xAC00 <= ord(char) <= 0xD7A3 or 0x1100 <= ord(char) <= 0x11FF for char in text):
        return romanize(text)
    if any(_is_japanese(char) for char in text):
        return romanize_japanese(text)
    return text


def _decompose(char):
    code = ord(char) - 0xAC00
    if not 0 <= code <= 11171:
        return char
    initial = chr(code // 588 + 0x1100)
    vowel = chr(code % 588 // 28 + 0x1161)
    final = chr(code % 28 + 0x11A7) if code % 28 else ""
    return initial + vowel + final


def _is_initial(text):
    return bool(text) and 0x1100 <= ord(text[0]) <= 0x1112


def romanize(text):
    parts = [_decompose(char) for char in text] + [""]
    out = []
    skip_initial = False
    for curr, nxt in zip(parts, parts[1:]):
        res = ""
        if not skip_initial:
            res += CHO.get(curr[0], curr[0])
        skip_initial = False
        if len(curr) > 1:
            res += JUNG.get(curr[1], curr[1])
            if len(curr) == 2 and _is_initial(nxt):
                res += " "
        if len(curr) > 2:
            final = curr[2]
            if final + nxt[:2] in JONG:
                res += JONG[final + nxt[:2]]
                skip_initial = True
            elif final + nxt[:1] in JONG:
                res += JONG[final + nxt[:1]]
                skip_initial = True
            else:
                res += JONG.get(final, final)
                if _is_initial(nxt):
                    res += " "
        if len(curr) > 1:
            res = res.replace(" ", "", 1)
        out.append(res)
    return "".join(out)
