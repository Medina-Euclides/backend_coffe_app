"""Protege los datos personales antes de enviarlos al proveedor de IA.

Groq es un tercero: nunca debe ver cédulas, teléfonos, correos, apellidos ni
nombres reales de trabajadores. A cada trabajador se le asigna un alias
("Trabajador A") que se usa en el contexto y en los mensajes; cuando llega la
respuesta, el alias se cambia por el nombre de pila para el productor.
"""

import re
import unicodedata
from collections import Counter

from apps.labor.models import Worker


HIDDEN = "[dato oculto]"

EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
MOBILE_PATTERN = re.compile(
    r"(?<!\d)(?:\+?57[\s-]?)?3\d{2}[\s-]?\d{3}[\s-]?\d{4}(?!\d)"
)
LABELED_NUMBER_PATTERN = re.compile(
    r"(?i)\b(c\.?\s?c\.?|c[eé]dula|documento|identificaci[oó]n|tel[eé]fono|"
    r"tel|celular|cel)(\s*(?:es|:|#|n[o°º]\.?|de)?\s*)"
    r"(\d[\d\s.-]{4,14}\d)"
)
# Los modelos a veces separan con espacios no separables (U+00A0, U+202F).
ALIAS_PATTERN = re.compile(r"\b[Tt]rabajador[\s\u00a0\u2007\u202f]*([A-Z]{1,2})\b")
# Palabras que no se ocultan aunque aparezcan como apellido.
COMMON_WORDS = {
    "del", "de", "la", "las", "los", "san", "santa", "trabajador",
    "trabajadora", "finca", "lote", "campo",
}


def _fold_char(character):
    """Minúscula y sin tilde, conservando un carácter por carácter."""
    folded = "".join(
        part
        for part in unicodedata.normalize("NFD", character.casefold())
        if unicodedata.category(part) != "Mn"
    )
    return folded if len(folded) == 1 else character


def _fold(text):
    return "".join(_fold_char(character) for character in text)


def _alias_letters(index):
    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _digits(value):
    return re.sub(r"\D", "", value or "")


class PrivacyGuard:
    def __init__(self, user):
        workers = Worker.objects.all()
        if not getattr(user, "is_administrator", False):
            workers = workers.filter(producer=user)
        workers = list(workers.order_by("id"))

        self.alias_by_worker_id = {}
        self._display_by_letters = {}
        self._name_terms = []
        self._private_numbers = set()
        self._private_words = set()

        first_names = [self._first_name(worker) for worker in workers]
        repeated = {
            name for name, count in Counter(map(_fold, first_names)).items()
            if count > 1
        }
        aliases_by_first_name = {}

        for index, worker in enumerate(workers):
            letters = _alias_letters(index)
            alias = f"Trabajador {letters}"
            self.alias_by_worker_id[worker.id] = alias

            first_name = first_names[index]
            display = first_name or alias
            if first_name and _fold(first_name) in repeated:
                initial = (worker.last_name or "").strip()[:1].upper()
                display = f"{first_name} {initial}." if initial else f"{first_name} ({letters})"
            self._display_by_letters[letters] = display

            full_name = f"{worker.first_name} {worker.last_name}".strip()
            if full_name:
                self._name_terms.append((full_name, alias))
            self._add_private_words(worker.last_name)
            if first_name:
                aliases_by_first_name.setdefault(_fold(first_name), []).append(alias)

            for value in (worker.identification, worker.phone):
                digits = _digits(value)
                if len(digits) >= 5:
                    self._private_numbers.add(digits)

        for folded_name, aliases in aliases_by_first_name.items():
            self._name_terms.append((folded_name, " o ".join(aliases)))

        for value in (
            getattr(user, "phone_number", ""),
            getattr(user, "identification", ""),
        ):
            digits = _digits(value)
            if len(digits) >= 5:
                self._private_numbers.add(digits)
        self._add_private_words(getattr(user, "last_name", ""))

        # Los nombres largos primero para que "Carlos Pérez" gane a "Carlos".
        self._name_terms.sort(key=lambda item: len(item[0]), reverse=True)

    def _add_private_words(self, value):
        for part in (value or "").split():
            if len(part) >= 4 and _fold(part) not in COMMON_WORDS:
                self._private_words.add(part)

    @staticmethod
    def _first_name(worker):
        parts = (worker.first_name or "").split()
        return parts[0].capitalize() if parts else ""

    def alias_for(self, worker_id):
        return self.alias_by_worker_id.get(worker_id, "Trabajador sin registrar")

    @staticmethod
    def _replace_terms(text, replacements):
        """Reemplaza términos sin importar tildes ni mayúsculas."""
        for term, replacement in replacements:
            folded_term = _fold(term)
            if not folded_term:
                continue
            pattern = re.compile(rf"(?<!\w){re.escape(folded_term)}(?!\w)")
            folded_text = _fold(text)
            pieces = []
            last = 0
            for match in pattern.finditer(folded_text):
                pieces.append(text[last:match.start()])
                pieces.append(replacement)
                last = match.end()
            if pieces:
                pieces.append(text[last:])
                text = "".join(pieces)
        return text

    def _hide_private_numbers(self, text):
        if not self._private_numbers:
            return text

        def replace(match):
            return HIDDEN if _digits(match.group(0)) in self._private_numbers else match.group(0)

        return re.sub(r"\+?\d[\d\s.-]{3,18}\d", replace, text)

    def redact(self, text):
        if not text:
            return text
        text = EMAIL_PATTERN.sub(HIDDEN, text)
        text = LABELED_NUMBER_PATTERN.sub(
            lambda match: f"{match.group(1)}{match.group(2)}{HIDDEN}", text
        )
        text = MOBILE_PATTERN.sub(HIDDEN, text)
        text = self._hide_private_numbers(text)
        text = self._replace_terms(text, self._name_terms)
        text = self._replace_terms(
            text, [(word, HIDDEN) for word in sorted(self._private_words, key=len, reverse=True)]
        )
        return text

    def restore(self, text):
        if not text:
            return text

        def replace(match):
            return self._display_by_letters.get(match.group(1), match.group(0))

        return ALIAS_PATTERN.sub(replace, text)
