import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from telefwd.internal_types import IRCMessage

_FLAG_LANGUAGES = {
    "🇬🇧": "English",
    "🇺🇸": "English",
    "🇪🇸": "Spanish",
    "🇲🇽": "Spanish",
    "🇷🇴": "Romanian",
    "🇫🇷": "French",
    "🇩🇪": "German",
    "🇮🇹": "Italian",
    "🇵🇹": "Portuguese",
    "🇧🇷": "Portuguese",
    "🇯🇵": "Japanese",
    "🇷🇺": "Russian",
    "🇰🇷": "Korean",
    "🇨🇳": "Chinese",
    "🇹🇼": "Chinese",
    "🇸🇦": "Arabic",
    "🇳🇱": "Dutch",
    "🇧🇬": "Bulgarian",
    "🇨🇿": "Czech",
    "🇩🇰": "Danish",
    "🇫🇮": "Finnish",
    "🇭🇷": "Croatian",
    "🇭🇺": "Hungarian",
    "🇵🇱": "Polish",
    "🇸🇪": "Swedish",
    "🇳🇴": "Norwegian",
    "🇹🇷": "Turkish",
    "🇬🇷": "Greek",
    "🇺🇦": "Ukrainian",
    "🏳️": "Unknown",
}
_LANGUAGE_ALIASES = {
    "ENG": "English",
    "EN": "English",
    "ESP": "Spanish",
    "SPA": "Spanish",
    "CAST": "Spanish",
    "LAT": "Spanish",
    "JAP": "Japanese",
    "JPN": "Japanese",
    "FRE": "French",
    "FRA": "French",
    "GER": "German",
    "DEU": "German",
    "ITA": "Italian",
    "POR": "Portuguese",
    "RUS": "Russian",
    "KOR": "Korean",
    "CHI": "Chinese",
    "ZHO": "Chinese",
    "DUT": "Dutch",
    "NLD": "Dutch",
    "ARA": "Arabic",
    "POL": "Polish",
    "TUR": "Turkish",
}
_LANGUAGE_ALIAS_PATTERN = re.compile(
    r"(?i)(?<![A-Z])("
    + "|".join(sorted(_LANGUAGE_ALIASES, key=len, reverse=True))
    + r")(?![A-Z])"
)
_EPISODE_PATTERN = re.compile(
    r"(?i)\bS(?P<season>\d{1,2})(?:E(?P<episode>\d{1,3}))?\b"
)
_TITLE_STOP_PATTERN = re.compile(
    r"(?i)\s+(?:"
    r"\(?((?:19|20)\d{2})\)?|"
    r"S\d{1,2}(?:E\d{1,3})?|"
    r"(?:4320|2160|1440|1080|720|576|480)p|"
    r"4K|WEB[-.]?DL|WEBRIP|BLURAY|BDREMUX|UHDREMUX|"
    r"NF|AMZN|DSN\+|NETFLIX|HMAX|DSNP|"
    r"HEVC|H\.?26[45]|X26[45]|AVC|XVID"
    r")(?=\W|$)"
)
_URL_PATTERN = re.compile(r"^https?://", re.IGNORECASE)


class DefinitionParser:
    def __init__(self, path: Path):
        if not path.is_file():
            raise FileNotFoundError(f"Parser definition does not exist: {path}")
        with path.open(encoding="utf-8") as definition_file:
            config: Any = yaml.safe_load(definition_file)
        if not isinstance(config, dict):
            raise TypeError(f"Parser definition must contain a YAML mapping: {path}")
        self.parser = ParserType(config)

    def parse(self, text: str, telegram_message: Any = None) -> IRCMessage:
        return self.parser.parse(text, telegram_message)


