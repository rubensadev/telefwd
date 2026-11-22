from dataclasses import dataclass


@dataclass
class IRCMessage:
    category: str
    title: str | None = None
    name: str | None = None
    season: int | None = None
    episode: str | None = None
    year: int | None = None
    size: str | None = None
    quality: str | None = None
    source: str | None = None
    codec: str | None = None
    audio_languages: list[str] | None = None
    subtitle_languages: list[str] | None = None
    release: str | None = None
    torrent: str | None = None
    imdb: str | None = None
    tmdb: str | None = None
