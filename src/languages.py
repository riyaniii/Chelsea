from gettext import gettext as _

from gi.repository import Gtk

LANGUAGES = (
    (_("English"), "eng,en"),
    (_("Arabic"), "ara,ar"),
    (_("Bengali"), "ben,bn"),
    (_("Bulgarian"), "bul,bg"),
    (_("Chinese"), "chi,zho,zh"),
    (_("Croatian"), "hrv,hr"),
    (_("Czech"), "cze,ces,cs"),
    (_("Danish"), "dan,da"),
    (_("Dutch"), "dut,nld,nl"),
    (_("Finnish"), "fin,fi"),
    (_("French"), "fre,fra,fr"),
    (_("German"), "ger,deu,de"),
    (_("Greek"), "gre,ell,el"),
    (_("Hebrew"), "heb,he"),
    (_("Hindi"), "hin,hi"),
    (_("Hungarian"), "hun,hu"),
    (_("Indonesian"), "ind,id"),
    (_("Italian"), "ita,it"),
    (_("Japanese"), "jpn,ja"),
    (_("Korean"), "kor,ko"),
    (_("Malay"), "may,msa,ms"),
    (_("Norwegian"), "nor,nob,nno,no,nb,nn"),
    (_("Persian"), "per,fas,fa"),
    (_("Polish"), "pol,pl"),
    (_("Portuguese"), "por,pt"),
    (_("Portuguese (Brazil)"), "pob,por,pt"),
    (_("Romanian"), "rum,ron,ro"),
    (_("Russian"), "rus,ru"),
    (_("Serbian"), "srp,scc,sr"),
    (_("Spanish"), "spa,es"),
    (_("Swedish"), "swe,sv"),
    (_("Tamil"), "tam,ta"),
    (_("Telugu"), "tel,te"),
    (_("Thai"), "tha,th"),
    (_("Turkish"), "tur,tr"),
    (_("Ukrainian"), "ukr,uk"),
    (_("Urdu"), "urd,ur"),
    (_("Vietnamese"), "vie,vi"),
)


def code_list(codes: str) -> list:
    return [code.strip().lower() for code in codes.split(",") if code.strip()]


def language_index(codes: str) -> int:
    for index, (name, language_codes) in enumerate(LANGUAGES):
        if language_codes == codes:
            return index + 1
    wanted = code_list(codes)
    for index, (name, language_codes) in enumerate(LANGUAGES):
        if wanted and wanted[0] in code_list(language_codes):
            return index + 1
    return 0


def setup_language_row(row, settings, key: str):
    names = [_("Automatic")] + [name for name, codes in LANGUAGES]
    row.set_model(Gtk.StringList.new(names))
    row.set_expression(Gtk.PropertyExpression.new(Gtk.StringObject, None, "string"))
    row.set_enable_search(True)
    row.set_selected(language_index(settings.get_string(key)))
    row.connect("notify::selected", on_language_selected, settings, key)


def on_language_selected(row, pspec, settings, key: str):
    index = row.get_selected()
    codes = LANGUAGES[index - 1][1] if index > 0 else ""
    settings.set_string(key, codes)