class ParserType:
    def __init__(self, config: dict[str, Any]):
        parser_config = config.get("parser")
        if not isinstance(parser_config, dict):
            raise TypeError("Parser definition must contain a 'parser' mapping")

        self.movie_pattern = _compile_config_pattern(
            parser_config, "movie_pattern"
        )
        self.series_pattern = _compile_config_pattern(
            parser_config, "series_pattern"
        )
        release_pattern = _compile_config_pattern(
            parser_config, "release_pattern", required=True
        )
        if release_pattern is None:
            raise ValueError("Parser definition is missing 'release_pattern'")
        self.release_pattern = release_pattern
        self.size_pattern = _compile_config_pattern(parser_config, "size_pattern")
        self.year_pattern = _compile_config_pattern(parser_config, "year_pattern")
        self.audio_pattern = _compile_config_pattern(parser_config, "audio_pattern")
        self.subtitles_pattern = _compile_config_pattern(
            parser_config, "subtitles_pattern"
        )

    def parse(self, text: str, telegram_message: Any = None) -> IRCMessage:
        result = IRCMessage(category="Unknown")

        if self.movie_pattern and self.movie_pattern.search(text):
            result.category = "Movie"
        elif self.series_pattern and self.series_pattern.search(text):
            result.category = "Serie"

        release_match = self.release_pattern.search(text)
        if release_match:
            result.release = _capture(release_match)
            result.title = _clean_title(result.release)
            result.name = result.release.strip()

        markdown_link = re.search(
            r"\[\s*__?\s*(.*?)\s*__?\s*\]\(\s*(https?://[^)\s]+)\s*\)",
            text,
        )
        if markdown_link:
            result.name = markdown_link.group(1).strip()

        if self.year_pattern:
            year_match = self.year_pattern.search(text)
            if not year_match:
                year_match = re.search(r"\b((?:19|20)\d{2})\b", result.release or "")
            if year_match:
                result.year = int(_capture(year_match))
        elif result.release:
            year_match = re.search(r"\b((?:19|20)\d{2})\b", result.release)
            if year_match:
                result.year = int(_capture(year_match))

        episode_match = _EPISODE_PATTERN.search(text)
        if episode_match:
            result.season = int(episode_match.group("season"))
            result.episode = episode_match.group(0).upper()

        if self.size_pattern:
            size_match = self.size_pattern.search(text)
            if size_match:
                result.size = _capture(size_match).replace("\u00a0", " ").strip()

        release = result.release or text
        result.quality = _first_match(
            release, r"(?i)\b((?:4320|2160|1440|1080|720|576|480)p|4K)\b"
        )
        result.source = _first_match(
            release,
            r"(?i)\b(WEB[-.]?DL|WEBRip|BluRay|BDRemux|UHDRemux|HDTV)\b",
        )
        result.codec = _first_match(
            release, r"(?i)\b(H\.?264|H\.?265|x264|x265|HEVC|AVC|AV1)\b"
        )

        result.audio_languages = _extract_languages(
            self.audio_pattern, text, release
        )
        result.subtitle_languages = _extract_languages(
            self.subtitles_pattern, text, ""
        )

        urls = _extract_urls(telegram_message)
        urls.extend(
            url.rstrip(".,;:!?")
            for url in re.findall(r"https?://[^\s)]+", text, re.IGNORECASE)
        )
        urls = list(dict.fromkeys(urls))
        result.torrent = _find_url(
            urls, lambda url: "torrent" in url.lower() or "details.php" in url.lower()
        )
        if result.torrent is None and len(urls) == 1:
            result.torrent = urls[0]
        result.imdb = _find_url(urls, lambda url: "imdb.com/" in url.lower())
        result.tmdb = _find_url(
            urls, lambda url: "themoviedb.org/" in url.lower()
        )

        return result


def _compile_config_pattern(
    config: dict[str, Any], key: str, required: bool = False
) -> re.Pattern[str] | None:
    value = config.get(key)
    if value is None:
        if required:
            raise ValueError(f"Parser definition is missing '{key}'")
        return None
    if not isinstance(value, str):
        raise TypeError(f"Parser definition '{key}' must be a string")
    try:
        return re.compile(value)
    except re.error as error:
        raise ValueError(f"Invalid regex in parser definition '{key}': {error}") from error


def _capture(match: re.Match[str]) -> str:
    for value in match.groups():
        if value is not None:
            return value.strip()
    raise ValueError("Parser regex matched but did not capture a value")


def _clean_title(release: str) -> str:
    title = release.strip()
    stop = _TITLE_STOP_PATTERN.search(title)
    if stop:
        title = title[: stop.start()]
    return title.strip(" \t-–—_:*.")


def _first_match(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text)
    if not match:
        return None
    for value in match.groups():
        if value:
            return value.strip().replace(".", "").upper()
    return None


def _extract_languages(
    field_pattern: re.Pattern[str] | None, text: str, fallback: str
) -> list[str]:
    candidates: list[str] = []
    if field_pattern:
        match = field_pattern.search(text)
        if match:
            candidates.append(_capture(match))
    if not candidates:
        candidates.append(fallback)

    languages: list[str] = []
    for candidate in candidates:
        for flag in re.findall(r"(?:[🇦-🇿]{2}|🏳️)", candidate):
            language = _FLAG_LANGUAGES.get(flag)
            if language and language not in languages:
                languages.append(language)
        for match in _LANGUAGE_ALIAS_PATTERN.finditer(candidate):
            language = _LANGUAGE_ALIASES[match.group(1).upper()]
            if language not in languages:
                languages.append(language)
    return languages


def _extract_urls(telegram_message: Any) -> list[str]:
    if telegram_message is None:
        return []
    if hasattr(telegram_message, "to_dict") and callable(telegram_message.to_dict):
        telegram_message = telegram_message.to_dict()
    elif not isinstance(telegram_message, dict):
        return []

    urls: list[str] = []
    for entity in telegram_message.get("entities") or []:
        url = entity.get("url") if isinstance(entity, dict) else None
        if isinstance(url, str) and _URL_PATTERN.match(url):
            urls.append(url)

    markup = telegram_message.get("reply_markup") or {}
    rows = markup.get("rows", []) if isinstance(markup, dict) else []
    for row in rows:
        buttons = row.get("buttons", []) if isinstance(row, dict) else []
        for button in buttons:
            button_type = button.get("type") if isinstance(button, dict) else None
            url = button_type.get("url") if isinstance(button_type, dict) else None
            if isinstance(url, str) and _URL_PATTERN.match(url):
                urls.append(url)

    return list(dict.fromkeys(urls))


def _find_url(urls: list[str], predicate: Callable[[str], bool]) -> str | None:
    return next((url for url in urls if predicate(url)), None)
